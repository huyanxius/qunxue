"""Deterministic end-to-end authorization at the actual Agent model boundary."""

import json
import logging
from io import BytesIO
from urllib.error import HTTPError
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


@pytest.mark.parametrize("embedding_failure", ("query_402", "documents_402", "invalid_cache"))
def test_shared_citations_survive_embedding_and_rerank_outages_with_failed_course_index(
    client, monkeypatch, tmp_path, caplog, embedding_failure
):
    from qunxue_api.adapters.research_agent.embedding import OpenAICompatibleEmbeddingProvider
    from qunxue_api.adapters.research_agent.reranker import SiliconFlowRerankerProvider
    from qunxue_api.adapters.retrieval import HybridRetriever, SqliteRetrievalIndex
    from qunxue_api.adapters.sqlite.shared_knowledge import SharedDocumentRow

    identity = _authenticate(client)
    kb = create_library(client)
    doc = upload(client, kb["id"])
    other = create_library(client)
    other_doc = upload(client, other["id"], "课堂记录标记：绝不能跨库流入的私密 B 文本")
    model = "BAAI/bge-m3"
    with client.app.state.shared_knowledge_scope() as app:
        row = app.repository.session.get(SharedDocumentRow, doc["id"])
        row.index_status = "failed"
        row.index_error = "语义索引失败，请重试。"
        row.vectors = (
            {
                model: {
                    f"material:{doc['id']}:{segment['segment_id']}": [1.0]
                    for segment in row.segments
                }
            }
            if embedding_failure == "invalid_cache"
            else {}
        )
        previous_vectors = row.vectors
        app.repository.commit()

    calls = []

    def provider_response(request, *, timeout):
        assert timeout == 1
        body = json.loads(request.data)
        calls.append((request.full_url, body))
        if request.full_url.endswith("/embeddings") and (
            embedding_failure != "query_402" and body["input"] == ["课堂记录标记"]
        ):
            return BytesIO(json.dumps({"data": [{"embedding": [1.0, 0.0]}]}).encode())
        raise HTTPError(request.full_url, 402, "private-provider-detail", {}, None)

    monkeypatch.setattr(
        "qunxue_api.adapters.research_agent.embedding.urlopen", provider_response
    )
    monkeypatch.setattr(
        "qunxue_api.adapters.research_agent.reranker.urlopen", provider_response
    )
    # The database fixture's Alembic fileConfig disables pre-existing app loggers.
    logger_name = "qunxue_api.retrieval"
    monkeypatch.setattr(logging.getLogger(logger_name), "disabled", False)
    caplog.set_level(logging.WARNING, logger=logger_name)
    retriever = HybridRetriever(
        index=SqliteRetrievalIndex(tmp_path / "unused-course-index.db"),
        embedder=OpenAICompatibleEmbeddingProvider(
            base_url="https://embedding.example.invalid/v1",
            api_key="synthetic-course-provider-key",
            model=model,
            timeout_seconds=1,
        ),
        embedding_model=model,
        chunk_schema_version="test-course-chunks",
        reranker=SiliconFlowRerankerProvider(
            base_url="https://reranker.example.invalid/v1",
            api_key="synthetic-course-provider-key",
            model="BAAI/bge-reranker-v2-m3",
            timeout_seconds=1,
        ),
        reranker_model="BAAI/bge-reranker-v2-m3",
        # A failed reranker must not compare small RRF scores against this threshold.
        min_rerank_score=0.99,
    )
    runner = InspectingRunner()
    with client.app.state.disciplinary_agent_scope() as app:
        app._runner = runner
        app._shared_references.retriever = retriever
        result = app.run_turn(
            user_id=UUID(identity["user"]["user_id"]),
            conversation_id=None,
            prompt="课堂记录标记",
            idempotency_key=str(uuid4()),
            reference_knowledge_base_id=UUID(kb["id"]),
        )

    context = runner.inputs[0][1]
    assert context["retrieval_mode"] == "lexical"
    assert context["degraded_reason"] == "embedding_unavailable,reranker_unavailable"
    assert context["error"] is None
    assert len(context["items"]) == 1
    assert "QX-A17" in context["items"][0]["excerpt"]
    assert "私密 B" not in str(runner.inputs)
    assert "私密 B" not in str(calls)
    assert [url.rsplit("/", 1)[-1] for url, _body in calls] == (
        ["embeddings", "embeddings", "rerank"]
        if embedding_failure == "documents_402"
        else ["embeddings", "rerank"]
    )
    citations = result.turn.assistant_message.citations
    assert {citation.material_id for citation in citations} == {doc["id"]}
    assert all(citation.knowledge_base_id == kb["id"] for citation in citations)
    conversation = client.get(
        f"/api/agent/conversations/{result.conversation.conversation_id}"
    ).json()
    persisted = conversation["turns"][0]["assistant"]["citations"]
    assert persisted[0]["source_kind"] == "shared_material"
    assert persisted[0]["material_id"] == doc["id"]
    assert other_doc["id"] not in str(persisted)
    with client.app.state.shared_knowledge_scope() as app:
        row = app.repository.session.get(SharedDocumentRow, doc["id"])
        assert row.status == "ready"
        assert row.index_status == "failed"
        assert row.vectors == previous_vectors
    assert "embedding" in caplog.text
    assert "reranker" in caplog.text
    assert "http_status=402" in caplog.text
    assert "QX-A17" not in caplog.text
    assert "private-provider-detail" not in caplog.text
    assert "synthetic-course-provider-key" not in caplog.text
