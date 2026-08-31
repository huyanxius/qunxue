import re
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from typing import Literal
from uuid import UUID, uuid4

from qunxue_api.modules.agent_conversation import (
    AgentCitation,
    AgentEvidence,
    AgentInterrupted,
    AgentRunResult,
    AgentRuntimeIdentity,
    AgentToolContext,
    AgentToolEvent,
    AgentTurn,
    Conversation,
    ConversationService,
    ConversationTaskBindingConflict,
    IdempotentTurn,
    RunAlreadyActive,
    SubjectAgentRunner,
)
from qunxue_api.modules.billing import CreditService

_PRODUCT_IDENTITY_ANSWER = "我是群学致知的社会学学科 Agent。"
_RUNTIME_IDENTITY_PATTERNS = (
    re.compile(
        r"(?:报告|说出|透露|披露|告诉我|确认|介绍)\s*(?:一下)?\s*"
        r"(?:你|您)(?:的)?(?:底层)?(?:模型|供应商|提供商|厂商|版本|型号)"
    ),
    re.compile(
        r"(?:你|您)(?:到底)?(?:是|是不是|属于)\s*"
        r"(?:什么|哪个|哪种|哪款)\s*(?:模型|版本|型号)"
    ),
    re.compile(
        r"(?:你|您)(?:到底)?(?:是|是不是|属于)\s*"
        r"(?:哪家|哪个|什么)\s*(?:供应商|提供商|厂商|公司)(?:的)?"
    ),
    re.compile(
        r"(?:你|您)(?:到底)?(?:是|是不是)\s*"
        r"(?:gpt|openai|deepseek|claude|gemini|terra|luna|sol|"
        r"[a-z0-9]+(?:[-_.][a-z0-9]+)+)\b"
    ),
    re.compile(
        r"(?:你|您)(?:正在)?(?:使用|用|基于|接入|运行于|运行在)(?:的)?\s*"
        r"(?:什么|哪个|哪种|哪款|哪家)?\s*"
        r"(?:模型|供应商|提供商|厂商|版本|型号)"
    ),
    re.compile(
        r"(?:你|您)(?:是)?由\s*(?:谁|哪家|哪个|什么)\s*"
        r"(?:公司|供应商|提供商|厂商)?(?:开发|提供|训练|运行)"
    ),
    re.compile(r"(?:你|您)(?:的)?(?:底层)?(?:模型|供应商|提供商|厂商|版本|型号)"),
    re.compile(
        r"\b(?:what|which)\s+(?:underlying\s+)?"
        r"(?:model|provider|vendor|version)\s+(?:are|do)\s+you\b"
    ),
    re.compile(
        r"\b(?:what|which)\s+(?:model|provider|vendor)\s+"
        r"do\s+you\s+(?:use|run)\b"
    ),
    re.compile(r"\byour\s+(?:underlying\s+)?(?:model|provider|vendor|version)\b"),
    re.compile(r"\b(?:who|what company)\s+(?:made|built|provides|runs)\s+you\b"),
)


@dataclass(frozen=True, slots=True)
class AgentTurnExecution:
    conversation: Conversation
    run_id: UUID
    result: AgentRunResult
    turn: AgentTurn | None
    replayed: bool
    tool_summary: tuple[dict[str, object], ...] = ()


