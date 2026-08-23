"""Collect the retrieval corpus pinned to one immutable knowledge release."""

from dataclasses import dataclass

from qunxue_api.modules.knowledge_catalog import (
    KnowledgeCatalog,
    KnowledgeReleaseLevel,
    KnowledgeReleaseRef,
    KnowledgeReviewStatus,
)

from .corpus import build_knowledge_entry_chunks, build_theory_profile_chunks
from .sqlite_index import RetrievalChunk

RETRIEVAL_CORPUS_SCHEMA_VERSION = "retrieval-corpus-v1"


@dataclass(frozen=True, slots=True)
class PublishedReleaseCorpus:
    release: KnowledgeReleaseRef
    chunks: tuple[RetrievalChunk, ...]
    knowledge_entry_count: int
    theory_profile_count: int


class PublishedReleaseCorpusCollector:
    """Read every eligible unit without changing or selecting another release."""

    def __init__(self, *, catalog: KnowledgeCatalog, page_size: int = 100) -> None:
        if page_size < 1:
            raise ValueError("retrieval corpus page size must be positive")
        self._catalog = catalog
        self._page_size = page_size

    def collect(self, *, release_id: str) -> PublishedReleaseCorpus:
        page = self._catalog.browse(
            release_id=release_id,
            query=None,
            category=None,
            category_id=None,
            dimension_id=None,
            cursor=None,
            limit=self._page_size,
        )
        release = page.release
        if release.knowledge_release_id != release_id:
            raise ValueError("knowledge catalog returned a different release")
        if release.level is not KnowledgeReleaseLevel.FINAL:
            raise ValueError("retrieval corpus requires an immutable final release")
        entries = self._catalog.list_rag_entries(release_id=release_id)
        if any(
            detail.release != release or not detail.summary.eligibility.rag_eligible
            for detail in entries
        ):
            raise ValueError("RAG entry is not bound to the collected release")
        profiles = self._catalog.list_match_profiles(release_id=release_id)
        allowed_review_statuses = {
            KnowledgeReviewStatus.PRE_REVIEW_COMPLETED,
            KnowledgeReviewStatus.REVIEWED,
        }
        if any(
            not profile.match_eligible or profile.review_status not in allowed_review_statuses
            for profile in profiles
        ):
            raise ValueError("theory profile has not passed the MATCH review gate")
        chunks = tuple(
            sorted(
                (
                    *build_knowledge_entry_chunks(entries),
                    *build_theory_profile_chunks(profiles),
                ),
                key=lambda item: item.chunk_id,
            )
        )
        return PublishedReleaseCorpus(
            release=release,
            chunks=chunks,
            knowledge_entry_count=len(entries),
            theory_profile_count=len(profiles),
        )
