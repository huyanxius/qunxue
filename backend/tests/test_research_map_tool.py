import json
from types import SimpleNamespace

import pytest
from pydantic_ai import ToolDefinition
from pydantic_ai.messages import RetryPromptPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from qunxue_api.adapters.research_agent.catalog_tools import KnowledgeToolRegistry
from qunxue_api.adapters.research_agent.pydantic_runner import (
    PydanticAIKnowledgeRunner,
    _compose_agent_prompt,
    _prepare_research_map_tool,
)
from qunxue_api.modules.agent_conversation import AgentRunResult, AgentToolEvent


class _Catalog:
    def current_release(self, *, purpose):
        del purpose
        return SimpleNamespace(knowledge_release_id="release-a")


def _patch() -> dict[str, object]:
    return {
        "schema_version": 1,
        "nodes": [
            {
                "id": "question-youth-loneliness",
                "kind": "question",
                "title": "为什么年轻人越来越孤独？",
                "summary": "把个体体验放回关系结构与制度节奏中解释。",
                "status": "developing",
                "citation_ids": [],
            },
            {
                "id": "claim-time-poverty",
                "kind": "claim",
                "title": "时间贫困压缩了稳定关系的维护空间",
                "summary": "高强度劳动与通勤使重复互动更难持续。",
                "status": "grounded",
                "citation_ids": [],
            },
        ],
        "relations": [
            {
                "id": "relation-time-explains-question",
                "source": "claim-time-poverty",
                "target": "question-youth-loneliness",
                "relation": "explains",
                "label": "结构机制",
            }
        ],
        "remove_node_ids": [],
        "remove_relation_ids": [],
    }


def _sse_events(payload: str) -> list[tuple[str, dict[str, object]]]:
    events = []
    for block in payload.split("\n\n"):
        lines = block.splitlines()
        name = next(
            (line.removeprefix("event: ") for line in lines if line.startswith("event: ")),
            None,
        )
        data = next(
            (line.removeprefix("data: ") for line in lines if line.startswith("data: ")),
            None,
        )
        if name and data:
            events.append((name, json.loads(data)))
    return events


def test_research_map_tool_validates_and_applies_a_real_argument_patch() -> None:
    registry = KnowledgeToolRegistry(_Catalog())
    registry.enable_research_map()

    result = registry.update_research_map(
        nodes=_patch()["nodes"],
        relations=_patch()["relations"],
        remove_node_ids=[],
        remove_relation_ids=[],
    )

    assert result == _patch()
    assert registry.research_map["nodes"][1]["kind"] == "claim"


def test_research_map_tool_rejects_invalid_kinds_and_dangling_relations() -> None:
    registry = KnowledgeToolRegistry(_Catalog())
    registry.enable_research_map()

    with pytest.raises(ValueError, match="node kind"):
        registry.update_research_map(
            nodes=[{"id": "tool-call", "kind": "tool", "title": "检索知识库"}],
            relations=[],
        )

    with pytest.raises(ValueError, match="relation target"):
        registry.update_research_map(
            nodes=[{"id": "claim-a", "kind": "claim", "title": "一条真实主张"}],
            relations=[
                {
                    "id": "relation-a",
                    "source": "claim-a",
                    "target": "missing-node",
                    "relation": "supports",
                }
            ],
        )


def test_research_map_tool_rejects_unobserved_citation_ids() -> None:
    registry = KnowledgeToolRegistry(_Catalog())
    registry.enable_research_map()

    with pytest.raises(ValueError, match="citation"):
        registry.update_research_map(
            nodes=[
                {
                    "id": "evidence-a",
                    "kind": "evidence",
                    "title": "无法核验的证据",
                    "citation_ids": ["knowledge:invented"],
                }
            ],
            relations=[],
        )


