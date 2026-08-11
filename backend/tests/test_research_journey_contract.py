from datetime import UTC, datetime
from unittest.mock import create_autospec
from uuid import UUID

import pytest

from qunxue_api.application import (
    ResearchJourney,
    ResearchJourneyConfigurationError,
    ResearchJourneyDependencies,
)
from qunxue_api.modules.knowledge_catalog import (
    KnowledgeCatalog,
    KnowledgeReleaseLevel,
    KnowledgeReleaseRef,
    KnowledgeReviewStatus,
    KnowledgeUsePurpose,
    SourceRecordSnapshot,
    SourceVerificationStatus,
    TheoryProfileSnapshot,
)
from qunxue_api.modules.research_framework import (
    AuditFindingSnapshot,
    AuditOverallStatus,
    AuditResolution,
    AuditResolutionAction,
    ConfirmedFrameworkSnapshot,
    FrameworkAuditSnapshot,
    FrameworkReviewRunSnapshot,
    FrameworkReviewRunStatus,
    FrameworkVersionSnapshot,
    MethodIntentSnapshot,
    ResearchFrameworkDraft,
    ResearchFrameworkWorkflow,
)
from qunxue_api.modules.research_intake import ConfirmedPhenomenonSnapshot
from qunxue_api.modules.theory_matching import (
    CandidateOrigin,
    ConfirmedTheoryPlanSnapshot,
    DeferredTheoryPlanSnapshot,
    EvidenceBundleSnapshot,
    EvidenceItemSnapshot,
    MatchCompletionBasis,
    MatchRunSnapshot,
    MatchRunStatus,
    TheoryCandidateContentSnapshot,
    TheoryCandidateSnapshot,
    TheoryDecisionAction,
    TheoryDecisionCommand,
    TheoryDecisionRecord,
    TheoryDecisionSetSnapshot,
    TheoryJudgementDraft,
    TheoryJudgementVerdict,
    TheoryMatching,
    TheoryRelationSnapshot,
    TheoryUseAssignment,
)

NOW = datetime(2026, 7, 28, 8, 0, tzinfo=UTC)
CANDIDATE_A = UUID(int=5)


def _decision(
    candidate_id: UUID,
    action: TheoryDecisionAction,
) -> TheoryDecisionRecord:
    return TheoryDecisionRecord(
        decision_id=UUID(int=10 + candidate_id.int),
        candidate_id=candidate_id,
        candidate_version=1,
        action=action,
        reason="用户完成比较后作出的决定",
        related_source_ids=("source-1",),
        revised_applicability=None,
        recorded_at=NOW,
    )


def _decision_set(
    *,
    decisions: tuple[TheoryDecisionRecord, ...],
    assignments: tuple[TheoryUseAssignment, ...] = (),
    relations: tuple[TheoryRelationSnapshot, ...] = (),
) -> TheoryDecisionSetSnapshot:
    return TheoryDecisionSetSnapshot(
        decision_set_id=UUID(int=20),
        match_run_id=UUID(int=4),
        version=1,
        decisions=decisions,
        use_assignments=assignments,
        relations=relations,
        recorded_at=NOW,
    )


