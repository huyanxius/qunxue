from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from qunxue_api.adapters.research_agent.pydantic_runner import (
    PydanticAIKnowledgeRunner,
)
from qunxue_api.adapters.sqlite.agent_conversation_repository import SqliteConversationRepository
from qunxue_api.application.disciplinary_agent import DisciplinaryAgentApplication
from qunxue_api.modules.agent_conversation import (
    AgentResearchEvent,
    AgentRunResult,
    ConversationService,
)


class Tools:
    release = SimpleNamespace(knowledge_release_id="test-release")
    evidence = {}
    research_map_enabled = False


@pytest.mark.parametrize("kind", [None, "ask", "plan"])
def test_new_conversation_persists_title_for_answers_and_pending_research(kind):
    conversations = ConversationService.in_memory()

    class Runner:
        def prepare_research(self, *, prompt, conversation, on_event, on_title=None):
            if on_title:
                on_title("  “青年孤独的社会成因”  ")
            if kind:
                on_event(AgentResearchEvent(
                    kind=kind,
                    payload={"title": "青年孤独", "steps": ["核对青年孤独的研究证据"]},
                ))

        def run(self, **kwargs):
            return AgentRunResult(
                answer="研究回答", citations=(), release_id="test-release",
                provider="test", model="test",
            )

    app = DisciplinaryAgentApplication(
        conversations=conversations, runner=Runner(), tools_factory=Tools,
    )
    execution = app.run_turn(
        user_id=UUID(int=1), conversation_id=None,
        prompt="我想快速研究一下年轻人为什么感到孤独", idempotency_key="first",
        mode="deep_research" if kind else "standard",
    )
    assert execution.conversation.title == "青年孤独的社会成因"
    assert app.list_conversations(user_id=UUID(int=1))[0].title == "青年孤独的社会成因"
    if kind is None:
        app.rename_conversation(
            user_id=UUID(int=1), conversation_id=execution.conversation.conversation_id,
            title="我的研究笔记",
        )
        followup = app.run_turn(
            user_id=UUID(int=1), conversation_id=execution.conversation.conversation_id,
            prompt="继续讨论", idempotency_key="second",
        )
        assert followup.conversation.title == "我的研究笔记"


@pytest.mark.parametrize("request_type,clarify", [
    ("conversation", False), ("research", False), ("research", True),
])
def test_planner_emits_title_for_all_decisions(request_type, clarify):
    runner = PydanticAIKnowledgeRunner(
        base_url="https://example.test/v1", api_key="test", model="test", timeout_seconds=10,
    )
    def model(messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "request_type": request_type, "needs_clarification": clarify,
            "title": "青年孤独的社会成因", "question": "研究哪个地区？",
            "options": ["本校", "本市", "全国"], "steps": ["核对青年孤独的研究证据"],
        })])
    titles = []
    with runner._planner_agent.override(model=FunctionModel(model)):
        runner.prepare_research(
            prompt="我想研究一下年轻人的孤独", conversation=(), tools=Tools(),
            on_event=lambda event: None, on_title=titles.append,
        )
    assert titles == ["青年孤独的社会成因"]


def test_planner_failure_keeps_existing_title():
    runner = PydanticAIKnowledgeRunner(
        base_url="https://example.test/v1", api_key="test", model="test", timeout_seconds=10,
    )
    def unavailable(messages, info):
        raise RuntimeError("offline")
    titles = []
    with (
        runner._planner_agent.override(model=FunctionModel(unavailable)),
        pytest.raises(RuntimeError),
    ):
        runner.prepare_research(
            prompt="你好", conversation=(), tools=Tools(),
            on_event=lambda event: None, on_title=titles.append,
        )
    assert titles == []


@pytest.mark.parametrize("generated,manual,expected", [
    ("", None, "我想了解青年孤独"),
    ("x" * 80, None, "x" * 48),
    ("青年孤独", "手动标题", "手动标题"),
])
def test_title_survives_sqlite_reload_and_respects_manual_rename(
    plain_client, generated, manual, expected,
):
    registered = plain_client.post(
        "/api/session/register",
        json={"email": "titles@example.com", "password": "password-123"},
        headers={"Idempotency-Key": "register-titles"},
    )
    user_id = UUID(registered.json()["user"]["user_id"])
    database = plain_client.app.state.database
    with database.session() as session:
        conversations = ConversationService(SqliteConversationRepository(session))

        class Runner:
            def prepare_research(self, *, on_title=None, **kwargs):
                if manual:
                    existing = conversations.list_conversations(user_id=user_id)[0]
                    conversations.rename_conversation(
                        user_id=user_id, conversation_id=existing.conversation_id, title=manual,
                    )
                if on_title:
                    on_title(generated)

            def run(self, **kwargs):
                return AgentRunResult(
                    answer="研究回答", citations=(), release_id="test-release",
                    provider="test", model="test",
                )

        app = DisciplinaryAgentApplication(
            conversations=conversations, runner=Runner(), tools_factory=Tools,
        )
        result = app.run_turn(
            user_id=user_id, conversation_id=None, prompt="我想了解青年孤独",
            idempotency_key="first",
        )
        assert result.conversation.title == expected

    with database.session() as session:
        saved = ConversationService(SqliteConversationRepository(session)).get_conversation(
            user_id=user_id, conversation_id=result.conversation.conversation_id,
        )
        assert saved.title == expected
