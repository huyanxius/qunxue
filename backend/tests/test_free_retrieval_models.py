from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from qunxue_api.adapters.retrieval import RetrievalChunk, SqliteRetrievalIndex
from qunxue_api.adapters.retrieval.hybrid import HybridRetriever
from qunxue_api.adapters.retrieval.sqlite_index import (
    RetrievalIndexMismatch,
    RetrievalIndexUnavailable,
)
from qunxue_api.adapters.sqlite.shared_knowledge import (
    SharedDocumentRow,
    SharedDocumentVectorCache,
)
from qunxue_api.bootstrap import create_app
from qunxue_api.settings import Settings


def configured_settings(tmp_path, **override):
    return Settings(
        _env_file=None,
        **{
            "runtime_mode": "base",
            "model_base_url": "https://chat.example.invalid/v1",
            "model_api_key": "synthetic-chat-key",
            "database_url": f"sqlite:///{tmp_path / 'product.db'}",
            "retrieval_index_path": tmp_path / "retrieval.db",
            "model_name": "synthetic-chat",
            "embedding_base_url": "https://embedding.example.invalid/v1",
            "embedding_api_key": "synthetic-embedding-key",
            "embedding_model": "BAAI/bge-m3",
            "reranker_base_url": "https://rerank.example.invalid/v1",
            "reranker_api_key": "synthetic-rerank-key",
            "reranker_model": "BAAI/bge-reranker-v2-m3",
            **override,
        },
    )


@pytest.mark.parametrize("embedding", ["BAAI/bge-m3", "Pro/BAAI/bge-m3"])
@pytest.mark.parametrize("reranker", ["BAAI/bge-reranker-v2-m3", "Pro/BAAI/bge-reranker-v2-m3"])
def test_same_family_models_are_accepted_without_rewriting_their_identity(
    tmp_path, embedding, reranker
):
    settings = configured_settings(
        tmp_path, embedding_model=f" {embedding} ", reranker_model=f" {reranker} "
    )
    config = settings.require_retrieval_config()
    assert config.embedding_model == embedding
    assert config.reranker_model == reranker
    assert settings.model_name == "synthetic-chat"


@pytest.mark.parametrize("fallback", [False, True])
def test_api_assembly_accepts_free_retrieval_models_with_complete_configuration(tmp_path, fallback):
    settings = configured_settings(tmp_path, allow_model_fallback=fallback)
    app = create_app(settings=settings)
    try:
        assert isinstance(app.state.knowledge_retriever, HybridRetriever)
        assert app.state.settings.embedding_model == "BAAI/bge-m3"
        assert app.state.settings.reranker_model == "BAAI/bge-reranker-v2-m3"
        assert app.state.settings.model_name == "synthetic-chat"
    finally:
        app.state.database.engine.dispose()


def chunk():
    return RetrievalChunk(
        chunk_id="material:synthetic-document:s1",
        document_kind="personal_material",
        knowledge_id=None,
        theory_id=None,
        content_version=1,
        content_hash="synthetic-hash",
        title="Synthetic document",
        text="Synthetic content",
        source_ids=(),
    )


def test_equal_dimension_pro_index_cannot_satisfy_free_model_lookup(tmp_path):
    index = SqliteRetrievalIndex(tmp_path / "retrieval.db")
    common = {
        "knowledge_release_id": "synthetic-release",
        "release_content_hash": "synthetic-release-hash",
        "chunk_schema_version": "synthetic-v1",
    }
    pro = index.rebuild(
        **common, embedding_model="Pro/BAAI/bge-m3", chunks=[chunk()], vectors=[[1.0, 0.0]]
    )
    with pytest.raises(RetrievalIndexUnavailable):
        index.find_ready_manifest(**common, embedding_model="BAAI/bge-m3")
    free = index.rebuild(
        **common, embedding_model="BAAI/bge-m3", chunks=[chunk()], vectors=[[0.0, 1.0]]
    )
    assert free.retrieval_index_id != pro.retrieval_index_id
    assert index.get_manifest(pro.retrieval_index_id) == pro
    assert index.find_ready_manifest(**common, embedding_model="BAAI/bge-m3") == free
    with pytest.raises(RetrievalIndexMismatch, match="dimension"):
        index.search(
            retrieval_index_id=free.retrieval_index_id,
            knowledge_release_id="synthetic-release",
            query_vector=[1.0, 0.0, 0.0],
            document_kind=None,
            limit=1,
        )


def test_document_cache_keeps_complete_pro_and_free_model_ids_separate():
    engine = create_engine("sqlite://")
    SharedDocumentRow.__table__.create(engine)
    try:
        with Session(engine) as session:
            session.add(
                SharedDocumentRow(
                    id="synthetic-document",
                    owner_user_id="synthetic-owner",
                    request_key="synthetic-upload",
                    filename="synthetic.txt",
                    media_type="text/plain",
                    content_hash="synthetic-hash",
                    content=b"Synthetic content",
                    size_bytes=17,
                    parse_id="synthetic-parse",
                    status="ready",
                    segments=[],
                    vectors={"Pro/BAAI/bge-m3": {chunk().chunk_id: [1.0, 0.0]}},
                    warnings=[],
                    created_at=datetime.now(UTC),
                )
            )
            session.flush()
            cache = SharedDocumentVectorCache(session, {"synthetic-document": "synthetic-hash"})
            assert cache.get_many([chunk()], "BAAI/bge-m3") == [None]
            cache.put_many([chunk()], "BAAI/bge-m3", [[0.0, 1.0]])
            assert cache.get_many([chunk()], "BAAI/bge-m3") == [[0.0, 1.0]]
            assert cache.get_many([chunk()], "Pro/BAAI/bge-m3") == [[1.0, 0.0]]
    finally:
        engine.dispose()
