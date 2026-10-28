import json
import logging
from pathlib import Path
from urllib.error import HTTPError

import pytest

import qunxue_api.adapters.research_agent.embedding as embedding
import qunxue_api.adapters.research_agent.reranker as reranker
from qunxue_api.adapters.research_agent.embedding import OpenAICompatibleEmbeddingProvider
from qunxue_api.adapters.research_agent.reranker import RerankScore, SiliconFlowRerankerProvider
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


@pytest.mark.parametrize("transient", [False, True], ids=["release", "materials"])
@pytest.mark.parametrize(
    ("embedding_fails", "reranker_fails"),
    [(True, False), (False, True), (True, True)],
    ids=["embedding-unavailable", "reranker-unavailable", "both-unavailable"],
)
@pytest.mark.parametrize("failure", [402, 503, "timeout", "invalid-response"])
def test_provider_outages_preserve_retrieval(
    tmp_path, monkeypatch, caplog, transient, embedding_fails, reranker_fails, failure
):
    index, index_id = _ready_index(tmp_path)
    monkeypatch.setattr(logging.getLogger("qunxue_api.retrieval"), "disabled", False)
    caplog.set_level(logging.WARNING, logger="qunxue_api.retrieval")
    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(self.payload).encode()

    def request(request, **_kwargs):
        stage = "embedding" if request.full_url.endswith("/embeddings") else "reranker"
        calls.append(stage)
        failed = embedding_fails if stage == "embedding" else reranker_fails
        if failed:
            if isinstance(failure, int):
                raise HTTPError(request.full_url, failure, "private-provider-body", {}, None)
            if failure == "timeout":
                raise TimeoutError("private-provider-body")
            return Response({"unexpected": "private-provider-body"})
        payload = json.loads(request.data)
        if stage == "embedding":
            return Response({"data": [{"embedding": [0.9, 0.1]} for _ in payload["input"]]})
        return Response({"results": [
            {"index": i, "relevance_score": 1.0} for i in range(len(payload["documents"]))
        ]})

    monkeypatch.setattr(embedding, "urlopen", request)
    monkeypatch.setattr(reranker, "urlopen", request)
    retriever = HybridRetriever(
        index=index,
        embedder=OpenAICompatibleEmbeddingProvider(
            base_url="https://private-provider.example/v1", api_key="private-key",
            model="Pro/BAAI/bge-m3", timeout_seconds=1,
        ),
        embedding_model="Pro/BAAI/bge-m3",
        chunk_schema_version="retrieval-corpus-v1",
        reranker=SiliconFlowRerankerProvider(
            base_url="https://private-provider.example/v1", api_key="private-key",
            model="reranker", timeout_seconds=1,
        ),
        reranker_model="reranker",
        # Fused RRF scores are far below this; fallback must NOT apply it.
        min_rerank_score=0.99,
    )
    kwargs = dict(
        query="社区互助", knowledge_release_id="release-reviewed-v1",
        release_content_hash="sha256:release-reviewed-v1", document_kind="theory_profile", limit=5,
    )
    trace = retriever.search_with_trace(**kwargs)
    if transient:
        chunks = index.list_chunks(
            retrieval_index_id=index_id, knowledge_release_id=kwargs["knowledge_release_id"],
            document_kind="theory_profile",
        )
        result = retriever.search_chunks(query=kwargs["query"], chunks=chunks, limit=5)
    else:
        result = trace.result
    assert result.hits
    assert result.hits[0].chunk.theory_id == "social-capital"
    assert result.degraded_reason == ",".join(
        name for failed, name in [
            (embedding_fails, "embedding_unavailable"), (reranker_fails, "reranker_unavailable")
        ] if failed
    )
    assert "embedding" in calls and "reranker" in calls
    if embedding_fails:
        assert trace.semantic == ()
        assert all(hit.retrieval_sources == ("lexical",) for hit in result.hits)
    if reranker_fails:
        assert [hit.chunk.chunk_id for hit in result.hits] == [hit.chunk_id for hit in trace.fused]
        assert all(hit.rerank_score is None for hit in result.hits)
        assert trace.reranked == ()
        assert result.reranker_model is None
        assert not result.mode.endswith("_reranked")
    else:
        assert result.mode == "lexical_reranked"
        assert all(hit.rerank_score == 1.0 for hit in result.hits)
    assert "retrieval_degraded" in caplog.text
    assert "private-provider" not in caplog.text and "private-key" not in caplog.text
    assert kwargs["query"] not in caplog.text
    if isinstance(failure, int):
        assert f"http_status={failure}" in caplog.text
    # A transient failure must not permanently switch off configured services.
    embedding_fails = reranker_fails = False
    restored = retriever.search(**kwargs)
    assert restored.degraded_reason is None
    assert restored.mode == "hybrid_reranked"


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


def test_material_vectors_are_reused_across_questions(tmp_path):
    index, _ = _ready_index(tmp_path)
    document_calls = []

    class Embedder:
        def embed_query(self, query):
            return [1.0, 0.0]

        def embed_documents(self, texts):
            document_calls.append(tuple(texts))
            return [[1.0, 0.0] for _ in texts]

    class Reranker:
        def rerank(self, *, query, documents, top_n):
            return tuple(RerankScore(index=i, score=0.9) for i in range(len(documents)))

    class Cache:
        values = {}

        def get_many(self, chunks, model):
            return [
                self.values.get((chunk.chunk_id, chunk.content_hash, model)) for chunk in chunks
            ]

        def put_many(self, chunks, model, vectors):
            for chunk, vector in zip(chunks, vectors, strict=True):
                self.values[(chunk.chunk_id, chunk.content_hash, model)] = vector

    retriever = HybridRetriever(
        index=index,
        embedder=Embedder(),
        embedding_model="test-embedding",
        chunk_schema_version="1",
        reranker=Reranker(),
        reranker_model="test-reranker",
        min_rerank_score=0,
    )
    chunks = (
        RetrievalChunk(
            chunk_id="file-1:parse-1:segment-1",
            document_kind="research_material",
            knowledge_id=None,
            theory_id=None,
            content_version=1,
            content_hash="content-1",
            title="记录",
            text="紫藤社区有37人参加夜间互助",
            source_ids=(),
        ),
    )
    cache = Cache()
    for question in ("紫藤社区人数", "多少居民参与互助"):
        result = retriever.search_chunks(query=question, chunks=chunks, limit=5, vector_cache=cache)
        assert result.hits[0].chunk.text == "紫藤社区有37人参加夜间互助"
    assert document_calls == [("紫藤社区有37人参加夜间互助",)]
