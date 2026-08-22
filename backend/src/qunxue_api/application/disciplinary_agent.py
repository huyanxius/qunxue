from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

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
    IdempotentTurn,
    RunAlreadyActive,
    SubjectAgentRunner,
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
    ) -> None:
        self._conversations = conversations
        self._runner = runner
        self._tools_factory = tools_factory

    def list_conversations(self, *, user_id: UUID):
        return self._conversations.list_conversations(user_id=user_id)

    def get_conversation(self, *, user_id: UUID, conversation_id: UUID) -> Conversation:
        return self._conversations.get_conversation(
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
        if existing_run is not None:
            existing_conversation = self.get_conversation(
                user_id=user_id,
                conversation_id=existing_run.conversation_id,
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
        tools = self._tools_factory()
        if workspace == "research":
            prepare_research_context = getattr(tools, "prepare_research_context", None)
            if callable(prepare_research_context):
                prepare_research_context(
                    user_id=user_id,
                    task_id=task_id,
                    document_id=document_id,
                    theory_plan_id=theory_plan_id,
                )
        conversation = (
            self._conversations.create_conversation(user_id=user_id, title=prompt)
            if conversation_id is None
            else self.get_conversation(user_id=user_id, conversation_id=conversation_id)
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
        current = self.get_conversation(
            user_id=user_id,
            conversation_id=conversation.conversation_id,
        )
        bind_agent_context = getattr(tools, "bind_agent_context", None)
        if callable(bind_agent_context):
            bind_agent_context(
                user_id=user_id,
                conversation_id=run.conversation_id,
                agent_run_id=run.run_id,
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
            self._conversations.finish_run(
                run_id=run.run_id,
                status="interrupted",
                tool_summary=(),
            )
            self._conversations.commit()
            raise AgentInterrupted("Agent run was interrupted by the client")

        transcript = "\n".join(
            f"{item.user_message.content}\n{item.assistant_message.content}"
            for item in current.turns[-8:]
        )
        tool_events: list[AgentToolEvent] = []

        def record_tool_event(event: AgentToolEvent) -> None:
            tool_events.append(event)
            if on_tool_event is not None:
                on_tool_event(event)

        try:
            stream_runner = getattr(self._runner, "run_stream", None)
            if on_delta is not None and callable(stream_runner):
                result = stream_runner(
                    prompt=prompt,
                    conversation=transcript,
                    tools=tools,
                    on_delta=on_delta,
                    on_tool_event=record_tool_event,
                )
            else:
                result = self._runner.run(prompt=prompt, conversation=transcript, tools=tools)
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
            turn_result = self._conversations.append_turn(
                user_id=user_id,
                conversation_id=conversation.conversation_id,
                idempotency_key=idempotency_key,
                user_content=prompt,
                assistant_content=result.answer,
                citations=citations,
                evidence_ids=evidence_ids,
            )
            self._conversations.finish_run(
                run_id=run.run_id,
                status="completed",
                turn_id=turn_result.turn_id if isinstance(turn_result, AgentTurn) else None,
                tool_summary=tuple(_tool_summary(item) for item in tool_events),
                provider=result.provider,
                model=result.model,
            )
        except AgentInterrupted:
            self._conversations.finish_run(
                run_id=run.run_id,
                status="interrupted",
                tool_summary=tuple(_tool_summary(item) for item in tool_events),
            )
            self._conversations.commit()
            raise
        except Exception as error:
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


def _evidence_from_citation(item):
    return AgentEvidence(
        citation_id=item.citation_id,
        label=item.label,
        kind=item.kind,
        excerpt=item.excerpt or "",
        knowledge_id=item.knowledge_id,
        source_id=item.source_id,
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
