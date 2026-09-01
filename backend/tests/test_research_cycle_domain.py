from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from qunxue_api.api.contracts.research_cycle import ResearchCycleResponse
from qunxue_api.modules.knowledge_catalog import (
    KnowledgeReleaseLevel,
    KnowledgeReleaseRef,
)
from qunxue_api.modules.research_analysis import (
    AnalysisAnnotation,
    AnalysisAnnotationKind,
    AnalysisCode,
    AnalysisMemo,
    AnalysisMemoKind,
    CaseComparison,
    ComparisonFinding,
    ComparisonFindingKind,
    NextResearchStep,
    ResearchAnalysisHandoff,
)
from qunxue_api.modules.research_cycle import (
    CycleEvidenceKind,
    GapDestination,
    ReportingCoverageStatus,
    ResearchCycleService,
)
from qunxue_api.modules.research_intake import ConfirmedPhenomenonSnapshot
from qunxue_api.modules.research_materials import (
    ConsentScope,
    DeidentificationStatus,
    MaterialArchiveProfile,
    MaterialKind,
    MaterialLocator,
    MaterialStatus,
    ModelProcessingScope,
    ProfessionalMaterialArchive,
    ProfessionalMaterialArchiveView,
    ResearchCase,
    ResearchMaterial,
    ResearchRole,
    ResearchStage,
    SensitivityLevel,
)
from qunxue_api.modules.theory_matching import (
    CandidateContentStatus,
    CandidateOrigin,
    ConfirmedTheoryPlanSnapshot,
    EvidenceBundleSnapshot,
    RetrievalProvenanceSnapshot,
    TheoryCandidateContentSnapshot,
    TheoryCandidateSnapshot,
    TheoryDecisionAction,
    TheoryDecisionRecord,
    TheoryJudgementDraft,
    TheoryJudgementVerdict,
)

_USER = UUID("00000000-0000-0000-0000-000000000188")
_TASK = UUID("10000000-0000-0000-0000-000000000188")
_NOW = datetime(2026, 9, 1, 1, 0, tzinfo=UTC)


def test_cycle_projects_only_confirmed_analysis_and_traceable_theory_gaps() -> None:
    annotation = _annotation()
    code = AnalysisCode.candidate(
        user_id=_USER,
        task_id=_TASK,
        label="时间约束",
        definition="照护时间压缩参与空间。",
        annotation_ids=(annotation.annotation_id,),
        rationale="原文反复出现排班冲突。",
        now=_NOW,
    ).confirm(user_confirmed=True, expected_version=1, reason="确认代码", now=_NOW)
    memo = AnalysisMemo.create_candidate(
        user_id=_USER,
        task_id=_TASK,
        title="负例备忘",
        content="资源相近的家庭仍出现不同参与结果。",
        memo_kind=AnalysisMemoKind.ANALYTIC,
        annotation_ids=(annotation.annotation_id,),
        source="user",
        now=_NOW,
    ).confirm(user_confirmed=True, expected_version=1, reason="确认备忘", now=_NOW)
    comparison = CaseComparison.create(
        user_id=_USER,
        task_id=_TASK,
        title="两类家庭比较",
        question="为什么资源接近但参与不同？",
        case_labels=("家庭甲", "家庭乙"),
        findings=(
            ComparisonFinding(
                ComparisonFindingKind.COUNTEREXAMPLE,
                "家庭乙不符合资源决定参与的预期。",
                (annotation.annotation_id,),
            ),
            ComparisonFinding(
                ComparisonFindingKind.COMPETING_EXPLANATION,
                "照护排班可能比经济资源更直接。",
                (annotation.annotation_id,),
            ),
        ),
        evidence_gaps=("缺少家庭成员对排班协商的叙述。",),
        next_steps=(NextResearchStep("interview", "追访家庭成员", "high"),),
        theory_implication="资源解释需要加入时间条件。",
        source="user",
        now=_NOW,
    ).confirm(user_confirmed=True, expected_version=1, reason="确认比较", now=_NOW)
    handoff = ResearchAnalysisHandoff.create(
        task_id=_TASK,
        annotations=(annotation,),
        codes=(code,),
        memos=(memo,),
        comparisons=(comparison,),
    )

    snapshot = ResearchCycleService().project(
        analysis=handoff,
        theory_plan=_theory_plan(),
        materials=(_material(),),
        archive=_archive(),
    )

    assert snapshot.analysis_content_hash == handoff.content_hash
    assert {item.kind for item in snapshot.evidence} == {
        CycleEvidenceKind.ANALYTIC_CODE,
        CycleEvidenceKind.ANALYTIC_MEMO,
        CycleEvidenceKind.COUNTEREXAMPLE,
        CycleEvidenceKind.COMPETING_EXPLANATION,
    }
    counterexample = next(
        item for item in snapshot.evidence if item.kind is CycleEvidenceKind.COUNTEREXAMPLE
    )
    assert counterexample.annotation_id == annotation.annotation_id
    assert counterexample.material_id == annotation.material_id
    assert counterexample.quote == annotation.quote
    assert counterexample.locator == annotation.locator.display()
    assert all(item.confirmed for item in snapshot.evidence)

    assert {item.destination for item in snapshot.gaps} == {
        GapDestination.MATERIAL_SCREENING,
        GapDestination.NEXT_ROUND_SAMPLING,
    }
    assert {item.source_kind for item in snapshot.gaps} >= {"analysis", "theory"}
    assert all(item.status == "open" for item in snapshot.gaps)
    assert all(item.analysis_content_hash == handoff.content_hash for item in snapshot.gaps)
    assert all(item.theory_plan_version == 3 for item in snapshot.gaps)


