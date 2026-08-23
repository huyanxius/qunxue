from pathlib import Path

import pytest

from qunxue_api.adapters.research_agent.embedding import EmbeddingProviderError
from qunxue_api.adapters.research_agent.reranker import RerankerProviderError, RerankScore
from qunxue_api.adapters.retrieval import RetrievalChunk, SqliteRetrievalIndex
from qunxue_api.adapters.retrieval.hybrid import (
    HybridRetriever,
    RetrievalPipelineUnavailable,
)


def _ready_index(tmp_path: Path) -> tuple[SqliteRetrievalIndex, str]:
    index = SqliteRetrievalIndex(tmp_path / "retrieval.db")
    manifest = index.rebuild(
        knowledge_release_id="release-reviewed-v1",
        release_content_hash="sha256:release-reviewed-v1",
        embedding_model="Pro/BAAI/bge-m3",
        chunk_schema_version="retrieval-corpus-v1",
        chunks=(
            RetrievalChunk(
                chunk_id="theory-profile:social-capital:v1",
                document_kind="theory_profile",
                knowledge_id="D2:P001",
                theory_id="social-capital",
                content_version=1,
                content_hash="sha256:social-capital",
                title="社会资本理论",
                text="社会资本理论解释社区互助如何依赖信任、互惠规范和关系网络。",
                source_ids=("source:putnam",),
            ),
            RetrievalChunk(
                chunk_id="theory-profile:symbolic-interaction:v1",
                document_kind="theory_profile",
                knowledge_id="D2:P002",
                theory_id="symbolic-interaction",
                content_version=1,
                content_hash="sha256:symbolic-interaction",
                title="符号互动论",
                text="符号互动论解释行动者如何在互动中协商意义。",
                source_ids=("source:mead",),
            ),
        ),
        vectors=((1.0, 0.0), (0.0, 1.0)),
    )
    return index, manifest.retrieval_index_id


def test_hybrid_retrieval_reranks_a_release_bound_closed_candidate_set(
    tmp_path: Path,
) -> None:
    index, _ = _ready_index(tmp_path)

    class Embedder:
        def embed_query(self, _query):
            return [0.9, 0.1]

    class Reranker:
        def rerank(self, *, query, documents, top_n):
            assert query == "成员流动后社区互助为什么减少？"
            assert len(documents) == 2
            assert top_n == 2
            return (RerankScore(index=0, score=0.94), RerankScore(index=1, score=0.21))

    result = HybridRetriever(
        index=index,
        embedder=Embedder(),
        embedding_model="Pro/BAAI/bge-m3",
        chunk_schema_version="retrieval-corpus-v1",
        reranker=Reranker(),
        reranker_model="Pro/BAAI/bge-reranker-v2-m3",
        min_rerank_score=0.3,
    ).search(
        query="成员流动后社区互助为什么减少？",
        knowledge_release_id="release-reviewed-v1",
        release_content_hash="sha256:release-reviewed-v1",
        document_kind="theory_profile",
        limit=5,
    )

    assert result.mode == "hybrid_reranked"
    assert result.reranker_model == "Pro/BAAI/bge-reranker-v2-m3"
    assert [hit.chunk.theory_id for hit in result.hits] == ["social-capital"]
    assert result.hits[0].retrieval_sources == ("lexical", "semantic")
    assert result.hits[0].rerank_score == 0.94


