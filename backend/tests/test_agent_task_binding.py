from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from qunxue_api.adapters.sqlite.agent_conversation_repository import (
    SqliteConversationRepository,
)
from qunxue_api.application.disciplinary_agent import DisciplinaryAgentApplication
from qunxue_api.modules.agent_conversation import (
    AgentRunResult,
    ConversationService,
    ConversationTaskBindingConflict,
)

USER_ID = UUID("00000000-0000-0000-0000-000000000201")
BOUND_TASK_ID = UUID("00000000-0000-0000-0000-000000000202")
OTHER_TASK_ID = UUID("00000000-0000-0000-0000-000000000203")


class _Runner:
    runtime_identity = SimpleNamespace(provider="test", model="test")

    def __init__(self):
        self.called = False

    def run(self, *, prompt, conversation, tools):
        del prompt, conversation
        self.called = True
        return AgentRunResult(
            answer="回答",
            citations=(),
            release_id=tools.release.knowledge_release_id,
            provider="test",
            model="test",
        )


class _Tools:
    release = SimpleNamespace(knowledge_release_id="release-1")
    evidence = {}


def test_agent_rejects_a_task_id_different_from_the_conversation_binding():
    conversations = ConversationService.in_memory()
    conversation = conversations.create_conversation(user_id=USER_ID, title="研究")
    conversations.link_research_task(
        user_id=USER_ID,
        conversation_id=conversation.conversation_id,
        task_id=BOUND_TASK_ID,
    )
    runner = _Runner()
    application = DisciplinaryAgentApplication(
        conversations=conversations,
        runner=runner,
        tools_factory=_Tools,
    )

    with pytest.raises(
        ConversationTaskBindingConflict,
        match="different research task",
    ):
        application.run_turn(
            user_id=USER_ID,
            conversation_id=conversation.conversation_id,
            prompt="读取材料",
            idempotency_key="task-binding-mismatch",
            workspace="research",
            task_id=OTHER_TASK_ID,
        )

    assert runner.called is False


def test_agent_stream_reports_a_stable_task_binding_conflict(client):
    registered = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "email": f"task-binding-{uuid4()}@example.com",
            "password": "research-passphrase",
        },
    )
    assert registered.status_code == 201
    first_task = client.post(
        "/api/research-tasks",
        headers={"Idempotency-Key": str(uuid4())},
        json={"entry_type": "direct_input"},
    )
    second_task = client.post(
        "/api/research-tasks",
        headers={"Idempotency-Key": str(uuid4())},
        json={"entry_type": "direct_input"},
    )
    assert first_task.status_code == second_task.status_code == 201
    user_id = UUID(registered.json()["user"]["user_id"])
    with client.app.state.database.session() as session:
        conversations = ConversationService(SqliteConversationRepository(session))
        conversation = conversations.create_conversation(user_id=user_id, title="研究")
        conversations.link_research_task(
            user_id=user_id,
            conversation_id=conversation.conversation_id,
            task_id=UUID(first_task.json()["task_id"]),
        )
        conversations.commit()

    response = client.post(
        "/api/agent/turns",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "conversation_id": str(conversation.conversation_id),
            "message": "读取研究材料",
            "workspace": "research",
            "task_id": second_task.json()["task_id"],
        },
    )

    assert response.status_code == 200
    assert '"code": "research_task_binding_conflict"' in response.text
    assert '"code": "agent_unavailable"' not in response.text


def test_credit_rejection_does_not_leave_an_empty_conversation():
    class _RejectedCredits:
        def ensure_can_start(self, *, user_id):
            del user_id
            raise RuntimeError("credits depleted")

    conversations = ConversationService.in_memory()
    application = DisciplinaryAgentApplication(
        conversations=conversations,
        runner=_Runner(),
        tools_factory=_Tools,
        credits=_RejectedCredits(),
    )

    with pytest.raises(RuntimeError, match="credits depleted"):
        application.run_turn(
            user_id=USER_ID,
            conversation_id=None,
            prompt="读取材料",
            idempotency_key="credit-rejected-before-create",
        )

    assert conversations.list_conversations(user_id=USER_ID) == ()