def test_cycle_auto_projects_project_facts_and_non_blocking_reporting_hints() -> None:
    snapshot = ResearchCycleService().project(
        analysis=ResearchAnalysisHandoff.create(
            task_id=_TASK,
            annotations=(),
            codes=(),
            memos=(),
            comparisons=(),
        ),
        theory_plan=None,
        materials=(_material(),),
        archive=_archive(),
    )

    assert snapshot.project_facts.material_count == 1
    assert snapshot.project_facts.material_kinds == (("interview_transcript", 1),)
    assert snapshot.project_facts.case_count == 1
    assert snapshot.project_facts.case_material_coverage == (("家庭甲", 1),)
    assert snapshot.project_facts.consent_scopes == (("project_only", 1),)
    assert snapshot.project_facts.pending_deidentification_count == 1
    assert snapshot.project_facts.analysis_counts == (
        ("codes", 0),
        ("memos", 0),
        ("comparisons", 0),
    )

    srqr = [item for item in snapshot.reporting_hints if item.guideline == "SRQR"]
    coreq = [item for item in snapshot.reporting_hints if item.guideline == "COREQ"]
    assert srqr and coreq
    assert all(not item.blocking for item in snapshot.reporting_hints)
    assert all(not hasattr(item, "score") for item in snapshot.reporting_hints)
    assert any(
        item.item_key == "ethics" and item.status is ReportingCoverageStatus.PRESENT
        for item in srqr
    )
    assert any(
        item.item_key == "researcher_characteristics"
        and item.status is ReportingCoverageStatus.MISSING
        for item in coreq
    )


def test_research_cycle_contract_serializes_versions_hints_and_map_patch() -> None:
    snapshot = ResearchCycleService().project(
        analysis=ResearchAnalysisHandoff.create(
            task_id=_TASK,
            annotations=(_annotation(),),
            codes=(),
            memos=(),
            comparisons=(),
        ),
        theory_plan=None,
        materials=(_material(),),
        archive=_archive(),
    )

    payload = ResearchCycleResponse.from_domain(snapshot).model_dump(mode="json")

    assert payload["schema_version"] == "research-cycle-v1"
    assert payload["analysis_content_hash"] == snapshot.analysis_content_hash
    assert payload["research_map_patch"] == snapshot.research_map_patch
    assert all(item["blocking"] is False for item in payload["reporting_hints"])


def _annotation() -> AnalysisAnnotation:
    quote = "晚班以后没有时间参加社区会议"
    return AnalysisAnnotation.create(
        user_id=_USER,
        task_id=_TASK,
        material_id=UUID("20000000-0000-0000-0000-000000000188"),
        parse_id=UUID("30000000-0000-0000-0000-000000000188"),
        segment_id="segment-18",
        segment_content_hash="1" * 64,
        quote=quote,
        quote_start=0,
        quote_end=len(quote),
        locator=MaterialLocator(page=8, paragraph=2, char_start=0, char_end=len(quote)),
        annotation_kind=AnalysisAnnotationKind.DESCRIPTIVE,
        case_label="家庭乙",
        note="参与受排班限制。",
        now=_NOW,
    )


def _material() -> ResearchMaterial:
    value = ResearchMaterial.create(
        material_id=UUID("20000000-0000-0000-0000-000000000188"),
        user_id=_USER,
        task_id=_TASK,
        idempotency_key="material-188",
        original_filename="家庭甲访谈.txt",
        media_type="text/plain",
        content=b"interview",
        material_kind=MaterialKind.INTERVIEW_TRANSCRIPT,
        processing_policy_version="v1",
        now=_NOW,
    )
    return replace(
        value,
        status=MaterialStatus.READY,
        current_parse_id=UUID("30000000-0000-0000-0000-000000000188"),
        current_parse_version=1,
    )


