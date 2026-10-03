# ruff: noqa: F811
import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.providers.openai import OpenAIProvider
from test_durable_billing import wallet  # noqa: F401

from qunxue_api.adapters.model import metering
from qunxue_api.adapters.model.routing import ModelEndpoint, ModelRouteExecutor
from qunxue_api.adapters.research_agent.pydantic_runner import _RetryingOpenAIChatModel


def test_actual_http_attempts_include_failed_primary_and_real_fallback_cost(wallet):
    runtime, engine = wallet
    calls = []

    def reply(request):
        body = json.loads(request.content)
        calls.append(body["model"])
        if body["model"] == "gpt-6.1-sol":
            return httpx.Response(503, json={"error": {"message": "synthetic unavailable"}})
        return httpx.Response(
            200,
            json={
                "id": "synthetic",
                "object": "chat.completion",
                "created": 1,
                "model": "gpt-6-luna",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "OK"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 1000,
                    "completion_tokens": 100,
                    "total_tokens": 1100,
                    "prompt_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                },
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as http:
            provider = OpenAIProvider(
                openai_client=AsyncOpenAI(
                    base_url="https://synthetic.test/v1",
                    api_key="synthetic",
                    http_client=http,
                    max_retries=0,
                )
            )
            model = _RetryingOpenAIChatModel(
                "gpt-6.1-sol",
                provider=provider,
                settings={"max_tokens": 100},
                require_billing=True,
                fallback_models={
                    "fallback-1": metering.MeteredOpenAIChatModel(
                        "gpt-6-luna", provider=provider, settings={"max_tokens": 100}
                    )
                },
                route_executor=ModelRouteExecutor(
                    endpoints=(
                        ModelEndpoint(
                            "primary", "https://synthetic.test/v1", "gpt-6.1-sol", None, 1
                        ),
                        ModelEndpoint(
                            "fallback-1", "https://synthetic.test/v1", "gpt-6-luna", None, 1
                        ),
                    )
                ),
            )
            with metering.OperationScope(
                runtime, user_id="user", run_id=str(uuid4()), fingerprint="synthetic"
            ) as scope:
                result = await Agent(model).run("synthetic")
                scope.finish("success")
                assert result.output == "OK"

    asyncio.run(run())
    assert calls == ["gpt-6.1-sol", "gpt-6-luna"]
    with engine.connect() as c:
        from sqlalchemy import text

        rows = c.execute(
            text(
                "SELECT endpoint_id,requested_model,returned_model,usage_state,"
                "reference_cost_pico FROM billing_attempts ORDER BY created_at"
            )
        ).all()
        assert rows == [
            ("primary", "gpt-6.1-sol", None, "unknown", None),
            ("fallback-1", "gpt-6-luna", "gpt-6-luna", "known", 150000000),
        ]
        assert c.scalar(text("SELECT balance FROM credit_accounts WHERE user_id='user'")) == 9999


def test_required_meter_refuses_http_when_no_operation_context():
    calls = []

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: calls.append(request))
        ) as http:
            model = metering.MeteredOpenAIChatModel(
                "gpt-6.1-sol",
                require_billing=True,
                provider=OpenAIProvider(
                    openai_client=AsyncOpenAI(api_key="synthetic", http_client=http, max_retries=0)
                ),
                settings={"max_tokens": 100},
            )
            with pytest.raises(metering.BillingContextMissing):
                await Agent(model).run("synthetic")

    asyncio.run(run())
    assert calls == []
