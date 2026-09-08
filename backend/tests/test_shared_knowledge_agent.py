"""Deterministic end-to-end authorization at the actual Agent model boundary."""

from uuid import UUID, uuid4

import pytest
from test_research_material_api import _authenticate
from test_shared_knowledge_api import create_library, mutation, upload

from qunxue_api.modules.agent_conversation import AgentRunResult


class InspectingRunner:
    def __init__(self):
        self.inputs = []

    def run(self, *, prompt, conversation, tools):
        self.inputs.append((conversation, getattr(tools, "shared_reference_context", None)))
        citations = tuple(tools.evidence.values())
        return AgentRunResult(
            answer="资料中使用 QX-A17。" if citations else "一般回答。",
            citations=citations,
            release_id=tools.release.knowledge_release_id,
            provider="test",
            model="boundary-inspector",
        )


def test_selected_library_reaches_original_runner_and_persists_citation(client):
    identity = _authenticate(client)
    kb = create_library(client)
    doc = upload(client, kb["id"])
    other = create_library(client)
    upload(client, other["id"], "绝不能跨库流入的私密 B 文本")
    runner = InspectingRunner()
    with client.app.state.disciplinary_agent_scope() as app:
        app._runner = runner
        result = app.run_turn(
            user_id=UUID(identity["user"]["user_id"]),
            conversation_id=None,
            prompt="课堂记录标记是什么",
            idempotency_key=str(uuid4()),
            reference_knowledge_base_id=UUID(kb["id"]),
        )
    assert "QX-A17" in str(runner.inputs)
    assert "私密 B" not in str(runner.inputs)
    assert result.turn.assistant_message.citations[0].material_id == doc["id"]
    conv = client.get(f"/api/agent/conversations/{result.conversation.conversation_id}").json()
    assert conv["reference_knowledge_base_id"] == kb["id"]
    citation = conv["turns"][0]["assistant"]["citations"][0]
    assert citation["knowledge_base_id"] == kb["id"]
    assert citation["source_kind"] == "shared_material"
    assert citation["deleted"] is False


def test_no_selection_does_not_add_shared_context(client):
    identity = _authenticate(client)
    runner = InspectingRunner()
    with client.app.state.disciplinary_agent_scope() as app:
        app._runner = runner
        app.run_turn(
            user_id=UUID(identity["user"]["user_id"]),
            conversation_id=None,
            prompt="你好",
            idempotency_key=str(uuid4()),
        )
    assert runner.inputs[0][1] is None


def test_revocation_blocks_bound_conversation_before_model_and_cannot_switch_in_place(client):
    from qunxue_api.modules.shared_knowledge import SharedKnowledgeUnavailable

    _authenticate(client)
    owner_cookies = dict(client.cookies)
    kb = create_library(client)
    upload(client, kb["id"])
    mutation(
        client, "patch", f"/api/shared-knowledge-bases/{kb['id']}", json={"sharing_enabled": True}
    )
    client.cookies.clear()
    reader = _authenticate(client)
    mutation(
        client,
        "post",
        "/api/shared-knowledge-base-subscriptions",
        json={"share_token": kb["share_token"]},
    )
    runner = InspectingRunner()
    with client.app.state.disciplinary_agent_scope() as app:
        app._runner = runner
        execution = app.run_turn(
            user_id=UUID(reader["user"]["user_id"]),
            conversation_id=None,
            prompt="课堂记录标记",
            idempotency_key=str(uuid4()),
            reference_knowledge_base_id=UUID(kb["id"]),
        )
    reader_cookies = dict(client.cookies)
    client.cookies.clear()
    client.cookies.update(owner_cookies)
    mutation(
        client, "patch", f"/api/shared-knowledge-bases/{kb['id']}", json={"sharing_enabled": False}
    )
    with client.app.state.disciplinary_agent_scope() as app:
        app._runner = runner
        with pytest.raises(SharedKnowledgeUnavailable):
            app.run_turn(
                user_id=UUID(reader["user"]["user_id"]),
                conversation_id=execution.conversation.conversation_id,
                prompt="继续",
                idempotency_key=str(uuid4()),
            )
    assert len(runner.inputs) == 1
    client.cookies.clear()
    client.cookies.update(reader_cookies)
    assert (
        client.get(f"/api/agent/conversations/{execution.conversation.conversation_id}").status_code
        == 200
    )


