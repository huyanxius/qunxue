from uuid import UUID

from fastapi.testclient import TestClient

from qunxue_api.adapters.research_agent.pydantic_runner import DeterministicKnowledgeRunner
from qunxue_api.application import DisciplinaryAgentApplication
from qunxue_api.modules.agent_conversation import (
    AgentResearchEvent,
    AgentRunResult,
    ConversationService,
)


def test_deep_research_mode_emits_model_research_event_before_answer() -> None:
    events: list[AgentResearchEvent] = []

    class Release:
        knowledge_release_id = "release-test"

    class Tools:
        release = Release()
        evidence = {}
        research_map_enabled = False
        web_search_enabled = False

    class Runner:
        runtime_identity = type("Identity", (), {"provider": "test", "model": "test"})()

        def prepare_research(self, *, prompt, conversation, on_event):
            assert prompt == "研究短视频平台上的劳动关系变化"
            assert conversation == ()
            on_event(
                AgentResearchEvent(
                    kind="plan",
                    payload={
                        "title": "短视频平台劳动关系变化",
                        "steps": ["检索知识库", "补充网页资料"],
                    },
                )
            )

        def run(self, *, prompt, conversation, tools):
            return AgentRunResult(
                answer="已完成研究。",
                citations=(),
                release_id=tools.release.knowledge_release_id,
                provider="test",
                model="test",
            )

    app = DisciplinaryAgentApplication(
        conversations=ConversationService.in_memory(),
        runner=Runner(),
        tools_factory=Tools,
    )

    execution = app.run_turn(
        user_id=UUID(int=1),
        conversation_id=None,
        prompt="研究短视频平台上的劳动关系变化",
        idempotency_key="deep-1",
        mode="deep_research",
        on_research_event=events.append,
    )

    assert execution.pending_research is None
    assert execution.result.answer == "已完成研究。"
    assert events[0].kind == "plan"
    assert events[0].payload["steps"] == ["检索知识库", "补充网页资料"]


def test_deep_research_waits_only_when_planner_needs_clarification() -> None:
    events: list[AgentResearchEvent] = []

    class Release:
        knowledge_release_id = "release-test"

    class Tools:
        release = Release()
        evidence = {}
        research_map_enabled = False
        web_search_enabled = False

    class Runner:
        runtime_identity = type("Identity", (), {"provider": "test", "model": "test"})()

        def prepare_research(self, *, prompt, conversation, on_event):
            on_event(
                AgentResearchEvent(
                    kind="ask",
                    payload={
                        "question": "你希望我研究哪个具体问题或对象？",
                        "options": ["社会现象", "群体或组织", "政策或制度"],
                    },
                )
            )

        def run(self, *, prompt, conversation, tools):
            raise AssertionError("deep research must wait for the card confirmation")

    app = DisciplinaryAgentApplication(
        conversations=ConversationService.in_memory(),
        runner=Runner(),
        tools_factory=Tools,
    )

    execution = app.run_turn(
        user_id=UUID(int=1),
        conversation_id=None,
        prompt="研究短视频平台上的劳动关系变化",
        idempotency_key="deep-wait-1",
        mode="deep_research",
        on_research_event=events.append,
    )

    assert execution.turn is None
    assert execution.pending_research is not None
    assert execution.pending_research["state"] == "awaiting_clarification"


def test_deep_research_does_not_ask_for_clarification_on_greeting() -> None:
    class Release:
        knowledge_release_id = "release-test"

    class Tools:
        release = Release()
        evidence = {}
        research_map_enabled = False
        web_search_enabled = False

    class Runner:
        runtime_identity = type("Identity", (), {"provider": "test", "model": "test"})()

        def prepare_research(self, *, prompt, conversation, on_event):
            del conversation, on_event
            assert prompt == "你好"

        def run(self, *, prompt, conversation, tools):
            return AgentRunResult(
                answer="你好！有什么想了解的？",
                citations=(),
                release_id=tools.release.knowledge_release_id,
                provider="test",
                model="test",
            )

    app = DisciplinaryAgentApplication(
        conversations=ConversationService.in_memory(),
        runner=Runner(),
        tools_factory=Tools,
    )
    execution = app.run_turn(
        user_id=UUID(int=2),
        conversation_id=None,
        prompt="你好",
        idempotency_key="deep-greeting-1",
        mode="deep_research",
    )
    assert execution.pending_research is None
    assert execution.result.answer == "你好！有什么想了解的？"


def test_deterministic_planner_asks_for_an_object_not_a_research_lens() -> None:
    runner = DeterministicKnowledgeRunner()

    topic_events: list[AgentResearchEvent] = []
    runner.prepare_research(
        prompt="研究平台劳动关系变化",
        conversation=(),
        on_event=topic_events.append,
    )
    assert [event.kind for event in topic_events] == ["plan"]

    underspecified_events: list[AgentResearchEvent] = []
    runner.prepare_research(
        prompt="研究一下",
        conversation=(),
        on_event=underspecified_events.append,
    )
    assert underspecified_events[0].kind == "ask"
    assert underspecified_events[0].payload["question"] == "你希望我研究哪个具体问题或对象？"
    assert underspecified_events[0].payload["options"][-1] == "更多自定义"


def test_deep_research_sse_exposes_plan_event(client: TestClient) -> None:
    register = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": "deep-register"},
        json={"email": "deep-mode@example.com", "password": "research-passphrase"},
    )
    assert register.status_code == 201
    response = client.post(
        "/api/agent/turns",
        headers={"Idempotency-Key": "deep-sse-1"},
        json={
            "message": "研究短视频平台上的劳动关系变化及其近五年的行业影响",
            "mode": "deep_research",
            "web_search": False,
        },
    )
    assert response.status_code == 200
    assert "event: research_plan" in response.text
