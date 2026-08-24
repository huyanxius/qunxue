import json
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from qunxue_api.adapters.research_agent.pydantic_runner import DeterministicKnowledgeRunner
from qunxue_api.adapters.retrieval import RetrievalPipelineUnavailable
from qunxue_api.modules.agent_conversation import (
    AgentEvidence,
    AgentRunResult,
    AgentToolEvent,
    AgentTurn,
)


def _sse_events(payload: str) -> list[tuple[str, dict[str, object]]]:
    events = []
    for block in payload.split("\n\n"):
        lines = block.splitlines()
        name = next(
            (line.removeprefix("event: ") for line in lines if line.startswith("event: ")), None
        )
        data = next(
            (line.removeprefix("data: ") for line in lines if line.startswith("data: ")), None
        )
        if name and data:
            events.append((name, json.loads(data)))
    return events


def test_deterministic_runner_answers_generic_sociology_question_without_tool() -> None:
    tools = SimpleNamespace(
        release=SimpleNamespace(knowledge_release_id="release-a"),
        evidence={},
        search_knowledge=Mock(side_effect=AssertionError("generic chat must not search")),
    )
    events: list[AgentToolEvent] = []
    deltas: list[str] = []

    result = DeterministicKnowledgeRunner().run_stream(
        prompt="怎么解释年轻人越来越孤独？",
        conversation=(),
        tools=tools,
        on_delta=deltas.append,
        on_tool_event=events.append,
    )

    assert events == []
    assert "当前知识库版本中没有找到足够相关的条目" not in result.answer
    assert "社会学" in result.answer
    assert "".join(deltas) == result.answer


def test_deterministic_runner_preflights_formal_research_requests() -> None:
    citation = AgentEvidence(
        citation_id="retrieval:theory-profile:social-capital:v2",
        label="社会资本理论",
        kind="theory",
        excerpt="持续关系、信任与互惠规范支持集体行动。",
        knowledge_id="D2:P001",
    )
    search = Mock(
        return_value=[
            {
                "citation_id": citation.citation_id,
                "knowledge_id": citation.knowledge_id,
                "title": citation.label,
                "excerpt": citation.excerpt,
                "evidence_status": "verified",
            }
        ]
    )
    tools = SimpleNamespace(
        release=SimpleNamespace(knowledge_release_id="release-a"),
        evidence={citation.citation_id: citation},
        search_knowledge=search,
    )

    result = DeterministicKnowledgeRunner().run(
        prompt="我要写本科生毕业论文，帮我想一个选题，我们快速研究。",
        conversation=(),
        tools=tools,
    )

    search.assert_called_once()
    assert [item.citation_id for item in result.citations] == [citation.citation_id]


@pytest.mark.parametrize(
    "prompt",
    [
        "好",
        "好的",
        "确认",
        "继续",
        "取消",
        "保存",
        "就这个",
        "好的！",
        "确认。",
        "继续。",
    ],
)
def test_research_workspace_flow_control_does_not_repeat_search(prompt: str) -> None:
    search = Mock(side_effect=AssertionError("flow control must not repeat search"))
    tools = SimpleNamespace(
        release=SimpleNamespace(knowledge_release_id="release-a"),
        evidence={},
        research_map_enabled=True,
        research_document_tools_enabled=False,
        search_knowledge=search,
    )
    conversation = (
        AgentTurn.create(
            user_content="我想研究社区流动如何改变邻里互助",
            assistant_content="可以先区分关系流失与互惠规范变化。",
            citations=(),
            evidence_ids=frozenset(),
        ),
    )

    DeterministicKnowledgeRunner().run(
        prompt=prompt,
        conversation=conversation,
        tools=tools,
    )

    search.assert_not_called()


