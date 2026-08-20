from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite import AgentConversationRow, AgentMessageRow, AgentRunRow
from qunxue_api.modules.agent_conversation import (
    AgentCitation,
    AgentMessage,
    AgentRun,
    AgentTurn,
    Conversation,
    ConversationNotFound,
    IdempotentTurn,
    RunAlreadyActive,
    aggregate_research_map,
    patches_from_tool_summary,
)


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class SqliteConversationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def commit(self) -> None:
        self._session.commit()

    def get_research_task_id(self, *, user_id: UUID, conversation_id: UUID) -> UUID | None:
        row = self._session.scalar(
            select(AgentConversationRow).where(
                AgentConversationRow.conversation_id == str(conversation_id),
                AgentConversationRow.user_id == str(user_id),
            )
        )
        if row is None:
            raise ConversationNotFound(str(conversation_id))
        return UUID(row.current_research_task_id) if row.current_research_task_id else None

    def link_research_task(self, *, user_id: UUID, conversation_id: UUID, task_id: UUID) -> None:
        row = self._session.scalar(
            select(AgentConversationRow).where(
                AgentConversationRow.conversation_id == str(conversation_id),
                AgentConversationRow.user_id == str(user_id),
            )
        )
        if row is None:
            raise ConversationNotFound(str(conversation_id))
        row.current_research_task_id = str(task_id)
        self._session.flush()

    def create(self, conversation: Conversation) -> Conversation:
        self._session.add(
            AgentConversationRow(
                conversation_id=str(conversation.conversation_id),
                user_id=str(conversation.user_id),
                title=conversation.title,
                version=1,
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
            )
        )
        self._session.flush()
        return conversation

    def get(self, *, user_id: UUID, conversation_id: UUID) -> Conversation:
        row = self._session.scalar(
            select(AgentConversationRow).where(
                AgentConversationRow.conversation_id == str(conversation_id),
                AgentConversationRow.user_id == str(user_id),
            )
        )
        if row is None:
            raise ConversationNotFound(str(conversation_id))
        messages = list(
            self._session.scalars(
                select(AgentMessageRow)
                .where(AgentMessageRow.conversation_id == str(conversation_id))
                .order_by(AgentMessageRow.sequence)
            )
        )
        run_summaries = {
            row.turn_id: tuple(dict(item) for item in (row.tool_summary or []))
            for row in self._session.scalars(
                select(AgentRunRow).where(
                    AgentRunRow.conversation_id == str(conversation_id),
                    AgentRunRow.turn_id.is_not(None),
                )
            )
            if row.turn_id is not None
        }
        patches_by_turn = {
            turn_id: patches_from_tool_summary(summary)
            for turn_id, summary in run_summaries.items()
        }
        turns: list[AgentTurn] = []
        for index in range(0, len(messages), 2):
            user_row, assistant_row = messages[index : index + 2]
            if user_row.role != "user" or assistant_row.role != "assistant":
                continue
            citations = tuple(_citation(item) for item in assistant_row.citations)
            turns.append(
                AgentTurn(
                    turn_id=UUID(user_row.turn_id),
                    user_message=_message(user_row),
                    assistant_message=_message(assistant_row),
                    evidence_ids=frozenset(item.citation_id for item in citations),
                    tool_summary=run_summaries.get(str(user_row.turn_id), ()),
                    canvas_patches=patches_by_turn.get(str(user_row.turn_id), ()),
                )
            )
        all_patches = [patch for turn in turns for patch in turn.canvas_patches]
        return Conversation(
            conversation_id=UUID(row.conversation_id),
            user_id=UUID(row.user_id),
            title=row.title,
            created_at=_utc(row.created_at),
            updated_at=_utc(row.updated_at),
            turns=tuple(turns),
            research_map=aggregate_research_map(all_patches),
        )

    def list(self, *, user_id: UUID) -> list[Conversation]:
        rows = self._session.scalars(
            select(AgentConversationRow)
            .where(AgentConversationRow.user_id == str(user_id))
            .order_by(AgentConversationRow.updated_at.desc())
        )
        return [
            self.get(user_id=user_id, conversation_id=UUID(row.conversation_id)) for row in rows
        ]

    def release_ids_by_turn(self, *, conversation_id: UUID) -> dict[UUID, str]:
        return {
            UUID(row.turn_id): row.knowledge_release_id
            for row in self._session.scalars(
                select(AgentRunRow).where(
                    AgentRunRow.conversation_id == str(conversation_id),
                    AgentRunRow.turn_id.is_not(None),
                    AgentRunRow.knowledge_release_id.is_not(None),
                )
            )
            if row.turn_id is not None and row.knowledge_release_id is not None
        }

    def append_turn(self, *, conversation: Conversation, turn: AgentTurn, idempotency_key: str):
        existing = self._session.scalar(
            select(AgentRunRow).where(
                AgentRunRow.conversation_id == str(conversation.conversation_id),
                AgentRunRow.idempotency_key == idempotency_key,
            )
        )
        if existing is not None and existing.status == "completed":
            return IdempotentTurn(UUID(existing.turn_id or existing.run_id))
        self._session.add_all(
            [
                AgentMessageRow(
                    message_id=str(turn.user_message.message_id),
                    conversation_id=str(conversation.conversation_id),
                    turn_id=str(turn.turn_id),
                    role="user",
                    content=turn.user_message.content,
                    citations=[],
                    sequence=turn.user_message.sequence,
                    created_at=turn.user_message.created_at,
                ),
                AgentMessageRow(
                    message_id=str(turn.assistant_message.message_id),
                    conversation_id=str(conversation.conversation_id),
                    turn_id=str(turn.turn_id),
                    role="assistant",
                    content=turn.assistant_message.content,
                    citations=[_citation_dict(item) for item in turn.assistant_message.citations],
                    sequence=turn.assistant_message.sequence,
                    created_at=turn.assistant_message.created_at,
                ),
            ]
        )
        row = self._session.get(AgentConversationRow, str(conversation.conversation_id))
        if row is not None:
            row.updated_at = turn.assistant_message.created_at
            row.version += 1
        self._session.flush()
        return turn

    def start_run(self, run: AgentRun) -> AgentRun:
        existing = self._session.scalar(
            select(AgentRunRow).where(
                AgentRunRow.conversation_id == str(run.conversation_id),
                AgentRunRow.idempotency_key == run.idempotency_key,
            )
        )
        if existing is not None:
            if existing.status == "running":
                raise RunAlreadyActive(str(run.conversation_id))
            if existing.status == "completed":
                return _run_from_row(existing)
            active = self._session.scalar(
                select(AgentRunRow).where(
                    AgentRunRow.conversation_id == str(run.conversation_id),
                    AgentRunRow.status == "running",
                    AgentRunRow.run_id != existing.run_id,
                )
            )
            if active is not None:
                raise RunAlreadyActive(str(run.conversation_id))
            try:
                existing.status = "running"
                existing.error = None
                existing.completed_at = None
                existing.started_at = datetime.now(UTC)
                existing.knowledge_release_id = run.knowledge_release_id
                existing.turn_id = None
                self._session.flush()
                return _run_from_row(existing)
            except IntegrityError as error:
                self._session.rollback()
                active = self._session.scalar(
                    select(AgentRunRow).where(
                        AgentRunRow.conversation_id == str(run.conversation_id),
                        AgentRunRow.status == "running",
                    )
                )
                if active is not None:
                    raise RunAlreadyActive(str(run.conversation_id)) from error
                existing = self._session.scalar(
                    select(AgentRunRow).where(
                        AgentRunRow.conversation_id == str(run.conversation_id),
                        AgentRunRow.idempotency_key == run.idempotency_key,
                    )
                )
                if existing is not None:
                    return _run_from_row(existing)
                raise error

        active = self._session.scalar(
            select(AgentRunRow).where(
                AgentRunRow.conversation_id == str(run.conversation_id),
                AgentRunRow.status == "running",
            )
        )
        if active is not None:
            raise RunAlreadyActive(str(run.conversation_id))
        try:
            self._session.add(
                AgentRunRow(
                    run_id=str(run.run_id),
                    turn_id=None,
                    conversation_id=str(run.conversation_id),
                    user_id=str(run.user_id),
                    idempotency_key=run.idempotency_key,
                    status=run.status,
                    provider="pydantic-ai",
                    model="knowledge-agent",
                    knowledge_release_id=run.knowledge_release_id,
                    usage={},
                    tool_summary=[],
                    started_at=datetime.now(UTC),
                )
            )
            self._session.flush()
        except IntegrityError as error:
            self._session.rollback()
            existing = self._session.scalar(
                select(AgentRunRow).where(
                    AgentRunRow.conversation_id == str(run.conversation_id),
                    AgentRunRow.idempotency_key == run.idempotency_key,
                )
            )
            if existing is not None:
                if existing.status == "running":
                    raise RunAlreadyActive(str(run.conversation_id)) from error
                return _run_from_row(existing)
            active = self._session.scalar(
                select(AgentRunRow).where(
                    AgentRunRow.conversation_id == str(run.conversation_id),
                    AgentRunRow.status == "running",
                )
            )
            if active is not None:
                raise RunAlreadyActive(str(run.conversation_id)) from error
            raise error
        return run

    def find_run(self, *, user_id: UUID, idempotency_key: str) -> AgentRun | None:
        row = self._session.scalar(
            select(AgentRunRow).where(
                AgentRunRow.user_id == str(user_id),
                AgentRunRow.idempotency_key == idempotency_key,
            )
        )
        if row is None:
            return None
        return _run_from_row(row)

    def finish_run(
        self,
        *,
        run_id: UUID,
        status: str,
        error: str | None = None,
        turn_id: UUID | None = None,
        tool_summary: tuple[dict[str, object], ...] = (),
    ) -> None:
        row = self._session.get(AgentRunRow, str(run_id))
        if row is None:
            return
        row.status = status
        row.error = error
        if turn_id is not None:
            row.turn_id = str(turn_id)
        row.tool_summary = [dict(item) for item in tool_summary]
        row.completed_at = datetime.now(UTC)
        self._session.flush()


