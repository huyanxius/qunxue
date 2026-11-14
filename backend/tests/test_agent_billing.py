import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import AsyncOpenAI
from sqlalchemy import text

from qunxue_api.adapters.research_agent import pydantic_runner
from qunxue_api.bootstrap import create_app
from qunxue_api.settings import Settings


@pytest.fixture
def model_requests(monkeypatch):
    def reject_network(*args):
        pytest.fail("Unexpected HTTP request outside MockTransport")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", reject_network)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", reject_network)
    requests = []

    def install(*, before_reply=None, usage_tokens=(80, 20)):
        def respond(request):
            assert request.url.host in {"r12.invalid", "api.deepseek.com"}
            assert request.url.path == "/v1/chat/completions"
            payload = json.loads(request.content)
            requests.append(payload)
            if before_reply is not None:
                before_reply(payload)
            receipt = {
                "id": str(uuid4()),
                "created": 1,
                "model": payload["model"],
            }
            input_tokens, output_tokens = usage_tokens
            usage = {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            }
            if payload["model"] == "deepseek-flash":
                usage.update(prompt_cache_hit_tokens=0, prompt_cache_miss_tokens=input_tokens)
            if payload["model"] == "test-model":
                usage["prompt_tokens_details"] = {"cached_tokens": 0, "cache_write_tokens": 0}
            if payload["stream"]:
                chunks = [
                    {
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"role": "assistant", "content": "正常回答"},
                                "finish_reason": None,
                            }
                        ]
                    },
                    {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
                    {"choices": [], "usage": usage},
                ]
                return httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    content="".join(
                        "data: "
                        + json.dumps(dict(receipt, object="chat.completion.chunk", **chunk))
                        + "\n\n"
                        for chunk in chunks
                    ) + "data: [DONE]\n\n",
                )

            research = "人口流动" in payload["messages"][-1]["content"]
            decision = (
                {
                    "request_type": "research",
                    "title": "人口流动",
                    "steps": ["界定问题", "查找材料", "比较证据"],
                }
                if research
                else {"request_type": "conversation", "title": "日常问候"}
            )
            return httpx.Response(
                200,
                json=dict(
                    receipt,
                    object="chat.completion",
                    usage=usage,
                    choices=[
                        {
                            "index": 0,
                            "finish_reason": "tool_calls",
                            "message": {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "id": "decision",
                                        "type": "function",
                                        "function": {
                                            "name": payload["tools"][0]["function"]["name"],
                                            "arguments": json.dumps(decision),
                                        },
                                    }
                                ],
                            },
                        }
                    ],
                ),
            )

        def model_client(**kwargs):
            return AsyncOpenAI(
                **kwargs,
                http_client=httpx.AsyncClient(
                    transport=httpx.MockTransport(respond), trust_env=False
                ),
            )

        monkeypatch.setattr(pydantic_runner, "AsyncOpenAI", model_client)
        return requests

    return install


@pytest.fixture
def make_agent(unstarted_client):
    database = unstarted_client.app.state.database

    def make(**overrides):
        config = dict(
            database_url=unstarted_client.app.state.settings.database_url,
            runtime_mode="base",
            model_base_url="https://r12.invalid/v1",
            model_api_key="synthetic",
            model_name="test-model",
            model_fallbacks=[],
            billing_model_aliases={"test-model": "gpt-6-luna"},
            account_signing_key="synthetic-signing-key",
            billing_max_attempt_usd_micro=200_000,
            billing_max_operation_usd_micro=400_000,
            billing_daily_budget_usd_micro=1_000_000,
            billing_agent_daily_budget_usd_micro=500_000,
            billing_agent_user_daily_budget_usd_micro=500_000,
        )
        return create_app(
            settings=Settings(_env_file=None, **(config | overrides)),
            database=database,
            require_email_verification=False,
        )

    return make


def register(client, email):
    result = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": email, "password": "password-123"},
    )
    assert result.status_code == 201, result.text
    user_id = result.json()["user"]["user_id"]
    return user_id


def set_balance(client, user_id, points):
    with client.app.state.database.engine.begin() as conn:
        conn.execute(
            text("UPDATE credit_accounts SET balance=:points WHERE user_id=:user"),
            {"points": points, "user": user_id},
        )


