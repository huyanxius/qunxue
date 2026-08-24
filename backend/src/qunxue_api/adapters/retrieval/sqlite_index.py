"""A small release-bound SQLite vector index for the current corpus scale."""

import json
import math
import sqlite3
import struct
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


class RetrievalIndexUnavailable(RuntimeError):
    """No ready retrieval index satisfies the requested identity."""


class RetrievalIndexMismatch(RetrievalIndexUnavailable):
    """The caller tried to cross an immutable release or vector boundary."""


@dataclass(frozen=True, slots=True)
class RetrievalChunk:
    chunk_id: str
    document_kind: str
    knowledge_id: str | None
    theory_id: str | None
    content_version: int
    content_hash: str
    title: str
    text: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RetrievalIndexManifest:
    retrieval_index_id: str
    knowledge_release_id: str
    release_content_hash: str
    embedding_model: str
    chunk_schema_version: str
    vector_dimension: int
    point_count: int
    manifest_content_hash: str
    status: str


@dataclass(frozen=True, slots=True)
class VectorSearchHit:
    chunk: RetrievalChunk
    score: float


class SqliteRetrievalIndex:
    """Persist vectors separately from the product database and query by cosine."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def rebuild(
        self,
        *,
        knowledge_release_id: str,
        release_content_hash: str,
        embedding_model: str,
        chunk_schema_version: str,
        chunks: Sequence[RetrievalChunk],
        vectors: Sequence[Sequence[float]],
    ) -> RetrievalIndexManifest:
        chunk_values = tuple(chunks)
        vector_values = tuple(tuple(float(value) for value in vector) for vector in vectors)
        if not chunk_values:
            raise ValueError("retrieval index requires at least one chunk")
        if len(chunk_values) != len(vector_values):
            raise ValueError("chunk and vector counts must match")
        vector_dimension = len(vector_values[0])
        if vector_dimension < 1 or any(len(vector) != vector_dimension for vector in vector_values):
            raise ValueError("every vector dimension must match")
        if any(not math.isfinite(value) for vector in vector_values for value in vector):
            raise ValueError("retrieval vectors must contain finite numbers")

        manifest = _build_manifest(
            knowledge_release_id=knowledge_release_id,
            release_content_hash=release_content_hash,
            embedding_model=embedding_model,
            chunk_schema_version=chunk_schema_version,
            chunks=chunk_values,
            vector_dimension=vector_dimension,
        )
        try:
            existing = self.get_manifest(manifest.retrieval_index_id)
        except RetrievalIndexUnavailable:
            pass
        else:
            if existing != manifest:
                raise RetrievalIndexMismatch("ready retrieval index identity is inconsistent")
            return existing
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO retrieval_indexes (
                    retrieval_index_id,
                    knowledge_release_id,
                    release_content_hash,
                    embedding_model,
                    chunk_schema_version,
                    vector_dimension,
                    point_count,
                    manifest_content_hash,
                    status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'building')
                ON CONFLICT(retrieval_index_id) DO UPDATE SET
                    point_count = excluded.point_count,
                    manifest_content_hash = excluded.manifest_content_hash,
                    status = 'building'
                """,
                (
                    manifest.retrieval_index_id,
                    manifest.knowledge_release_id,
                    manifest.release_content_hash,
                    manifest.embedding_model,
                    manifest.chunk_schema_version,
                    manifest.vector_dimension,
                    manifest.point_count,
                    manifest.manifest_content_hash,
                ),
            )
            connection.execute(
                "DELETE FROM retrieval_points WHERE retrieval_index_id = ?",
                (manifest.retrieval_index_id,),
            )
            connection.executemany(
                """
                INSERT INTO retrieval_points (
                    retrieval_index_id,
                    chunk_id,
                    document_kind,
                    knowledge_id,
                    theory_id,
                    content_version,
                    content_hash,
                    title,
                    text,
                    source_ids_json,
                    vector
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        manifest.retrieval_index_id,
                        chunk.chunk_id,
                        chunk.document_kind,
                        chunk.knowledge_id,
                        chunk.theory_id,
                        chunk.content_version,
                        chunk.content_hash,
                        chunk.title,
                        chunk.text,
                        json.dumps(chunk.source_ids, ensure_ascii=False),
                        _pack_vector(vector),
                    )
                    for chunk, vector in zip(chunk_values, vector_values, strict=True)
                ),
            )
            connection.execute(
                "UPDATE retrieval_indexes SET status = 'ready' WHERE retrieval_index_id = ?",
                (manifest.retrieval_index_id,),
            )
        return manifest

    def search(
        self,
        *,
        retrieval_index_id: str,
        knowledge_release_id: str,
        query_vector: Sequence[float],
        document_kind: str | None,
        limit: int,
    ) -> tuple[VectorSearchHit, ...]:
        manifest = self.get_manifest(retrieval_index_id)
        if manifest.knowledge_release_id != knowledge_release_id:
            raise RetrievalIndexMismatch("retrieval index belongs to a different knowledge release")
        values = tuple(float(value) for value in query_vector)
        if len(values) != manifest.vector_dimension:
            raise RetrievalIndexMismatch("query vector dimension does not match index")
        query_norm = math.sqrt(sum(value * value for value in values))
        if query_norm == 0:
            raise ValueError("query vector must not be zero")
        safe_limit = max(1, limit)
        where = "retrieval_index_id = ?"
        parameters: list[object] = [retrieval_index_id]
        if document_kind is not None:
            where += " AND document_kind = ?"
            parameters.append(document_kind)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    chunk_id,
                    document_kind,
                    knowledge_id,
                    theory_id,
                    content_version,
                    content_hash,
                    title,
                    text,
                    source_ids_json,
                    vector
                FROM retrieval_points
                WHERE {where}
                """,
                parameters,
            ).fetchall()
        hits = [
            VectorSearchHit(
                chunk=_chunk_from_row(row),
                score=_cosine_similarity(values, _unpack_vector(row[9])),
            )
            for row in rows
        ]
        return tuple(sorted(hits, key=lambda item: (-item.score, item.chunk.chunk_id))[:safe_limit])

    def list_chunks(
        self,
        *,
        retrieval_index_id: str,
        knowledge_release_id: str,
        document_kind: str | None,
    ) -> tuple[RetrievalChunk, ...]:
        manifest = self.get_manifest(retrieval_index_id)
        if manifest.knowledge_release_id != knowledge_release_id:
            raise RetrievalIndexMismatch("retrieval index belongs to a different knowledge release")
        where = "retrieval_index_id = ?"
        parameters: list[object] = [retrieval_index_id]
        if document_kind is not None:
            where += " AND document_kind = ?"
            parameters.append(document_kind)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    chunk_id,
                    document_kind,
                    knowledge_id,
                    theory_id,
                    content_version,
                    content_hash,
                    title,
                    text,
                    source_ids_json
                FROM retrieval_points
                WHERE {where}
                ORDER BY chunk_id
                """,
                parameters,
            ).fetchall()
        return tuple(_chunk_from_row(row) for row in rows)

    def get_manifest(self, retrieval_index_id: str) -> RetrievalIndexManifest:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    retrieval_index_id,
                    knowledge_release_id,
                    release_content_hash,
                    embedding_model,
                    chunk_schema_version,
                    vector_dimension,
                    point_count,
                    manifest_content_hash,
                    status
                FROM retrieval_indexes
                WHERE retrieval_index_id = ?
                """,
                (retrieval_index_id,),
            ).fetchone()
        if row is None or row[8] != "ready":
            raise RetrievalIndexUnavailable("retrieval index is not ready")
        return RetrievalIndexManifest(*row)

    def find_ready_manifest(
        self,
        *,
        knowledge_release_id: str,
        release_content_hash: str,
        embedding_model: str,
        chunk_schema_version: str,
    ) -> RetrievalIndexManifest:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    manifest.retrieval_index_id,
                    manifest.knowledge_release_id,
                    manifest.release_content_hash,
                    manifest.embedding_model,
                    manifest.chunk_schema_version,
                    manifest.vector_dimension,
                    manifest.point_count,
                    manifest.manifest_content_hash,
                    manifest.status
                FROM retrieval_indexes AS manifest
                WHERE manifest.knowledge_release_id = ?
                  AND manifest.release_content_hash = ?
                  AND manifest.embedding_model = ?
                  AND manifest.chunk_schema_version = ?
                  AND manifest.status = 'ready'
                  AND manifest.point_count > 0
                  AND (
                      SELECT COUNT(*)
                      FROM retrieval_points AS point
                      WHERE point.retrieval_index_id = manifest.retrieval_index_id
                  ) = manifest.point_count
                ORDER BY manifest.retrieval_index_id
                LIMIT 1
                """,
                (
                    knowledge_release_id,
                    release_content_hash,
                    embedding_model,
                    chunk_schema_version,
                ),
            ).fetchone()
        if row is None:
            raise RetrievalIndexUnavailable("no ready index matches the release and model")
        return RetrievalIndexManifest(*row)

    def _initialize_schema(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS retrieval_indexes (
                    retrieval_index_id TEXT PRIMARY KEY,
                    knowledge_release_id TEXT NOT NULL,
                    release_content_hash TEXT NOT NULL,
                    embedding_model TEXT NOT NULL,
                    chunk_schema_version TEXT NOT NULL,
                    vector_dimension INTEGER NOT NULL,
                    point_count INTEGER NOT NULL,
                    manifest_content_hash TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('building', 'ready', 'failed'))
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS retrieval_points (
                    retrieval_index_id TEXT NOT NULL,
                    chunk_id TEXT NOT NULL,
                    document_kind TEXT NOT NULL,
                    knowledge_id TEXT,
                    theory_id TEXT,
                    content_version INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    title TEXT NOT NULL,
                    text TEXT NOT NULL,
                    source_ids_json TEXT NOT NULL,
                    vector BLOB NOT NULL,
                    PRIMARY KEY (retrieval_index_id, chunk_id),
                    FOREIGN KEY (retrieval_index_id)
                        REFERENCES retrieval_indexes(retrieval_index_id)
                        ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_retrieval_points_kind
                ON retrieval_points (retrieval_index_id, document_kind)
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._path)
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()


def _build_manifest(
    *,
    knowledge_release_id: str,
    release_content_hash: str,
    embedding_model: str,
    chunk_schema_version: str,
    chunks: tuple[RetrievalChunk, ...],
    vector_dimension: int,
) -> RetrievalIndexManifest:
    points = [
        {
            "chunk_id": chunk.chunk_id,
            "document_kind": chunk.document_kind,
            "knowledge_id": chunk.knowledge_id,
            "theory_id": chunk.theory_id,
            "content_version": chunk.content_version,
            "content_hash": chunk.content_hash,
        }
        for chunk in chunks
    ]
    payload = json.dumps(
        {
            "knowledge_release_id": knowledge_release_id,
            "release_content_hash": release_content_hash,
            "embedding_model": embedding_model,
            "chunk_schema_version": chunk_schema_version,
            "vector_dimension": vector_dimension,
            "points": sorted(points, key=lambda item: item["chunk_id"]),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    content_hash = f"sha256:{sha256(payload).hexdigest()}"
    return RetrievalIndexManifest(
        retrieval_index_id=f"retrieval-index:{content_hash.removeprefix('sha256:')[:24]}",
        knowledge_release_id=knowledge_release_id,
        release_content_hash=release_content_hash,
        embedding_model=embedding_model,
        chunk_schema_version=chunk_schema_version,
        vector_dimension=vector_dimension,
        point_count=len(chunks),
        manifest_content_hash=content_hash,
        status="ready",
    )


def _pack_vector(vector: Sequence[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def _unpack_vector(value: bytes) -> tuple[float, ...]:
    if len(value) % 4:
        raise RetrievalIndexUnavailable("stored vector has an invalid byte length")
    return struct.unpack(f"<{len(value) // 4}f", value)


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    right_norm = math.sqrt(sum(value * value for value in right))
    if right_norm == 0:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


def _chunk_from_row(row: sqlite3.Row | tuple[object, ...]) -> RetrievalChunk:
    return RetrievalChunk(
        chunk_id=str(row[0]),
        document_kind=str(row[1]),
        knowledge_id=str(row[2]) if row[2] is not None else None,
        theory_id=str(row[3]) if row[3] is not None else None,
        content_version=int(row[4]),
        content_hash=str(row[5]),
        title=str(row[6]),
        text=str(row[7]),
        source_ids=tuple(str(value) for value in json.loads(str(row[8]))),
    )
