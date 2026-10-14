import json
import sqlite3
from io import BytesIO

import pytest

from qunxue_api.adapters.retrieval import RetrievalChunk, SqliteRetrievalIndex
from qunxue_api.adapters.retrieval.sqlite_index import (
    RetrievalIndexMismatch,
    RetrievalIndexUnavailable,
)
from qunxue_api.bootstrap import create_app
from qunxue_api.settings import Settings

RELEASE = {
    "knowledge_release_id": "synthetic-release",
    "release_content_hash": "sha256:synthetic-release",
    "chunk_schema_version": "retrieval-corpus-v1",
}
BASE_URL = "https://api.siliconflow.cn/v1"
PRO = "Pro/BAAI/bge-m3"
FREE = "BAAI/bge-m3"


def build(index, *, model=PRO, dimension=1024):
    return index.rebuild(
        **RELEASE,
        embedding_model=model,
        chunks=[
            RetrievalChunk(
                chunk_id="synthetic-chunk",
                document_kind="knowledge_entry",
                knowledge_id="synthetic-knowledge",
                theory_id=None,
                content_version=1,
                content_hash="sha256:synthetic-chunk",
                title="Synthetic knowledge",
                text="Synthetic knowledge about relationships",
                source_ids=(),
            )
        ],
        vectors=[[1.0] + [0.0] * (dimension - 1)],
    )


def test_live_retriever_uses_pro_index_but_sends_free_model_requests(tmp_path, monkeypatch):
    index = SqliteRetrievalIndex(tmp_path / "retrieval.db")
    old = build(index)
    sent = []

    def response(request, **kwargs):
        del kwargs
        payload = json.loads(request.data)
        sent.append((request.full_url, payload["model"]))
        if request.full_url.endswith("/embeddings"):
            return BytesIO(
                json.dumps({"data": [{"index": 0, "embedding": [1.0] + [0.0] * 1023}]}).encode()
            )
        return BytesIO(json.dumps({"results": [{"index": 0, "relevance_score": 0.9}]}).encode())

    monkeypatch.setattr("qunxue_api.adapters.research_agent.embedding.urlopen", response)
    monkeypatch.setattr("qunxue_api.adapters.research_agent.reranker.urlopen", response)
    settings = Settings(
        _env_file=None,
        runtime_mode="base",
        model_base_url="https://chat.example.invalid/v1",
        model_api_key="synthetic-chat-key",
        model_name="synthetic-chat",
        database_url=f"sqlite:///{tmp_path / 'product.db'}",
        retrieval_index_path=tmp_path / "retrieval.db",
        embedding_base_url=BASE_URL,
        embedding_api_key="synthetic-embedding-key",
        embedding_model=FREE,
        reranker_base_url=BASE_URL,
        reranker_api_key="synthetic-reranker-key",
        reranker_model="BAAI/bge-reranker-v2-m3",
    )
    app = create_app(settings=settings)
    try:
        result = app.state.knowledge_retriever.search(
            query="Synthetic relationships",
            knowledge_release_id=RELEASE["knowledge_release_id"],
            release_content_hash=RELEASE["release_content_hash"],
            document_kind="knowledge_entry",
            limit=1,
        )
        assert result.retrieval_index_id == old.retrieval_index_id
        assert result.embedding_model == FREE
        assert result.hits[0].chunk.chunk_id == "synthetic-chunk"
        assert result.degraded_reason is None
        assert sent == [
            (BASE_URL + "/embeddings", FREE),
            (BASE_URL + "/rerank", "BAAI/bge-reranker-v2-m3"),
        ]
        assert index.get_manifest(old.retrieval_index_id) == old
        with sqlite3.connect(tmp_path / "retrieval.db") as connection:
            assert connection.execute("SELECT COUNT(*) FROM retrieval_indexes").fetchone()[0] == 1
    finally:
        app.state.database.engine.dispose()