def test_research_map_tool_restores_existing_nodes_for_incremental_relations() -> None:
    registry = KnowledgeToolRegistry(_Catalog())
    registry.enable_research_map(
        {
            "schema_version": 1,
            "nodes": [_patch()["nodes"][0]],
            "relations": [],
        }
    )

    patch = registry.update_research_map(
        nodes=[{"id": "theory-social-capital", "kind": "theory", "title": "社会资本理论"}],
        relations=[
            {
                "id": "relation-theory-explains-question",
                "source": "theory-social-capital",
                "target": "question-youth-loneliness",
                "relation": "explains",
            }
        ],
    )

    assert patch["relations"][0]["target"] == "question-youth-loneliness"
    assert len(registry.research_map["nodes"]) == 2


def test_research_map_tool_accepts_model_content_and_relation_aliases() -> None:
    registry = KnowledgeToolRegistry(_Catalog())
    registry.enable_research_map()

    patch = registry.update_research_map(
        nodes=[
            {"id": "q1", "kind": "question", "content": "如何解释青年孤独感上升？"},
            {"id": "t1", "kind": "theory", "content": "个体化理论：传统纽带脱嵌。"},
        ],
        relations=[
            {"id": "r1", "from": "t1", "to": "q1", "type": "explains"},
        ],
    )

    assert patch["nodes"][0]["title"] == "如何解释青年孤独感上升？"
    assert patch["relations"] == [
        {
            "id": "r1",
            "source": "t1",
            "target": "q1",
            "relation": "explains",
            "label": None,
        }
    ]


def test_research_map_tool_assigns_stable_ids_when_model_omits_relation_ids() -> None:
    registry = KnowledgeToolRegistry(_Catalog())
    registry.enable_research_map()

    patch = registry.update_research_map(
        nodes=[
            {"id": "q1", "kind": "question", "content": "如何解释青年孤独感？"},
            {"id": "t1", "kind": "theory", "content": "个体化理论"},
        ],
        relations=[{"from": "t1", "to": "q1", "type": "explains"}],
    )

    relation = patch["relations"][0]
    assert isinstance(relation, dict)
    assert relation["id"]
    assert relation["source"] == "t1"
    assert relation["target"] == "q1"
    assert relation["relation"] == "explains"

    repeat = registry.update_research_map(
        nodes=[],
        relations=[{"from": "t1", "to": "q1", "type": "explains"}],
    )
    assert repeat["relations"][0]["id"] == relation["id"]


def test_research_map_tool_is_hidden_from_plain_agent_turns() -> None:
    definition = ToolDefinition(name="update_research_map")
    disabled = SimpleNamespace(deps=SimpleNamespace(research_map_enabled=False))
    enabled = SimpleNamespace(deps=SimpleNamespace(research_map_enabled=True))

    assert _prepare_research_map_tool(disabled, definition) is None
    assert _prepare_research_map_tool(enabled, definition) is definition


def test_research_map_tool_schema_requires_canonical_nodes_and_relations() -> None:
    registry = KnowledgeToolRegistry(_Catalog())
    registry.enable_research_map()
    schemas: dict[str, dict[str, object]] = {}

    async def model_stream(_messages, info):
        schemas.update(
            {
                tool.name: tool.parameters_json_schema
                for tool in info.function_tools
            }
        )
        yield "继续梳理研究地图。"

    runner = PydanticAIKnowledgeRunner(
        base_url="https://api.deepseek.com",
        api_key="local-test-key",
        model="deepseek-v4-flash",
        timeout_seconds=30,
    )
    with runner._agent.override(model=FunctionModel(stream_function=model_stream)):
        runner.run_stream(
            prompt="继续",
            conversation=(),
            tools=registry,
            on_delta=lambda _delta: None,
        )

    schema = schemas["update_research_map"]
    node_schema = schema["$defs"]["ResearchMapNodeInput"]
    relation_schema = schema["$defs"]["ResearchMapRelationInput"]
    assert node_schema["additionalProperties"] is False
    assert set(node_schema["required"]) == {"id", "kind", "title"}
    assert node_schema["properties"]["kind"]["enum"] == [
        "question",
        "theory",
        "claim",
        "evidence",
        "gap",
        "synthesis",
    ]
    assert relation_schema["additionalProperties"] is False
    assert set(relation_schema["required"]) == {"source", "target", "relation"}
    assert relation_schema["properties"]["relation"]["enum"] == [
        "explains",
        "supports",
        "challenges",
        "derives",
        "refines",
    ]


