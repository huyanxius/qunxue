import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qunxue_api.api.billing_errors import install_billing_error_handlers
from qunxue_api.api.contracts.agent import AgentTurnRequest
from qunxue_api.api.routes.agent import stream_agent_turn
from qunxue_api.modules.billing import (
    BillingBudgetExceeded,
    BillingContextMissing,
    BillingReplayBlocked,
)
from qunxue_api.settings import Settings


@pytest.mark.parametrize(
    "error,status,code",
    [
        (
            BillingBudgetExceeded("synthetic-secret", reason="credits_depleted"),
            402,
            "credits_depleted",
        ),
        (BillingBudgetExceeded("synthetic-secret"), 429, "billing_budget_exceeded"),
        (BillingContextMissing("synthetic-secret"), 503, "billing_not_configured"),
        (BillingReplayBlocked("synthetic-secret"), 409, "billing_replay_blocked"),
    ],
)
def test_new_billing_failures_use_safe_json_error_contract(error, status, code):
    app = FastAPI()
    install_billing_error_handlers(app)

    @app.get("/synthetic")
    def fail():
        raise error

    with TestClient(app) as client:
        response = client.get("/synthetic")
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert "synthetic-secret" not in response.text


@pytest.mark.parametrize(
    "error,code",
    [
        (BillingBudgetExceeded("synthetic-secret", reason="credits_depleted"), "credits_depleted"),
        (BillingBudgetExceeded("synthetic-secret"), "billing_budget_exceeded"),
        (BillingContextMissing("synthetic-secret"), "billing_not_configured"),
        (BillingReplayBlocked("synthetic-secret"), "billing_replay_blocked"),
    ],
)
def test_stream_terminal_billing_error_preserves_event_contract(error, code):
    class Application:
        def run_turn(self, **kwargs):
            raise error

    @contextmanager
    def scope():
        yield Application()

    async def exercise():
        request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    settings=Settings(_env_file=None), disciplinary_agent_scope=scope
                )
            )
        )
        response = stream_agent_turn(
            payload=AgentTurnRequest(message="synthetic"),
            request=request,
            current=SimpleNamespace(user=SimpleNamespace(user_id=UUID(int=923))),
            idempotency_key="synthetic",
        )
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        return "".join(chunks)

    events = asyncio.run(exercise())
    assert "event: turn_failed" in events
    assert code in events
    assert "event: turn_completed" not in events
    assert "synthetic-secret" not in events
