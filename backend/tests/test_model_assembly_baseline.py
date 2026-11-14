import json
from collections import Counter
from contextlib import closing
from functools import partial

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import AsyncOpenAI
from sqlalchemy import text
from test_agent_memory import project, register, save, seed_learning_source
from test_memory_overview import overview
from test_shared_knowledge_api import create_library, upload

from qunxue_api.adapters.model.metering import current_operation
from qunxue_api.adapters.research_agent import course_knowledge, memory_extractor, memory_overview
from qunxue_api.bootstrap import create_app
from qunxue_api.settings import Settings

PHASE_CAPS = {"memory_overview": 900, "memory_learning": 1500, "course_knowledge": 3000}


@pytest.fixture
def assembled_model_app(plain_client, monkeypatch, configuration):
    # Reject every HTTP call except the adapter-specific MockTransports.
    def reject_network(*args):
        pytest.fail("Unexpected HTTP request outside the injected transport")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", reject_network)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", reject_network)
    policies = (
        {"memory_overview": "user", "course_knowledge": "operator"}
        if configuration == "mixed-policy"
        else dict.fromkeys(PHASE_CAPS, "operator")
    )
    database = plain_client.app.state.database
    app = create_app(
        settings=Settings(
            _env_file=None,
            database_url=plain_client.app.state.settings.database_url,
            runtime_mode="base",
            model_base_url="https://r11.invalid/v1",
            model_api_key="synthetic",
            model_name="test-model",
            model_fallbacks=[],
            billing_model_aliases={"test-model": "gpt-6-luna"},
            billing_phase_policies=policies,
            billing_max_attempt_usd_micro=100_000,
            billing_max_operation_usd_micro=100_000,
            billing_daily_budget_usd_micro=1 if configuration == "budget-exhausted" else None,
        ),
        database=database,
        require_email_verification=False,
    )
    # Drive the real workers deterministically instead of waiting for the schedulers.
    with closing(TestClient(app)) as client:
        yield client


@pytest.mark.parametrize(
    "configuration", ["operator", "budget-exhausted", "mixed-policy"]
)
def test_bootstrap_operator_funded_capabilities(assembled_model_app, monkeypatch, configuration):
    client = assembled_model_app
    app = client.app
    database = app.state.database
    user_id = register(client)
    task_id = project(client)
    assert save(client, task_id=task_id).status_code == 201
    _, source_id = seed_learning_source(client, user_id)
    library = create_library(client)
    document = upload(client, library["id"])
    assert document["knowledge_status"] == "queued"

    with database.engine.begin() as connection:
        connection.execute(
            text("UPDATE credit_accounts SET balance=0 WHERE user_id=:user"), {"user": user_id}
        )
        ledger_count = connection.scalar(text("SELECT count(*) FROM credit_ledger"))

    replies = {
        "memory_overview": "你偏好用中文简洁回答。",
        "memory_learning": {
            "memories": [
                {
                    "scope": "user",
                    "key": "learned_language",
                    "content": "中文简洁回答",
                    "source_message_id": str(source_id),
                    "source_quote": "以后请用中文简洁回答",
                }
            ],
        },
        "course_knowledge": {
            "summary": "课堂使用 QX-A17 标记。",
            "topics": [
                {
                    "title": "课堂标记",
                    "summary": "统一使用 QX-A17。",
                    "segment_ids": ["0"],
                }
            ],
            "relations": [],
        },
    }
    calls = Counter()

    def respond(request, *, phase):
        calls[phase] += 1
        assert request.method == "POST"
        assert str(request.url) == "https://r11.invalid/v1/chat/completions"
        body = json.loads(request.content)
        assert body["model"] == "test-model"
        assert body["max_completion_tokens"] == PHASE_CAPS[phase]
        assert current_operation(required=True).exempt
        output = replies[phase]
        if isinstance(output, str):
            message = {"role": "assistant", "content": output}
        else:
            message = {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "output",
                        "type": "function",
                        "function": {
                            "name": body["tools"][0]["function"]["name"],
                            "arguments": json.dumps(output),
                        },
                    }
                ],
            }
        return httpx.Response(
            200,
            json={
                "id": phase,
                "object": "chat.completion",
                "created": 1,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop" if isinstance(output, str) else "tool_calls",
                        "message": message,
                    }
                ],
                "usage": {
                    "prompt_tokens": 80,
                    "completion_tokens": 20,
                    "total_tokens": 100,
                    "prompt_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                },
            },
        )

    def model_client(*, transport, **kwargs):
        return AsyncOpenAI(
            **kwargs, http_client=httpx.AsyncClient(transport=transport, trust_env=False)
        )

    for module, phase in (
        (memory_overview, "memory_overview"),
        (memory_extractor, "memory_learning"),
        (course_knowledge, "course_knowledge"),
    ):
        transport = httpx.MockTransport(partial(respond, phase=phase))
        monkeypatch.setattr(
            module,
            "AsyncOpenAI",
            partial(model_client, transport=transport),
        )

    result = overview(client, task_id)
    learned = app.state.memory_worker.run_once()
    assert app.state.course_organization_worker.run_once()
    course = client.get(f"/api/shared-knowledge-bases/{library['id']}").json()["documents"][0]
    enabled_phases = {
        "operator": {"memory_overview", "memory_learning", "course_knowledge"},
        "mixed-policy": {"course_knowledge"},
    }.get(configuration, set())
    assert {phase: calls[phase] for phase in PHASE_CAPS} == {
        phase: int(phase in enabled_phases) for phase in PHASE_CAPS
    }
    if "memory_overview" in enabled_phases:
        assert result.status_code == 200, result.text
        assert result.json()["summary"] == replies["memory_overview"]
    else:
        assert result.status_code == 503
    assert learned == ("memory_learning" in enabled_phases or configuration == "budget-exhausted")
    items = client.get("/api/memories").json()["items"]
    assert any(item["source_message_id"] == str(source_id) for item in items) == (
        "memory_learning" in enabled_phases
    )
    if "course_knowledge" in enabled_phases:
        assert course["knowledge_status"] == "ready", course
        assert course["knowledge"]["summary"] == replies["course_knowledge"]["summary"]
    else:
        assert course["knowledge_status"] == "failed"

    with database.engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT balance FROM credit_accounts WHERE user_id=:user"), {"user": user_id}
            )
            == 0
        )
        assert connection.scalar(text("SELECT count(*) FROM credit_ledger")) == ledger_count
        operations = connection.execute(
            text(
                "SELECT user_id, exempt, hold_points, charged_points, status "
                "FROM billing_operations"
            )
        )
        expected = (
            [(user_id, 1, 0, 0, "error")] * len(PHASE_CAPS)
            if configuration == "budget-exhausted"
            else [(user_id, 1, 0, 0, "success")] * len(enabled_phases)
        )
        assert operations.all() == expected
        receipts = connection.execute(
            text("SELECT provider_response_id, output_limit, usage_state FROM billing_attempts")
        )
        assert set(receipts) == {(phase, PHASE_CAPS[phase], "known") for phase in enabled_phases}