def turn(client, key=None, **payload):
    response = client.post(
        "/api/agent/turns",
        headers={"Idempotency-Key": key or str(uuid4())},
        json={"message": "你好", **payload},
    )
    assert response.status_code == 200, response.text
    return response.text


def event_data(stream, event):
    data = stream.split(f"event: {event}\n", 1)[1].splitlines()[0]
    return json.loads(data.removeprefix("data: "))



def wallet(client):
    with client.app.state.database.engine.connect() as conn:
        balances = conn.scalars(text("SELECT balance FROM credit_accounts ORDER BY user_id")).all()
        ledger = conn.scalar(text("SELECT count(*) FROM credit_ledger"))
        return balances, ledger


def billing_rows(client):
    with client.app.state.database.engine.connect() as conn:
        operations = conn.execute(
            text("SELECT exempt, hold_points, charged_points, status FROM billing_operations")
        ).all()
        attempts = conn.execute(
            text(
                "SELECT outcome, usage_state, reference_cost_pico FROM billing_attempts "
                "ORDER BY created_at, attempt_id"
            )
        ).all()
        return operations, attempts


def product_settings(client, **overrides):
    values = dict(
        _env_file=None,
        database_url=client.app.state.settings.database_url,
        runtime_mode="base",
        release_revision="test-release",
        model_base_url="https://r12.invalid/v1",
        model_api_key="synthetic",
        model_name="gpt-5.6-sol",
        account_signing_key="synthetic-signing-key",
    )
    return Settings(**(values | overrides))


def test_registered_member_can_chat_and_replay_without_legacy_billing_env(
    unstarted_client, model_requests
):
    requests = model_requests(usage_tokens=(900, 90))
    app = create_app(
        settings=product_settings(unstarted_client),
        database=unstarted_client.app.state.database,
        require_email_verification=False,
    )
    with TestClient(app) as client:
        user_id = register(client, "member-paid@example.com")
        assert client.get("/api/account/credits").json()["balance"] == 1000
        key = str(uuid4())
        result = turn(client, key)
        assert "event: turn_completed" in result, result
        assert "正常回答" in result
        assert "event: turn_completed" in turn(client, key)
        assert len(requests) == 2
        credits = client.get("/api/account/credits").json()
        assert credits["balance"] == 925
        assert [entry["points"] for entry in credits["entries"]] == [-75]
        assert "operations" not in credits and "pricing" not in credits

        set_balance(client, user_id, 0)
        stopped = turn(client)
        assert event_data(stopped, "turn_failed")["code"] == "credits_depleted"
        assert "event: turn_completed" not in stopped
        conversation_id = event_data(stopped, "turn_started")["conversation_id"]
        recovered = client.get(f"/api/agent/conversations/{conversation_id}").json()
        run, = recovered["unfinished_runs"]
        assert run["credits_depleted"] is True
        assert len(requests) == 2


def test_low_balance_uses_affordable_fallback_and_finishes_ten_turns(
    unstarted_client, model_requests
):
    requests = model_requests(usage_tokens=(900, 90))
    settings = product_settings(
        unstarted_client,
        model_fallbacks=[dict(
            base_url="https://api.deepseek.com/v1", model="deepseek-flash", api_key="synthetic"
        )],
    )
    app = create_app(
        settings=settings,
        database=unstarted_client.app.state.database,
        require_email_verification=False,
    )
    with TestClient(app) as client:
        register(client, "member-ten@example.com")
        conversation_id = None
        for _ in range(10):
            result = turn(client, conversation_id=conversation_id)
            assert "event: turn_completed" in result, result
            conversation = event_data(result, "turn_completed")["conversation"]
            conversation_id = conversation["conversation_id"]
        assert len(requests) == 20
        assert {request["model"] for request in requests} == {"gpt-5.6-sol", "deepseek-flash"}
        credits = client.get("/api/account/credits").json()
        assert 0 < credits["balance"] < 1000
        assert len(credits["entries"]) == 10


