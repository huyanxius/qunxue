from qunxue_api.adapters.retrieval.corpus import (
    build_knowledge_entry_chunks,
    build_theory_profile_chunks,
)
from qunxue_api.modules.knowledge_catalog import (
    KnowledgeEntryDetail,
    KnowledgeEntrySummary,
    KnowledgeReleaseLevel,
    KnowledgeReleaseRef,
    KnowledgeReviewStatus,
    KnowledgeUseEligibility,
    TheoryProfileSnapshot,
)


def _profile(*, eligible: bool = True) -> TheoryProfileSnapshot:
    return TheoryProfileSnapshot(
        theory_id="social-capital",
        related_knowledge_ids=("D2:P001",),
        title="社会资本理论",
        core_propositions=("信任与互惠规范支持集体行动",),
        applicable_phenomena=("社区互助", "公共参与"),
        analysis_levels=("关系", "社区"),
        prerequisites=("存在可持续的关系网络",),
        exclusion_signals=("互动完全是一次性的",),
        observable_evidence=("互助频率", "信任叙述"),
        competing_or_complementary_theory_ids=("collective-efficacy",),
        source_ids=("source:putnam",),
        content_version=2,
        review_status=KnowledgeReviewStatus.REVIEWED,
        match_eligible=eligible,
    )


def test_theory_profile_corpus_keeps_applicability_signals_and_stable_identity() -> None:
    first = build_theory_profile_chunks((_profile(), _profile(eligible=False)))
    second = build_theory_profile_chunks((_profile(),))

    assert first == second
    assert len(first) == 1
    chunk = first[0]
    assert chunk.chunk_id == "theory-profile:social-capital:v2"
    assert chunk.theory_id == "social-capital"
    assert chunk.knowledge_id == "D2:P001"
    assert chunk.source_ids == ("source:putnam",)
    assert "适用现象：社区互助；公共参与" in chunk.text
    assert "排除信号：互动完全是一次性的" in chunk.text
    assert chunk.content_hash.startswith("sha256:")


def test_knowledge_entry_corpus_keeps_all_published_content() -> None:
    release = KnowledgeReleaseRef(
        knowledge_release_id="release-reviewed-v1",
        level=KnowledgeReleaseLevel.FINAL,
        content_hash="sha256:release-reviewed-v1",
    )
    entries = tuple(
        KnowledgeEntryDetail(
            release=release,
            summary=KnowledgeEntrySummary(
                knowledge_id=f"D1:C00{index}",
                content_version=1,
                title=title,
                category_id="D1",
                category="基础概念",
                dimension_id="D1",
                dimension="本体论",
                directory_path=(),
                review_status=KnowledgeReviewStatus.REVIEWED,
                eligibility=KnowledgeUseEligibility(
                    browse_eligible=True,
                    rag_eligible=eligible,
                    training_candidate_eligible=False,
                    match_eligible=False,
                    review_record_ids=(f"review-{index}",),
                ),
            ),
            aliases=(alias,),
            content=content,
            sources=(),
            relations=(),
            theory_profile=None,
        )
        for index, title, alias, content, eligible in (
            (1, "符号互动论", "互动论", "意义在互动过程中被解释和修订。", True),
            (2, "社会事实", "集体事实", "社会事实具有外在性和约束力。", False),
        )
    )

    chunks = build_knowledge_entry_chunks(entries)

    assert [chunk.knowledge_id for chunk in chunks] == ["D1:C001", "D1:C002"]
    assert chunks[0].chunk_id == "knowledge-entry:D1:C001:v1:0"
    assert chunks[0].text.startswith("标题：符号互动论\n别名：互动论")
