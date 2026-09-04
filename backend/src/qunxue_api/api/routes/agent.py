import json
import logging
import queue
import threading
import time
from collections.abc import Iterator
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request, status
from fastapi.responses import StreamingResponse

from qunxue_api.api.contracts.agent import (
    AgentCitationResponse,
    AgentConversationListResponse,
    AgentConversationResponse,
    AgentConversationSummaryResponse,
    AgentConversationUpdateRequest,
    AgentMessageResponse,
    AgentResearchJourneyResponse,
    AgentTurnRequest,
    AgentTurnResponse,
    ConfirmResearchStartRequest,
    ConfirmResearchStartResponse,
    ResearchStartProposalResponse,
)
from qunxue_api.api.contracts.common import ErrorResponse
from qunxue_api.api.dependencies import CurrentSessionDependency
from qunxue_api.api.routes.research_tasks import _match_status, _navigation_response
from qunxue_api.api.routes.stubs import IdempotencyKey
from qunxue_api.modules.agent_conversation import (
    AgentInterrupted,
    AgentResearchEvent,
    AgentToolEvent,
    ConversationNotFound,
    ConversationTaskBindingConflict,
    ResearchMaterialCitationUnavailable,
    RunAlreadyActive,
)
from qunxue_api.modules.billing import CreditRunInProgress, CreditsDepleted
from qunxue_api.modules.knowledge_catalog import RetrievalPipelineUnavailable
from qunxue_api.modules.research_intake import ResearchStartProposalStatus

router = APIRouter(
    prefix="/api/agent",
    tags=["agent"],
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
logger = logging.getLogger(__name__)
AgentRuntimeMode = Literal["mock", "base", "sft"]
_SSE_HEARTBEAT_SECONDS = 5.0
_AGENT_TURN_TIMEOUT_SECONDS = 300.0
_ACTIVE_RUNS_LOCK = threading.Lock()
_ACTIVE_RUN_CANCEL_EVENTS: dict[tuple[UUID, UUID], threading.Event] = {}


def _register_active_run(
    user_id: UUID,
    run_id: UUID,
    cancel_event: threading.Event,
) -> None:
    with _ACTIVE_RUNS_LOCK:
        _ACTIVE_RUN_CANCEL_EVENTS[(user_id, run_id)] = cancel_event


def _cancel_active_run(user_id: UUID, run_id: UUID) -> bool:
    with _ACTIVE_RUNS_LOCK:
        cancel_event = _ACTIVE_RUN_CANCEL_EVENTS.get((user_id, run_id))
    if cancel_event is None:
        return False
    cancel_event.set()
    return True


def _release_active_run(
    user_id: UUID,
    run_id: UUID,
    cancel_event: threading.Event,
) -> None:
    with _ACTIVE_RUNS_LOCK:
        key = (user_id, run_id)
        if _ACTIVE_RUN_CANCEL_EVENTS.get(key) is cancel_event:
            _ACTIVE_RUN_CANCEL_EVENTS.pop(key, None)


def _effective_agent_runtime_mode(request: Request) -> AgentRuntimeMode:
    """Expose the runtime actually selected for the independent Agent runner.

    The Agent deliberately has its own API-key override and does not use the
    legacy model gateway reported by ``/api/health``.  Keeping this decision at
    the route boundary prevents the frontend from labeling an API-key-backed
    run as a deterministic preview just because the legacy gateway remains in
    its zero-config ``mock`` mode.
    """
    settings = request.app.state.settings
    if settings.runtime_mode != "mock":
        return settings.runtime_mode
    return "base" if settings.has_model_api_key else "mock"


@router.get(
    "/conversations",
    response_model=AgentConversationListResponse,
    operation_id="list_agent_conversations",
)
def list_agent_conversations(
    request: Request, current: CurrentSessionDependency
) -> AgentConversationListResponse:
    with request.app.state.disciplinary_agent_scope() as app:
        return AgentConversationListResponse(
            items=[_summary(item) for item in app.list_conversations(user_id=current.user.user_id)]
        )


@router.get(
    "/conversations/{conversation_id}",
    response_model=AgentConversationResponse,
    operation_id="get_agent_conversation",
)
def get_agent_conversation(
    conversation_id: UUID,
    request: Request,
    current: CurrentSessionDependency,
) -> AgentConversationResponse:
    with request.app.state.disciplinary_agent_scope() as app:
        conversation = app.get_conversation(
            user_id=current.user.user_id,
            conversation_id=conversation_id,
        )
        return _conversation(
            conversation,
            release_ids=app.release_ids_by_turn(
                user_id=current.user.user_id,
                conversation_id=conversation_id,
            ),
        )


@router.patch(
    "/conversations/{conversation_id}",
    response_model=AgentConversationSummaryResponse,
    operation_id="update_agent_conversation",
)
def update_agent_conversation(
    conversation_id: UUID,
    payload: AgentConversationUpdateRequest,
    request: Request,
    current: CurrentSessionDependency,
    _idempotency_key: IdempotencyKey,
) -> AgentConversationSummaryResponse:
    with request.app.state.disciplinary_agent_scope() as app:
        return _summary(
            app.rename_conversation(
                user_id=current.user.user_id,
                conversation_id=conversation_id,
                title=payload.title,
            )
        )


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="delete_agent_conversation",
)
def delete_agent_conversation(
    conversation_id: UUID,
    request: Request,
    current: CurrentSessionDependency,
    _idempotency_key: IdempotencyKey,
) -> None:
    with request.app.state.disciplinary_agent_scope() as app:
        app.delete_conversation(
            user_id=current.user.user_id,
            conversation_id=conversation_id,
        )


