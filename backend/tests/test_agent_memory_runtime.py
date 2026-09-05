import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from test_agent_memory import register, save, seed_learning_source

from qunxue_api.adapters.research_agent.memory_tools import AgentMemoryTools
from qunxue_api.adapters.research_agent.pydantic_runner import PydanticAIKnowledgeRunner


def test_real_runner_injects_memory_and_executes_explicit_write(plain_client):
    client = plain_client
    user_id = UUID(register(client))
    assert save(client).status_code == 201
    tools = SimpleNamespace(
        memory=AgentMemoryTools(
            client.app.state.memory_service_scope,
            user_id=user_id,
            task_id=None,
            conversation_id=uuid4(),
            run_id=uuid4(),
            prompt="记住：先给结论",
        ),
        release=SimpleNamespace(knowledge_release_id="memory-test"),
        evidence={},
        selected_evidence_ids=(),
        research_map_enabled=False,
        research_map={},
        web_search_enabled=False,
    )
    observed = []

    def model(messages, info):
        observed.append(info.instructions)
        if len(observed) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "change_memory",
                        {
                            "action": "remember",
                            "scope": "user",
                            "key": "conclusion",
                            "content": "先给结论",
                        },
                        tool_call_id="memory-write",
                    )
                ]
            )
        return ModelResponse(parts=[TextPart("已记住，先给结论。")])

    runner = PydanticAIKnowledgeRunner(
        base_url="https://model.example.test/v1",
        api_key="test-key",
        model="test-model",
        timeout_seconds=10,
    )
    with runner._agent.override(model=FunctionModel(model)):
        result = runner.run(prompt="记住：先给结论", conversation=(), tools=tools)
    assert result.answer == "已记住，先给结论。"
    assert all("优先用中文简洁回答" in instructions for instructions in observed)
    entries = client.get("/api/memories").json()["items"]
    assert any(item["key"] == "conclusion" and item["origin"] == "explicit" for item in entries)


def test_planner_receives_same_memory_without_memory_tools(plain_client):
    client = plain_client
    user_id = UUID(register(client))
    assert save(client).status_code == 201
    tools = SimpleNamespace(
        memory=AgentMemoryTools(
            client.app.state.memory_service_scope,
            user_id=user_id,
            task_id=None,
            conversation_id=uuid4(),
            run_id=uuid4(),
            prompt="你好",
        )
    )
    seen = []

    def model(messages, info):
        seen.append(info.instructions)
        assert not info.function_tools
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {
                        "request_type": "conversation",
                        "title": "日常交流",
                    },
                    tool_call_id="plan-output",
                )
            ]
        )

    runner = PydanticAIKnowledgeRunner(
        base_url="https://model.example.test/v1",
        api_key="test-key",
        model="test-model",
        timeout_seconds=10,
    )
    with runner._planner_agent.override(model=FunctionModel(model)):
        runner.prepare_research(
            prompt="你好", conversation=(), tools=tools, on_event=lambda _: None
        )
    assert seen and "优先用中文简洁回答" in seen[0]


@pytest.mark.parametrize("model_name", ["test-model", "deepseek-v4-flash"])
def test_extractor_uses_one_bounded_model_request_with_source_provenance(
    plain_client, monkeypatch, model_name
):
    from qunxue_api.adapters.research_agent import memory_extractor

    client = plain_client
    user_id = register(client)
    _, source_id = seed_learning_source(client, user_id)
    requests = []

    def response(request):
        body = json.loads(request.content)
        requests.append(body)
        name = body["tools"][0]["function"]["name"]
        return httpx.Response(
            200,
            json={
                "id": "memory-output",
                "object": "chat.completion",
                "created": 1,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "output",
                                    "type": "function",
                                    "function": {
                                        "name": name,
                                        "arguments": json.dumps(
                                            {
                                                "memories": [
                                                    {
                                                        "scope": "user",
                                                        "key": "style",
                                                        "content": "中文简洁回答",
                                                        "source_message_id": str(source_id),
                                                        "source_quote": "以后请用中文简洁回答",
                                                    }
                                                ],
                                            },
                                            ensure_ascii=False,
                                        ),
                                    },
                                }
                            ],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 80, "completion_tokens": 20, "total_tokens": 100},
            },
        )

    def model_client(**kwargs):
        return AsyncOpenAI(
            **kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(response))
        )

    monkeypatch.setattr(memory_extractor, "AsyncOpenAI", model_client)
    extractor = memory_extractor.PydanticMemoryExtractor(
        base_url="https://api.deepseek.com", api_key="test-key", model=model_name
    )
    assert client.app.state.memory_worker.run_once(extractor=extractor)
    entries = client.get("/api/memories").json()["items"]
    assert len(entries) == 1 and entries[0]["source_message_id"] == str(source_id)
    assert len(requests) == 1
    assert str(source_id) in json.dumps(requests[0]["messages"])
    assert requests[0]["max_completion_tokens"] == 1500
    if model_name == "deepseek-v4-flash":
        assert requests[0]["thinking"] == {"type": "disabled"}


def test_planner_and_cancellable_answer_share_client_event_loop(monkeypatch):
    import asyncio

    from pydantic_ai.usage import RunUsage

    runner = PydanticAIKnowledgeRunner(
        base_url="https://model.example.test/v1",
        api_key="test-key",
        model="test-model",
        timeout_seconds=10,
    )
    loops = []

    async def plan(messages, info):
        loops.append(asyncio.get_running_loop())
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {
                        "request_type": "conversation",
                        "title": "日常交流",
                    },
                    tool_call_id="plan-output",
                )
            ]
        )

    async def answer(*args, **kwargs):
        assert asyncio.get_running_loop() is loops[0]
        return SimpleNamespace(output="你好", usage=RunUsage())

    tools = SimpleNamespace(release=SimpleNamespace(knowledge_release_id="test"), evidence={})
    with runner._planner_agent.override(model=FunctionModel(plan)):
        runner.prepare_research(
            prompt="你好", conversation=(), tools=tools, on_event=lambda _: None
        )
    monkeypatch.setattr(runner._agent, "run", answer)
    result = runner.run_stream(
        prompt="你好",
        conversation=(),
        tools=tools,
        on_delta=lambda _: None,
        is_cancelled=lambda: False,
    )
    assert result.answer == "你好"
