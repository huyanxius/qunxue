from dataclasses import dataclass
from types import SimpleNamespace
from uuid import UUID

import pytest

from qunxue_api.adapters.retrieval import RetrievalChunk, RetrievalPipelineUnavailable
from qunxue_api.adapters.retrieval.hybrid import (
    HybridRetrievalHit,
    HybridRetrievalResult,
)
from qunxue_api.adapters.theory_evidence import CatalogTheoryEvidenceSource
from qunxue_api.modules.knowledge_catalog import (
    KnowledgeEntryDetail,
    KnowledgeEntryPage,
    KnowledgeEntrySummary,
    KnowledgeReleaseLevel,
    KnowledgeReleaseRef,
    KnowledgeReviewStatus,
    KnowledgeUseEligibility,
    KnowledgeUsePurpose,
    SourceRecordSnapshot,
    SourceVerificationStatus,
    TheoryProfileSnapshot,
)
from qunxue_api.modules.research_intake import (
    ConfirmedPhenomenonSnapshot,
    PhenomenonEvidenceRefSnapshot,
    PhenomenonEvidenceVerificationStatus,
)

RELEASE = KnowledgeReleaseRef(
    knowledge_release_id="release-reviewed-v1",
    level=KnowledgeReleaseLevel.FINAL,
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
    evidence_refs=(
        PhenomenonEvidenceRefSnapshot(
            evidence_ref_id="phenomenon-evidence:interview-1",
            excerpt="多名居民提到新成员较少参与持续互助。",
            source_ref_id="material:interview-1",
            source_description="去标识化访谈摘要",
            locator="访谈摘要，第 4 段",
            verification_status=PhenomenonEvidenceVerificationStatus.VERIFIED,
            use_boundary="仅说明受访者报告的互助变化，不证明成员流动是唯一原因。",
        ),
        PhenomenonEvidenceRefSnapshot(
            evidence_ref_id="phenomenon-evidence:field-note-2",
            excerpt="用户记录的新成员活动参与观察。",
            source_ref_id="material:field-note-2",
            source_description="用户提供的观察笔记",
            locator="观察笔记，2026-08-01",
            verification_status=PhenomenonEvidenceVerificationStatus.USER_ATTESTED,
            use_boundary="用户确认材料来源，但尚未经过外部核验。",
        ),
    ),
)


@dataclass
class _CatalogFixture:
    entries: tuple[KnowledgeEntryDetail, ...]
    current: KnowledgeReleaseRef = RELEASE

    def current_release(self, *, purpose: object) -> KnowledgeReleaseRef:
        assert purpose is KnowledgeUsePurpose.MATCH
        return self.current

    def list_match_profiles(
        self,
        *,
        release_id: str,
    ) -> tuple[TheoryProfileSnapshot, ...]:
        assert release_id == RELEASE.knowledge_release_id
        return tuple(
            entry.theory_profile for entry in self.entries if entry.theory_profile is not None
        )

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
            total_count=len(self.entries),
            next_cursor=str(next_offset) if next_offset < len(self.entries) else None,
        )

    def get_entry(self, *, knowledge_id: str, release_id: str) -> KnowledgeEntryDetail:
        assert release_id == RELEASE.knowledge_release_id
        return next(item for item in self.entries if item.summary.knowledge_id == knowledge_id)

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
            if item.theory_profile is not None and item.theory_profile.theory_id == theory_id
        )

    def get_sources(
        self,
        *,
        source_ids: tuple[str, ...],
        release_id: str,
    ) -> tuple[SourceRecordSnapshot, ...]:
        assert release_id == RELEASE.knowledge_release_id
        by_id = {source.source_id: source for item in self.entries for source in item.sources}
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