@pytest.mark.parametrize(
    "prompt",
    ["有文献吗？", "为什么？", "这个理论靠谱吗？", "这个理论的依据是什么？"],
)
def test_contextual_evidence_followup_reuses_recent_topic(prompt: str) -> None:
    search = Mock(return_value=[])
    tools = SimpleNamespace(
        release=SimpleNamespace(knowledge_release_id="release-a"),
        evidence={},
        research_map_enabled=False,
        research_document_tools_enabled=False,
        search_knowledge=search,
    )
    conversation = (
        AgentTurn.create(
            user_content="我想研究社区流动如何改变邻里互助",
            assistant_content="可以用社会资本理论检查关系流失与互惠规范变化。",
            citations=(),
            evidence_ids=frozenset(),
        ),
        AgentTurn.create(
            user_content="谢谢你",
            assistant_content="不客气。",
            citations=(),
            evidence_ids=frozenset(),
        ),
    )

    result = DeterministicKnowledgeRunner().run(
        prompt=prompt,
        conversation=conversation,
        tools=tools,
    )

    query = search.call_args.args[0]
    assert "我想研究社区流动如何改变邻里互助" in query
    assert prompt in query
    assert result.answer.startswith("当前绑定的知识发布中没有检索到")


def test_contextual_why_does_not_search_without_research_context() -> None:
    search = Mock(side_effect=AssertionError("casual context must not search"))
    tools = SimpleNamespace(
        release=SimpleNamespace(knowledge_release_id="release-a"),
        evidence={},
        research_map_enabled=False,
        research_document_tools_enabled=False,
        search_knowledge=search,
    )
    conversation = (
        AgentTurn.create(
            user_content="你今天怎么样？",
            assistant_content="我状态不错。",
            citations=(),
            evidence_ids=frozenset(),
        ),
    )

    DeterministicKnowledgeRunner().run(
        prompt="为什么？",
        conversation=conversation,
        tools=tools,
    )

    search.assert_not_called()


def test_agent_identity_context_does_not_turn_why_into_research() -> None:
    search = Mock(side_effect=AssertionError("identity context must not search"))
    tools = SimpleNamespace(
        release=SimpleNamespace(knowledge_release_id="release-a"),
        evidence={},
        research_map_enabled=False,
        research_document_tools_enabled=False,
        search_knowledge=search,
    )
    conversation = (
        AgentTurn.create(
            user_content="你是社会学 Agent 吗？",
            assistant_content="是，我是社会学学科 Agent。",
            citations=(),
            evidence_ids=frozenset(),
        ),
    )

    DeterministicKnowledgeRunner().run(
        prompt="为什么？",
        conversation=conversation,
        tools=tools,
    )

    search.assert_not_called()


@pytest.mark.parametrize(
    "prompt",
    [
        "把这个理论解释改得更准确",
        "把它改得更准确",
        "调整研究问题，使表述更准确",
    ],
)
def test_document_knowledge_edit_cannot_bypass_evidence_preflight(
    prompt: str,
) -> None:
    search = Mock(return_value=[])
    tools = SimpleNamespace(
        release=SimpleNamespace(knowledge_release_id="release-a"),
        evidence={},
        research_map_enabled=True,
        research_document_tools_enabled=True,
        search_knowledge=search,
    )
    conversation = (
        AgentTurn.create(
            user_content="用社会资本理论解释邻里互助减少",
            assistant_content="当前解释强调关系网络流失。",
            citations=(),
            evidence_ids=frozenset(),
        ),
    )

    result = DeterministicKnowledgeRunner().run(
        prompt=prompt,
        conversation=conversation,
        tools=tools,
    )

    query = search.call_args.args[0]
    assert "用社会资本理论解释邻里互助减少" in query
    assert prompt in query
    assert result.answer.startswith("当前绑定的知识发布中没有检索到")


def test_document_presentation_edit_does_not_repeat_search() -> None:
    search = Mock(side_effect=AssertionError("presentation edit must not search"))
    tools = SimpleNamespace(
        release=SimpleNamespace(knowledge_release_id="release-a"),
        evidence={},
        research_map_enabled=True,
        research_document_tools_enabled=True,
        search_knowledge=search,
    )
    conversation = (
        AgentTurn.create(
            user_content="用社会资本理论解释邻里互助减少",
            assistant_content="当前解释强调关系网络流失。",
            citations=(),
            evidence_ids=frozenset(),
        ),
    )

    DeterministicKnowledgeRunner().run(
        prompt="把这句话润色得更简洁",
        conversation=conversation,
        tools=tools,
    )

    search.assert_not_called()


