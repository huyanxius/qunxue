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

    def install(*, before_reply=None):
        def respond(request):
            assert str(request.url) == "https://r12.invalid/v1/chat/completions"
            payload = json.loads(request.content)
            requests.append(payload)
            if before_reply is not None:
                before_reply(payload)
            receipt = {
                "id": str(uuid4()),
                "created": 1,
                "model": "test-model",
            }
            usage = {
                "prompt_tokens": 80,
                "completion_tokens": 20,
                "total_tokens": 100,
                "prompt_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
            }
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
            billing_price_version="r12-test",
            billing_credits_per_usd=10_000,
            billing_model_aliases={"test-model": "gpt-6-luna"},
            billing_phase_policies={"agent_turn": "operator"},
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
    with client.app.state.database.engine.begin() as conn:
        conn.execute(
            text("UPDATE credit_accounts SET balance=0 WHERE user_id=:user"), {"user": user_id}
        )
    return user_id


def turn(client, key=None, **payload):
    response = client.post(
        "/api/agent/turns",
        headers={"Idempotency-Key": key or str(uuid4())},
        json={"message": "你好", **payload},
    )
    assert response.status_code == 200, response.text
    return response.text


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


def test_main_agent_records_operator_cost_at_zero_balance_and_replays(make_agent, model_requests):
    requests = model_requests()
    app = make_agent(
        account_initial_admin_email="admin@example.com",
        account_initial_admin_password="synthetic-admin-passphrase",
    )
    with TestClient(app) as client:
        register(client, "free@example.com")
        before = wallet(client)
        key = str(uuid4())
        result = turn(client, key)
        assert "event: turn_completed" in result and "正常回答" in result, result
        assert len(requests) == 2
        assert "event: turn_completed" in turn(client, key)
        assert len(requests) == 2
        assert wallet(client) == before
        assert billing_rows(client) == (
            [(1, 0, 0, "success")],
            [("success", "known", 18_000_000)] * 2,
        )
        credits = client.get("/api/account/credits")
        assert credits.status_code == 200
        operation, = credits.json()["operations"]
        assert operation["exempt"] and operation["points_charged"] == 0
        for attempt in operation["attempts"]:
            assert attempt["price_snapshot"]["version"] == "r12-test"
            assert "agent_lease_token" not in attempt["price_snapshot"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"billing_phase_policies": {}},
        {"billing_phase_policies": {"agent_turn": "user"}},
        {"billing_agent_user_daily_budget_usd_micro": None},
    ],
)
def test_disabled_billing_blocks_new_http_and_replays_old_turns(
    unstarted_client, make_agent, model_requests, overrides
):
    requests = model_requests()
    register(unstarted_client, "legacy@example.com")
    key = str(uuid4())
    assert "event: turn_completed" in turn(unstarted_client, key)
    with TestClient(make_agent(**overrides)) as client:
        client.cookies.update(unstarted_client.cookies)
        assert "event: turn_completed" in turn(client, key)
        result = turn(client)
        assert "billing_not_configured" in result, (len(requests), result)
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
        assert "billing_budget_exceeded" in result, (len(requests), result)
        assert requests == []
        assert billing_rows(limited) == ([(1, 0, 0, "error")], [])

    with TestClient(make_agent()) as restored:
        restored.cookies.update(limited.cookies)
        result = turn(restored, key)
        assert "event: turn_completed" in result, result
        assert len(requests) == 2
        assert wallet(restored) == before
        assert billing_rows(restored) == (
            [(1, 0, 0, "success")],
            [("success", "known", 18_000_000)] * 2,
        )


@pytest.mark.parametrize(
    "setting,same_user",
    [
        ("billing_daily_budget_usd_micro", False),
        ("billing_agent_daily_budget_usd_micro", False),
        ("billing_agent_user_daily_budget_usd_micro", True),
    ],
)
def test_concurrent_agent_turns_reserve_before_http(make_agent, model_requests, setting, same_user):
    entered, release = Event(), Event()

    def before_reply(_payload):
        if not entered.is_set():
            entered.set()
            assert release.wait(timeout=10), "concurrent turn did not finish"

    requests = model_requests(before_reply=before_reply)
    app = make_agent(**{setting: 4000})
    payload = {"message": "研究人口流动", "mode": "deep_research"}
    with TestClient(app) as first, TestClient(app) as second, ThreadPoolExecutor(1) as pool:
        register(first, "first@example.com")
        if same_user:
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
        assert "billing_budget_exceeded" in rejected, (
            len(requests), [len(json.dumps(request).encode()) for request in requests], rejected
        )
        assert in_flight == ([(1, 0, 0, "active")], [("in_flight", "unknown", None)])
        assert len(requests) == 1
        assert wallet(first) == before
        operations, attempts = billing_rows(first)
        assert sorted(operations) == [(1, 0, 0, "error"), (1, 0, 0, "paused")]
        assert attempts == [("success", "known", 18_000_000)]
        assert "event: research_waiting" in turn(second, retry_key, **payload)
        assert len(requests) == 2
        assert billing_rows(second) == (
            [(1, 0, 0, "paused")] * 2,
            [("success", "known", 18_000_000)] * 2,
        )
        assert wallet(second) == before


def test_retry_after_provider_error_keeps_attempt_history(make_agent, model_requests):
    failed = False

    def before_reply(payload):
        nonlocal failed
        if payload["stream"] and not failed:
            failed = True
            raise httpx.ReadTimeout("synthetic response timeout")

    requests = model_requests(before_reply=before_reply)
    with TestClient(make_agent()) as client:
        register(client, "retry@example.com")
        before = wallet(client)
        key = str(uuid4())
        assert "event: turn_failed" in turn(client, key)
        assert billing_rows(client) == (
            [(1, 0, 0, "error")],
            [("success", "known", 18_000_000), ("error", "unknown", None)],
        )
        assert "event: turn_completed" in turn(client, key)
        assert "event: turn_completed" in turn(client, key)
        assert len(requests) == 4
        assert billing_rows(client) == (
            [(1, 0, 0, "success")],
            [
                ("success", "known", 18_000_000),
                ("error", "unknown", None),
                ("success", "known", 18_000_000),
                ("success", "known", 18_000_000),
            ],
        )
        assert wallet(client) == before


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
                [(1, 0, 0, "active")],
                [("success", "known", 18_000_000), ("in_flight", "unknown", None)],
            )
        finally:
            for signal in release:
                signal.set()
        assert "event: research_waiting" in reclaimed.result(timeout=5)
        assert len(requests) == 2
        assert billing_rows(second) == (
            [(1, 0, 0, "paused")],
            [("success", "known", 18_000_000)] * 2,
        )
        with app.state.database.engine.connect() as conn:
            assert conn.scalars(
                text("SELECT billable FROM billing_attempts ORDER BY created_at, attempt_id")
            ).all() == [0, 1]
        assert wallet(second) == before
