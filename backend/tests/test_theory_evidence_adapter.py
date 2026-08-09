from dataclasses import dataclass
from uuid import UUID

from qunxue_api.adapters.theory_evidence import CatalogTheoryEvidenceSource
from qunxue_api.modules.knowledge_catalog import (
    KnowledgeEntryDetail,
    KnowledgeEntryPage,
    KnowledgeEntrySummary,
    KnowledgeReleaseLevel,
    KnowledgeReleaseRef,
    KnowledgeReviewStatus,
    KnowledgeUseEligibility,
    SourceRecordSnapshot,
    SourceVerificationStatus,
    TheoryProfileSnapshot,
)
from qunxue_api.modules.research_intake import ConfirmedPhenomenonSnapshot

RELEASE = KnowledgeReleaseRef(
    knowledge_release_id="release-reviewed-v1",
    level=KnowledgeReleaseLevel.PREVIEW,
    content_hash="sha256:reviewed-release",
)
PHENOMENON = ConfirmedPhenomenonSnapshot(
    task_id=UUID(int=1),
    phenomenon_query_id=UUID(int=2),
    version=1,
    phenomenon="社区互助为何随成员流动减少？",
    research_intent="比较不同解释",
    context="社区成员持续流动",
    content_hash="phenomenon-hash",
)


@dataclass
class _CatalogFixture:
    entries: tuple[KnowledgeEntryDetail, ...]

    def current_release(self, *, purpose: object) -> KnowledgeReleaseRef:
        del purpose
        return RELEASE

    def browse(
        self,
        *,
        release_id: str,
        query: str | None,
        category: str | None,
        category_id: str | None,
        dimension_id: str | None,
        cursor: str | None,
        limit: int,
    ) -> KnowledgeEntryPage:
        del query, category, category_id, dimension_id
        assert release_id == RELEASE.knowledge_release_id
        offset = int(cursor) if cursor else 0
        page_size = min(2, limit)
        page_entries = self.entries[offset : offset + page_size]
        next_offset = offset + len(page_entries)
        return KnowledgeEntryPage(
            release=RELEASE,
            entries=tuple(item.summary for item in page_entries),
            next_cursor=str(next_offset) if next_offset < len(self.entries) else None,
        )

    def get_entry(self, *, knowledge_id: str, release_id: str) -> KnowledgeEntryDetail:
        assert release_id == RELEASE.knowledge_release_id
        return next(
            item for item in self.entries if item.summary.knowledge_id == knowledge_id
        )

    def get_theory_profile(
        self,
        *,
        theory_id: str,
        release_id: str,
    ) -> TheoryProfileSnapshot:
        assert release_id == RELEASE.knowledge_release_id
        return next(
            item.theory_profile
            for item in self.entries
            if item.theory_profile is not None
            and item.theory_profile.theory_id == theory_id
        )

    def get_sources(
        self,
        *,
        source_ids: tuple[str, ...],
        release_id: str,
    ) -> tuple[SourceRecordSnapshot, ...]:
        assert release_id == RELEASE.knowledge_release_id
        by_id = {
            source.source_id: source
            for item in self.entries
            for source in item.sources
        }
        return tuple(by_id[source_id] for source_id in source_ids)


def _entry(index: int, *, eligible: bool = True) -> KnowledgeEntryDetail:
    knowledge_id = f"D2:P{index:03d}"
    source = SourceRecordSnapshot(
        source_id=f"source-{index}",
        source_type="reviewed_publication",
        title=f"理论 {index} 来源",
        authors_or_institution=("作者",),
        year=2020 + index,
        publication="社会学期刊",
        locator=f"p.{index}",
        url=f"https://example.com/source-{index}",
        verification_status=SourceVerificationStatus.VERIFIED,
        use_boundary="已核验来源，仅支持档案中列出的命题。",
    )
    eligibility = KnowledgeUseEligibility(
        browse_eligible=True,
        rag_eligible=False,
        training_candidate_eligible=False,
        match_eligible=eligible,
        review_record_ids=(f"review-{index}",) if eligible else (),
    )
    summary = KnowledgeEntrySummary(
        knowledge_id=knowledge_id,
        content_version=1,
        title=f"理论 {index}",
        category_id="category",
        category="理论",
        dimension_id="D2",
        dimension="实践论",
        directory_path=(),
        review_status=(
            KnowledgeReviewStatus.REVIEWED if eligible else KnowledgeReviewStatus.PENDING
        ),
        eligibility=eligibility,
    )
    profile = (
        TheoryProfileSnapshot(
            theory_id=f"theory-{index}",
            related_knowledge_ids=(knowledge_id,),
            title=f"理论 {index}",
            core_propositions=(f"理论 {index} 的已审校命题",),
            applicable_phenomena=("社区互动",),
            analysis_levels=("关系",),
            prerequisites=("存在持续互动",),
            exclusion_signals=("没有互动记录",),
            observable_evidence=("互动频率",),
            competing_or_complementary_theory_ids=(),
            source_ids=(source.source_id,),
            content_version=1,
            review_status=KnowledgeReviewStatus.REVIEWED,
            match_eligible=True,
        )
        if eligible
        else None
    )
    return KnowledgeEntryDetail(
        release=RELEASE,
        summary=summary,
        aliases=(),
        content=f"理论 {index} 的已审核知识正文。",
        sources=(source,),
        relations=(),
        theory_profile=profile,
    )


def test_recall_pages_in_catalog_order_and_stops_after_five_eligible_profiles() -> None:
    catalog = _CatalogFixture(
        entries=(_entry(0, eligible=False), *(_entry(index) for index in range(1, 7)))
    )
    source = CatalogTheoryEvidenceSource(catalog)

    first = source.retrieve(phenomenon=PHENOMENON, release=RELEASE)
    second = source.retrieve(phenomenon=PHENOMENON, release=RELEASE)

    assert [profile.theory_id for profile in first.theory_profiles] == [
        "theory-1",
        "theory-2",
        "theory-3",
        "theory-4",
        "theory-5",
    ]
    assert [item.source.source_id for item in first.evidence_items if item.source] == [
        "source-1",
        "source-2",
        "source-3",
        "source-4",
        "source-5",
    ]
    assert all(item.excerpt is None for item in first.evidence_items)
    assert first == second