def _citation_dict(item: AgentCitation) -> dict[str, object]:
    return {
        "citation_id": item.citation_id,
        "label": item.label,
        "kind": item.kind,
        "excerpt": item.excerpt,
        "knowledge_id": item.knowledge_id,
        "source_id": item.source_id,
    }


def _run_from_row(row: AgentRunRow) -> AgentRun:
    return AgentRun(
        run_id=UUID(row.run_id),
        conversation_id=UUID(row.conversation_id),
        user_id=UUID(row.user_id),
        idempotency_key=row.idempotency_key,
        status=row.status,  # type: ignore[arg-type]
        knowledge_release_id=row.knowledge_release_id,
        turn_id=UUID(row.turn_id) if row.turn_id else None,
        tool_summary=tuple(dict(item) for item in row.tool_summary),
    )


def _citation(item: dict[str, object]) -> AgentCitation:
    return AgentCitation(
        citation_id=str(item["citation_id"]),
        label=str(item["label"]),
        kind=str(item["kind"]),  # type: ignore[arg-type]
        excerpt=str(item["excerpt"]) if item.get("excerpt") else None,
        knowledge_id=str(item["knowledge_id"]) if item.get("knowledge_id") else None,
        source_id=str(item["source_id"]) if item.get("source_id") else None,
    )


def _message(row: AgentMessageRow) -> AgentMessage:
    return AgentMessage(
        message_id=UUID(row.message_id),
        role=row.role,  # type: ignore[arg-type]
        content=row.content,
        citations=tuple(_citation(item) for item in row.citations),
        sequence=row.sequence,
        created_at=_utc(row.created_at),
    )
