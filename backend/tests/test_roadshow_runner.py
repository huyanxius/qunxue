from types import SimpleNamespace
from uuid import UUID

import pytest

from qunxue_api.adapters.research_agent.roadshow_runner import RoadshowRunner
from qunxue_api.application import DisciplinaryAgentApplication
from qunxue_api.modules.agent_conversation import (
    AgentInterrupted,
    AgentRunResult,
    AgentRuntimeIdentity,
    ConversationService,
)


class Fallback:
    runtime_identity = AgentRuntimeIdentity(provider="normal", model="normal")

    def prepare_research(self, **kwargs):
        pass

    def run(self, **kwargs):
        return AgentRunResult("normal answer", (), "release", "normal", "normal")

    def run_stream(self, **kwargs):
        kwargs["on_delta"]("normal answer")
        return self.run()


class Tools:
    release = SimpleNamespace(knowledge_release_id="release")
    research_map_enabled = False
    web_search_enabled = False

    def __init__(self, user_id=None):
        self._user_id = user_id or UUID(int=1)
        self.evidence = {}
        self.calls = []

    def bind_agent_context(self, **kwargs):
        self._user_id = kwargs["user_id"]

    def agent_route_context(self):
        return {"user_id": self._user_id}

    def enable_web_search(self):
        self.web_search_enabled = True

    def search_knowledge(self, query, **kwargs):
        self.calls.append(("knowledge", query))
        return []

    def search_web(self, query, **kwargs):
        self.calls.append(("web", query))
        return [{"title": "Source", "url": "https://example.org/paper"}]

    def read_web_page(self, url):
        self.calls.append(("read", url))
        return {"title": "Source", "text": "Evidence"}


@pytest.fixture
def runner():
    return RoadshowRunner(
        Fallback(),
        {
            "user_id": str(UUID(int=1)),
            "chunk_delay": 0,
            "cases": [
                {
                    "keywords": ["食堂"],
                    "title": "食堂空间",
                    "question": "研究什么？",
                    "options": ["空间使用", "空间治理"],
                    "steps": ["检索理论", "阅读网页"],
                    "knowledge_queries": ["空间生产"],
                    "web_queries": ["校园食堂空间"],
                    "answer": "# 审定研究报告\n\n空间分析正文。",
                }
            ],
        },
    )


def test_account_and_topic_scope_and_stream(runner):
    for uid, prompt in [(UUID(int=2), "食堂"), (UUID(int=1), "数字劳动")]:
        tools = Tools(uid)
        result = runner.run(prompt=prompt, conversation=(), tools=tools)
        assert result.answer == "normal answer"
        assert tools.calls == []
    chunks, events = [], []
    tools = Tools()
    result = runner.run_stream(
        prompt="食堂",
        conversation=(),
        tools=tools,
        on_delta=chunks.append,
        on_tool_event=events.append,
    )
    assert "".join(chunks) == result.answer
    assert "空间分析正文" in result.answer
    assert [x[0] for x in tools.calls] == ["knowledge", "web", "read"]
    assert [e.phase for e in events] == ["started", "finished"] * 3


def test_cancel_before_tools(runner):
    tools = Tools()
    with pytest.raises(AgentInterrupted):
        runner.run_stream(
            prompt="食堂",
            conversation=(),
            tools=tools,
            on_delta=lambda _: None,
            is_cancelled=lambda: True,
        )
    assert tools.calls == []


def test_clarification_then_plan_then_report(runner):
    tools = Tools()
    app = DisciplinaryAgentApplication(
        conversations=ConversationService.in_memory(), runner=runner, tools_factory=lambda: tools
    )
    args = dict(
        user_id=UUID(int=1),
        conversation_id=None,
        prompt="食堂",
        idempotency_key="case-1",
        mode="deep_research",
    )
    first = app.run_turn(**args)
    assert first.pending_research["state"] == "awaiting_clarification"
    plan = app.run_turn(
        **args,
        deep_research_run_id=first.run_id,
        deep_research_action="clarify",
        deep_research_selection="空间治理",
    )
    assert plan.pending_research["state"] == "awaiting_plan_confirmation"
    assert "空间治理" in str(plan.pending_research)
    assert tools.calls == []
    result = app.run_turn(**args, deep_research_run_id=first.run_id, deep_research_action="confirm")
    assert "空间分析正文" in result.result.answer
    assert result.turn is not None
