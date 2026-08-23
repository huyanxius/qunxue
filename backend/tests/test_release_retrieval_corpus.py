import pytest

from qunxue_api.adapters.retrieval.release_corpus import (
    PublishedReleaseCorpusCollector,
)
from qunxue_api.modules.knowledge_catalog import (
    KnowledgeEntryDetail,
    KnowledgeEntryPage,
    KnowledgeEntrySummary,
    KnowledgeReleaseLevel,
    KnowledgeReleaseRef,
    KnowledgeReviewStatus,
    KnowledgeUseEligibility,
    TheoryProfileSnapshot,
)


def test_collector_keeps_all_rag_entries_and_pre_reviewed_profiles() -> None:
    release = KnowledgeReleaseRef(
        knowledge_release_id="release-final-v1",
        level=KnowledgeReleaseLevel.FINAL,
        content_hash="sha256:release-final-v1",
    )
    eligible_first = _summary("D1:C001", rag_eligible=True)
    ineligible = _summary("D1:C002", rag_eligible=False)
    eligible_second = _summary("D1:C003", rag_eligible=True)

    class Catalog:
        def browse(self, *, release_id, cursor, **_filters):
            if release_id != release.knowledge_release_id:
                raise LookupError(release_id)
            if cursor is None:
                return KnowledgeEntryPage(
                    release=release,
                    entries=(eligible_first, ineligible),
                    total_count=3,
                    next_cursor="second-page",
                )
            if cursor == "second-page":
                return KnowledgeEntryPage(
                    release=release,
                    entries=(eligible_second,),
                    total_count=3,
                    next_cursor=None,
                )
            raise ValueError("unexpected cursor")

        def get_entry(self, *, knowledge_id, release_id):
            if release_id != release.knowledge_release_id:
                raise LookupError(release_id)
            return _detail(
                release,
                {
                    eligible_first.knowledge_id: eligible_first,
                    eligible_second.knowledge_id: eligible_second,
                }[knowledge_id],
            )

        def list_rag_entries(self, *, release_id):
            return (
                self.get_entry(
                    knowledge_id=eligible_first.knowledge_id,
                    release_id=release_id,
                ),
                self.get_entry(
                    knowledge_id=eligible_second.knowledge_id,
                    release_id=release_id,
                ),
            )

        def list_match_profiles(self, *, release_id):
            if release_id != release.knowledge_release_id:
                raise LookupError(release_id)
            return (_profile(KnowledgeReviewStatus.PRE_REVIEW_COMPLETED),)

    corpus = PublishedReleaseCorpusCollector(catalog=Catalog(), page_size=2).collect(
        release_id=release.knowledge_release_id
    )

    assert corpus.release == release
    assert corpus.knowledge_entry_count == 2
    assert corpus.theory_profile_count == 1
    assert [chunk.chunk_id for chunk in corpus.chunks] == [
        "knowledge-entry:D1:C001:v1:0",
        "knowledge-entry:D1:C003:v1:0",
        "theory-profile:theory-social-capital:v1",
    ]


def test_collector_rejects_a_profile_that_has_not_passed_a_match_review_gate() -> None:
    release = KnowledgeReleaseRef(
        knowledge_release_id="release-final-v1",
        level=KnowledgeReleaseLevel.FINAL,
        content_hash="sha256:release-final-v1",
    )

    class Catalog:
        def browse(self, **_filters):
            return KnowledgeEntryPage(
                release=release,
                entries=(),
                total_count=0,
                next_cursor=None,
            )

        def list_match_profiles(self, **_filters):
            return (_profile(KnowledgeReviewStatus.PENDING),)

        def list_rag_entries(self, **_filters):
            return ()

    with pytest.raises(ValueError, match="review gate"):
        PublishedReleaseCorpusCollector(catalog=Catalog()).collect(
            release_id=release.knowledge_release_id
        )


def _summary(knowledge_id: str, *, rag_eligible: bool) -> KnowledgeEntrySummary:
    return KnowledgeEntrySummary(
        knowledge_id=knowledge_id,
        content_version=1,
        title=f"知识 {knowledge_id}",
        category_id="D1:C",
        category="基础概念",
        dimension_id="D1",
        dimension="本体论",
        directory_path=(),
        review_status=KnowledgeReviewStatus.REVIEWED,
        eligibility=KnowledgeUseEligibility(
            browse_eligible=True,
            rag_eligible=rag_eligible,
            training_candidate_eligible=False,
            match_eligible=False,
            review_record_ids=(f"review:{knowledge_id}",),
        ),
    )


def _detail(
    release: KnowledgeReleaseRef,
    summary: KnowledgeEntrySummary,
) -> KnowledgeEntryDetail:
    return KnowledgeEntryDetail(
        release=release,
        summary=summary,
        aliases=(),
        content=f"{summary.title} 的正文。",
        sources=(),
        relations=(),
        theory_profile=None,
    )


def _profile(review_status: KnowledgeReviewStatus) -> TheoryProfileSnapshot:
    return TheoryProfileSnapshot(
        theory_id="theory-social-capital",
        related_knowledge_ids=("D1:C001",),
        title="社会资本理论",
        core_propositions=("信任与互惠规范支持集体行动",),
        applicable_phenomena=("社区互助",),
        analysis_levels=("关系", "社区"),
        prerequisites=("存在可持续的关系网络",),
        exclusion_signals=("互动完全是一次性的",),
        observable_evidence=("互助频率",),
        competing_or_complementary_theory_ids=(),
        source_ids=("source:putnam",),
        content_version=1,
        review_status=review_status,
        match_eligible=True,
    )