def test_deterministic_runner_reports_insufficient_evidence_after_empty_search() -> None:
    tools = SimpleNamespace(
        release=SimpleNamespace(knowledge_release_id="release-a"),
        evidence={},
        search_knowledge=lambda _query: [],
    )

    result = DeterministicKnowledgeRunner().run(
        prompt="请检索知识库解释符号互动论",
        conversation=(),
        tools=tools,
    )

    assert result.answer == (
        "当前绑定的知识发布中没有检索到足以支持本次回答的证据。"
        "本轮不生成正式知识结论；请补充研究情境、概念线索或材料后再试。"
    )
    assert result.citations == ()


def test_search_tool_trace_includes_real_result_preview() -> None:
    citation = AgentEvidence(
        citation_id="knowledge:D1:C029",
        label="社会行动四类型",
        kind="preview",
        excerpt="韦伯将社会行动区分为目的理性、价值理性、情感和传统四类。",
        knowledge_id="D1:C029",
    )
    tools = SimpleNamespace(
        release=SimpleNamespace(knowledge_release_id="release-preview"),
        evidence={citation.citation_id: citation},
        search_knowledge=lambda _query: [
            {
                "citation_id": citation.citation_id,
                "knowledge_id": citation.knowledge_id,
                "title": citation.label,
                "excerpt": citation.excerpt,
                "evidence_status": "preview_unverified",
            }
        ],
    )
    events: list[AgentToolEvent] = []

    DeterministicKnowledgeRunner().run_stream(
        prompt="请检索知识库解释社会行动四类型",
        conversation=(),
        tools=tools,
        on_delta=lambda _: None,
        on_tool_event=events.append,
    )

    finished = next(event for event in events if event.phase == "finished")
    assert finished.output == {
        "result_count": 1,
        "items": [
            {
                "knowledge_id": "D1:C029",
                "title": "社会行动四类型",
                "excerpt": "韦伯将社会行动区分为目的理性、价值理性、情感和传统四类。",
                "evidence_status": "preview_unverified",
            }
        ],
    }
    assert "社会行动四类型" in (finished.detail or "")
    assert "韦伯将社会行动" in (finished.detail or "")


def test_agent_stream_starts_as_thinking_and_exposes_real_tool_input(client) -> None:
    registered = client.post(
        "/api/session/register",
        json={
            "email": "trace@example.com",
            "password": "password-123",
            "display_name": "学生",
        },
        headers={"Idempotency-Key": "register-trace"},
    )
    assert registered.status_code == 201

    response = client.post(
        "/api/agent/turns",
        json={"message": "请检索知识库，解释什么是符号互动论？"},
        headers={"Idempotency-Key": "agent-trace-1"},
    )

    events = _sse_events(response.text)
    assert events[0] == ("agent_status", {"status": "thinking"})
    turn_started = next(payload for name, payload in events if name == "turn_started")
    assert turn_started["runtime_mode"] == "mock"
    started = next(payload for name, payload in events if name == "tool_started")
    finished = next(payload for name, payload in events if name == "tool_finished")
    assert started["tool"] == "search_knowledge"
    assert started["input"] == {"query": "请检索知识库，解释什么是符号互动论？"}
    assert finished["call_id"] == started["call_id"]
    assert finished["output"]["result_count"] == 1
    assert finished["output"]["items"][0]["title"]
    assert finished["output"]["items"][0]["excerpt"]