def test_invalid_research_map_patch_gets_one_model_retry() -> None:
    registry = KnowledgeToolRegistry(_Catalog())
    registry.enable_research_map()
    tool_attempts = 0

    async def model_stream(messages, _info):
        nonlocal tool_attempts
        last_parts = messages[-1].parts
        if tool_attempts == 0:
            tool_attempts += 1
            yield {
                0: DeltaToolCall(
                    name="update_research_map",
                    json_args=(
                        '{"nodes":[{"id":"q1","kind":"question",'
                        '"title":"为什么社区互助减少？"}],'
                        '"relations":[{"source":"q1","target":"missing",'
                        '"relation":"refines"}]}'
                    ),
                    tool_call_id="call-map-invalid",
                )
            }
        elif any(isinstance(part, RetryPromptPart) for part in last_parts):
            tool_attempts += 1
            yield {
                0: DeltaToolCall(
                    name="update_research_map",
                    json_args=(
                        '{"nodes":['
                        '{"id":"q1","kind":"question","title":"为什么社区互助减少？"},'
                        '{"id":"c1","kind":"claim","title":"重复互动机会正在减少"}],'
                        '"relations":[{"source":"c1","target":"q1",'
                        '"relation":"explains"}]}'
                    ),
                    tool_call_id="call-map-corrected",
                )
            }
        else:
            yield "已修正并保存研究地图。"

    runner = PydanticAIKnowledgeRunner(
        base_url="https://api.deepseek.com",
        api_key="local-test-key",
        model="deepseek-v4-flash",
        timeout_seconds=30,
    )
    events: list[AgentToolEvent] = []
    with runner._agent.override(model=FunctionModel(stream_function=model_stream)):
        result = runner.run_stream(
            prompt="继续",
            conversation=(),
            tools=registry,
            on_delta=lambda _delta: None,
            on_tool_event=events.append,
        )

    assert tool_attempts == 2
    assert [(event.phase, event.call_id) for event in events] == [
        ("started", "call-map-invalid"),
        ("failed", "call-map-invalid"),
        ("started", "call-map-corrected"),
        ("finished", "call-map-corrected"),
    ]
    assert [node["id"] for node in registry.research_map["nodes"]] == ["q1", "c1"]
    assert result.answer == "已修正并保存研究地图。"


def test_research_map_storage_failure_aborts_the_turn(monkeypatch) -> None:
    registry = KnowledgeToolRegistry(_Catalog())
    registry.enable_research_map()
    tool_attempted = False

    def unavailable_map(**_payload):
        raise RuntimeError("storage details must not be converted into an answer")

    monkeypatch.setattr(registry, "update_research_map", unavailable_map)

    async def model_stream(_messages, _info):
        nonlocal tool_attempted
        if not tool_attempted:
            tool_attempted = True
            yield {
                0: DeltaToolCall(
                    name="update_research_map",
                    json_args=(
                        '{"nodes":[{"id":"q1","kind":"question",'
                        '"title":"为什么社区互助减少？"}],"relations":[]}'
                    ),
                    tool_call_id="call-map-unavailable",
                )
            }
        else:
            yield "地图没保存，但我先继续回答。"

    runner = PydanticAIKnowledgeRunner(
        base_url="https://api.deepseek.com",
        api_key="local-test-key",
        model="deepseek-v4-flash",
        timeout_seconds=30,
    )
    events: list[AgentToolEvent] = []
    with (
        runner._agent.override(model=FunctionModel(stream_function=model_stream)),
        pytest.raises(RuntimeError, match="storage details"),
    ):
        runner.run_stream(
            prompt="继续",
            conversation=(),
            tools=registry,
            on_delta=lambda _delta: None,
            on_tool_event=events.append,
        )

    assert [(event.phase, event.call_id) for event in events] == [
        ("started", "call-map-unavailable"),
        ("failed", "call-map-unavailable"),
    ]


