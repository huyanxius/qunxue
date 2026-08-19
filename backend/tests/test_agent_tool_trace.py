import json
from types import SimpleNamespace
from unittest.mock import Mock

from qunxue_api.adapters.research_agent.pydantic_runner import DeterministicKnowledgeRunner
from qunxue_api.modules.agent_conversation import AgentEvidence, AgentRunResult, AgentToolEvent


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
        conversation="",
        tools=tools,
        on_delta=deltas.append,
        on_tool_event=events.append,
    )

    assert events == []
    assert "当前知识库版本中没有找到足够相关的条目" not in result.answer
    assert "社会学" in result.answer
    assert "".join(deltas) == result.answer


def test_deterministic_runner_does_not_use_fixed_refusal_after_empty_search() -> None:
    tools = SimpleNamespace(
        release=SimpleNamespace(knowledge_release_id="release-a"),
        evidence={},
        search_knowledge=lambda _query: [],
    )

    result = DeterministicKnowledgeRunner().run(
        prompt="请检索知识库解释符号互动论",
        conversation="",
        tools=tools,
    )

    assert "当前知识库版本中没有找到足够相关的条目" not in result.answer
    assert "知识库" in result.answer


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
        conversation="",
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


def test_agent_stream_exposes_tool_failure_and_still_completes_the_answer(
    client,
    monkeypatch,
) -> None:
    class _UnavailableKnowledgeRunner:
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
            assert on_tool_event is not None
            on_tool_event(
                AgentToolEvent(
                    tool="search_knowledge",
                    phase="started",
                    call_id="call-search-failed",
                    input={"query": prompt},
                    detail="正在检索知识库",
                )
            )
            on_tool_event(
                AgentToolEvent(
                    tool="search_knowledge",
                    phase="failed",
                    call_id="call-search-failed",
                    input={"query": prompt},
                    detail="知识库检索暂时失败",
                    error="knowledge_search_failed",
                )
            )
            answer = "知识库暂时不可用，我先从社会联结的结构性变化来分析。"
            on_delta(answer)
            return AgentRunResult(
                answer=answer,
                citations=(),
                release_id=tools.release.knowledge_release_id,
                provider="test",
                model="tool-failure-fallback",
            )

    monkeypatch.setattr(
        "qunxue_api.bootstrap.DeterministicKnowledgeRunner",
        _UnavailableKnowledgeRunner,
    )
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
    assert tool_events[0][1]["call_id"] == "call-search-failed"
    assert tool_events[1][1] == {
        "tool": "search_knowledge",
        "call_id": "call-search-failed",
        "input": {"query": "请结合知识库解释年轻人越来越孤独。"},
        "detail": "知识库检索暂时失败",
        "message": "知识库检索暂时失败",
        "error_code": "knowledge_search_failed",
    }
    assert "turn_failed" not in [name for name, _ in events]
    assert events[-1][0] == "turn_completed"