def test_agent_stream_does_not_invent_tool_events_for_a_direct_answer(
    client,
    monkeypatch,
) -> None:
    class _DirectAnswerRunner:
        def run_stream(
            self,
            *,
            prompt,
            conversation,
            tools,
            on_delta,
            on_tool_event=None,
        ) -> AgentRunResult:
            del prompt, conversation, on_tool_event
            answer = "可以从社会联结、劳动节奏与城市流动三个层面理解。"
            on_delta(answer)
            return AgentRunResult(
                answer=answer,
                citations=(),
                release_id=tools.release.knowledge_release_id,
                provider="test",
                model="direct-answer",
            )

    monkeypatch.setattr(
        "qunxue_api.bootstrap.DeterministicKnowledgeRunner",
        _DirectAnswerRunner,
    )
    registered = client.post(
        "/api/session/register",
        json={
            "email": "direct-answer@example.com",
            "password": "password-123",
            "display_name": "学生",
        },
        headers={"Idempotency-Key": "register-direct-answer"},
    )
    assert registered.status_code == 201

    response = client.post(
        "/api/agent/turns",
        json={"message": "怎么解释年轻人越来越孤独？"},
        headers={"Idempotency-Key": "agent-direct-answer-1"},
    )

    events = _sse_events(response.text)
    assert not [name for name, _ in events if name.startswith("tool_")]
    assert [name for name, _ in events] == [
        "agent_status",
        "turn_started",
        "agent_status",
        "assistant_delta",
        "turn_completed",
    ]


def test_agent_stream_keeps_the_connection_alive_while_the_model_is_idle(
    client,
    monkeypatch,
) -> None:
    class _SlowAnswerRunner:
        def run_stream(
            self,
            *,
            prompt,
            conversation,
            tools,
            on_delta,
            on_tool_event=None,
        ) -> AgentRunResult:
            del prompt, conversation, on_tool_event
            time.sleep(0.05)
            answer = "先确认研究对象，再收窄问题。"
            on_delta(answer)
            return AgentRunResult(
                answer=answer,
                citations=(),
                release_id=tools.release.knowledge_release_id,
                provider="test",
                model="slow-answer",
            )

    monkeypatch.setattr(
        "qunxue_api.bootstrap.DeterministicKnowledgeRunner",
        _SlowAnswerRunner,
    )
    monkeypatch.setattr(
        "qunxue_api.api.routes.agent._SSE_HEARTBEAT_SECONDS",
        0.01,
        raising=False,
    )
    registered = client.post(
        "/api/session/register",
        json={
            "email": "slow-agent@example.com",
            "password": "password-123",
            "display_name": "学生",
        },
        headers={"Idempotency-Key": "register-slow-agent"},
    )
    assert registered.status_code == 201

    response = client.post(
        "/api/agent/turns",
        json={"message": "帮我收窄一个本科论文选题。"},
        headers={"Idempotency-Key": "agent-slow-answer-1"},
    )

    assert response.status_code == 200
    assert ": keep-alive\n\n" in response.text
    assert "event: turn_completed" in response.text


def test_agent_stream_exposes_tool_failure_and_aborts_the_turn(client) -> None:
    class _UnavailableRetriever:
        def search(self, **kwargs):
            del kwargs
            raise RetrievalPipelineUnavailable("test retrieval outage")

    client.app.state.knowledge_retriever = _UnavailableRetriever()
    registered = client.post(
        "/api/session/register",
        json={
            "email": "tool-failure@example.com",
            "password": "password-123",
            "display_name": "学生",
        },
        headers={"Idempotency-Key": "register-tool-failure"},
    )
    assert registered.status_code == 201

    response = client.post(
        "/api/agent/turns",
        json={"message": "请结合知识库解释年轻人越来越孤独。"},
        headers={"Idempotency-Key": "agent-tool-failure-1"},
    )

    events = _sse_events(response.text)
    tool_events = [(name, payload) for name, payload in events if name.startswith("tool_")]
    assert [name for name, _ in tool_events] == ["tool_started", "tool_failed"]
    assert tool_events[0][1]["call_id"] == "deterministic:search_knowledge"
    assert tool_events[1][1]["call_id"] == "deterministic:search_knowledge"
    assert tool_events[1][1]["error_code"] == "knowledge_search_failed"
    assert "assistant_delta" not in [name for name, _ in events]
    assert "turn_completed" not in [name for name, _ in events]
    assert events[-1][0] == "turn_failed"
