import json
import logging
import queue
import threading
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
    AgentMessageResponse,
    AgentTurnRequest,
    AgentTurnResponse,
)
from qunxue_api.api.contracts.common import ErrorResponse
from qunxue_api.api.dependencies import CurrentSessionDependency
from qunxue_api.api.routes.stubs import IdempotencyKey
from qunxue_api.modules.agent_conversation import (
    AgentInterrupted,
    AgentToolEvent,
    ConversationNotFound,
    RunAlreadyActive,
)

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
        runtime_mode = _effective_agent_runtime_mode(request)

        def on_run_started(run_id: UUID, conversation_id: UUID, replayed: bool) -> None:
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

        def run_agent() -> None:
            try:
                with request.app.state.disciplinary_agent_scope() as app:
                    execution = app.run_turn(
                        user_id=current.user.user_id,
                        conversation_id=payload.conversation_id,
                        prompt=payload.message,
                        idempotency_key=idempotency_key,
                        on_run_started=on_run_started,
                        on_delta=on_delta,
                        on_tool_event=on_tool_event,
                        is_cancelled=cancel_event.is_set,
                    )
                event_queue.put(("completed", execution))
            except Exception as error:
                event_queue.put(("failed", error))

        worker = threading.Thread(target=run_agent, daemon=True)
        worker.start()
        yield _event("agent_status", {"status": "thinking"})
        streamed_answer = False
        try:
            while True:
                event_name, event_payload = event_queue.get()
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
                elif event_name == "failed":
                    if isinstance(event_payload, BaseException):
                        raise event_payload
                    raise RuntimeError("Agent worker failed")
                else:
                    execution = event_payload
                    if not hasattr(execution, "result"):
                        raise RuntimeError("Agent worker returned no execution")
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
                            ).model_dump(
                                mode="json"
                            ),
                            "knowledge_release_id": execution.result.release_id,
                        },
                    )
                    break
        except ConversationNotFound:
            yield _event("turn_failed", {"code": "not_found", "message": "对话不存在或无权访问。"})
        except RunAlreadyActive:
            yield _event(
                "turn_failed",
                {"code": "run_in_progress", "message": "这段对话正在生成回答，请稍候。"},
            )
        except AgentInterrupted:
            yield _event(
                "turn_interrupted",
                {"code": "interrupted", "message": "已停止生成，未保存未完成的回答。"},
            )
        except Exception:
            logger.exception("Agent turn failed")
            yield _event(
                "turn_failed",
                {"code": "agent_unavailable", "message": "Agent 暂时无法完成回答，请稍后重试。"},
            )
        finally:
            cancel_event.set()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
            )
            for turn in item.turns
        ],
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
