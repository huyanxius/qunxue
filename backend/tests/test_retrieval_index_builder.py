from pathlib import Path

from qunxue_api.adapters.retrieval import RetrievalChunk, SqliteRetrievalIndex
from qunxue_api.adapters.retrieval.index_builder import RetrievalIndexBuilder
from qunxue_api.modules.knowledge_catalog import (
    KnowledgeReleaseLevel,
    KnowledgeReleaseRef,
)


def test_index_builder_batches_remote_embeddings_and_persists_ready_manifest(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, ...]] = []

    class Embedder:
        def embed_documents(self, texts):
            values = tuple(texts)
            calls.append(values)
            return [
                [1.0, 0.0] if "社会资本" in text else [0.0, 1.0]
                for text in values
            ]

    chunks = tuple(
        RetrievalChunk(
            chunk_id=f"theory-profile:theory-{index}:v1",
            document_kind="theory_profile",
            knowledge_id=f"D2:P00{index}",
            theory_id=f"theory-{index}",
            content_version=1,
            content_hash=f"sha256:theory-{index}",
            title=title,
            text=f"理论：{title}",
            source_ids=(f"source:{index}",),
        )
        for index, title in ((1, "社会资本理论"), (2, "符号互动论"), (3, "惯习理论"))
    )
    release = KnowledgeReleaseRef(
        knowledge_release_id="release-reviewed-v1",
        level=KnowledgeReleaseLevel.FINAL,
        content_hash="sha256:release-reviewed-v1",
    )
    index = SqliteRetrievalIndex(tmp_path / "retrieval.db")

    manifest = RetrievalIndexBuilder(
        index=index,
        embedder=Embedder(),
        embedding_model="Pro/BAAI/bge-m3",
        chunk_schema_version="retrieval-corpus-v1",
        batch_size=2,
    ).build(release=release, chunks=chunks)

    assert calls == [
        ("理论：社会资本理论", "理论：符号互动论"),
        ("理论：惯习理论",),
    ]
    assert manifest.point_count == 3
    assert index.find_ready_manifest(
        knowledge_release_id=release.knowledge_release_id,
        release_content_hash=release.content_hash,
        embedding_model="Pro/BAAI/bge-m3",
        chunk_schema_version="retrieval-corpus-v1",
    ) == manifest