@router.get(
    "/conversations/{conversation_id}/research-start-proposal",
    response_model=ResearchStartProposalResponse,
    operation_id="get_agent_research_start_proposal",
)
def get_agent_research_start_proposal(
    conversation_id: UUID,
    request: Request,
    current: CurrentSessionDependency,
) -> ResearchStartProposalResponse:
    with request.app.state.research_start_application_scope() as application:
        proposal = application.get_conversation_proposal(
            user_id=current.user.user_id,
            conversation_id=conversation_id,
        )
        return ResearchStartProposalResponse.from_domain(proposal)


@router.get(
    "/conversations/{conversation_id}/journey",
    response_model=AgentResearchJourneyResponse,
    operation_id="get_agent_research_journey",
)
def get_agent_research_journey(
    conversation_id: UUID,
    request: Request,
    current: CurrentSessionDependency,
) -> AgentResearchJourneyResponse:
    with request.app.state.research_start_application_scope() as application:
        journey = application.get_journey(
            user_id=current.user.user_id,
            conversation_id=conversation_id,
        )
        match_status = None
        if journey.task is not None:
            with request.app.state.research_navigation_match_reader_scope() as matches:
                match_status = _match_status(matches, journey.task)
        return AgentResearchJourneyResponse(
            conversation_id=journey.conversation_id,
            status=(
                "proposal_pending"
                if journey.proposal is not None
                and journey.proposal.status is ResearchStartProposalStatus.PENDING_CONFIRMATION
                else "task_bound"
                if journey.task is not None
                else "collecting"
            ),
            task_id=journey.task.task_id if journey.task is not None else None,
            proposal=(
                ResearchStartProposalResponse.from_domain(journey.proposal)
                if journey.proposal is not None
                else None
            ),
            navigation=(
                _navigation_response(
                    journey.task,
                    journey.progress,
                    match_status=match_status,
                )
                if journey.task is not None and journey.progress is not None
                else None
            ),
        )


@router.post(
    "/research-start-proposals/{proposal_id}/confirm",
    response_model=ConfirmResearchStartResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="confirm_agent_research_start",
    responses={409: {"model": ErrorResponse}},
)
def confirm_agent_research_start(
    proposal_id: UUID,
    payload: ConfirmResearchStartRequest,
    request: Request,
    current: CurrentSessionDependency,
    idempotency_key: IdempotencyKey,
) -> ConfirmResearchStartResponse:
    with request.app.state.research_start_application_scope() as application:
        result = application.confirm(
            user_id=current.user.user_id,
            proposal_id=proposal_id,
            idempotency_key=idempotency_key,
            expected_version=payload.expected_version,
            phenomenon=payload.phenomenon,
            research_intent=payload.research_intent,
            context=payload.context,
        )
        return ConfirmResearchStartResponse(
            conversation_id=result.proposal.conversation_id,
            status="task_bound",
            task_id=result.task.task_id,
            proposal=ResearchStartProposalResponse.from_domain(result.proposal),
            navigation=_navigation_response(result.task, result.progress),
        )


