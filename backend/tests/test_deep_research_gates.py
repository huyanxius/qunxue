"""Research execution requires a server-held plan, not a client action string."""

from types import SimpleNamespace
from uuid import UUID

import pytest

from qunxue_api.application import DisciplinaryAgentApplication
from qunxue_api.modules.agent_conversation import (
    AgentInterrupted,
    AgentResearchEvent,
    AgentRunResult,
    ConversationService,
)


class Tools:
    release = SimpleNamespace(knowledge_release_id="release-test")
    evidence = {}
    deep_research_enabled = False
    web_search_enabled = False

    def enable_web_search(self):
        self.web_search_enabled = True

    def enable_deep_research(self):
        self.deep_research_enabled = True


class Runner:
    def __init__(self, decision="research", ask=False):
        self.decision = decision
        self.ask = ask
        self.prompts = []
        self.interrupt = False

    def prepare_research(self, *, prompt, on_event, **kwargs):
        if self.decision != "research":
            return self.decision
        if self.ask and "用户选择的研究重点" not in prompt and "跳过了本次澄清" not in prompt:
            on_event(AgentResearchEvent(kind="ask", payload={
                "question": "关注哪类高校？",
                "options": ["本校", "全国高校", "高校类型比较", "更多自定义"],
            }))
        else:
            on_event(AgentResearchEvent(kind="plan", payload={
                "title": "高校就餐选择",
                "steps": ["验证就餐频率变化", "比较价格与排队成本", "寻找反例和替代解释"],
            }))
        return "research"

    def run(self, *, prompt, tools, **kwargs):
        self.prompts.append((prompt, tools.deep_research_enabled))
        if self.interrupt:
            raise AgentInterrupted("pause")
        return AgentRunResult(answer="结果", citations=(), release_id="release-test",
                              provider="test", model="test")


def setup(runner=None):
    runner = runner or Runner()
    app = DisciplinaryAgentApplication(conversations=ConversationService.in_memory(),
                                      runner=runner, tools_factory=Tools)
    return app, runner


def turn(app, **kwargs):
    return app.run_turn(user_id=UUID(int=1), conversation_id=None,
                        prompt="为什么大学生越来越不愿意去食堂？",
                        idempotency_key="research", mode="deep_research", **kwargs)


@pytest.mark.parametrize("decision", [None, "research"])
def test_missing_plan_does_not_authorize_research(decision):
    class EmptyPlanner(Runner):
        def prepare_research(self, **kwargs):
            return decision

    app, runner = setup(EmptyPlanner())
    with pytest.raises(ValueError):
        turn(app)
    assert runner.prompts == []


@pytest.mark.parametrize("action", ["confirm", "clarify", "skip"])
def test_client_action_without_pending_run_cannot_bypass_planning(action):
    app, runner = setup()
    with pytest.raises(ValueError):
        turn(app, deep_research_action=action, deep_research_selection="本校")
    assert runner.prompts == []


def test_ask_answer_then_plan_then_confirm_executes_the_approved_scope():
    app, runner = setup(Runner(ask=True))
    asked = turn(app)
    assert asked.pending_research["state"] == "awaiting_clarification"
    planned = turn(app, deep_research_run_id=asked.run_id,
                   deep_research_action="clarify", deep_research_selection="本校")
    assert planned.pending_research["state"] == "awaiting_plan_confirmation"
    assert runner.prompts == []
    waiting = turn(app, deep_research_run_id=asked.run_id)
    assert waiting.pending_research == planned.pending_research
    done = turn(app, deep_research_run_id=asked.run_id, deep_research_action="confirm")
    assert done.result.answer == "结果"
    prompt, deep = runner.prompts[0]
    assert deep is True
    assert "本校" in prompt
    assert "比较价格与排队成本" in prompt
    assert "寻找反例和替代解释" in prompt
    replay = turn(app, deep_research_run_id=asked.run_id, deep_research_action="confirm")
    assert replay.replayed
    assert len(runner.prompts) == 1


def test_cannot_confirm_an_unanswered_ask():
    app, runner = setup(Runner(ask=True))
    asked = turn(app)
    with pytest.raises(ValueError):
        turn(app, deep_research_run_id=asked.run_id, deep_research_action="confirm")
    assert runner.prompts == []


def test_explicit_conversation_decision_uses_normal_answer_without_research_card():
    app, runner = setup(Runner(decision="conversation"))
    done = turn(app)
    assert done.pending_research is None
    assert runner.prompts[0][1] is False
    assert "普通模式" in runner.prompts[0][0]
    assert not any(item.get("tool") == "deep_research" for item in done.tool_summary)


def test_skip_still_generates_a_plan_without_executing():
    app, runner = setup(Runner(ask=True))
    asked = turn(app)
    planned = turn(app, deep_research_run_id=asked.run_id, deep_research_action="skip")
    assert planned.pending_research["state"] == "awaiting_plan_confirmation"
    assert runner.prompts == []


def test_confirmed_research_resumes_with_the_same_plan():
    app, runner = setup()
    planned = turn(app)
    runner.interrupt = True
    with pytest.raises(AgentInterrupted):
        turn(app, deep_research_run_id=planned.run_id, deep_research_action="confirm")
    runner.interrupt = False
    turn(app)
    assert len(runner.prompts) == 2
    assert runner.prompts[0] == runner.prompts[1]
    assert "寻找反例和替代解释" in runner.prompts[1][0]


def test_a_new_request_supersedes_the_previous_pending_plan():
    app, runner = setup()
    original = turn(app)
    revised = app.run_turn(user_id=UUID(int=1),
                          conversation_id=original.conversation.conversation_id,
                          prompt="修改范围为本校近三年", idempotency_key="revised",
                          mode="deep_research")
    assert revised.pending_research is not None
    with pytest.raises(ValueError):
        turn(app, deep_research_run_id=original.run_id, deep_research_action="confirm")
    assert runner.prompts == []


def test_plan_can_be_revised_but_must_be_confirmed_again():
    app, runner = setup()
    original = turn(app)
    revised = turn(app, deep_research_run_id=original.run_id,
                   deep_research_action="clarify", deep_research_selection="改为全国高校")
    assert revised.pending_research["state"] == "awaiting_plan_confirmation"
    assert "全国高校" in revised.pending_research["prompt"]
    assert runner.prompts == []
