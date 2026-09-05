import time
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from inspect import Parameter, signature
from typing import Literal
from uuid import UUID, uuid4

from qunxue_api.modules.agent_conversation import (
    AgentCitation,
    AgentEvidence,
    AgentInterrupted,
    AgentResearchEvent,
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


@dataclass(frozen=True, slots=True)
class AgentTurnExecution:
    conversation: Conversation
    run_id: UUID
    result: AgentRunResult
    turn: AgentTurn | None
    replayed: bool
    tool_summary: tuple[dict[str, object], ...] = ()
    pending_research: dict[str, object] | None = None


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

    def find_run(self, *, user_id: UUID, idempotency_key: str):
        return self._conversations.find_run(
            user_id=user_id,
            idempotency_key=idempotency_key,
        )

    def run_turn(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID | None,
        prompt: str,
        idempotency_key: str,
        workspace: Literal["agent", "research"] = "agent",
        web_search: bool = False,
        task_id: UUID | None = None,
        document_id: UUID | None = None,
        section_id: str | None = None,
        document_version: int | None = None,
        theory_plan_id: UUID | None = None,
        material_ids: tuple[UUID, ...] = (),
        mode: Literal["standard", "deep_research"] = "standard",
        deep_research_run_id: UUID | None = None,
        deep_research_action: Literal["clarify", "confirm", "skip"] | None = None,
        deep_research_selection: str | None = None,
        on_run_started: Callable[[UUID, UUID, bool], None] | None = None,
        on_delta: Callable[[str], None] | None = None,
        on_tool_event: Callable[[AgentToolEvent], None] | None = None,
        on_research_event: Callable[[AgentResearchEvent], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> AgentTurnExecution:
        if not prompt.strip():
            raise ValueError("message must not be empty")
        material_ids = tuple(dict.fromkeys(material_ids))
        if len(material_ids) > 20:
            raise ValueError("an Agent turn accepts at most 20 research materials")
        if material_ids and workspace != "research":
            raise ValueError("research material attachments require a research workspace")
        existing_run = self._conversations.find_run(
            user_id=user_id,
            idempotency_key=idempotency_key,
        )
        if deep_research_run_id is not None:
            pending_run = self._conversations.find_run_by_id(
                user_id=user_id, run_id=deep_research_run_id
            )
            if pending_run is None or pending_run.idempotency_key != idempotency_key:
                raise ValueError("deep research session is invalid")
            existing_run = pending_run
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
            persisted_material_ids = tuple(
                item.material_id for item in existing_run.material_attachments
            )
            if material_ids and material_ids != persisted_material_ids:
                raise ValueError("idempotent Agent run material scope does not match")
            if existing_run.status == "running":
                raise RunAlreadyActive(str(existing_run.conversation_id))
            if existing_run.status in {"awaiting_clarification", "awaiting_plan_confirmation"}:
                pending = _pending_research(existing_run)
                if pending is None:
                    raise ValueError("deep research session is missing its plan")
                if deep_research_action is None:
                    return AgentTurnExecution(
                        conversation=existing_conversation,
                        run_id=existing_run.run_id,
                        result=AgentRunResult(
                            answer="",
                            citations=(),
                            release_id=existing_run.knowledge_release_id or "",
                            provider=existing_run.provider,
                            model=existing_run.model,
                        ),
                        turn=None,
                        replayed=False,
                        tool_summary=existing_run.tool_summary,
                        pending_research=pending,
                    )
                if deep_research_action == "clarify":
                    selection = (deep_research_selection or "").strip()
                    if not selection:
                        raise ValueError("research selection must not be empty")
                    prompt = f"{pending.get('prompt') or prompt}\n\n用户选择的研究重点：{selection}"
                elif deep_research_action == "skip":
                    prompt = (
                        str(pending.get("prompt") or prompt)
                        + "\n\n用户跳过了本次澄清，请采用合理默认范围生成研究方案，不要再次询问。"
                    )
                elif deep_research_action == "confirm":
                    if existing_run.status != "awaiting_plan_confirmation":
                        raise ValueError("research plan is not ready for confirmation")
                    prompt = str(pending.get("prompt") or prompt)
                    selection = str(pending.get("selected_intent") or "").strip()
                    if selection:
                        prompt = f"{prompt}\n\n用户确认的研究重点：{selection}"
                    prompt = (
                        "执行已确认的深入研究。请主动完成多轮知识库检索、网页搜索并读取网页正文，"
                        "核对证据后直接输出详细研究结论；不要只输出研究起点、计划或‘研究完成’占位语。\n\n"
                        f"{prompt}"
                    )
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
        if mode == "deep_research":
            enable_deep_research = getattr(tools, "enable_deep_research", None)
            if callable(enable_deep_research):
                enable_deep_research()
        # Deep research owns web evidence by product definition; the toggle is
        # only optional for ordinary Agent turns.
        if web_search or mode == "deep_research":
            enable_web_search = getattr(tools, "enable_web_search", None)
            if callable(enable_web_search):
                enable_web_search()
        enable_research_handoff_tools = getattr(
            tools, "enable_research_handoff_tools", None
        )
        # Deep research owns its full plan/retrieve/conclusion lifecycle. The
        # legacy handoff tool is available only to ordinary Agent turns; if it
        # is exposed here the model can bypass the research cards and jump to
        # the old “new research” flow before producing a conclusion.
        if callable(enable_research_handoff_tools) and mode != "deep_research":
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
        if existing_run is not None:
            material_attachments = existing_run.material_attachments
        elif material_ids:
            if task_id is None:
                raise ValueError("research material attachments require a research task")
            pin_research_material_scope = getattr(tools, "pin_research_material_scope", None)
            if not callable(pin_research_material_scope):
                raise RuntimeError("research material attachments are unavailable")
            material_attachments = pin_research_material_scope(
                user_id=user_id,
                task_id=task_id,
                material_ids=material_ids,
            )
        else:
            material_attachments = ()
        runtime_identity = _runner_identity(self._runner)
        run = self._conversations.start_run(
            user_id=user_id,
            conversation_id=conversation.conversation_id,
            idempotency_key=idempotency_key,
            knowledge_release_id=tools.release.knowledge_release_id,
            provider=runtime_identity.provider,
            model=runtime_identity.model,
            material_attachments=material_attachments,
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
        bind_research_material_scope = getattr(tools, "bind_research_material_scope", None)
        if callable(bind_research_material_scope):
            bind_research_material_scope(run.material_attachments)
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
        deep_research_started = mode == "deep_research" and deep_research_action == "confirm"

        # Every Agent turn gets the same lightweight intent check. Deep mode
        # additionally pauses on a plan; ordinary mode only pauses when the
        # planner identifies a material clarification question.
        if deep_research_action not in {"clarify", "confirm"}:
            prepare_research = getattr(self._runner, "prepare_research", None)
            planning_events: list[AgentResearchEvent] = []
            planning_failed = False
            if callable(prepare_research):
                try:
                    prepare_kwargs = {
                        "prompt": prompt,
                        "conversation": conversation_history,
                        "on_event": planning_events.append,
                    }
                    parameters = signature(prepare_research).parameters
                    if "tools" in parameters or any(
                        parameter.kind is Parameter.VAR_KEYWORD
                        for parameter in parameters.values()
                    ):
                        prepare_kwargs["tools"] = tools
                    prepare_research(
                        **prepare_kwargs,
                    )
                except Exception:
                    planning_events.clear()
                    planning_failed = True
                if planning_events or planning_failed:
                    planning_event = (
                        planning_events[-1]
                        if planning_events
                        else AgentResearchEvent(
                            kind="plan",
                            payload={
                                "title": "深入研究",
                                "steps": ["检索知识库", "补充网页资料", "整理证据并形成结论"],
                            },
                        )
                    )
                    if deep_research_action == "skip" and planning_event.kind == "ask":
                        planning_event = AgentResearchEvent(
                            kind="plan",
                            payload={
                                "title": prompt.strip()[:80] or "深入研究",
                                "steps": ["检索知识库", "补充网页资料", "整理证据并形成结论"],
                            },
                        )
                    should_pause = mode == "deep_research" or planning_event.kind == "ask"
                    if should_pause:
                        if on_research_event is not None:
                            on_research_event(planning_event)
                        deep_research_started = mode == "deep_research"
                        state = (
                            "awaiting_clarification"
                            if planning_event.kind == "ask"
                            else "awaiting_plan_confirmation"
                        )
                        pending = {
                            "kind": "deep_research_pending",
                            "version": 1,
                            "state": state,
                            "prompt": prompt,
                            **dict(planning_event.payload),
                        }
                        if deep_research_selection:
                            pending["selected_intent"] = deep_research_selection
                        self._conversations.finish_run(
                            run_id=run.run_id,
                            status=state,
                            tool_summary=(pending,),
                        )
                        if self._credits is not None:
                            self._credits.release(user_id=user_id, run_id=run.run_id)
                        self._conversations.commit()
                        return AgentTurnExecution(
                            conversation=current,
                            run_id=run.run_id,
                            result=AgentRunResult(
                                answer="",
                                citations=(),
                                release_id=(
                                    run.knowledge_release_id or tools.release.knowledge_release_id
                                ),
                                provider=run.provider,
                                model=run.model,
                            ),
                            turn=None,
                            replayed=False,
                            tool_summary=(pending,),
                            pending_research=pending,
                        )

        def record_tool_event(event: AgentToolEvent) -> None:
            tool_events.append(event)
            if on_tool_event is not None:
                on_tool_event(event)

        # 深入研究的用时从确认计划那一刻算到出结论，中间等用户回答的时间不计入。
        research_started_at = time.monotonic() if deep_research_started else None

        try:
            stream_runner = getattr(self._runner, "run_stream", None)
            if on_delta is not None and callable(stream_runner):
                runner_kwargs = {
                    "prompt": prompt,
                    "conversation": conversation_history,
                    "tools": tools,
                    "on_delta": on_delta,
                    "on_tool_event": record_tool_event,
                }
                if "is_cancelled" in __import__("inspect").signature(stream_runner).parameters:
                    runner_kwargs["is_cancelled"] = cancelled
                result = stream_runner(
                    **runner_kwargs,
                )
            else:
                result = self._runner.run(
                    prompt=prompt,
                    conversation=conversation_history,
                    tools=tools,
                )
            if deep_research_started and on_research_event is not None:
                on_research_event(
                    AgentResearchEvent(
                        kind="result",
                        payload={
                            "summary": result.answer,
                            "knowledge_count": sum(
                                1
                                for item in result.citations
                                if item.kind in {"entry", "theory", "source"}
                            ),
                            "web_count": sum(
                                1 for item in result.citations if item.source_kind == "web"
                            ),
                        },
                    )
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
                completed_tool_summary = (
                    *(_tool_summary(item) for item in tool_events),
                    *_deep_research_summary(result, research_started_at),
                )
                self._conversations.finish_run(
                    run_id=run.run_id,
                    status="completed",
                    turn_id=(
                        turn_result.turn_id if isinstance(turn_result, AgentTurn) else None
                    ),
                    tool_summary=completed_tool_summary,
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
            tool_summary=completed_tool_summary,
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


def _pending_research(run) -> dict[str, object] | None:
    for item in run.tool_summary:
        if item.get("kind") == "deep_research_pending":
            return dict(item)
    return None


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


def _deep_research_summary(
    result: AgentRunResult,
    started_at: float | None,
) -> tuple[dict[str, object], ...]:
    """一条深入研究结束的留痕，让重开对话时还能还原那张研究完成卡片。

    走的是工具轨迹这条已有通道（研究地图的画布补丁也存在这里），所以不必为它单开
    一个契约字段；前端按 tool 名把它挑出来，不当普通工具调用展示。
    """
    if started_at is None:
        return ()
    return (
        {
            "tool": "deep_research",
            "phase": "finished",
            "call_id": "deep-research",
            "output": {
                "schema_version": 1,
                "elapsed_seconds": round(time.monotonic() - started_at, 1),
                "knowledge_count": sum(
                    1 for item in result.citations if item.kind in {"entry", "theory", "source"}
                ),
                "web_count": sum(1 for item in result.citations if item.source_kind == "web"),
            },
        },
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
