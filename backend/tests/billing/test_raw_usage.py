import asyncio
import json

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.providers.openai import OpenAIProvider

from qunxue_api.adapters.model.routing import ModelEndpoint, ModelRouteExecutor
from qunxue_api.adapters.research_agent.pydantic_runner import _RetryingOpenAIChatModel


@pytest.mark.parametrize("missing", [False, True])
@pytest.mark.parametrize("reasoning", [0, 20])
@pytest.mark.parametrize("stream", [False, True])
def test_real_sdk_preserves_usage_including_cached_and_reasoning_subset(reasoning, stream, missing):
    """A swallowed genai-prices TypeError must never erase billable usage."""
    usage = {
        "prompt_tokens": 100,
        "completion_tokens": 30,
        "total_tokens": 130,
        "prompt_tokens_details": {"cached_tokens": 40},
        "completion_tokens_details": {"reasoning_tokens": reasoning},
    }

    if missing:
        usage = None

    def reply(request):
        body = json.loads(request.content)
        if body.get("stream"):
            chunks = [
                {
                    "id": "synthetic",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "test-model",
                    "choices": [{"index": 0, "delta": {"content": "OK"}, "finish_reason": None}],
                },
                {
                    "id": "synthetic",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "test-model",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                },
                {
                    "id": "synthetic",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "test-model",
                    "choices": [],
                    "usage": usage,
                },
            ]
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content="".join("data: " + json.dumps(c) + "\n\n" for c in chunks)
                + "data: [DONE]\n\n",
            )
        return httpx.Response(
            200,
            json={
                "id": "synthetic",
                "object": "chat.completion",
                "created": 1,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "OK"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": usage,
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as http:
            client = AsyncOpenAI(
                base_url="https://synthetic.test/v1",
                api_key="synthetic",
                http_client=http,
                max_retries=0,
            )
            model = _RetryingOpenAIChatModel(
                "test-model",
                provider=OpenAIProvider(openai_client=client),
                route_executor=ModelRouteExecutor(
                    endpoints=(
                        ModelEndpoint(
                            "primary", "https://synthetic.test/v1", "test-model", None, 1
                        ),
                    )
                ),
            )
            agent = Agent(model)
            if stream:
                async with agent.run_stream("synthetic") as result:
                    await result.get_output()
                    return result.usage
            result = await agent.run("synthetic")
            return result.usage

    if missing:
        from qunxue_api.adapters.model.token_usage import UnknownTokenUsage

        with pytest.raises(UnknownTokenUsage):
            asyncio.run(run())
        return
    observed = asyncio.run(run())
    assert (observed.input_tokens, observed.output_tokens, observed.cache_read_tokens) == (
        100,
        30,
        40,
    )


@pytest.mark.parametrize(
    "raw",
    [
        None,
        {},
        {"prompt_tokens": 1},
        {"prompt_tokens": True, "completion_tokens": 1},
        {"prompt_tokens": -1, "completion_tokens": 1},
        {"prompt_tokens": 3, "completion_tokens": 2, "prompt_tokens_details": {"cached_tokens": 4}},
        {
            "prompt_tokens": 3,
            "completion_tokens": 2,
            "completion_tokens_details": {"reasoning_tokens": 3},
        },
    ],
)
def test_unknown_or_contradictory_raw_usage_fails_closed(raw):
    from qunxue_api.adapters.model.token_usage import UnknownTokenUsage, normalized_usage

    with pytest.raises(UnknownTokenUsage):
        normalized_usage(raw)


def test_response_usage_and_cache_write_are_disjoint_input_subsets():
    from qunxue_api.adapters.model.token_usage import normalized_usage

    observed = normalized_usage(
        {
            "input_tokens": 1000,
            "output_tokens": 100,
            "input_tokens_details": {"cached_tokens": 200, "cache_write_tokens": 300},
            "output_tokens_details": {"reasoning_tokens": 50},
        }
    )
    assert (
        observed.input_tokens,
        observed.output_tokens,
        observed.cache_read_tokens,
        observed.cache_write_tokens,
    ) == (1000, 100, 200, 300)


@pytest.mark.parametrize("details", [False, 0, [], ""])
def test_invalid_falsy_details_are_not_zero_usage(details):
    from qunxue_api.adapters.model.token_usage import UnknownTokenUsage, normalized_usage

    with pytest.raises(UnknownTokenUsage):
        normalized_usage(
            {"prompt_tokens": 10, "completion_tokens": 1, "prompt_tokens_details": details}
        )


def test_deepseek_hit_miss_are_provider_input_partition():
    from qunxue_api.adapters.model.token_usage import normalized_usage

    usage = normalized_usage(
        {
            "prompt_tokens": 100,
            "completion_tokens": 30,
            "prompt_cache_hit_tokens": 40,
            "prompt_cache_miss_tokens": 60,
        }
    )
    assert (usage.input_tokens, usage.cache_read_tokens, usage.cache_write_tokens) == (100, 40, 0)


@pytest.mark.parametrize("miss,cached", [(59, 40), (60, 39)])
def test_deepseek_partition_and_nested_cache_disagreement_are_unknown(miss, cached):
    from qunxue_api.adapters.model.token_usage import UnknownTokenUsage, normalized_usage

    with pytest.raises(UnknownTokenUsage):
        normalized_usage(
            {
                "prompt_tokens": 100,
                "completion_tokens": 30,
                "prompt_cache_hit_tokens": 40,
                "prompt_cache_miss_tokens": miss,
                "prompt_tokens_details": {"cached_tokens": cached},
            }
        )
