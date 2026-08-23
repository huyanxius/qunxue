"""Persistent, provider-independent retrieval adapters."""

from .corpus import (
    KNOWLEDGE_ENTRY_CHUNK_SCHEMA_VERSION,
    THEORY_PROFILE_CHUNK_SCHEMA_VERSION,
    build_knowledge_entry_chunks,
    build_theory_profile_chunks,
)
from .errors import RetrievalPipelineUnavailable
from .hybrid import (
    HybridRetrievalHit,
    HybridRetrievalResult,
    HybridRetrievalTrace,
    HybridRetriever,
    RetrievalStageHit,
)
from .index_builder import RetrievalIndexBuilder
from .release_corpus import (
    RETRIEVAL_CORPUS_SCHEMA_VERSION,
    PublishedReleaseCorpus,
    PublishedReleaseCorpusCollector,
)
from .sqlite_index import (
    RetrievalChunk,
    RetrievalIndexManifest,
    RetrievalIndexMismatch,
    RetrievalIndexUnavailable,
    SqliteRetrievalIndex,
    VectorSearchHit,
)

__all__ = [
    "KNOWLEDGE_ENTRY_CHUNK_SCHEMA_VERSION",
    "HybridRetrievalHit",
    "HybridRetrievalResult",
    "HybridRetrievalTrace",
    "HybridRetriever",
    "RetrievalChunk",
    "RetrievalIndexManifest",
    "RetrievalIndexMismatch",
    "RetrievalIndexUnavailable",
    "RetrievalPipelineUnavailable",
    "RetrievalStageHit",
    "RetrievalIndexBuilder",
    "RETRIEVAL_CORPUS_SCHEMA_VERSION",
    "PublishedReleaseCorpus",
    "PublishedReleaseCorpusCollector",
    "SqliteRetrievalIndex",
    "THEORY_PROFILE_CHUNK_SCHEMA_VERSION",
    "VectorSearchHit",
    "build_knowledge_entry_chunks",
    "build_theory_profile_chunks",
]