@router.post(
    "/turns",
    status_code=status.HTTP_200_OK,
    operation_id="stream_agent_turn",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Server-sent Agent events",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        }
    },
)
def stream_agent_turn(
    payload: AgentTurnRequest,
    request: Request,
    current: CurrentSessionDependency,
    idempotency_key: IdempotencyKey,
) -> StreamingResponse:
    def events() -> Iterator[str]:
        event_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        cancel_event = threading.Event()
        user_id = current.user.user_id
        deadline = time.monotonic() + _AGENT_TURN_TIMEOUT_SECONDS
        runtime_mode = _effective_agent_runtime_mode(request)
        registered_run_id: UUID | None = None

        def on_run_started(run_id: UUID, conversation_id: UUID, replayed: bool) -> None:
            nonlocal registered_run_id
            registered_run_id = run_id
            if not replayed:
                _register_active_run(user_id, run_id, cancel_event)
            event_queue.put(
                (
                    "started",
                    {
                        "conversation_id": str(conversation_id),
                        "run_id": str(run_id),
                        "replayed": replayed,
                        "runtime_mode": runtime_mode,
                    },
                )
            )

        def on_delta(delta: str) -> None:
            event_queue.put(("delta", delta))

        def on_tool_event(event: AgentToolEvent) -> None:
            event_queue.put(("tool", event))

        def on_research_event(event: AgentResearchEvent) -> None:
            event_queue.put(("research", event))

        def run_agent() -> None:
            try:
                while True:
                    try:
                        with request.app.state.disciplinary_agent_scope() as app:
                            execution = app.run_turn(
                                user_id=user_id,
                                conversation_id=payload.conversation_id,
                                prompt=payload.message,
                                idempotency_key=idempotency_key,
                                workspace=payload.workspace,
                                web_search=payload.web_search,
                                task_id=payload.task_id,
                                document_id=payload.document_id,
                                section_id=payload.section_id,
                                document_version=payload.document_version,
                                theory_plan_id=payload.theory_plan_id,
                                material_ids=payload.material_ids,
                                mode=payload.mode,
                                deep_research_run_id=payload.deep_research_run_id,
                                deep_research_action=payload.deep_research_action,
                                deep_research_selection=payload.deep_research_selection,
                                on_run_started=on_run_started,
                                on_delta=on_delta,
                                on_tool_event=on_tool_event,
                                on_research_event=on_research_event,
                                is_cancelled=cancel_event.is_set,
                            )
                        break
                    except RunAlreadyActive:
                        with request.app.state.disciplinary_agent_scope() as app:
                            existing = app.find_run(
                                user_id=user_id,
                                idempotency_key=idempotency_key,
                            )
                        if existing is None or existing.status != "running":
                            raise
                        if cancel_event.wait(0.5):
                            raise AgentInterrupted("Agent run was stopped") from None
                event_queue.put(("completed", execution))
            except Exception as error:
                event_queue.put(("failed", error))
            finally:
                if registered_run_id is not None:
                    _release_active_run(user_id, registered_run_id, cancel_event)

        worker = threading.Thread(target=run_agent, daemon=True)
        worker.start()
        yield _event("agent_status", {"status": "thinking"})
        streamed_answer = False
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    yield _event(
                        "turn_failed",
                        {
                            "code": "turn_timeout",
                            "message": "连接等待超时，回答仍在后台生成，可重连恢复。",
                        },
                    )
                    break
                try:
                    event_name, event_payload = event_queue.get(
                        timeout=min(_SSE_HEARTBEAT_SECONDS, remaining)
                    )
                except queue.Empty:
                    if time.monotonic() < deadline:
                        yield ": keep-alive\n\n"
                    continue
                deadline = time.monotonic() + _AGENT_TURN_TIMEOUT_SECONDS
                if event_name == "started":
                    yield _event("turn_started", event_payload)  # type: ignore[arg-type]
                elif event_name == "delta":
                    if not streamed_answer:
                        yield _event("agent_status", {"status": "answering"})
                    streamed_answer = True
                    yield _event("assistant_delta", {"delta": str(event_payload)})
                elif event_name == "tool":
                    if not isinstance(event_payload, AgentToolEvent):
                        raise RuntimeError("Agent worker returned an invalid tool event")
                    tool_payload: dict[str, object] = {
                        "tool": event_payload.tool,
                        "call_id": event_payload.call_id,
                    }
                    if event_payload.input is not None:
                        tool_payload["input"] = dict(event_payload.input)
                    if event_payload.output is not None:
                        tool_payload["output"] = event_payload.output
                    if event_payload.detail is not None:
                        tool_payload["detail"] = event_payload.detail
                    if event_payload.error is not None:
                        tool_payload["message"] = event_payload.detail or "工具调用失败"
                        tool_payload["error_code"] = event_payload.error
                    yield _event(
                        f"tool_{event_payload.phase}",
                        tool_payload,
                    )
                    if (
                        event_payload.tool == "update_research_map"
                        and event_payload.phase == "finished"
                        and isinstance(event_payload.output, dict)
                        and event_payload.output.get("schema_version") == 1
                    ):
                        yield _event("canvas_patch", event_payload.output)
                elif event_name == "research":
                    if not isinstance(event_payload, AgentResearchEvent):
                        raise RuntimeError("Agent worker returned an invalid research event")
                    yield _event(
                        f"research_{event_payload.kind}",
                        dict(event_payload.payload),
                    )
                elif event_name == "failed":
                    if isinstance(event_payload, BaseException):
                        raise event_payload
                    raise RuntimeError("Agent worker failed")
                else:
                    execution = event_payload
                    if not hasattr(execution, "result"):
                        raise RuntimeError("Agent worker returned no execution")
                    if execution.pending_research is not None:
                        pending = execution.pending_research
                        yield _event("research_waiting", {
                            "run_id": str(execution.run_id),
                            **pending,
                        })
                        break
                    if not streamed_answer:
                        yield _event("agent_status", {"status": "answering"})
                        for chunk in _chunks(execution.result.answer):
                            yield _event("assistant_delta", {"delta": chunk})
                    for citation in execution.result.citations:
                        yield _event("citation_added", _citation(citation))
                    yield _event(
                        "turn_completed",
                        {
                            "conversation": _conversation(
                                execution.conversation,
                                tool_summaries={execution.turn.turn_id: execution.tool_summary}
                                if execution.turn is not None
                                else {},
                                release_ids={execution.turn.turn_id: execution.result.release_id}
                                if execution.turn is not None
                                else {},
                            ).model_dump(mode="json"),
                            "knowledge_release_id": execution.result.release_id,
                        },
                    )
                    break
        except ConversationNotFound:
            yield _event("turn_failed", {"code": "not_found", "message": "对话不存在或无权访问。"})
        except ConversationTaskBindingConflict as error:
            yield _event(
                "turn_failed",
                {
                    "code": error.code,
                    "message": "该对话已属于另一个研究任务，无法读取当前任务材料。",
                },
            )
        except ResearchMaterialCitationUnavailable as error:
            yield _event(
                "turn_failed",
                {
                    "code": error.code,
                    "message": "引用的个人研究材料已删除或不属于当前研究，本轮未保存。",
                },
            )
        except RunAlreadyActive:
            yield _event(
                "turn_failed",
                {"code": "run_in_progress", "message": "这段对话正在生成回答，请稍候。"},
            )
        except CreditRunInProgress:
            yield _event(
                "turn_failed",
                {"code": "run_in_progress", "message": "当前账户已有一轮对话正在生成，请稍候。"},
            )
        except CreditsDepleted:
            yield _event(
                "turn_failed",
                {
                    "code": "credits_depleted",
                    "message": "积分不足，请前往账户设置查看用量。",
                },
            )
        except AgentInterrupted:
            yield _event(
                "turn_interrupted",
                {"code": "interrupted", "message": "已停止生成，未保存未完成的回答。"},
            )
        except RetrievalPipelineUnavailable:
            logger.exception("Agent retrieval failed")
            yield _event(
                "turn_failed",
                {
                    "code": "retrieval_unavailable",
                    "message": "发布绑定的知识检索暂时不可用，本轮未生成研究回答。",
                },
            )
        except Exception:
            logger.exception("Agent turn failed")
            yield _event(
                "turn_failed",
                {"code": "agent_unavailable", "message": "Agent 暂时无法完成回答，请稍后重试。"},
            )
        finally:
            # Closing the stream is an implicit user stop (navigation, new
            # conversation, tab close). The worker checks this cooperative
            # signal before starting another model or tool operation.
            cancel_event.set()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/runs/{run_id}/stop",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="stop_agent_run",
)
def stop_agent_run(
    run_id: UUID,
    current: CurrentSessionDependency,
    _idempotency_key: IdempotencyKey,
) -> None:
    _cancel_active_run(current.user.user_id, run_id)