@pytest.mark.parametrize("stored,requested", [(PRO, FREE), (FREE, PRO)])
@pytest.mark.parametrize("base_url", [BASE_URL, BASE_URL + "/"])
def test_only_explicit_siliconflow_pair_can_share_ready_manifest(
    tmp_path, stored, requested, base_url
):
    index = SqliteRetrievalIndex(tmp_path / "retrieval.db")
    old = build(index, model=stored)
    assert (
        index.find_ready_manifest(**RELEASE, embedding_model=requested, embedding_base_url=base_url)
        == old
    )


@pytest.mark.parametrize(
    "base_url",
    [None, "https://other.example/v1", "http://api.siliconflow.cn/v1", BASE_URL + ".invalid"],
)
def test_alias_is_rejected_for_missing_or_other_provider(tmp_path, base_url):
    index = SqliteRetrievalIndex(tmp_path / "retrieval.db")
    build(index)
    with pytest.raises(RetrievalIndexUnavailable):
        index.find_ready_manifest(**RELEASE, embedding_model=FREE, embedding_base_url=base_url)


@pytest.mark.parametrize(
    "model", ["BAAI/bge-large-zh-v1.5", "Qwen/Qwen3-Embedding-8B", "Pro/BAAI/bge-m3-custom"]
)
def test_alias_does_not_match_other_model_names(tmp_path, model):
    index = SqliteRetrievalIndex(tmp_path / "retrieval.db")
    build(index)
    with pytest.raises(RetrievalIndexUnavailable):
        index.find_ready_manifest(**RELEASE, embedding_model=model, embedding_base_url=BASE_URL)


@pytest.mark.parametrize("field", list(RELEASE))
def test_alias_keeps_release_content_hash_and_schema_checks(tmp_path, field):
    index = SqliteRetrievalIndex(tmp_path / "retrieval.db")
    build(index)
    with pytest.raises(RetrievalIndexUnavailable):
        index.find_ready_manifest(
            **{**RELEASE, field: "different"}, embedding_model=FREE, embedding_base_url=BASE_URL
        )


def test_exact_model_index_is_preferred_to_alias(tmp_path):
    index = SqliteRetrievalIndex(tmp_path / "retrieval.db")
    build(index)
    exact = build(index, model=FREE)
    assert (
        index.find_ready_manifest(**RELEASE, embedding_model=FREE, embedding_base_url=BASE_URL)
        == exact
    )


def test_alias_requires_1024_dimension_and_search_keeps_query_dimension_guard(tmp_path):
    index = SqliteRetrievalIndex(tmp_path / "retrieval.db")
    build(index, dimension=2)
    with pytest.raises(RetrievalIndexUnavailable):
        index.find_ready_manifest(**RELEASE, embedding_model=FREE, embedding_base_url=BASE_URL)
    valid = build(index)
    selected = index.find_ready_manifest(
        **RELEASE, embedding_model=FREE, embedding_base_url=BASE_URL
    )
    assert selected == valid
    with pytest.raises(RetrievalIndexMismatch, match="dimension"):
        index.search(
            retrieval_index_id=selected.retrieval_index_id,
            knowledge_release_id=RELEASE["knowledge_release_id"],
            query_vector=[1.0, 0.0],
            document_kind=None,
            limit=1,
        )


@pytest.mark.parametrize("damage", ["point_count", "status"])
def test_alias_keeps_ready_status_and_complete_point_count_checks(tmp_path, damage):
    path = tmp_path / "retrieval.db"
    index = SqliteRetrievalIndex(path)
    build(index)
    with sqlite3.connect(path) as connection:
        if damage == "point_count":
            connection.execute("DELETE FROM retrieval_points")
        else:
            connection.execute("UPDATE retrieval_indexes SET status='failed'")
    with pytest.raises(RetrievalIndexUnavailable):
        index.find_ready_manifest(**RELEASE, embedding_model=FREE, embedding_base_url=BASE_URL)