def _retriever(*indices: int):
    class Retriever:
        def search(self, **kwargs):
            del kwargs
            return HybridRetrievalResult(
                retrieval_index_id="retrieval-index:reviewed-v1",
                mode="hybrid_reranked",
                embedding_model="Pro/BAAI/bge-m3",
                reranker_model="Pro/BAAI/bge-reranker-v2-m3",
                degraded_reason=None,
                hits=tuple(
                    HybridRetrievalHit(
                        chunk=RetrievalChunk(
                            chunk_id=f"theory-profile:theory-{index}:v1",
                            document_kind="theory_profile",
                            knowledge_id=f"D2:P{index:03d}",
                            theory_id=f"theory-{index}",
                            content_version=1,
                            content_hash=f"sha256:theory-{index}",
                            title=f"理论 {index}",
                            text=f"理论 {index} 的检索文本",
                            source_ids=(f"source-{index}",),
                        ),
                        fused_score=0.03,
                        retrieval_sources=("lexical", "semantic"),
                        rerank_score=0.9,
                    )
                    for index in indices
                ),
            )

    return Retriever()


def test_recall_requires_the_release_bound_hybrid_retriever() -> None:
    catalog = _CatalogFixture(
        entries=(_entry(0, eligible=False), *(_entry(index) for index in range(1, 7)))
    )
    source = CatalogTheoryEvidenceSource(catalog)

    with pytest.raises(RetrievalPipelineUnavailable, match="hybrid retriever is required"):
        source.retrieve(phenomenon=PHENOMENON, release=RELEASE)


def test_recall_uses_hybrid_ranking_and_records_index_provenance() -> None:
    catalog = _CatalogFixture(entries=tuple(_entry(index) for index in range(1, 7)))
    calls: list[str] = []

    class Retriever:
        def search(self, **kwargs):
            calls.append(kwargs["query"])
            assert kwargs["knowledge_release_id"] == RELEASE.knowledge_release_id
            assert kwargs["release_content_hash"] == RELEASE.content_hash
            assert kwargs["document_kind"] == "theory_profile"
            return HybridRetrievalResult(
                retrieval_index_id="retrieval-index:reviewed-v1",
                mode="hybrid_reranked",
                embedding_model="Pro/BAAI/bge-m3",
                reranker_model="Pro/BAAI/bge-reranker-v2-m3",
                degraded_reason=None,
                hits=tuple(
                    HybridRetrievalHit(
                        chunk=RetrievalChunk(
                            chunk_id=f"theory-profile:theory-{index}:v1",
                            document_kind="theory_profile",
                            knowledge_id=f"D2:P{index:03d}",
                            theory_id=f"theory-{index}",
                            content_version=1,
                            content_hash=f"sha256:theory-{index}",
                            title=f"理论 {index}",
                            text=f"理论 {index} 的检索文本",
                            source_ids=(f"source-{index}",),
                        ),
                        fused_score=0.03,
                        retrieval_sources=("lexical", "semantic"),
                        rerank_score=score,
                    )
                    for index, score in ((6, 0.92), (2, 0.81))
                ),
            )

    bundle = CatalogTheoryEvidenceSource(catalog, retriever=Retriever()).retrieve(
        phenomenon=PHENOMENON,
        release=RELEASE,
    )

    assert calls and PHENOMENON.phenomenon in calls[0]
    assert [profile.theory_id for profile in bundle.theory_profiles] == [
        "theory-6",
        "theory-2",
    ]
    assert bundle.retrieval.retrieval_index_id == "retrieval-index:reviewed-v1"
    assert bundle.retrieval.mode == "hybrid_reranked"
    assert bundle.retrieval.retrieved_chunk_ids == (
        "theory-profile:theory-6:v1",
        "theory-profile:theory-2:v1",
    )


def test_recall_preserves_an_auditable_empty_result_for_no_reliable_candidate() -> None:
    catalog = _CatalogFixture(entries=tuple(_entry(index) for index in range(1, 4)))

    bundle = CatalogTheoryEvidenceSource(catalog, retriever=_retriever()).retrieve(
        phenomenon=PHENOMENON,
        release=RELEASE,
    )

    assert bundle.theory_profiles == ()
    assert bundle.retrieval.retrieval_index_id == "retrieval-index:reviewed-v1"
    assert bundle.retrieval.mode == "hybrid_reranked"
    assert bundle.retrieval.retrieved_chunk_ids == ()