def _event(name: str, payload: dict[str, object]) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _chunks(value: str, size: int = 72) -> Iterator[str]:
    for index in range(0, len(value), size):
        yield value[index : index + size]


def _summary(item) -> AgentConversationSummaryResponse:
    return AgentConversationSummaryResponse(
        conversation_id=item.conversation_id,
        title=item.title,
        updated_at=item.updated_at,
        turn_count=len(item.turns),
    )


def _conversation(
    item,
    *,
    tool_summaries: (
        dict[UUID, tuple[dict[str, object], ...] | list[dict[str, object]]] | None
    ) = None,
    release_ids: dict[UUID, str | None] | None = None,
) -> AgentConversationResponse:
    resolved_tool_summaries = tool_summaries or {}
    resolved_release_ids = release_ids or {}
    return AgentConversationResponse(
        conversation_id=item.conversation_id,
        title=item.title,
        created_at=item.created_at,
        updated_at=item.updated_at,
        turn_count=len(item.turns),
        turns=[
            AgentTurnResponse(
                turn_id=turn.turn_id,
                user=_message(turn.user_message),
                assistant=_message(turn.assistant_message),
                tool_traces=[
                    _tool_trace(entry)
                    for entry in resolved_tool_summaries.get(turn.turn_id, turn.tool_summary)
                ],
                knowledge_release_id=resolved_release_ids.get(turn.turn_id),
                canvas_patches=[dict(patch) for patch in turn.canvas_patches],
            )
            for turn in item.turns
        ],
        research_map=dict(item.research_map),
    )