class DisciplinaryAgentApplication:
    """Coordinates persistence, release pinning, tools, and the runtime adapter."""

    def __init__(
        self,
        *,
        conversations: ConversationService,
        runner: SubjectAgentRunner,
        tools_factory: Callable[[], AgentToolContext],
        credits: CreditService | None = None,
        atomic: Callable[[], AbstractContextManager[object]] | None = None,
        ensure_research_draft: Callable[..., UUID] | None = None,
        bind_research_draft: Callable[..., UUID] | None = None,
    ) -> None:
        self._conversations = conversations
        self._runner = runner
        self._tools_factory = tools_factory
        self._credits = credits
        self._atomic = atomic or nullcontext
        self._ensure_research_draft = ensure_research_draft
        self._bind_research_draft = bind_research_draft

    def list_conversations(self, *, user_id: UUID):
        return self._conversations.list_conversations(user_id=user_id)

    def get_conversation(self, *, user_id: UUID, conversation_id: UUID) -> Conversation:
        return self._conversations.get_conversation(
            user_id=user_id,
            conversation_id=conversation_id,
        )

    def rename_conversation(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        title: str,
    ) -> Conversation:
        return self._conversations.rename_conversation(
            user_id=user_id,
            conversation_id=conversation_id,
            title=title,
        )

    def delete_conversation(self, *, user_id: UUID, conversation_id: UUID) -> None:
        self._conversations.delete_conversation(
            user_id=user_id,
            conversation_id=conversation_id,
        )

    def release_ids_by_turn(self, *, user_id: UUID, conversation_id: UUID):
        return self._conversations.release_ids_by_turn(
            user_id=user_id,
            conversation_id=conversation_id,
        )

    def run_turn(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID | None,
        prompt: str,
        idempotency_key: str,
        workspace: Literal["agent", "research"] = "agent",
        task_id: UUID | None = None,
        document_id: UUID | None = None,
        section_id: str | None = None,
        document_version: int | None = None,
        theory_plan_id: UUID | None = None,
        on_run_started: Callable[[UUID, UUID, bool], None] | None = None,
        on_delta: Callable[[str], None] | None = None,
        on_tool_event: Callable[[AgentToolEvent], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> AgentTurnExecution:
        if not prompt.strip():
            raise ValueError("message must not be empty")
        existing_run = self._conversations.find_run(
            user_id=user_id,
            idempotency_key=idempotency_key,
        )
        conversation: Conversation | None = None
        if existing_run is not None:
            existing_conversation = self.get_conversation(
                user_id=user_id,
                conversation_id=existing_run.conversation_id,
            )
            task_id = _resolve_task_binding(
                conversations=self._conversations,
                user_id=user_id,
                conversation_id=existing_conversation.conversation_id,
                requested_task_id=task_id,
            )
            if existing_run.status == "running":
                raise RunAlreadyActive(str(existing_run.conversation_id))
            if existing_run.status == "completed" and existing_run.turn_id is not None:
                replayed_turn = _find_turn(existing_conversation, existing_run.turn_id)
                if replayed_turn is None:
                    raise RuntimeError("completed Agent run is missing its persisted turn")
                if on_run_started is not None:
                    on_run_started(existing_run.run_id, existing_run.conversation_id, True)
                return AgentTurnExecution(
                    conversation=existing_conversation,
                    run_id=existing_run.run_id,
                    result=_result_from_turn(
                        replayed_turn,
                        release_id=existing_run.knowledge_release_id or "",
                        provider=existing_run.provider,
                        model=existing_run.model,
                    ),
                    turn=replayed_turn,
                    replayed=True,
                    tool_summary=existing_run.tool_summary,
                )
            if conversation_id is None:
                conversation_id = existing_run.conversation_id
            elif conversation_id != existing_run.conversation_id:
                raise ValueError("idempotency key belongs to another conversation")
            conversation = existing_conversation
        else:
            if (
                conversation_id is None
                and task_id is not None
                and (workspace != "research" or self._bind_research_draft is None)
            ):
                raise ConversationTaskBindingConflict(
                    "A new conversation cannot be started with an unbound research task."
                )
            if conversation_id is not None:
                conversation = self.get_conversation(
                    user_id=user_id,
                    conversation_id=conversation_id,
                )
                task_id = _resolve_task_binding(
                    conversations=self._conversations,
                    user_id=user_id,
                    conversation_id=conversation.conversation_id,
                    requested_task_id=task_id,
                )
        if self._credits is not None:
            self._credits.ensure_can_start(user_id=user_id)
            self._conversations.commit()
        conversation_was_created = conversation is None
        if conversation is None:
            conversation = self._conversations.create_conversation(
                user_id=user_id,
                title=prompt,
            )
        if workspace == "research":
            if conversation_was_created and task_id is not None and self._bind_research_draft:
                task_id = self._bind_research_draft(
                    user_id=user_id,
                    conversation_id=conversation.conversation_id,
                    task_id=task_id,
                )
            elif task_id is None and self._ensure_research_draft:
                task_id = self._ensure_research_draft(
                    user_id=user_id,
                    conversation_id=conversation.conversation_id,
                    project_title=prompt,
                )
        tools = self._tools_factory()
        enable_research_handoff_tools = getattr(
            tools, "enable_research_handoff_tools", None
        )
        if callable(enable_research_handoff_tools):
            enable_research_handoff_tools()
        if workspace == "research":
            prepare_research_context = getattr(tools, "prepare_research_context", None)
            if callable(prepare_research_context):
                prepare_research_context(
                    user_id=user_id,
                    task_id=task_id,
                    document_id=document_id,
                    theory_plan_id=theory_plan_id,
                )
        runtime_identity = _runner_identity(self._runner)
        run = self._conversations.start_run(
            user_id=user_id,
            conversation_id=conversation.conversation_id,
            idempotency_key=idempotency_key,
            knowledge_release_id=tools.release.knowledge_release_id,
            provider=runtime_identity.provider,
            model=runtime_identity.model,
        )
        if self._credits is not None:
            try:
                self._credits.reserve(user_id=user_id, run_id=run.run_id)
                self._conversations.commit()
            except Exception as error:
                self._conversations.finish_run(
                    run_id=run.run_id,
                    status="failed",
                    error=str(error),
                )
                self._conversations.commit()
                raise
        current = self.get_conversation(
            user_id=user_id,
            conversation_id=conversation.conversation_id,
        )
        planned_turn_id = uuid4()
        bind_agent_context = getattr(tools, "bind_agent_context", None)
        if callable(bind_agent_context):
            bind_agent_context(
                user_id=user_id,
                conversation_id=run.conversation_id,
                agent_run_id=run.run_id,
                agent_turn_id=planned_turn_id,
                task_id=task_id,
                document_id=document_id,
                section_id=section_id,
                document_version=document_version,
                theory_plan_id=theory_plan_id,
            )
        if workspace == "research":
            enable_research_document_tools = getattr(
                tools, "enable_research_document_tools", None
            )
            if callable(enable_research_document_tools):
                enable_research_document_tools()
            enable_research_map = getattr(tools, "enable_research_map", None)
            if not callable(enable_research_map):
                raise RuntimeError("research workspace tools are unavailable")
            enable_research_map(current.research_map)
        if on_run_started is not None:
            on_run_started(run.run_id, run.conversation_id, run.status == "completed")
        if run.status == "completed" and run.turn_id is not None:
            completed_turn = _find_turn(current, run.turn_id)
            if completed_turn is None:
                raise RuntimeError("completed Agent run is missing its persisted turn")
            return AgentTurnExecution(
                conversation=current,
                run_id=run.run_id,
                result=_result_from_turn(
                    completed_turn,
                    release_id=run.knowledge_release_id or tools.release.knowledge_release_id,
                    provider=run.provider,
                    model=run.model,
                ),
                turn=completed_turn,
                replayed=True,
                tool_summary=run.tool_summary,
            )

        cancelled = is_cancelled or (lambda: False)
        if cancelled():
            if self._credits is not None:
                self._credits.release(user_id=user_id, run_id=run.run_id)
            self._conversations.finish_run(
                run_id=run.run_id,
                status="interrupted",
                tool_summary=(),
            )
            self._conversations.commit()
            raise AgentInterrupted("Agent run was interrupted by the client")

        conversation_history = current.turns[-8:]
        tool_events: list[AgentToolEvent] = []

        def record_tool_event(event: AgentToolEvent) -> None:
            tool_events.append(event)
            if on_tool_event is not None:
                on_tool_event(event)

        try:
            if _asks_about_runtime_identity(prompt):
                result = AgentRunResult(
                    answer=_PRODUCT_IDENTITY_ANSWER,
                    citations=(),
                    release_id=tools.release.knowledge_release_id,
                    provider=runtime_identity.provider,
                    model=runtime_identity.model,
                )
                if on_delta is not None:
                    on_delta(_PRODUCT_IDENTITY_ANSWER)
            else:
                stream_runner = getattr(self._runner, "run_stream", None)
                if on_delta is not None and callable(stream_runner):
                    result = stream_runner(
                        prompt=prompt,
                        conversation=conversation_history,
                        tools=tools,
                        on_delta=on_delta,
                        on_tool_event=record_tool_event,
                    )
                else:
                    result = self._runner.run(
                        prompt=prompt,
                        conversation=conversation_history,
                        tools=tools,
                    )
            if cancelled():
                self._conversations.finish_run(
                    run_id=run.run_id,
                    status="interrupted",
                    tool_summary=tuple(_tool_summary(item) for item in tool_events),
                )
                self._conversations.commit()
                raise AgentInterrupted("Agent run was interrupted by the client")
            citations = tuple(_agent_citation(item) for item in result.citations)
            evidence_ids = frozenset(tools.evidence)
            with self._atomic():
                turn_result = self._conversations.append_turn(
                    user_id=user_id,
                    conversation_id=conversation.conversation_id,
                    idempotency_key=idempotency_key,
                    user_content=prompt,
                    assistant_content=result.answer,
                    citations=citations,
                    evidence_ids=evidence_ids,
                    turn_id=planned_turn_id,
                )
                if self._credits is not None:
                    self._credits.charge(
                        user_id=user_id,
                        run_id=run.run_id,
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens,
                        model=result.model,
                    )
                self._conversations.finish_run(
                    run_id=run.run_id,
                    status="completed",
                    turn_id=(
                        turn_result.turn_id if isinstance(turn_result, AgentTurn) else None
                    ),
                    tool_summary=tuple(_tool_summary(item) for item in tool_events),
                    provider=result.provider,
                    model=result.model,
                )
                if isinstance(turn_result, AgentTurn):
                    finalize_agent_turn = getattr(tools, "finalize_agent_turn", None)
                    if callable(finalize_agent_turn):
                        finalize_agent_turn(source_turn_id=turn_result.turn_id)
        except AgentInterrupted:
            if self._credits is not None:
                self._credits.release(user_id=user_id, run_id=run.run_id)
            self._conversations.finish_run(
                run_id=run.run_id,
                status="interrupted",
                tool_summary=tuple(_tool_summary(item) for item in tool_events),
            )
            self._conversations.commit()
            raise
        except Exception as error:
            if self._credits is not None:
                self._credits.release(user_id=user_id, run_id=run.run_id)
            self._conversations.finish_run(
                run_id=run.run_id,
                status="failed",
                error=str(error),
                tool_summary=tuple(_tool_summary(item) for item in tool_events),
            )
            self._conversations.commit()
            raise
        if isinstance(turn_result, IdempotentTurn):
            refreshed = self.get_conversation(
                user_id=user_id,
                conversation_id=conversation.conversation_id,
            )
            replayed_turn = _find_turn(refreshed, turn_result.turn_id)
            if replayed_turn is None:
                raise RuntimeError("idempotent Agent run is missing its persisted turn")
            return AgentTurnExecution(
                conversation=refreshed,
                run_id=run.run_id,
                result=_result_from_turn(
                    replayed_turn,
                    release_id=run.knowledge_release_id or tools.release.knowledge_release_id,
                    provider=run.provider,
                    model=run.model,
                ),
                turn=replayed_turn,
                replayed=True,
                tool_summary=tuple(_tool_summary(item) for item in tool_events),
            )
        refreshed = self.get_conversation(
            user_id=user_id,
            conversation_id=conversation.conversation_id,
        )
        return AgentTurnExecution(
            conversation=refreshed,
            run_id=run.run_id,
            result=result,
            turn=turn_result,
            replayed=False,
            tool_summary=tuple(_tool_summary(item) for item in tool_events),
        )


def _agent_citation(item) -> AgentCitation:
    return AgentCitation(
        citation_id=item.citation_id,
        label=item.label,
        kind=item.kind,  # type: ignore[arg-type]
        excerpt=item.excerpt,
        knowledge_id=item.knowledge_id,
        source_id=item.source_id,
        source_kind=item.source_kind,
        material_id=item.material_id,
        parse_id=item.parse_id,
        segment_id=item.segment_id,
        locator=dict(item.locator) if item.locator is not None else None,
        deleted=item.deleted,
    )


def _find_turn(conversation: Conversation, turn_id: UUID) -> AgentTurn | None:
    return next((turn for turn in conversation.turns if turn.turn_id == turn_id), None)


def _result_from_turn(
    turn: AgentTurn,
    *,
    release_id: str,
    provider: str,
    model: str,
) -> AgentRunResult:
    return AgentRunResult(
        answer=turn.assistant_message.content,
        citations=tuple(_evidence_from_citation(item) for item in turn.assistant_message.citations),
        release_id=release_id,
        provider=provider,
        model=model,
    )


def _runner_identity(runner: SubjectAgentRunner) -> AgentRuntimeIdentity:
    identity = getattr(runner, "runtime_identity", None)
    provider = str(getattr(identity, "provider", "pydantic-ai")).strip()
    model = str(getattr(identity, "model", "knowledge-agent")).strip()
    if not provider or not model:
        raise ValueError("Agent runtime provider and model must not be empty")
    return AgentRuntimeIdentity(provider=provider, model=model)


def _resolve_task_binding(
    *,
    conversations: ConversationService,
    user_id: UUID,
    conversation_id: UUID,
    requested_task_id: UUID | None,
) -> UUID | None:
    """Use only the task already bound to this conversation.

    A missing request task is resolved from the binding so the shared Agent
    conversation can be reopened without duplicating context.  Supplying a
    different task (or attaching one to an unbound conversation) is rejected
    before a run or tool scope is created.
    """

    bound_task_id = conversations.get_research_task_id(
        user_id=user_id,
        conversation_id=conversation_id,
    )
    if requested_task_id is not None and requested_task_id != bound_task_id:
        raise ConversationTaskBindingConflict(
            "The conversation is already bound to a different research task."
        )
    return bound_task_id


def _asks_about_runtime_identity(prompt: str) -> bool:
    normalized = " ".join(prompt.lower().split())
    return any(pattern.search(normalized) for pattern in _RUNTIME_IDENTITY_PATTERNS)


def _evidence_from_citation(item):
    return AgentEvidence(
        citation_id=item.citation_id,
        label=item.label,
        kind=item.kind,
        excerpt=item.excerpt or "",
        knowledge_id=item.knowledge_id,
        source_id=item.source_id,
        source_kind=item.source_kind,
        material_id=item.material_id,
        parse_id=item.parse_id,
        segment_id=item.segment_id,
        locator=dict(item.locator) if item.locator is not None else None,
        deleted=item.deleted,
    )


def _tool_summary(event: AgentToolEvent) -> dict[str, object]:
    summary: dict[str, object] = {
        "tool": event.tool,
        "phase": event.phase,
        "call_id": event.call_id,
    }
    if event.input is not None:
        summary["input"] = _sanitize_tool_value(dict(event.input))
    if event.output is not None:
        summary["output"] = _sanitize_tool_value(event.output)
    if event.detail is not None:
        summary["detail"] = event.detail
    if event.error is not None:
        summary["error"] = event.error
    return summary


def _sanitize_tool_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _sanitize_tool_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_sanitize_tool_value(item) for item in value]
    return {"type": type(value).__name__}
