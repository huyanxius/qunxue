from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from qunxue_api.modules.agent_conversation.domain import (
    AgentCitation,
    AgentRun,
    AgentTurn,
    Conversation,
    IdempotentTurn,
)
from qunxue_api.modules.agent_conversation.errors import ConversationNotFound, RunAlreadyActive
from qunxue_api.modules.agent_conversation.ports import ConversationRepository
from qunxue_api.modules.agent_conversation.research_map import (
    aggregate_research_map,
    patches_from_tool_summary,
)


class _MemoryRepository:
    def __init__(self) -> None:
        self.conversations: dict[UUID, Conversation] = {}
        self.turn_keys: dict[tuple[UUID, str], UUID] = {}
        self.runs: dict[UUID, AgentRun] = {}

    def commit(self) -> None:
        return None

    def create(self, conversation: Conversation) -> Conversation:
        self.conversations[conversation.conversation_id] = conversation
        return conversation

    def get(self, *, user_id: UUID, conversation_id: UUID) -> Conversation:
        conversation = self.conversations.get(conversation_id)
        if conversation is None or conversation.user_id != user_id:
            raise ConversationNotFound(str(conversation_id))
        runs_by_turn = {
            run.turn_id: run.tool_summary
            for run in self.runs.values()
            if run.conversation_id == conversation_id and run.turn_id is not None
        }
        if not runs_by_turn:
            return conversation
        patches_by_turn = {
            turn_id: patches_from_tool_summary(summary) for turn_id, summary in runs_by_turn.items()
        }
        all_patches = [
            patch for turn in conversation.turns for patch in patches_by_turn.get(turn.turn_id, ())
        ]
        return replace(
            conversation,
            turns=tuple(
                replace(
                    turn,
                    tool_summary=runs_by_turn.get(turn.turn_id, turn.tool_summary),
                    canvas_patches=patches_by_turn.get(turn.turn_id, turn.canvas_patches),
                )
                for turn in conversation.turns
            ),
            research_map=aggregate_research_map(all_patches),
        )

    def list(self, *, user_id: UUID) -> Sequence[Conversation]:
        return tuple(
            sorted(
                (item for item in self.conversations.values() if item.user_id == user_id),
                key=lambda item: item.updated_at,
                reverse=True,
            )
        )

    def release_ids_by_turn(self, *, conversation_id: UUID) -> Mapping[UUID, str]:
        return {
            run.turn_id: run.knowledge_release_id
            for run in self.runs.values()
            if run.conversation_id == conversation_id
            and run.turn_id is not None
            and run.knowledge_release_id is not None
        }

    def append_turn(self, *, conversation: Conversation, turn: AgentTurn, idempotency_key: str):
        key = (conversation.conversation_id, idempotency_key)
        existing = self.turn_keys.get(key)
        if existing is not None:
            return IdempotentTurn(existing)
        turns = (*conversation.turns, turn)
        updated = Conversation(
            conversation_id=conversation.conversation_id,
            user_id=conversation.user_id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=datetime.now(UTC),
            turns=turns,
        )
        self.conversations[conversation.conversation_id] = updated
        self.turn_keys[key] = turn.turn_id
        return turn

    def start_run(self, run: AgentRun) -> AgentRun:
        existing = next(
            (
                item
                for item in self.runs.values()
                if item.conversation_id == run.conversation_id
                and item.idempotency_key == run.idempotency_key
            ),
            None,
        )
        if existing is not None:
            if existing.status == "running":
                raise RunAlreadyActive(str(run.conversation_id))
            if existing.status == "completed":
                return existing
            run = AgentRun(
                run_id=existing.run_id,
                conversation_id=run.conversation_id,
                user_id=run.user_id,
                idempotency_key=run.idempotency_key,
                status="running",
                knowledge_release_id=run.knowledge_release_id,
                turn_id=None,
                tool_summary=(),
            )
        if any(
            item.conversation_id == run.conversation_id and item.status == "running"
            for item in self.runs.values()
        ):
            raise RunAlreadyActive(str(run.conversation_id))
        self.runs[run.run_id] = run
        return run

    def find_run(self, *, user_id: UUID, idempotency_key: str) -> AgentRun | None:
        return next(
            (
                item
                for item in self.runs.values()
                if item.user_id == user_id and item.idempotency_key == idempotency_key
            ),
            None,
        )

    def finish_run(
        self,
        *,
        run_id: UUID,
        status: str,
        error: str | None = None,
        turn_id: UUID | None = None,
        tool_summary: tuple[dict[str, object], ...] = (),
    ) -> None:
        del error
        current = self.runs[run_id]
        self.runs[run_id] = AgentRun(
            run_id=current.run_id,
            conversation_id=current.conversation_id,
            user_id=current.user_id,
            idempotency_key=current.idempotency_key,
            status=status,  # type: ignore[arg-type]
            knowledge_release_id=current.knowledge_release_id,
            turn_id=current.turn_id if turn_id is None else turn_id,
            tool_summary=tool_summary,
        )


