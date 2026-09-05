import asyncio
import threading
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import UUID

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from qunxue_api.api.contracts.agent import AgentTurnRequest
from qunxue_api.api.dependencies import get_current_session
from qunxue_api.api.routes.agent import router, stream_agent_turn
from qunxue_api.modules.agent_conversation import AgentInterrupted, ConversationNotFound
from qunxue_api.settings import Settings


def test_asgi_disconnect_cancels_worker_without_waiting_for_another_model_event():
    """A silent model must stop when the response connection disappears."""
    stopped = threading.Event()
    cleanup = threading.Event()
    run_id = UUID(int=921)
    conversation_id = UUID(int=922)

    class SlowApplication:
        def run_turn(self, **kwargs):
            kwargs["on_run_started"](run_id, conversation_id, False)
            while not cleanup.wait(0.01):
                if kwargs["is_cancelled"]():
                    stopped.set()
                    raise AgentInterrupted("disconnected")

        def heartbeat(self, **kwargs):
            return False

        def request_cancel(self, **kwargs):
            return SimpleNamespace(status="interrupted")

    @contextmanager
    def application_scope():
        yield SlowApplication()

    async def exercise():
        disconnect = asyncio.Event()
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
            settings=Settings(_env_file=None),
            disciplinary_agent_scope=application_scope,
        )))
        response = stream_agent_turn(
            payload=AgentTurnRequest(message="test a silent model"),
            request=request,
            current=SimpleNamespace(user=SimpleNamespace(user_id=UUID(int=923))),
            idempotency_key="disconnect-test",
        )

        async def receive():
            await disconnect.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            if b"turn_started" in message.get("body", b""):
                disconnect.set()

        try:
            await asyncio.wait_for(response(
                {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.0"}},
                receive,
                send,
            ), timeout=1)
            assert await asyncio.to_thread(stopped.wait, 0.5), (
                "closing the response left the model worker running"
            )
        finally:
            cleanup.set()
            await asyncio.sleep(0.02)

    asyncio.run(exercise())


def test_stop_unknown_run_does_not_claim_success():
    class Application:
        def request_cancel(self, **kwargs):
            raise ConversationNotFound("run does not belong to this user")

    @contextmanager
    def application_scope():
        yield Application()

    app = FastAPI()
    app.state.disciplinary_agent_scope = application_scope
    app.dependency_overrides[get_current_session] = lambda: SimpleNamespace(
        user=SimpleNamespace(user_id=UUID(int=931)),
    )
    app.add_exception_handler(ConversationNotFound, lambda request, error: JSONResponse(
        {"error": {"code": "not_found"}}, status_code=404,
    ))
    app.include_router(router)
    with TestClient(app) as client:
        response = client.post(
            f"/api/agent/runs/{UUID(int=932)}/stop",
            headers={"Idempotency-Key": "stop-unknown"},
        )
    assert response.status_code == 404