def test_hybrid_retrieval_exposes_auditable_same_condition_stage_rankings(
    tmp_path: Path,
) -> None:
    index, _ = _ready_index(tmp_path)

    class Embedder:
        def embed_query(self, _query):
            return [0.9, 0.1]

    class Reranker:
        def rerank(self, **_kwargs):
            return (RerankScore(index=0, score=0.94), RerankScore(index=1, score=0.21))

    trace = HybridRetriever(
        index=index,
        embedder=Embedder(),
        embedding_model="Pro/BAAI/bge-m3",
        chunk_schema_version="retrieval-corpus-v1",
        reranker=Reranker(),
        reranker_model="Pro/BAAI/bge-reranker-v2-m3",
        min_rerank_score=0.3,
    ).search_with_trace(
        query="成员流动后社区互助为什么减少？",
        knowledge_release_id="release-reviewed-v1",
        release_content_hash="sha256:release-reviewed-v1",
        document_kind="theory_profile",
        limit=5,
    )

    assert [item.chunk_id for item in trace.lexical] == [
        "theory-profile:social-capital:v1",
        "theory-profile:symbolic-interaction:v1",
    ]
    assert [item.chunk_id for item in trace.semantic] == [
        "theory-profile:social-capital:v1",
        "theory-profile:symbolic-interaction:v1",
    ]
    assert [item.chunk_id for item in trace.fused] == [
        "theory-profile:social-capital:v1",
        "theory-profile:symbolic-interaction:v1",
    ]
    assert [(item.chunk_id, item.score) for item in trace.reranked] == [
        ("theory-profile:social-capital:v1", 0.94),
        ("theory-profile:symbolic-interaction:v1", 0.21),
    ]
    assert [item.chunk.theory_id for item in trace.result.hits] == ["social-capital"]


def test_embedding_failure_aborts_retrieval_instead_of_returning_lexical_evidence(
    tmp_path: Path,
) -> None:
    index, _ = _ready_index(tmp_path)

    class UnavailableEmbedder:
        def embed_query(self, _query):
            raise EmbeddingProviderError("provider unavailable")

    with pytest.raises(RetrievalPipelineUnavailable, match="embedding"):
        HybridRetriever(
            index=index,
            embedder=UnavailableEmbedder(),
            embedding_model="Pro/BAAI/bge-m3",
            chunk_schema_version="retrieval-corpus-v1",
            reranker=_PassingReranker(),
            reranker_model="Pro/BAAI/bge-reranker-v2-m3",
            min_rerank_score=0.3,
        ).search(
            query="社会资本理论",
            knowledge_release_id="release-reviewed-v1",
            release_content_hash="sha256:release-reviewed-v1",
            document_kind="theory_profile",
            limit=5,
        )


def test_reranker_failure_aborts_retrieval_instead_of_returning_rrf_order(
    tmp_path: Path,
) -> None:
    index, _ = _ready_index(tmp_path)

    class Embedder:
        def embed_query(self, _query):
            return [0.9, 0.1]

    class UnavailableReranker:
        def rerank(self, **_kwargs):
            raise RerankerProviderError("provider unavailable")

    with pytest.raises(RetrievalPipelineUnavailable, match="reranker"):
        HybridRetriever(
            index=index,
            embedder=Embedder(),
            embedding_model="Pro/BAAI/bge-m3",
            chunk_schema_version="retrieval-corpus-v1",
            reranker=UnavailableReranker(),
            reranker_model="Pro/BAAI/bge-reranker-v2-m3",
            min_rerank_score=0.3,
        ).search(
            query="社区互助",
            knowledge_release_id="release-reviewed-v1",
            release_content_hash="sha256:release-reviewed-v1",
            document_kind="theory_profile",
            limit=5,
        )


def test_missing_release_index_aborts_retrieval_instead_of_searching_any_other_index(
    tmp_path: Path,
) -> None:
    index, _ = _ready_index(tmp_path)

    with pytest.raises(RetrievalPipelineUnavailable, match="index"):
        HybridRetriever(
            index=index,
            embedder=SimpleEmbedder(),
            embedding_model="Pro/BAAI/bge-m3",
            chunk_schema_version="retrieval-corpus-v1",
            reranker=_PassingReranker(),
            reranker_model="Pro/BAAI/bge-reranker-v2-m3",
            min_rerank_score=0.3,
        ).search(
            query="社区互助",
            knowledge_release_id="release-other",
            release_content_hash="sha256:release-other",
            document_kind="theory_profile",
            limit=5,
        )


class SimpleEmbedder:
    def embed_query(self, _query):
        return [0.9, 0.1]


class _PassingReranker:
    def rerank(self, *, documents, **_kwargs):
        return tuple(
            RerankScore(index=index, score=0.8) for index, _document in enumerate(documents)
        )