def test_research_journey_calls_public_protocols_with_complete_snapshots() -> None:
    catalog = create_autospec(KnowledgeCatalog, instance=True, spec_set=True)
    matching = create_autospec(TheoryMatching, instance=True, spec_set=True)
    frameworks = create_autospec(
        ResearchFrameworkWorkflow,
        instance=True,
        spec_set=True,
    )
    journey = ResearchJourney(
        ResearchJourneyDependencies(
            knowledge_catalog=catalog,
            theory_matching=matching,
            research_framework=frameworks,
        )
    )
    phenomenon = ConfirmedPhenomenonSnapshot(
        task_id=UUID(int=1),
        phenomenon_query_id=UUID(int=2),
        version=3,
        phenomenon="同一社区中的互助为何逐渐减少？",
        research_intent="比较规范和资源条件的解释",
        context="社区持续更新，成员流动增加",
    )
    release = KnowledgeReleaseRef(
        knowledge_release_id="knowledge-preview-1",
        level=KnowledgeReleaseLevel.PREVIEW,
        content_hash="sha256:reviewed",
    )
    source = SourceRecordSnapshot(
        source_id="source-1",
        source_type="article",
        title="社区互助研究",
        authors_or_institution=("研究者甲",),
        year=2025,
        publication="社会学研究",
        locator="p. 12",
        url=None,
        verification_status=SourceVerificationStatus.VERIFIED,
        use_boundary="仅支持已标明的经验判断",
    )
    profile = TheoryProfileSnapshot(
        theory_id="theory-1",
        related_knowledge_ids=("knowledge-1",),
        title="社会资本理论",
        core_propositions=("稳定关系促进互惠",),
        applicable_phenomena=("社区互助",),
        analysis_levels=("关系网络",),
        prerequisites=("存在持续互动",),
        exclusion_signals=("成员从不重复互动",),
        observable_evidence=("互助频率",),
        competing_or_complementary_theory_ids=(),
        source_ids=(source.source_id,),
        content_version=2,
        review_status=KnowledgeReviewStatus.REVIEWED,
        match_eligible=True,
    )
    evidence = EvidenceItemSnapshot(
        evidence_ref_id="evidence-1",
        claim="成员流动削弱重复互动",
        excerpt="互助频率随成员流动上升而下降。",
        locator=source.locator,
        source=source,
        verification_status=SourceVerificationStatus.VERIFIED,
        use_boundary=source.use_boundary,
    )
    bundle = EvidenceBundleSnapshot(
        evidence_bundle_id="bundle-1",
        version=1,
        content_hash="sha256:evidence",
        release=release,
        theory_profiles=(profile,),
        evidence_items=(evidence,),
    )
    candidate = TheoryCandidateSnapshot(
        candidate_id=CANDIDATE_A,
        candidate_version=1,
        content=TheoryCandidateContentSnapshot(
            theory_id=profile.theory_id,
            title=profile.title,
            origin=CandidateOrigin.REVIEWED_KNOWLEDGE,
            problem_focus="重复互动如何影响互惠",
            core_claims=profile.core_propositions,
            analysis_levels=profile.analysis_levels,
            source_ids=profile.source_ids,
            reviewed_profile=profile,
            formal_adoption_eligible=True,
            adoption_blockers=(),
        ),
        judgement=TheoryJudgementDraft(
            verdict=TheoryJudgementVerdict.CONDITIONAL,
            match_rationale="现象与理论机制相符，但仍需比较资源条件",
            applicable_conditions=("成员曾有持续互动",),
            limitations=("不能单独解释资源差异",),
            material_requirements=("成员互动记录",),
            evidence_gaps=("缺少流动前后的对照",),
            alternative_explanations=("资源供给变化",),
            evidence_ref_ids=(evidence.evidence_ref_id,),
        ),
        trace_id=UUID(int=7),
        request_id=UUID(int=8),
        contract_version="theory-judgement.v1",
    )
    match_run = MatchRunSnapshot(
        match_run_id=UUID(int=4),
        task_id=phenomenon.task_id,
        version=1,
        status=MatchRunStatus.AWAITING_DECISION,
        phenomenon=phenomenon,
        knowledge_release=release,
        evidence_bundle=bundle,
        candidates=(candidate,),
    )
    catalog.current_release.return_value = release
    matching.start.return_value = match_run

    decisions = (
        TheoryDecisionCommand(
            candidate_id=candidate.candidate_id,
            candidate_version=candidate.candidate_version,
            action=TheoryDecisionAction.ADOPT,
            reason="保留其机制解释，并单列资源条件限制",
            related_source_ids=(source.source_id,),
        ),
    )
    assignments = (
        TheoryUseAssignment(
            candidate_id=candidate.candidate_id,
            role_code="primary",
            responsibility="解释重复互动与互助规范",
        ),
    )
    decision_set = _decision_set(
        decisions=(_decision(CANDIDATE_A, TheoryDecisionAction.ADOPT),),
        assignments=assignments,
    )
    matching.record_decisions.return_value = decision_set
    theory_plan = ConfirmedTheoryPlanSnapshot(
        theory_plan_id=UUID(int=40),
        task_id=phenomenon.task_id,
        match_run_id=match_run.match_run_id,
        decision_set_id=decision_set.decision_set_id,
        version=1,
        phenomenon=phenomenon,
        knowledge_release=release,
        evidence_bundle=bundle,
        candidates=(candidate,),
        decisions=decision_set.decisions,
        use_assignments=decision_set.use_assignments,
        relations=(),
        confirmed_at=NOW,
    )
    matching.confirm_plan.return_value = theory_plan

    def create_framework(*, input):
        return FrameworkVersionSnapshot(
            framework_id=UUID(int=50),
            task_id=input.theory_plan.task_id,
            version=1,
            input=input,
            draft=ResearchFrameworkDraft(
                concept_mappings=(),
                evidence_requirements=(),
                inference_links=(),
                alternative_explanations=(),
                method_plan=None,
                scope_and_limitations=(),
                unresolved_items=(),
                next_actions=(),
            ),
        )

    frameworks.create_draft.side_effect = create_framework

    started = journey.start_theory_matching(phenomenon=phenomenon)
    recorded = journey.record_theory_decisions(
        match_run_id=started.match_run_id,
        expected_version=started.version,
        completion_basis=MatchCompletionBasis.COMPLETE,
        decisions=decisions,
        use_assignments=assignments,
        relations=(),
    )
    confirmed = journey.confirm_theory_plan(
        decision_set_id=recorded.decision_set_id,
        expected_version=recorded.version,
    )
    framework = journey.create_framework_draft(
        theory_plan=confirmed,
        original_research_question="社区互助为什么减少？",
        confirmed_research_question="成员流动如何通过重复互动影响社区互助？",
        question_adjustment_reason="把现象收敛为可检验机制",
        research_object="社区成员",
        analysis_unit="成员关系",
        context=phenomenon.context,
        method_intent=MethodIntentSnapshot(
            method_kind="访谈与关系材料",
            constraints=("不接收真实敏感材料",),
            source="user_confirmed",
        ),
    )

    first_finding = AuditFindingSnapshot(
        finding_id=UUID(int=60),
        summary="证据区分规则仍不清楚",
        reason="支持与排除信号尚未连接到材料",
        impact="无法判断竞争解释",
        recommendation="补充区分性证据计划",
        blocking=True,
    )
    first_audit = FrameworkAuditSnapshot(
        audit_id=UUID(int=61),
        framework_id=framework.framework_id,
        framework_version=framework.version,
        overall_status=AuditOverallStatus.REVISE,
        findings=(first_finding,),
    )
    first_review = FrameworkReviewRunSnapshot(
        review_run_id=UUID(int=62),
        framework_id=framework.framework_id,
        framework_version=framework.version,
        trace_id=UUID(int=63),
        idempotency_key="review-framework-v1",
        version=1,
        status=FrameworkReviewRunStatus.SUCCEEDED,
        audit=first_audit,
    )
    resolution = AuditResolution(
        finding_id=first_finding.finding_id,
        action=AuditResolutionAction.ACCEPT,
        reason="按建议补充区分性证据计划",
    )
    revised_draft = ResearchFrameworkDraft(
        concept_mappings=framework.draft.concept_mappings,
        evidence_requirements=framework.draft.evidence_requirements,
        inference_links=framework.draft.inference_links,
        alternative_explanations=framework.draft.alternative_explanations,
        method_plan=framework.draft.method_plan,
        scope_and_limitations=framework.draft.scope_and_limitations,
        unresolved_items=(),
        next_actions=("补充竞争解释的区分性材料",),
    )
    revised_framework = FrameworkVersionSnapshot(
        framework_id=framework.framework_id,
        task_id=framework.task_id,
        version=2,
        input=framework.input,
        draft=revised_draft,
    )
    final_audit = FrameworkAuditSnapshot(
        audit_id=UUID(int=64),
        framework_id=revised_framework.framework_id,
        framework_version=revised_framework.version,
        overall_status=AuditOverallStatus.PASS,
        findings=(),
    )
    final_review = FrameworkReviewRunSnapshot(
        review_run_id=UUID(int=65),
        framework_id=revised_framework.framework_id,
        framework_version=revised_framework.version,
        trace_id=UUID(int=66),
        idempotency_key="review-framework-v2",
        version=1,
        status=FrameworkReviewRunStatus.SUCCEEDED,
        audit=final_audit,
    )
    confirmed_framework = ConfirmedFrameworkSnapshot(
        framework=revised_framework,
        audit=final_audit,
        resolutions=(),
        confirmed_at=NOW,
    )
    frameworks.start_review.side_effect = (first_review, final_review)
    frameworks.revise.return_value = revised_framework
    frameworks.confirm.return_value = confirmed_framework

    reviewed = journey.start_framework_review(
        framework_id=framework.framework_id,
        expected_version=framework.version,
    )
    revised = journey.revise_framework(
        framework_id=framework.framework_id,
        expected_version=framework.version,
        audit_id=reviewed.audit.audit_id,
        revised_draft=revised_draft,
        resolutions=(resolution,),
        revision_reason="处理阻断审校项",
    )
    reviewed_again = journey.start_framework_review(
        framework_id=revised.framework_id,
        expected_version=revised.version,
    )
    final = journey.confirm_framework(
        framework_id=revised.framework_id,
        expected_version=revised.version,
        audit_id=reviewed_again.audit.audit_id,
        resolutions=(),
    )

    catalog.current_release.assert_called_once_with(
        purpose=KnowledgeUsePurpose.MATCH
    )
    matching.start.assert_called_once_with(
        phenomenon=phenomenon,
        release=release,
    )
    matching.record_decisions.assert_called_once_with(
        match_run_id=match_run.match_run_id,
        expected_version=match_run.version,
        completion_basis=MatchCompletionBasis.COMPLETE,
        decisions=decisions,
        use_assignments=assignments,
        relations=(),
    )
    matching.confirm_plan.assert_called_once_with(
        decision_set_id=decision_set.decision_set_id,
        expected_version=decision_set.version,
    )
    draft_input = frameworks.create_draft.call_args.kwargs["input"]
    assert draft_input.theory_plan == theory_plan
    assert draft_input.theory_plan.phenomenon == phenomenon
    assert draft_input.theory_plan.evidence_bundle == bundle
    assert draft_input.theory_plan.candidates[0].content.reviewed_profile == profile
    assert draft_input.confirmed_research_question.startswith("成员流动如何")
    assert framework.input == draft_input
    assert framework.task_id == phenomenon.task_id
    frameworks.revise.assert_called_once_with(
        framework_id=framework.framework_id,
        expected_version=framework.version,
        audit_id=first_audit.audit_id,
        revised_draft=revised_draft,
        resolutions=(resolution,),
        revision_reason="处理阻断审校项",
    )
    assert frameworks.start_review.call_count == 2
    frameworks.confirm.assert_called_once_with(
        framework_id=revised_framework.framework_id,
        expected_version=revised_framework.version,
        audit_id=final_audit.audit_id,
        resolutions=(),
    )
    assert final == confirmed_framework


