"""Release-bound lexical, dense, and reranked retrieval orchestration."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from qunxue_api.adapters.research_agent.embedding import EmbeddingProviderError
from qunxue_api.adapters.research_agent.reranker import (
    RerankerProviderError,
    RerankScore,
)
from qunxue_api.adapters.research_agent.retrieval import (
    RetrievalCandidate,
    lexical_relevance_score,
    rrf_fuse,
)

from .errors import RetrievalPipelineUnavailable
from .sqlite_index import (
    RetrievalChunk,
    RetrievalIndexManifest,
    RetrievalIndexUnavailable,
    SqliteRetrievalIndex,
)

_GENERIC_RETRIEVAL_TERMS = (
    "请检索知识库",
    "请解释",
    "为什么",
    "什么是",
    "如何",
    "理论",
    "概念",
    "观点",
)


class QueryEmbedder(Protocol):
    def embed_query(self, text: str) -> list[float]: ...


class CandidateReranker(Protocol):
    def rerank(
        self,
        *,
        query: str,
        documents: Sequence[str],
        top_n: int,
    ) -> tuple[RerankScore, ...]: ...


@dataclass(frozen=True, slots=True)
class HybridRetrievalHit:
    chunk: RetrievalChunk
    fused_score: float
    retrieval_sources: tuple[str, ...]
    rerank_score: float | None


@dataclass(frozen=True, slots=True)
class HybridRetrievalResult:
    retrieval_index_id: str
    mode: str
    embedding_model: str
    reranker_model: str | None
    degraded_reason: str | None
    hits: tuple[HybridRetrievalHit, ...]


@dataclass(frozen=True, slots=True)
class RetrievalStageHit:
    chunk_id: str
    score: float


@dataclass(frozen=True, slots=True)
class HybridRetrievalTrace:
    """Same-query rankings used by the frozen retrieval evaluation."""

    lexical: tuple[RetrievalStageHit, ...]
    semantic: tuple[RetrievalStageHit, ...]
    fused: tuple[RetrievalStageHit, ...]
    reranked: tuple[RetrievalStageHit, ...]
    rerank_query: str
    result: HybridRetrievalResult


class HybridRetriever:
    def __init__(
        self,
        *,
        index: SqliteRetrievalIndex,
        embedder: QueryEmbedder,
        embedding_model: str,
        chunk_schema_version: str,
        reranker: CandidateReranker,
        reranker_model: str,
        min_rerank_score: float,
        min_lexical_score: float = 0.12,
        recall_limit: int = 30,
    ) -> None:
        self._index = index
        self._embedder = embedder
        self._embedding_model = embedding_model
        self._chunk_schema_version = chunk_schema_version
        self._reranker = reranker
        self._reranker_model = reranker_model
        self._min_rerank_score = min_rerank_score
        self._min_lexical_score = min_lexical_score
        self._recall_limit = max(1, recall_limit)

    def require_ready_manifest(
        self,
        *,
        knowledge_release_id: str,
        release_content_hash: str,
    ) -> RetrievalIndexManifest:
        """Require the exact index identity used by live retrieval."""

        try:
            return self._index.find_ready_manifest(
                knowledge_release_id=knowledge_release_id,
                release_content_hash=release_content_hash,
                embedding_model=self._embedding_model,
                chunk_schema_version=self._chunk_schema_version,
            )
        except RetrievalIndexUnavailable as error:
            raise RetrievalPipelineUnavailable(
                "retrieval index is unavailable"
            ) from error

    def search(
        self,
        *,
        query: str,
        knowledge_release_id: str,
        release_content_hash: str,
        document_kind: str | None,
        limit: int,
    ) -> HybridRetrievalResult:
        return self.search_with_trace(
            query=query,
            knowledge_release_id=knowledge_release_id,
            release_content_hash=release_content_hash,
            document_kind=document_kind,
            limit=limit,
        ).result

    def search_with_trace(
        self,
        *,
        query: str,
        knowledge_release_id: str,
        release_content_hash: str,
        document_kind: str | None,
        limit: int,
    ) -> HybridRetrievalTrace:
        manifest = self.require_ready_manifest(
            knowledge_release_id=knowledge_release_id,
            release_content_hash=release_content_hash,
        )
        try:
            chunks = self._index.list_chunks(
                retrieval_index_id=manifest.retrieval_index_id,
                knowledge_release_id=knowledge_release_id,
                document_kind=document_kind,
            )
        except RetrievalIndexUnavailable as error:
            raise RetrievalPipelineUnavailable("retrieval index is unavailable") from error
        chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        lexical = self._lexical_candidates(query=query, chunks=chunks)
        try:
            query_vector = self._embedder.embed_query(query)
            semantic_hits = self._index.search(
                retrieval_index_id=manifest.retrieval_index_id,
                knowledge_release_id=knowledge_release_id,
                query_vector=query_vector,
                document_kind=document_kind,
                limit=self._recall_limit,
            )
            semantic = [
                RetrievalCandidate(
                    citation_id=hit.chunk.chunk_id,
                    score=hit.score,
                    source="semantic",
                )
                for hit in semantic_hits
            ]
        except EmbeddingProviderError as error:
            raise RetrievalPipelineUnavailable("embedding service is unavailable") from error
        except RetrievalIndexUnavailable as error:
            raise RetrievalPipelineUnavailable("retrieval index is unavailable") from error

        ranked_lists = tuple(value for value in (lexical, semantic) if value)
        fused = rrf_fuse(ranked_lists, limit=self._recall_limit) if ranked_lists else []
        safe_limit = max(1, limit)
        if lexical and semantic:
            mode = "hybrid"
        elif semantic:
            mode = "semantic"
        else:
            mode = "lexical"

        if not fused:
            result = HybridRetrievalResult(
                retrieval_index_id=manifest.retrieval_index_id,
                mode=mode,
                embedding_model=self._embedding_model,
                reranker_model=self._reranker_model,
                degraded_reason=None,
                hits=(),
            )
            return HybridRetrievalTrace(
                lexical=_stage_hits(lexical),
                semantic=_stage_hits(semantic),
                fused=(),
                reranked=(),
                rerank_query=query,
                result=result,
            )

        rerank_query = query
        try:
            scores = self._reranker.rerank(
                query=rerank_query,
                documents=tuple(chunks_by_id[item.citation_id].text for item in fused),
                top_n=len(fused),
            )
        except RerankerProviderError as error:
            raise RetrievalPipelineUnavailable("reranker service is unavailable") from error
        reranked = tuple(
            RetrievalStageHit(
                chunk_id=fused[item.index].citation_id,
                score=item.score,
            )
            for item in scores
        )
        hits = tuple(
            HybridRetrievalHit(
                chunk=chunks_by_id[fused[item.index].citation_id],
                fused_score=fused[item.index].score,
                retrieval_sources=fused[item.index].sources,
                rerank_score=item.score,
            )
            for item in scores
            if item.score >= self._min_rerank_score
        )[:safe_limit]
        result = HybridRetrievalResult(
            retrieval_index_id=manifest.retrieval_index_id,
            mode=f"{mode}_reranked",
            embedding_model=self._embedding_model,
            reranker_model=self._reranker_model,
            degraded_reason=None,
            hits=hits,
        )
        return HybridRetrievalTrace(
            lexical=_stage_hits(lexical),
            semantic=_stage_hits(semantic),
            fused=_stage_hits(fused),
            reranked=reranked,
            rerank_query=rerank_query,
            result=result,
        )

    def _lexical_candidates(
        self,
        *,
        query: str,
        chunks: tuple[RetrievalChunk, ...],
    ) -> list[RetrievalCandidate]:
        candidates = [
            RetrievalCandidate(
                citation_id=chunk.chunk_id,
                score=lexical_relevance_score(
                    _meaningful_lexical_text(query),
                    title=_meaningful_lexical_text(chunk.title),
                    text=_meaningful_lexical_text(chunk.text),
                ),
                source="lexical",
            )
            for chunk in chunks
        ]
        return sorted(
            (item for item in candidates if item.score >= self._min_lexical_score),
            key=lambda item: (-item.score, item.citation_id),
        )[: self._recall_limit]


def _meaningful_lexical_text(value: str) -> str:
    result = value
    for term in _GENERIC_RETRIEVAL_TERMS:
        result = result.replace(term, "")
    return result


def _stage_hits(values: Sequence[RetrievalCandidate]) -> tuple[RetrievalStageHit, ...]:
    return tuple(RetrievalStageHit(chunk_id=item.citation_id, score=item.score) for item in values)
