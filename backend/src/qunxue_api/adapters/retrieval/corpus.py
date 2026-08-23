"""Build stable retrieval units from one immutable knowledge release."""

import json
from collections.abc import Sequence
from hashlib import sha256

from qunxue_api.modules.knowledge_catalog import (
    KnowledgeEntryDetail,
    KnowledgeReviewStatus,
    TheoryProfileSnapshot,
)

from .sqlite_index import RetrievalChunk

THEORY_PROFILE_CHUNK_SCHEMA_VERSION = "theory-profile-v1"
KNOWLEDGE_ENTRY_CHUNK_SCHEMA_VERSION = "knowledge-entry-v1"


def build_theory_profile_chunks(
    profiles: Sequence[TheoryProfileSnapshot],
) -> tuple[RetrievalChunk, ...]:
    chunks = []
    for profile in sorted(profiles, key=lambda item: item.theory_id):
        if not profile.match_eligible or profile.review_status not in {
            KnowledgeReviewStatus.PRE_REVIEW_COMPLETED,
            KnowledgeReviewStatus.REVIEWED,
        }:
            continue
        text = "\n".join(
            (
                f"理论：{profile.title}",
                f"核心命题：{_join(profile.core_propositions)}",
                f"适用现象：{_join(profile.applicable_phenomena)}",
                f"分析层次：{_join(profile.analysis_levels)}",
                f"适用前提：{_join(profile.prerequisites)}",
                f"排除信号：{_join(profile.exclusion_signals)}",
                f"可观察证据：{_join(profile.observable_evidence)}",
            )
        )
        chunk_id = f"theory-profile:{profile.theory_id}:v{profile.content_version}"
        chunks.append(
            RetrievalChunk(
                chunk_id=chunk_id,
                document_kind="theory_profile",
                knowledge_id=(
                    profile.related_knowledge_ids[0] if profile.related_knowledge_ids else None
                ),
                theory_id=profile.theory_id,
                content_version=profile.content_version,
                content_hash=_content_hash(
                    chunk_id=chunk_id,
                    text=text,
                    source_ids=profile.source_ids,
                ),
                title=profile.title,
                text=text,
                source_ids=profile.source_ids,
            )
        )
    return tuple(chunks)


def build_knowledge_entry_chunks(
    entries: Sequence[KnowledgeEntryDetail],
    *,
    max_chars: int = 1600,
    overlap_chars: int = 160,
) -> tuple[RetrievalChunk, ...]:
    chunks = []
    for entry in sorted(entries, key=lambda item: item.summary.knowledge_id):
        if not entry.summary.eligibility.rag_eligible:
            continue
        prefix = f"标题：{entry.summary.title}\n别名：{_join(entry.aliases)}"
        content_parts = _split_text(
            entry.content,
            max_chars=max(200, max_chars - len(prefix) - 1),
            overlap_chars=overlap_chars,
        ) or ("",)
        source_ids = tuple(source.source_id for source in entry.sources)
        for index, content in enumerate(content_parts):
            text = f"{prefix}\n{content}".rstrip()
            chunk_id = (
                f"knowledge-entry:{entry.summary.knowledge_id}:"
                f"v{entry.summary.content_version}:{index}"
            )
            chunks.append(
                RetrievalChunk(
                    chunk_id=chunk_id,
                    document_kind="knowledge_entry",
                    knowledge_id=entry.summary.knowledge_id,
                    theory_id=(
                        entry.theory_profile.theory_id if entry.theory_profile is not None else None
                    ),
                    content_version=entry.summary.content_version,
                    content_hash=_content_hash(
                        chunk_id=chunk_id,
                        text=text,
                        source_ids=source_ids,
                    ),
                    title=entry.summary.title,
                    text=text,
                    source_ids=source_ids,
                )
            )
    return tuple(chunks)


def _split_text(
    value: str,
    *,
    max_chars: int,
    overlap_chars: int,
) -> tuple[str, ...]:
    normalized = value.replace("\r\n", "\n").strip()
    if not normalized:
        return ()
    if len(normalized) <= max_chars:
        return (normalized,)
    overlap = max(0, min(overlap_chars, max_chars // 3))
    step = max_chars - overlap
    return tuple(
        normalized[start : start + max_chars].strip()
        for start in range(0, len(normalized), step)
        if normalized[start : start + max_chars].strip()
    )


def _content_hash(*, chunk_id: str, text: str, source_ids: tuple[str, ...]) -> str:
    payload = json.dumps(
        {"chunk_id": chunk_id, "source_ids": source_ids, "text": text},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return f"sha256:{sha256(payload).hexdigest()}"


def _join(values: Sequence[str]) -> str:
    return "；".join(value.strip() for value in values if value.strip()) or "未提供"