class ConversationService:
    def __init__(self, repository: ConversationRepository) -> None:
        self._repository = repository

    @classmethod
    def in_memory(cls) -> "ConversationService":
        return cls(_MemoryRepository())

    def create_conversation(self, *, user_id: UUID, title: str) -> Conversation:
        now = datetime.now(UTC)
        conversation = Conversation(
            conversation_id=uuid4(),
            user_id=user_id,
            title=title.strip()[:120] or "新对话",
            created_at=now,
            updated_at=now,
        )
        return self._repository.create(conversation)

    def commit(self) -> None:
        self._repository.commit()

    def get_conversation(self, *, user_id: UUID, conversation_id: UUID) -> Conversation:
        return self._repository.get(user_id=user_id, conversation_id=conversation_id)

    def list_conversations(self, *, user_id: UUID) -> Sequence[Conversation]:
        return self._repository.list(user_id=user_id)

    def release_ids_by_turn(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
    ) -> Mapping[UUID, str]:
        self.get_conversation(user_id=user_id, conversation_id=conversation_id)
        return self._repository.release_ids_by_turn(conversation_id=conversation_id)

    def append_turn(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        idempotency_key: str,
        user_content: str,
        assistant_content: str,
        citations: tuple[AgentCitation, ...],
        evidence_ids: frozenset[str] | None = None,
    ) -> AgentTurn | IdempotentTurn:
        conversation = self.get_conversation(user_id=user_id, conversation_id=conversation_id)
        turn = AgentTurn.create(
            user_content=user_content,
            assistant_content=assistant_content,
            citations=citations,
            evidence_ids=(
                evidence_ids
                if evidence_ids is not None
                else frozenset(c.citation_id for c in citations)
            ),
            sequence=len(conversation.turns) * 2,
        )
        return self._repository.append_turn(
            conversation=conversation,
            turn=turn,
            idempotency_key=idempotency_key,
        )

    def start_run(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        idempotency_key: str,
        knowledge_release_id: str,
    ) -> AgentRun:
        self.get_conversation(user_id=user_id, conversation_id=conversation_id)
        return self._repository.start_run(
            AgentRun(
                run_id=uuid4(),
                conversation_id=conversation_id,
                user_id=user_id,
                idempotency_key=idempotency_key,
                status="running",
                knowledge_release_id=knowledge_release_id,
            )
        )

    def find_run(self, *, user_id: UUID, idempotency_key: str) -> AgentRun | None:
        return self._repository.find_run(user_id=user_id, idempotency_key=idempotency_key)

    def finish_run(
        self,
        *,
        run_id: UUID,
        status: str,
        error: str | None = None,
        turn_id: UUID | None = None,
        tool_summary: tuple[dict[str, object], ...] = (),
    ) -> None:
        self._repository.finish_run(
            run_id=run_id,
            status=status,
            error=error,
            turn_id=turn_id,
            tool_summary=tool_summary,
        )