def test_agent_openapi_exposes_typed_research_map_nodes_and_relations(client) -> None:
    schemas = client.app.openapi()["components"]["schemas"]

    node_schema = schemas["AgentResearchMapNodeResponse"]
    relation_schema = schemas["AgentResearchMapRelationResponse"]
    patch_schema = schemas["AgentResearchMapPatchResponse"]
    assert set(node_schema["required"]) == {
        "id",
        "kind",
        "title",
        "status",
        "citation_ids",
    }
    assert set(relation_schema["required"]) == {
        "id",
        "source",
        "target",
        "relation",
    }
    assert patch_schema["properties"]["nodes"]["items"]["$ref"].endswith(
        "/AgentResearchMapNodeResponse"
    )
    assert patch_schema["properties"]["relations"]["items"]["$ref"].endswith(
        "/AgentResearchMapRelationResponse"
    )


def test_research_prompt_carries_the_persisted_map_into_the_next_turn() -> None:
    prompt = _compose_agent_prompt(
        prompt="还缺什么证据？",
        research_map={
            "schema_version": 1,
            "nodes": [_patch()["nodes"][1]],
            "relations": [],
        },
    )

    assert "<current_research_map>" in prompt
    assert '"id":"claim-time-poverty"' in prompt
    assert "<research_map_policy>" in prompt
    assert "形成或修订研究问题、理论、主张、证据、缺口或综合判断" in prompt


def test_research_workspace_streams_and_rehydrates_canvas_patch(
    client,
    monkeypatch,
) -> None:
    patch = _patch()

    class _ResearchMapRunner:
        def run_stream(
            self,
            *,
            prompt,
            conversation,
            tools,
            on_delta,
            on_tool_event=None,
        ) -> AgentRunResult:
            del conversation
            assert prompt == "为什么年轻人越来越孤独？"
            assert tools.research_map_enabled is True
            assert on_tool_event is not None
            on_tool_event(
                AgentToolEvent(
                    tool="update_research_map",
                    phase="started",
                    call_id="call-map-1",
                    input={"nodes": patch["nodes"], "relations": patch["relations"]},
                    detail="正在组织研究地图",
                )
            )
            on_tool_event(
                AgentToolEvent(
                    tool="update_research_map",
                    phase="finished",
                    call_id="call-map-1",
                    output=patch,
                    detail="已更新 2 个研究节点与 1 条关系",
                )
            )
            answer = "可以先检验时间贫困如何改变稳定互动。"
            on_delta(answer)
            return AgentRunResult(
                answer=answer,
                citations=(),
                release_id=tools.release.knowledge_release_id,
                provider="test",
                model="research-map",
            )

    monkeypatch.setattr(
        "qunxue_api.bootstrap.DeterministicKnowledgeRunner",
        _ResearchMapRunner,
    )
    registered = client.post(
        "/api/session/register",
        json={
            "email": "research-map@example.com",
            "password": "password-123",
            "display_name": "学生",
        },
        headers={"Idempotency-Key": "register-research-map"},
    )
    assert registered.status_code == 201

    response = client.post(
        "/api/agent/turns",
        json={"message": "为什么年轻人越来越孤独？", "workspace": "research"},
        headers={"Idempotency-Key": "research-map-turn-1"},
    )

    events = _sse_events(response.text)
    canvas_event = next(payload for name, payload in events if name == "canvas_patch")
    assert canvas_event == patch
    completed = next(payload for name, payload in events if name == "turn_completed")
    conversation = completed["conversation"]
    assert conversation["research_map"]["nodes"] == patch["nodes"]
    assert conversation["turns"][0]["canvas_patches"] == [patch]

    detail = client.get(f"/api/agent/conversations/{conversation['conversation_id']}")
    assert detail.status_code == 200
    assert detail.json()["research_map"] == conversation["research_map"]
    assert detail.json()["turns"][0]["canvas_patches"] == [patch]