def test_unpriced_release_cannot_report_ready(unstarted_client):
    settings = product_settings(unstarted_client, model_name="unpriced-product-model")
    with pytest.raises(ValueError, match="unpriced-product-model"):
        app = create_app(settings=settings, database=unstarted_client.app.state.database)
        with TestClient(app):
            pass


def test_provisioned_admin_usage_is_recorded_without_charging(make_agent, model_requests):
    requests = model_requests()
    app = make_agent(
        account_initial_admin_email="admin@example.com",
        account_initial_admin_password="synthetic-admin-passphrase",
    )
    with TestClient(app) as client:
        login = client.post(
            "/api/session/login",
            headers={"Idempotency-Key": str(uuid4())},
            json={"email": "admin@example.com", "password": "synthetic-admin-passphrase"},
        )
        assert login.status_code == 200, login.text
        assert client.get("/api/account/credits").json()["is_unlimited"]
        before = wallet(client)
        key = str(uuid4())
        result = turn(client, key)
        assert "event: turn_completed" in result and "正常回答" in result, result
        assert "event: turn_completed" in turn(client, key)
        assert len(requests) == 2
        assert wallet(client) == before
        assert billing_rows(client) == (
            [(1, 0, 0, "success")],
            [("success", "known", 18_000_000)] * 2,
        )


def test_old_completed_turn_replays_even_if_member_has_no_credit(
    unstarted_client, make_agent, model_requests
):
    requests = model_requests()
    user_id = register(unstarted_client, "legacy@example.com")
    key = str(uuid4())
    assert "event: turn_completed" in turn(unstarted_client, key)
    set_balance(unstarted_client, user_id, 0)
    with TestClient(make_agent()) as client:
        client.cookies.update(unstarted_client.cookies)
        assert "event: turn_completed" in turn(client, key)
        assert "credits_depleted" in turn(client)
        assert requests == []
        assert billing_rows(client) == ([], [])


@pytest.mark.parametrize(
    "setting",
    [
        "billing_daily_budget_usd_micro",
        "billing_agent_daily_budget_usd_micro",
        "billing_agent_user_daily_budget_usd_micro",
    ],
)
def test_budget_exhaustion_stops_before_http_and_can_retry_same_run(
    make_agent, model_requests, setting
):
    requests = model_requests()
    key = str(uuid4())
    with TestClient(make_agent(**{setting: 1})) as limited:
        register(limited, "limited@example.com")
        before = wallet(limited)
        result = turn(limited, key)
        assert "capability_unavailable" in result, (len(requests), result)
        assert requests == []
        assert billing_rows(limited) == ([(0, 0, 0, "error")], [])

    with TestClient(make_agent()) as restored:
        restored.cookies.update(limited.cookies)
        result = turn(restored, key)
        assert "event: turn_completed" in result, result
        assert len(requests) == 2
        assert wallet(restored)[0] == before[0]
        assert billing_rows(restored) == (
            [(0, 0, 0, "success")],
            [("success", "known", 18_000_000)] * 2,
        )


@pytest.mark.parametrize(
    "setting",
    ["billing_daily_budget_usd_micro", "billing_agent_daily_budget_usd_micro",
     "billing_agent_user_daily_budget_usd_micro"],
)
def test_concurrent_agent_turns_reserve_before_http(make_agent, model_requests, setting):
    same_user = setting == "billing_agent_user_daily_budget_usd_micro"
    entered, release = Event(), Event()

    def before_reply(_payload):
        if not entered.is_set():
            entered.set()
            assert release.wait(timeout=10), "concurrent turn did not finish"

    requests = model_requests(before_reply=before_reply)
    app = make_agent(**{setting: 4000})
    payload = {"message": "研究人口流动", "mode": "deep_research"}
    with TestClient(app) as first, TestClient(app) as second, ThreadPoolExecutor(1) as pool:
        first_user_id = register(first, "first@example.com")
        if same_user:
            # Use an existing balance that covers both holds. This case should
            # be stopped by the per-user spend cap rather than by the wallet.
            set_balance(first, first_user_id, 6000)
            second.cookies.update(first.cookies)
        else:
            register(second, "second@example.com")
        before = wallet(first)
        retry_key = str(uuid4())
        admitted = pool.submit(turn, first, **payload)
        try:
            assert entered.wait(timeout=5), "first request did not reach the transport"
            in_flight = billing_rows(first)
            rejected = turn(second, retry_key, **payload)
        finally:
            release.set()
        finished = admitted.result(timeout=10)
        assert "event: research_waiting" in finished, finished
        assert event_data(rejected, "turn_failed")["code"] == "capability_unavailable"
        expected_hold = 2800 if same_user else 1000
        assert in_flight == ([(0, expected_hold, 0, "active")], [("in_flight", "unknown", None)])
        assert len(requests) == 1
        assert wallet(first)[0] == before[0]
        operations, attempts = billing_rows(first)
        assert sorted(operations) == [(0, 0, 0, "error"), (0, 0, 0, "paused")]
        assert attempts == [("success", "known", 18_000_000)]
        assert "event: research_waiting" in turn(second, retry_key, **payload)
        assert len(requests) == 2
        assert billing_rows(second) == (
            [(0, 0, 0, "paused")] * 2,
            [("success", "known", 18_000_000)] * 2,
        )
        assert wallet(second)[0] == before[0]


