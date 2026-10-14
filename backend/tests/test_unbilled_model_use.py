from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from qunxue_api.bootstrap import create_app
from qunxue_api.modules.agent_conversation import AgentRunResult
from qunxue_api.settings import Settings


@pytest.mark.parametrize("old_billing_config", [False, True])
def test_real_agent_answers_at_zero_balance_without_billing_config_or_charges(
    plain_client,
    monkeypatch,
    old_billing_config,
):
    calls = []

    class Runner:
        def __init__(self, **kwargs):
            self.require_billing = kwargs.get("require_billing", False)

        def run(self, *, prompt, conversation, tools):
            assert not self.require_billing
            calls.append(prompt)
            return AgentRunResult(
                answer="正常回答",
                citations=(),
                release_id="test-release",
                provider="synthetic",
                model="test-model",
                input_tokens=200,
                output_tokens=20,
            )

    monkeypatch.setattr("qunxue_api.bootstrap.PydanticAIKnowledgeRunner", Runner)
    extra = (
        dict(
            billing_price_version="old-explicit-config",
            billing_credits_per_usd=100,
            billing_max_attempt_usd_micro=1000,
            billing_max_operation_usd_micro=10000,
            billing_daily_budget_usd_micro=100000,
        )
        if old_billing_config
        else {}
    )
    settings = Settings(
        _env_file=None,
        database_url=plain_client.app.state.settings.database_url,
        runtime_mode="base",
        model_base_url="https://synthetic.test/v1",
        model_api_key="synthetic",
        model_name="test-model",
        **extra,
    )
    app = create_app(
        settings=settings,
        database=plain_client.app.state.database,
        require_email_verification=False,
    )
    client = TestClient(app)
    result = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": "unbilled@example.com", "password": "password-123"},
    )
    assert result.status_code == 201
    user_id = result.json()["user"]["user_id"]
    engine = app.state.database.engine
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE credit_accounts SET balance=0 WHERE user_id=:user"), {"user": user_id}
        )
        ledger_count = conn.scalar(text("SELECT count(*) FROM credit_ledger"))
    response = client.post(
        "/api/agent/turns",
        headers={"Idempotency-Key": str(uuid4())},
        json={"message": "请打个招呼"},
    )
    assert response.status_code == 200
    assert "event: turn_completed" in response.text, response.text
    assert "正常回答" in response.text
    assert "event: error" not in response.text
    assert len(calls) == 1
    with engine.connect() as conn:
        assert (
            conn.scalar(
                text("SELECT balance FROM credit_accounts WHERE user_id=:user"), {"user": user_id}
            )
            == 0
        )
        assert conn.scalar(text("SELECT count(*) FROM credit_ledger")) == ledger_count
        assert conn.scalar(text("SELECT count(*) FROM billing_operations")) == 0
        assert conn.scalar(text("SELECT count(*) FROM billing_attempts")) == 0
    assert all(
        not provider._require_billing for provider in app.state.model_provider._providers.values()
    )
