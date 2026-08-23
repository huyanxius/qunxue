"""Batch-build a persistent retrieval index through a replaceable embedder."""

from collections.abc import Sequence
from typing import Protocol

from qunxue_api.modules.knowledge_catalog import KnowledgeReleaseRef

from .sqlite_index import RetrievalChunk, RetrievalIndexManifest, SqliteRetrievalIndex


class DocumentEmbedder(Protocol):
    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...


class RetrievalIndexBuilder:
    def __init__(
        self,
        *,
        index: SqliteRetrievalIndex,
        embedder: DocumentEmbedder,
        embedding_model: str,
        chunk_schema_version: str,
        batch_size: int = 32,
    ) -> None:
        if batch_size < 1:
            raise ValueError("embedding batch size must be positive")
        self._index = index
        self._embedder = embedder
        self._embedding_model = embedding_model
        self._chunk_schema_version = chunk_schema_version
        self._batch_size = batch_size

    def build(
        self,
        *,
        release: KnowledgeReleaseRef,
        chunks: Sequence[RetrievalChunk],
    ) -> RetrievalIndexManifest:
        values = tuple(chunks)
        if not values:
            raise ValueError("retrieval corpus is empty")
        vectors: list[list[float]] = []
        for start in range(0, len(values), self._batch_size):
            batch = values[start : start + self._batch_size]
            embedded = self._embedder.embed_documents([item.text for item in batch])
            if len(embedded) != len(batch):
                raise ValueError("embedding response count does not match batch")
            vectors.extend(embedded)
        return self._index.rebuild(
            knowledge_release_id=release.knowledge_release_id,
            release_content_hash=release.content_hash,
            embedding_model=self._embedding_model,
            chunk_schema_version=self._chunk_schema_version,
            chunks=values,
            vectors=vectors,
        )