def _archive() -> ProfessionalMaterialArchiveView:
    material_id = UUID("20000000-0000-0000-0000-000000000188")
    profile = MaterialArchiveProfile.create(
        material_id=material_id,
        user_id=_USER,
        task_id=_TASK,
        research_role=ResearchRole.EMPIRICAL_MATERIAL,
        specific_type="半结构访谈",
        stage=ResearchStage.ANALYSIS,
        sensitivity=SensitivityLevel.SENSITIVE,
        consent_scope=ConsentScope.PROJECT_ONLY,
        deidentification_status=DeidentificationStatus.PENDING,
        model_processing_scope=ModelProcessingScope.MANUAL_ONLY,
        now=_NOW,
    )
    case = ResearchCase.create(
        user_id=_USER,
        task_id=_TASK,
        name="家庭甲",
        attributes={"社区": "甲区"},
        material_ids=(material_id,),
        now=_NOW,
    )
    return ProfessionalMaterialArchiveView(
        archive=ProfessionalMaterialArchive(profiles=(profile,), cases=(case,)),
        inventory=None,  # type: ignore[arg-type]
    )


def _theory_plan() -> ConfirmedTheoryPlanSnapshot:
    release = KnowledgeReleaseRef(
        knowledge_release_id="release-final-188",
        level=KnowledgeReleaseLevel.FINAL,
        content_hash="sha256:" + "2" * 64,
    )
    phenomenon = ConfirmedPhenomenonSnapshot(
        phenomenon_query_id=UUID("40000000-0000-0000-0000-000000000188"),
        task_id=_TASK,
        version=1,
        phenomenon="社区参与下降",
        research_intent="理解家庭间差异",
        context="甲社区",
        evidence_refs=(),
        content_hash="sha256:" + "3" * 64,
    )
    content = TheoryCandidateContentSnapshot(
        theory_id="theory:resource",
        title="资源动员理论",
        origin=CandidateOrigin.REVIEWED_KNOWLEDGE,
        problem_focus="资源如何影响参与",
        core_claims=("资源提升参与能力",),
        analysis_levels=("家庭",),
        source_ids=("source:1",),
        reviewed_profile=None,
        formal_adoption_eligible=True,
        adoption_blockers=(),
        content_status=CandidateContentStatus.REVIEWED,
    )
    judgement = TheoryJudgementDraft(
        verdict=TheoryJudgementVerdict.CONDITIONAL,
        match_rationale="资源解释受到时间条件限制。",
        applicable_conditions=("家庭可支配时间相近",),
        limitations=("尚未覆盖照护排班",),
        material_requirements=("补充不同排班家庭的访谈",),
        evidence_gaps=("缺少排班协商过程材料",),
        alternative_explanations=("照护时间结构",),
        evidence_ref_ids=(),
    )
    candidate = TheoryCandidateSnapshot(
        candidate_id=UUID("50000000-0000-0000-0000-000000000188"),
        candidate_version=1,
        content=content,
        judgement=judgement,
        trace_id=UUID("60000000-0000-0000-0000-000000000188"),
        request_id=UUID("70000000-0000-0000-0000-000000000188"),
        contract_version="v1",
    )
    decision = TheoryDecisionRecord(
        decision_id=UUID("b0000000-0000-0000-0000-000000000188"),
        candidate_id=candidate.candidate_id,
        candidate_version=1,
        action=TheoryDecisionAction.ADOPT,
        reason="保留并加入时间边界",
        related_source_ids=(),
        revised_applicability=None,
        recorded_at=_NOW,
    )
    bundle = EvidenceBundleSnapshot(
        evidence_bundle_id="bundle-188",
        version=1,
        content_hash="sha256:" + "4" * 64,
        release=release,
        theory_profiles=(),
        evidence_items=(),
        retrieval=RetrievalProvenanceSnapshot(),
    )
    return ConfirmedTheoryPlanSnapshot(
        theory_plan_id=UUID("80000000-0000-0000-0000-000000000188"),
        task_id=_TASK,
        match_run_id=UUID("90000000-0000-0000-0000-000000000188"),
        decision_set_id=UUID("a0000000-0000-0000-0000-000000000188"),
        version=3,
        phenomenon=phenomenon,
        knowledge_release=release,
        evidence_bundle=bundle,
        candidates=(candidate,),
        decisions=(decision,),
        use_assignments=(),
        relations=(),
        confirmed_at=_NOW,
    )
