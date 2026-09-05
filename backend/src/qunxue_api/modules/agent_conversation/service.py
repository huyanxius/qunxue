from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from qunxue_api.modules.agent_conversation.domain import (
    AgentCitation,
    AgentMaterialAttachment,
    AgentRun,
    AgentTurn,
    Conversation,
    IdempotentTurn,
)
from qunxue_api.modules.agent_conversation.errors import (
    ConversationNotFound,
    ConversationTaskBindingConflict,
    RunAlreadyActive,
)
from qunxue_api.modules.agent_conversation.ports import ConversationRepository
from qunxue_api.modules.agent_conversation.research_map import (
    aggregate_research_map,
    patches_from_tool_summary,
)

from .canvas_editing import CanvasEditConflict, apply_canvas_edits, prepare_canvas_edit


class _MemoryRepository:
    def __init__(self) -> None:
        self.conversations: dict[UUID, Conversation] = {}
        self.turn_keys: dict[tuple[UUID, str], UUID] = {}
        self.runs: dict[UUID, AgentRun] = {}
        self.research_task_ids: dict[UUID, UUID] = {}
        self.canvas_edits: dict[UUID, dict] = {}

    def commit(self) -> None:
        return None

    def create(self, conversation: Conversation) -> Conversation:
        self.conversations[conversation.conversation_id] = conversation
        return conversation

    def get_research_task_id(self, *, user_id: UUID, conversation_id: UUID) -> UUID | None:
        self.get(user_id=user_id, conversation_id=conversation_id)
        return self.research_task_ids.get(conversation_id)

    def link_research_task(self, *, user_id: UUID, conversation_id: UUID, task_id: UUID) -> None:
        self.get(user_id=user_id, conversation_id=conversation_id)
        existing = self.research_task_ids.get(conversation_id)
        if existing is not None and existing != task_id:
            raise ConversationTaskBindingConflict(
                "The conversation is already bound to a different research task."
            )
        self.research_task_ids[conversation_id] = task_id
        self.conversations[conversation_id] = replace(
            self.conversations[conversation_id], task_id=task_id
        )

    def get(self, *, user_id: UUID, conversation_id: UUID) -> Conversation:
        conversation = self.conversations.get(conversation_id)
        if conversation is None or conversation.user_id != user_id:
            raise ConversationNotFound(str(conversation_id))
        runs_by_turn = {
            run.turn_id: run.tool_summary
            for run in self.runs.values()
            if run.conversation_id == conversation_id
            and run.status == "completed"
            and run.turn_id is not None
        }
        unfinished = tuple(
            run
            for run in self.runs.values()
            if run.conversation_id == conversation_id and run.status != "completed"
        )
        if not runs_by_turn:
            return replace(conversation, unfinished_runs=unfinished)
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
            research_map=apply_canvas_edits(
                aggregate_research_map(
                    all_patches,
                    protected_since={
                        key: value.get("_patch_count", 0)
                        for key, value in self.canvas_edits.get(conversation_id, {}).items()
                    },
                ),
                self.canvas_edits.get(conversation_id, {}),
            ),
            unfinished_runs=unfinished,
        )

    def edit_canvas_node(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        node_id: str,
        title: str,
        summary: str,
        expected_title: str,
        expected_summary: str | None,
        expected_version: int,
    ) -> Conversation:
        current = self.get(user_id=user_id, conversation_id=conversation_id)
        if current.canvas_edit_version != expected_version:
            raise CanvasEditConflict("卡片已经更新，请重新载入后再保存。")
        edit = prepare_canvas_edit(
            current.research_map,
            node_id=node_id,
            title=title,
            summary=summary,
            expected_title=expected_title,
            expected_summary=expected_summary,
        )
        previous = self.canvas_edits.get(conversation_id, {}).get(node_id, {})
        edit["_patch_count"] = min(
            edit["_patch_count"], previous.get("_patch_count", edit["_patch_count"])
        )
        edit["user_edit_version"] = expected_version + 1
        self.canvas_edits.setdefault(conversation_id, {})[node_id] = edit
        self.conversations[conversation_id] = replace(
            current, canvas_edit_version=expected_version + 1, updated_at=datetime.now(UTC)
        )
        return self.get(user_id=user_id, conversation_id=conversation_id)

    def list(self, *, user_id: UUID) -> Sequence[Conversation]:
        return tuple(
            sorted(
                (item for item in self.conversations.values() if item.user_id == user_id),
                key=lambda item: item.updated_at,
                reverse=True,
            )
        )

    def rename(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        title: str,
        updated_at: datetime,
    ) -> Conversation:
        conversation = self.get(user_id=user_id, conversation_id=conversation_id)
        renamed = replace(conversation, title=title, updated_at=updated_at)
        self.conversations[conversation_id] = renamed
        return renamed

    def delete(self, *, user_id: UUID, conversation_id: UUID) -> None:
        self.get(user_id=user_id, conversation_id=conversation_id)
        self.conversations.pop(conversation_id)
        self.turn_keys = {
            key: turn_id for key, turn_id in self.turn_keys.items() if key[0] != conversation_id
        }
        self.runs = {
            run_id: run
            for run_id, run in self.runs.items()
            if run.conversation_id != conversation_id
        }
        self.research_task_ids.pop(conversation_id, None)

    def release_ids_by_turn(self, *, conversation_id: UUID) -> Mapping[UUID, str]:
        return {
            run.turn_id: run.knowledge_release_id
            for run in self.runs.values()
            if run.conversation_id == conversation_id
            and run.status == "completed"
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
            task_id=conversation.task_id,
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
            run = replace(
                existing,
                status="running",
                provider=run.provider,
                model=run.model,
                knowledge_release_id=run.knowledge_release_id,
                turn_id=None,
                request_snapshot=run.request_snapshot or existing.request_snapshot,
                cancel_requested=False,
                lease_token=run.lease_token,
                lease_expires_at=run.lease_expires_at,
                updated_at=run.updated_at,
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

    def find_run_by_id(self, *, user_id: UUID, run_id: UUID) -> AgentRun | None:
        run = self.runs.get(run_id)
        if run is None or run.user_id != user_id:
            return None
        return run

    def finish_run(
        self,
        *,
        run_id: UUID,
        status: str,
        error: str | None = None,
        turn_id: UUID | None = None,
        tool_summary: tuple[dict[str, object], ...] = (),
        provider: str | None = None,
        model: str | None = None,
        lease_token: str | None = None,
    ) -> None:
        del error
        current = self.runs[run_id]
        if lease_token is not None and (
            current.lease_token != lease_token or current.status != "running"
        ):
            return
        self.runs[run_id] = replace(
            current,
            status=status,
            provider=provider or current.provider,
            model=model or current.model,
            turn_id=turn_id,
            tool_summary=tool_summary,
            updated_at=datetime.now(UTC),
            lease_expires_at=None,
        )

    def checkpoint_run(
        self,
        *,
        user_id,
        run_id,
        lease_token=None,
        partial_answer=None,
        tool_summary=None,
        request_snapshot=None,
        require_not_cancelled=False,
    ) -> bool:
        run = self.find_run_by_id(user_id=user_id, run_id=run_id)
        if (
            run is None
            or run.status != "running"
            or (require_not_cancelled and run.cancel_requested)
            or (lease_token is not None and run.lease_token != lease_token)
        ):
            return False
        now = datetime.now(UTC)
        changes = {"updated_at": now, "lease_expires_at": now + timedelta(seconds=30)}
        if partial_answer is not None:
            changes["partial_answer"] = partial_answer
        if tool_summary is not None:
            changes["tool_summary"] = tool_summary
        if request_snapshot is not None:
            changes["request_snapshot"] = dict(request_snapshot)
        self.runs[run_id] = replace(run, **changes)
        return True

    def request_cancel(self, *, user_id: UUID, run_id: UUID) -> AgentRun:
        run = self.find_run_by_id(user_id=user_id, run_id=run_id)
        if run is None:
            raise ConversationNotFound(str(run_id))
        if run.status == "running":
            run = replace(run, cancel_requested=True, updated_at=datetime.now(UTC))
            self.runs[run_id] = run
        return run

    def recover_expired_runs(self, *, user_id: UUID, conversation_id: UUID) -> tuple[AgentRun, ...]:
        now = datetime.now(UTC)
        expired = []
        for run in tuple(self.runs.values()):
            if (
                run.user_id == user_id
                and run.conversation_id == conversation_id
                and run.status == "running"
                and (run.lease_expires_at is None or run.lease_expires_at <= now)
            ):
                recovered = replace(
                    run,
                    status="interrupted",
                    cancel_requested=True,
                    updated_at=now,
                    lease_expires_at=None,
                )
                self.runs[run.run_id] = recovered
                expired.append(recovered)
        return tuple(expired)


class ConversationService:
    def __init__(self, repository: ConversationRepository) -> None:
        self._repository = repository

    @classmethod
    def in_memory(cls) -> "ConversationService":
        return cls(_MemoryRepository())

    def create_conversation(
        self, *, user_id: UUID, title: str, conversation_id: UUID | None = None
    ) -> Conversation:
        now = datetime.now(UTC)
        conversation = Conversation(
            conversation_id=conversation_id or uuid4(),
            user_id=user_id,
            title=title.strip()[:120] or "新对话",
            created_at=now,
            updated_at=now,
        )
        return self._repository.create(conversation)

    def commit(self) -> None:
        self._repository.commit()

    def get_research_task_id(self, *, user_id: UUID, conversation_id: UUID) -> UUID | None:
        return self._repository.get_research_task_id(
            user_id=user_id,
            conversation_id=conversation_id,
        )

    def link_research_task(self, *, user_id: UUID, conversation_id: UUID, task_id: UUID) -> None:
        self._repository.link_research_task(
            user_id=user_id,
            conversation_id=conversation_id,
            task_id=task_id,
        )

    def get_conversation(self, *, user_id: UUID, conversation_id: UUID) -> Conversation:
        return self._repository.get(user_id=user_id, conversation_id=conversation_id)

    def list_conversations(self, *, user_id: UUID) -> Sequence[Conversation]:
        return self._repository.list(user_id=user_id)

    def rename_conversation(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        title: str,
    ) -> Conversation:
        normalized_title = title.strip()
        if not normalized_title:
            raise ValueError("conversation title must not be empty")
        return self._repository.rename(
            user_id=user_id,
            conversation_id=conversation_id,
            title=normalized_title[:120],
            updated_at=datetime.now(UTC),
        )

    def edit_canvas_node(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        node_id: str,
        title: str,
        summary: str,
        expected_title: str,
        expected_summary: str | None,
        expected_version: int,
    ) -> Conversation:
        return self._repository.edit_canvas_node(
            user_id=user_id,
            conversation_id=conversation_id,
            node_id=node_id,
            title=title,
            summary=summary,
            expected_title=expected_title,
            expected_summary=expected_summary,
            expected_version=expected_version,
        )

    def delete_conversation(self, *, user_id: UUID, conversation_id: UUID) -> None:
        self._repository.delete(user_id=user_id, conversation_id=conversation_id)

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
        turn_id: UUID | None = None,
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
            turn_id=turn_id,
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
        provider: str = "pydantic-ai",
        model: str = "knowledge-agent",
        material_attachments: tuple[AgentMaterialAttachment, ...] = (),
        request_snapshot: dict[str, object] | None = None,
    ) -> AgentRun:
        self.get_conversation(user_id=user_id, conversation_id=conversation_id)
        normalized_provider = provider.strip()
        normalized_model = model.strip()
        if not normalized_provider or not normalized_model:
            raise ValueError("Agent runtime provider and model must not be empty")
        return self._repository.start_run(
            AgentRun(
                run_id=uuid4(),
                conversation_id=conversation_id,
                user_id=user_id,
                idempotency_key=idempotency_key,
                status="running",
                provider=normalized_provider,
                model=normalized_model,
                knowledge_release_id=knowledge_release_id,
                material_attachments=material_attachments,
                request_snapshot=dict(request_snapshot or {}),
            )
        )

    def find_run(self, *, user_id: UUID, idempotency_key: str) -> AgentRun | None:
        return self._repository.find_run(user_id=user_id, idempotency_key=idempotency_key)

    def find_run_by_id(self, *, user_id: UUID, run_id: UUID) -> AgentRun | None:
        return self._repository.find_run_by_id(user_id=user_id, run_id=run_id)

    def finish_run(
        self,
        *,
        run_id: UUID,
        status: str,
        error: str | None = None,
        turn_id: UUID | None = None,
        tool_summary: tuple[dict[str, object], ...] = (),
        provider: str | None = None,
        model: str | None = None,
        lease_token: str | None = None,
    ) -> None:
        self._repository.finish_run(
            run_id=run_id,
            status=status,
            error=error,
            turn_id=turn_id,
            tool_summary=tool_summary,
            provider=provider,
            model=model,
            lease_token=lease_token,
        )

    def checkpoint_run(self, **kwargs) -> bool:
        return self._repository.checkpoint_run(**kwargs)

    def request_cancel(self, *, user_id: UUID, run_id: UUID) -> AgentRun:
        return self._repository.request_cancel(user_id=user_id, run_id=run_id)

    def recover_expired_runs(self, *, user_id: UUID, conversation_id: UUID) -> tuple[AgentRun, ...]:
        return self._repository.recover_expired_runs(
            user_id=user_id, conversation_id=conversation_id
        )