def _message(item) -> AgentMessageResponse:
    return AgentMessageResponse(
        message_id=item.message_id,
        role=item.role,
        content=item.content,
        sequence=item.sequence,
        created_at=item.created_at,
        citations=[
            AgentCitationResponse(
                citation_id=citation.citation_id,
                label=citation.label,
                kind=citation.kind,
                excerpt=citation.excerpt,
                knowledge_id=citation.knowledge_id,
                source_id=citation.source_id,
                source_kind=citation.source_kind,
                material_id=citation.material_id,
                parse_id=citation.parse_id,
                segment_id=citation.segment_id,
                locator=citation.locator,
                deleted=citation.deleted,
            )
            for citation in item.citations
        ],
    )


def _citation(item) -> dict[str, object]:
    return {
        "citation_id": item.citation_id,
        "label": item.label,
        "kind": item.kind,
        "excerpt": item.excerpt,
        "knowledge_id": item.knowledge_id,
        "source_id": item.source_id,
        "source_kind": item.source_kind,
        "material_id": item.material_id,
        "parse_id": item.parse_id,
        "segment_id": item.segment_id,
        "locator": item.locator,
        "deleted": item.deleted,
    }


def _tool_trace(item: dict[str, object]):
    return {
        "tool": str(item.get("tool", "unknown")),
        "phase": str(item.get("phase", "finished")),
        "call_id": str(item.get("call_id", "unknown")),
        "input": item.get("input"),
        "output": item.get("output"),
        "detail": item.get("detail"),
        "error": item.get("error"),
    }
