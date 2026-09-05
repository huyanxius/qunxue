from uuid import UUID

from fastapi.testclient import TestClient

from qunxue_api.adapters.research_agent.pydantic_runner import (
    DeterministicKnowledgeRunner,
    VisibleTextStream,
)
from qunxue_api.application import DisciplinaryAgentApplication
from qunxue_api.modules.agent_conversation import (
    AgentResearchEvent,
    AgentRunResult,
    ConversationService,
)


def test_visible_text_stream_drops_thinking_across_chunks() -> None:
    visible: list[str] = []
    stream = VisibleTextStream(visible.append)

    stream.push("<thi")
    stream.push("nking>先规划</thinking>真正")
    stream.push("的回答")
    stream.finish()

    assert "".join(visible) == "真正的回答"


def test_deep_research_mode_emits_model_research_event_before_answer() -> None:
    events: list[AgentResearchEvent] = []

    class Release:
        knowledge_release_id = "release-test"

    class Tools:
        release = Release()
        evidence = {}
        research_map_enabled = False
        handoff_enabled = False
        web_search_enabled = False

        def enable_research_handoff_tools(self):
            self.handoff_enabled = True

        def enable_web_search(self):
            self.web_search_enabled = True

        def propose_start_research(self, **_payload):
            raise AssertionError("deep research must not create a research-start proposal")

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
            assert tools.handoff_enabled is False
            assert tools.web_search_enabled is True
            assert "直接输出详细研究结论" in prompt
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

    assert execution.pending_research is not None
    assert execution.pending_research["state"] == "awaiting_plan_confirmation"
    assert events[0].kind == "plan"
    assert events[0].payload["steps"] == ["检索知识库", "补充网页资料"]

    confirmed = app.run_turn(
        user_id=UUID(int=1),
        conversation_id=None,
        prompt="研究短视频平台上的劳动关系变化",
        idempotency_key="deep-1",
        mode="deep_research",
        deep_research_run_id=execution.run_id,
        deep_research_action="confirm",
        on_research_event=events.append,
    )
    assert confirmed.result.answer == "已完成研究。"
    assert events[-1].kind == "result"
    assert events[-1].payload["summary"] == "已完成研究。"


def test_deep_research_waits_for_plan_confirmation_before_running() -> None:
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
                    kind="plan", payload={"title": prompt, "steps": ["检索知识库"]}
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
    assert execution.pending_research["state"] == "awaiting_plan_confirmation"


def test_confirmed_deep_research_passes_cancellation_into_the_stream_runner() -> None:
    class Release:
        knowledge_release_id = "release-test"

    class Tools:
        release = Release()
        evidence = {}
        research_map_enabled = False
        web_search_enabled = False
        deep_research_enabled = False

        def enable_web_search(self):
            self.web_search_enabled = True

        def enable_deep_research(self):
            self.deep_research_enabled = True

    cancellation_checks = 0

    def is_cancelled():
        nonlocal cancellation_checks
        cancellation_checks += 1
        return False

    class Runner:
        runtime_identity = type("Identity", (), {"provider": "test", "model": "test"})()

        def prepare_research(self, *, prompt, conversation, on_event):
            on_event(AgentResearchEvent(kind="plan", payload={"title": prompt, "steps": ["调查"]}))

        def run_stream(self, *, prompt, conversation, tools, on_delta, on_tool_event, is_cancelled):
            assert tools.deep_research_enabled is True
            assert is_cancelled() is False
            return AgentRunResult(
                answer="完整结论",
                citations=(),
                release_id=tools.release.knowledge_release_id,
                provider="test",
                model="test",
            )

    app = DisciplinaryAgentApplication(
        conversations=ConversationService.in_memory(), runner=Runner(), tools_factory=Tools
    )
    planned = app.run_turn(
        user_id=UUID(int=3),
        conversation_id=None,
        prompt="研究社区照护",
        idempotency_key="cancel-1",
        mode="deep_research",
        on_delta=lambda _delta: None,
        is_cancelled=is_cancelled,
    )
    completed = app.run_turn(
        user_id=UUID(int=3),
        conversation_id=None,
        prompt="研究社区照护",
        idempotency_key="cancel-1",
        mode="deep_research",
        deep_research_run_id=planned.run_id,
        deep_research_action="confirm",
        on_delta=lambda _delta: None,
        is_cancelled=is_cancelled,
    )

    assert completed.result.answer == "完整结论"
    assert cancellation_checks >= 3