def test_foreign_user_cannot_select_unsubscribed_library(client):
    _authenticate(client)
    kb = create_library(client)
    client.cookies.clear()
    identity = _authenticate(client)
    from qunxue_api.modules.shared_knowledge import SharedKnowledgeUnavailable

    with client.app.state.disciplinary_agent_scope() as app:
        app._runner = InspectingRunner()
        with pytest.raises(SharedKnowledgeUnavailable):
            app.run_turn(
                user_id=UUID(identity["user"]["user_id"]),
                conversation_id=None,
                prompt="课件",
                idempotency_key=str(uuid4()),
                reference_knowledge_base_id=UUID(kb["id"]),
            )


def test_shared_evidence_survives_empty_public_search():
    from types import SimpleNamespace

    from qunxue_api.adapters.research_agent.pydantic_runner import _select_result_evidence
    from qunxue_api.modules.agent_conversation import AgentEvidence

    tools = SimpleNamespace(
        evidence={
            "course-source": AgentEvidence(
                "course-source",
                "课件",
                "research_material",
                "QX-A17",
                source_kind="shared_material",
            )
        },
        selected_evidence_ids=("course-source",),
    )
    _select_result_evidence(tools, [])
    assert tools.selected_evidence_ids == ("course-source",)


def test_removed_document_is_not_replayed_as_model_history(client):
    identity = _authenticate(client)
    kb = create_library(client)
    doc = upload(client, kb["id"])
    runner = InspectingRunner()
    with client.app.state.disciplinary_agent_scope() as app:
        app._runner = runner
        first = app.run_turn(
            user_id=UUID(identity["user"]["user_id"]),
            conversation_id=None,
            prompt="课堂标记",
            idempotency_key=str(uuid4()),
            reference_knowledge_base_id=UUID(kb["id"]),
        )
    mutation(client, "delete", f"/api/shared-knowledge-bases/{kb['id']}/documents/{doc['id']}")
    with client.app.state.disciplinary_agent_scope() as app:
        app._runner = runner
        app.run_turn(
            user_id=UUID(identity["user"]["user_id"]),
            conversation_id=first.conversation.conversation_id,
            prompt="继续解释",
            idempotency_key=str(uuid4()),
        )
    assert "QX-A17" not in str(runner.inputs[-1])
    assert (
        client.get(f"/api/agent/conversations/{first.conversation.conversation_id}").json()[
            "turns"
        ][0]["assistant"]["content"]
        == "资料中使用 QX-A17。"
    )


def test_shared_turn_does_not_store_revocable_teacher_content_in_personal_memory(client):
    identity = _authenticate(client)
    kb = create_library(client)
    upload(client, kb["id"])

    class MemoryInspectingRunner(InspectingRunner):
        def run(self, **kwargs):
            self.memory = getattr(kwargs["tools"], "memory", None)
            return super().run(**kwargs)

    runner = MemoryInspectingRunner()
    with client.app.state.disciplinary_agent_scope() as app:
        app._runner = runner
        app.run_turn(
            user_id=UUID(identity["user"]["user_id"]),
            conversation_id=None,
            prompt="课堂标记",
            idempotency_key=str(uuid4()),
            reference_knowledge_base_id=UUID(kb["id"]),
        )
    assert runner.memory is None


def test_reference_uses_existing_lexical_retriever_without_vector_cache_argument(client):
    from qunxue_api.adapters.theory_evidence import CatalogTheoryLexicalRetriever

    identity = _authenticate(client)
    kb = create_library(client)
    upload(client, kb["id"])
    runner = InspectingRunner()
    with client.app.state.disciplinary_agent_scope() as app:
        app._runner = runner
        app._shared_references.retriever = CatalogTheoryLexicalRetriever(None)
        app.run_turn(
            user_id=UUID(identity["user"]["user_id"]),
            conversation_id=None,
            prompt="课堂记录标记",
            idempotency_key=str(uuid4()),
            reference_knowledge_base_id=UUID(kb["id"]),
        )
    assert "QX-A17" in str(runner.inputs)