def test_research_journey_rejects_working_release_for_matching() -> None:
    catalog = create_autospec(KnowledgeCatalog, instance=True, spec_set=True)
    matching = create_autospec(TheoryMatching, instance=True, spec_set=True)
    frameworks = create_autospec(
        ResearchFrameworkWorkflow,
        instance=True,
        spec_set=True,
    )
    journey = ResearchJourney(
        ResearchJourneyDependencies(catalog, matching, frameworks)
    )
    catalog.current_release.return_value = KnowledgeReleaseRef(
        knowledge_release_id="knowledge-working-1",
        level=KnowledgeReleaseLevel.WORKING,
        content_hash="sha256:working",
    )
    phenomenon = ConfirmedPhenomenonSnapshot(
        task_id=UUID(int=1),
        phenomenon_query_id=UUID(int=2),
        version=1,
        phenomenon="社区互助减少",
        research_intent=None,
        context=None,
    )

    with pytest.raises(ResearchJourneyConfigurationError, match="working"):
        journey.start_theory_matching(phenomenon=phenomenon)

    matching.start.assert_not_called()


def test_research_journey_defer_path_does_not_create_framework() -> None:
    catalog = create_autospec(KnowledgeCatalog, instance=True, spec_set=True)
    matching = create_autospec(TheoryMatching, instance=True, spec_set=True)
    frameworks = create_autospec(
        ResearchFrameworkWorkflow,
        instance=True,
        spec_set=True,
    )
    journey = ResearchJourney(
        ResearchJourneyDependencies(catalog, matching, frameworks)
    )
    deferred = DeferredTheoryPlanSnapshot(
        task_id=UUID(int=1),
        match_run_id=UUID(int=4),
        version=2,
        reason="现有来源不足，先暂停理论承诺",
        deferred_at=NOW,
    )
    matching.defer_plan.return_value = deferred

    result = journey.defer_theory_plan(
        match_run_id=deferred.match_run_id,
        expected_version=1,
        reason=deferred.reason,
    )

    assert result == deferred
    matching.defer_plan.assert_called_once_with(
        match_run_id=deferred.match_run_id,
        expected_version=1,
        reason=deferred.reason,
    )
    frameworks.create_draft.assert_not_called()