def test_confirmed_deep_research_persists_a_completion_record_for_the_card() -> None:
    """重开对话时前端要还原那张研究完成卡片，用时与条数只能从这条留痕里读。"""

    class Release:
        knowledge_release_id = "release-test"

    class Citation:
        def __init__(self, kind, source_kind=None):
            self.kind = kind
            self.source_kind = source_kind
            self.citation_id = f"c-{kind}-{source_kind}"
            self.label = kind
            self.excerpt = None
            self.knowledge_id = None
            self.source_id = None
            self.material_id = None
            self.parse_id = None
            self.segment_id = None
            self.locator = None
            self.deleted = False

    cited = (Citation("entry"), Citation("theory"), Citation("source", source_kind="web"))

    class Tools:
        release = Release()
        evidence = {item.citation_id: item for item in cited}
        research_map_enabled = False
        web_search_enabled = False
        deep_research_enabled = False

        def enable_web_search(self):
            self.web_search_enabled = True

        def enable_deep_research(self):
            self.deep_research_enabled = True

    class Runner:
        runtime_identity = type("Identity", (), {"provider": "test", "model": "test"})()

        def prepare_research(self, *, prompt, conversation, on_event):
            on_event(AgentResearchEvent(kind="plan", payload={"title": prompt, "steps": ["调查"]}))

        def run(self, *, prompt, conversation, tools):
            return AgentRunResult(
                answer="完整结论",
                citations=cited,
                release_id=tools.release.knowledge_release_id,
                provider="test",
                model="test",
            )

    conversations = ConversationService.in_memory()
    app = DisciplinaryAgentApplication(
        conversations=conversations, runner=Runner(), tools_factory=Tools
    )
    planned = app.run_turn(
        user_id=UUID(int=7),
        conversation_id=None,
        prompt="研究社区照护",
        idempotency_key="record-1",
        mode="deep_research",
    )
    completed = app.run_turn(
        user_id=UUID(int=7),
        conversation_id=None,
        prompt="研究社区照护",
        idempotency_key="record-1",
        mode="deep_research",
        deep_research_run_id=planned.run_id,
        deep_research_action="confirm",
    )

    records = [item for item in completed.tool_summary if item.get("tool") == "deep_research"]
    assert len(records) == 1
    output = records[0]["output"]
    assert output["schema_version"] == 1
    assert output["knowledge_count"] == 3
    assert output["web_count"] == 1
    assert output["elapsed_seconds"] >= 0


def test_standard_turn_leaves_no_deep_research_record() -> None:
    class Release:
        knowledge_release_id = "release-test"

    class Tools:
        release = Release()
        evidence = {}
        research_map_enabled = False
        web_search_enabled = False

    class Runner:
        runtime_identity = type("Identity", (), {"provider": "test", "model": "test"})()

        def run(self, *, prompt, conversation, tools):
            return AgentRunResult(
                answer="普通回答",
                citations=(),
                release_id=tools.release.knowledge_release_id,
                provider="test",
                model="test",
            )

    app = DisciplinaryAgentApplication(
        conversations=ConversationService.in_memory(), runner=Runner(), tools_factory=Tools
    )
    completed = app.run_turn(
        user_id=UUID(int=8),
        conversation_id=None,
        prompt="随便问问",
        idempotency_key="record-2",
        mode="standard",
    )

    assert all(item.get("tool") != "deep_research" for item in completed.tool_summary)


def test_skipping_clarification_still_requires_plan_confirmation() -> None:
    events: list[AgentResearchEvent] = []

    class Release:
        knowledge_release_id = "release-test"

    class Tools:
        release = Release()
        evidence = {}
        research_map_enabled = False

        def enable_web_search(self):
            pass

    class Runner:
        runtime_identity = type("Identity", (), {"provider": "test", "model": "test"})()

        def prepare_research(self, *, prompt, conversation, on_event):
            if "跳过了本次澄清" in prompt:
                on_event(AgentResearchEvent(kind="ask", payload={"question": "再次询问"}))
            else:
                on_event(AgentResearchEvent(kind="ask", payload={"question": "研究什么"}))

        def run(self, *, prompt, conversation, tools):
            raise AssertionError("skip must not start research")

    app = DisciplinaryAgentApplication(
        conversations=ConversationService.in_memory(), runner=Runner(), tools_factory=Tools
    )
    first = app.run_turn(
        user_id=UUID(int=3),
        conversation_id=None,
        prompt="研究青年孤独",
        idempotency_key="skip-1",
        mode="deep_research",
        on_research_event=events.append,
    )
    skipped = app.run_turn(
        user_id=UUID(int=3),
        conversation_id=None,
        prompt="研究青年孤独",
        idempotency_key="skip-1",
        mode="deep_research",
        deep_research_run_id=first.run_id,
        deep_research_action="skip",
        on_research_event=events.append,
    )
    assert skipped.pending_research is not None
    assert skipped.pending_research["state"] == "awaiting_plan_confirmation"
    assert events[-1].kind == "plan"


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


def test_agent_may_select_more_than_eight_evidence_items() -> None:
    """PR #299 去掉了运行器里的静默裁剪，工具这一侧不能再压回八条上限。

    深入研究读满知识库再补网页，采用十几条是常态；留着上限会让整轮直接抛错。
    """
    from qunxue_api.adapters.research_agent.catalog_tools import KnowledgeToolRegistry

    tools = KnowledgeToolRegistry.__new__(KnowledgeToolRegistry)
    tools.evidence = {f"c{index}": object() for index in range(12)}
    tools.selected_evidence_ids = ()

    selected = KnowledgeToolRegistry.select_evidence(tools, [f"c{index}" for index in range(12)])

    assert len(selected) == 12
