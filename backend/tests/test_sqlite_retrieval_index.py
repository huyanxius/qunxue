from pathlib import Path

import pytest

from qunxue_api.adapters.retrieval import (
    RetrievalChunk,
    RetrievalIndexMismatch,
    SqliteRetrievalIndex,
)


def _index(path: Path) -> SqliteRetrievalIndex:
    return SqliteRetrievalIndex(path)


def _chunks() -> tuple[RetrievalChunk, ...]:
    return (
        RetrievalChunk(
            chunk_id="theory:social-capital:v2:0",
            document_kind="theory_profile",
            knowledge_id="D2:P001",
            theory_id="social-capital",
            content_version=2,
            content_hash="sha256:social-capital-v2",
            title="社会资本理论",
            text="社会资本通过信任、规范和关系网络支持集体行动。",
            source_ids=("source:putnam",),
        ),
        RetrievalChunk(
            chunk_id="theory:symbolic-interaction:v1:0",
            document_kind="theory_profile",
            knowledge_id="D2:P002",
            theory_id="symbolic-interaction",
            content_version=1,
            content_hash="sha256:symbolic-interaction-v1",
            title="符号互动论",
            text="行动者在持续互动中协商意义并形成自我理解。",
            source_ids=("source:mead",),
        ),
    )


def test_rebuild_is_deterministic_and_searches_only_the_pinned_release(
    tmp_path: Path,
) -> None:
    index = _index(tmp_path / "retrieval.db")
    chunks = _chunks()

    first = index.rebuild(
        knowledge_release_id="release-reviewed-v1",
        release_content_hash="sha256:release-reviewed-v1",
        embedding_model="Pro/BAAI/bge-m3",
        chunk_schema_version="theory-profile-v1",
        chunks=chunks,
        vectors=((1.0, 0.0), (0.0, 1.0)),
    )
    second = index.rebuild(
        knowledge_release_id="release-reviewed-v1",
        release_content_hash="sha256:release-reviewed-v1",
        embedding_model="Pro/BAAI/bge-m3",
        chunk_schema_version="theory-profile-v1",
        chunks=chunks,
        vectors=((1.0, 0.0), (0.0, 1.0)),
    )

    assert first == second
    assert first.point_count == 2
    assert first.vector_dimension == 2
    assert first.status == "ready"
    assert index.search(
        retrieval_index_id=first.retrieval_index_id,
        knowledge_release_id="release-reviewed-v1",
        query_vector=(0.9, 0.1),
        document_kind="theory_profile",
        limit=2,
    )[0].chunk.chunk_id == "theory:social-capital:v2:0"

    with pytest.raises(RetrievalIndexMismatch, match="knowledge release"):
        index.search(
            retrieval_index_id=first.retrieval_index_id,
            knowledge_release_id="release-other",
            query_vector=(0.9, 0.1),
            document_kind="theory_profile",
            limit=2,
        )


def test_rebuild_rejects_vectors_with_inconsistent_dimensions(tmp_path: Path) -> None:
    index = _index(tmp_path / "retrieval.db")

    with pytest.raises(ValueError, match="vector dimension"):
        index.rebuild(
            knowledge_release_id="release-reviewed-v1",
            release_content_hash="sha256:release-reviewed-v1",
            embedding_model="Pro/BAAI/bge-m3",
            chunk_schema_version="theory-profile-v1",
            chunks=_chunks(),
            vectors=((1.0, 0.0), (0.0, 1.0, 0.0)),
        )