def test_recall_adds_only_owner_scoped_confirmed_comparison_evidence() -> None:
    owner_id = UUID(int=77)
    calls: list[tuple[UUID, UUID]] = []

    def confirmed_analysis_evidence(*, user_id: UUID, task_id: UUID):
        calls.append((user_id, task_id))
        return (
            SimpleNamespace(
                evidence_ref_id="analysis-comparison:1:finding:0:annotation:1",
                kind=SimpleNamespace(value="counterexample"),
                statement="第二个案例并未因成员流动而减少互助。",
                quote="新成员仍会轮流照看孩子。",
                material_id=UUID(int=81),
                parse_id=UUID(int=82),
                segment_id="segment-12",
                locator="第4页，第12段",
                case_label="社区 B",
                observed_at="2026-08",
            ),
        )

    bundle = CatalogTheoryEvidenceSource(
        _CatalogFixture(entries=(_entry(1),)),
        retriever=_retriever(1),
        get_confirmed_analysis_evidence=confirmed_analysis_evidence,
    ).retrieve(user_id=owner_id, phenomenon=PHENOMENON, release=RELEASE)

    assert calls == [(owner_id, PHENOMENON.task_id)]
    evidence = next(
        item
        for item in bundle.evidence_items
        if item.evidence_ref_id == "analysis-comparison:1:finding:0:annotation:1"
    )
    assert evidence.claim == "第二个案例并未因成员流动而减少互助。"
    assert evidence.excerpt == "新成员仍会轮流照看孩子。"
    assert evidence.locator == "第4页，第12段"
    assert evidence.source is not None
    assert evidence.source.source_type == "personal_research_material"
    assert evidence.source.source_id == (
        "research-material:00000000-0000-0000-0000-000000000051:"
        "00000000-0000-0000-0000-000000000052:segment-12"
    )
    assert evidence.verification_status is SourceVerificationStatus.VERIFIED
    assert "反例" in evidence.use_boundary


def test_recall_rejects_non_final_and_keeps_a_pinned_final_release_reproducible() -> None:
    catalog = _CatalogFixture(entries=tuple(_entry(index) for index in range(1, 4)))
    source = CatalogTheoryEvidenceSource(catalog, retriever=_retriever(1, 2, 3))

    with pytest.raises(ValueError, match="final MATCH knowledge release"):
        source.retrieve(
            phenomenon=PHENOMENON,
            release=KnowledgeReleaseRef(
                knowledge_release_id=RELEASE.knowledge_release_id,
                level=KnowledgeReleaseLevel.PREVIEW,
                content_hash=RELEASE.content_hash,
            ),
        )

    catalog.current = KnowledgeReleaseRef(
        knowledge_release_id="release-newer",
        level=KnowledgeReleaseLevel.FINAL,
        content_hash="sha256:newer",
    )
    recalled = source.retrieve(phenomenon=PHENOMENON, release=RELEASE)

    assert recalled.release == RELEASE


@pytest.mark.parametrize(
    "source",
    [
        SourceRecordSnapshot(
            source_id="source-1",
            source_type="reviewed_publication",
            title="无定位来源",
            authors_or_institution=("作者",),
            year=2021,
            publication="社会学期刊",
            locator=None,
            url="https://example.com/source-1",
            verification_status=SourceVerificationStatus.VERIFIED,
            use_boundary="已核验来源。",
        ),
        SourceRecordSnapshot(
            source_id="source-1",
            source_type="reviewed_publication",
            title="待核验来源",
            authors_or_institution=("作者",),
            year=2021,
            publication="社会学期刊",
            locator="p.1",
            url="https://example.com/source-1",
            verification_status=SourceVerificationStatus.PENDING,
            use_boundary="待核验来源。",
        ),
    ],
)
def test_recall_rejects_untraceable_evidence_sources(
    source: SourceRecordSnapshot,
) -> None:
    entry = _entry(1)
    catalog = _CatalogFixture(
        entries=(
            KnowledgeEntryDetail(
                release=entry.release,
                summary=entry.summary,
                aliases=entry.aliases,
                content=entry.content,
                sources=(source,),
                relations=entry.relations,
                theory_profile=entry.theory_profile,
            ),
        )
    )

    with pytest.raises(ValueError, match="verified source with a locator"):
        CatalogTheoryEvidenceSource(catalog, retriever=_retriever(1)).retrieve(
            phenomenon=PHENOMENON,
            release=RELEASE,
        )