def test_retry_after_provider_error_keeps_attempt_history(make_agent, model_requests):
    failed = False

    def before_reply(payload):
        nonlocal failed
        if payload["stream"] and not failed:
            failed = True
            raise httpx.ReadTimeout("synthetic response timeout")

    requests = model_requests(before_reply=before_reply, usage_tokens=(4_000, 2_000))
    with TestClient(make_agent()) as client:
        register(client, "retry@example.com")
        before = wallet(client)
        key = str(uuid4())
        assert "event: turn_failed" in turn(client, key)
        assert billing_rows(client) == (
            [(0, 0, 0, "error")],
            [("success", "known", 1_400_000_000), ("error", "unknown", None)],
        )
        assert "event: turn_completed" in turn(client, key)
        assert "event: turn_completed" in turn(client, key)
        assert len(requests) == 4
        assert billing_rows(client) == (
            [(0, 0, 19, "success")],
            [
                ("success", "known", 1_400_000_000),
                ("error", "unknown", None),
                ("success", "known", 1_400_000_000),
                ("success", "known", 1_400_000_000),
            ],
        )
        assert wallet(client)[0] == [before[0][0] - 19]


def test_late_receipt_does_not_settle_the_reclaimed_run(make_agent, model_requests):
    entered = [Event(), Event()]
    release = [Event(), Event()]
    gates = iter(zip(entered, release, strict=True))

    def before_reply(_payload):
        ready, reply = next(gates)
        ready.set()
        assert reply.wait(timeout=10), "response gate timed out"

    requests = model_requests(before_reply=before_reply)
    app = make_agent()
    key = str(uuid4())
    payload = {"message": "研究人口流动", "mode": "deep_research"}
    with TestClient(app) as first, TestClient(app) as second, ThreadPoolExecutor(2) as pool:
        register(first, "lease@example.com")
        second.cookies.update(first.cookies)
        before = wallet(first)
        original = pool.submit(turn, first, key, **payload)
        try:
            assert entered[0].wait(timeout=5)
            with app.state.database.engine.begin() as conn:
                conn.execute(
                    text("UPDATE agent_runs SET lease_expires_at='2000-01-01' "
                         "WHERE idempotency_key=:key"),
                    {"key": key},
                )
            reclaimed = pool.submit(turn, second, key, **payload)
            assert entered[1].wait(timeout=5)
            release[0].set()
            assert "event: turn_interrupted" in original.result(timeout=5)
            assert billing_rows(first) == (
                [(0, 1000, 0, "active")],
                [("success", "known", 18_000_000), ("in_flight", "unknown", None)],
            )
        finally:
            for signal in release:
                signal.set()
        assert "event: research_waiting" in reclaimed.result(timeout=5)
        assert len(requests) == 2
        assert billing_rows(second) == (
            [(0, 0, 0, "paused")],
            [("success", "known", 18_000_000)] * 2,
        )
        with app.state.database.engine.connect() as conn:
            assert conn.scalars(
                text("SELECT billable FROM billing_attempts ORDER BY created_at, attempt_id")
            ).all() == [0, 1]
        assert wallet(second)[0] == before[0]
