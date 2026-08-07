from datetime import UTC, datetime
from uuid import UUID

import pytest

from qunxue_api.modules.theory_matching import (
    CandidateOrigin,
    TheoryCandidateContentSnapshot,
    TheoryCandidateSnapshot,
    TheoryDecisionAction,
    TheoryDecisionRecord,
    TheoryDecisionSetSnapshot,
    TheoryJudgementDraft,
    TheoryJudgementVerdict,
    TheoryPlanGateViolation,
    TheoryRelationSnapshot,
    TheoryUseAssignment,
    validate_theory_plan_confirmation,
)

NOW = datetime(2026, 7, 28, 8, 0, tzinfo=UTC)
CANDIDATE_A = UUID(int=5)
CANDIDATE_B = UUID(int=6)


def _candidate(
    candidate_id: UUID,
    *,
    eligible: bool = True,
    verdict: TheoryJudgementVerdict = TheoryJudgementVerdict.CONDITIONAL,
) -> TheoryCandidateSnapshot:
    return TheoryCandidateSnapshot(
        candidate_id=candidate_id,
        candidate_version=1,
        content=TheoryCandidateContentSnapshot(
            theory_id=None,
            title=f"候选 {candidate_id.int}",
            origin=CandidateOrigin.USER_SUPPLIED,
            problem_focus="解释社区互助变化",
            core_claims=("关系条件影响互助",),
            analysis_levels=("关系",),
            source_ids=(),
            reviewed_profile=None,
            formal_adoption_eligible=eligible,
            adoption_blockers=() if eligible else ("来源仍待核验",),
        ),
        judgement=TheoryJudgementDraft(
            verdict=verdict,
            match_rationale="用于门禁测试",
            applicable_conditions=("存在持续互动",),
            limitations=(),
            material_requirements=("互动材料",),
            evidence_gaps=(),
            alternative_explanations=(),
            evidence_ref_ids=(),
        ),
        trace_id=UUID(int=70 + candidate_id.int),
        request_id=UUID(int=80 + candidate_id.int),
        contract_version="theory-judgement.v1",
    )


def _decision(
    candidate_id: UUID,
    action: TheoryDecisionAction,
    *,
    related_candidate_ids: tuple[UUID, ...] = (),
) -> TheoryDecisionRecord:
    related_candidates = (
        {"related_candidate_ids": related_candidate_ids}
        if related_candidate_ids
        else {}
    )
    return TheoryDecisionRecord(
        decision_id=UUID(int=10 + candidate_id.int),
        candidate_id=candidate_id,
        candidate_version=1,
        action=action,
        reason="用户完成比较后作出的决定",
        related_source_ids=("source-1",),
        revised_applicability=None,
        recorded_at=NOW,
        **related_candidates,
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


def test_confirmation_gate_rejects_no_adopted_theory() -> None:
    decision_set = _decision_set(
        decisions=(_decision(CANDIDATE_A, TheoryDecisionAction.RETAIN),),
    )

    with pytest.raises(TheoryPlanGateViolation, match="at least one candidate"):
        validate_theory_plan_confirmation(
            decision_set,
            (_candidate(CANDIDATE_A),),
        )


def test_confirmation_gate_rejects_missing_multi_theory_roles_and_relations() -> None:
    decision_set = _decision_set(
        decisions=(
            _decision(CANDIDATE_A, TheoryDecisionAction.ADOPT),
            _decision(CANDIDATE_B, TheoryDecisionAction.ADOPT),
        ),
        assignments=(
            TheoryUseAssignment(
                candidate_id=CANDIDATE_A,
                role_code="primary",
                responsibility="解释互助规范如何被维持",
            ),
        ),
    )

    with pytest.raises(TheoryPlanGateViolation) as caught:
        validate_theory_plan_confirmation(
            decision_set,
            (_candidate(CANDIDATE_A), _candidate(CANDIDATE_B)),
        )

    assert "every adopted theory must have a role and responsibility" in (
        caught.value.violations
    )
    assert "all adopted theories must be connected by explained relations" in (
        caught.value.violations
    )


def test_confirmation_gate_accepts_complete_multi_theory_plan() -> None:
    decision_set = _decision_set(
        decisions=(
            _decision(CANDIDATE_A, TheoryDecisionAction.ADOPT),
            _decision(CANDIDATE_B, TheoryDecisionAction.ADOPT),
        ),
        assignments=(
            TheoryUseAssignment(CANDIDATE_A, "primary", "解释规范形成"),
            TheoryUseAssignment(CANDIDATE_B, "complementary", "解释资源约束"),
        ),
        relations=(
            TheoryRelationSnapshot(
                relation_id=UUID(int=30),
                candidate_ids=(CANDIDATE_A, CANDIDATE_B),
                relation_kind="complementary",
                explanation="分别解释规范与资源两个层面",
                premise_compatibility="两者分析层次不同且前提不冲突",
                supporting_evidence=("稳定互助规则",),
                excluding_evidence=("不存在资源差异",),
                distinguishing_evidence=("跨资源组比较",),
            ),
        ),
    )

    assert validate_theory_plan_confirmation(
        decision_set,
        (_candidate(CANDIDATE_A), _candidate(CANDIDATE_B)),
    ) == (CANDIDATE_A, CANDIDATE_B)


def test_confirmation_gate_treats_explicit_combine_as_selected_theories() -> None:
    combine = getattr(TheoryDecisionAction, "COMBINE", None)
    assert combine is not None
    decision_set = _decision_set(
        decisions=(
            _decision(
                CANDIDATE_A,
                combine,
                related_candidate_ids=(CANDIDATE_B,),
            ),
            _decision(
                CANDIDATE_B,
                combine,
                related_candidate_ids=(CANDIDATE_A,),
            ),
        ),
        assignments=(
            TheoryUseAssignment(CANDIDATE_A, "primary", "解释规范形成"),
            TheoryUseAssignment(CANDIDATE_B, "complementary", "解释资源约束"),
        ),
        relations=(
            TheoryRelationSnapshot(
                relation_id=UUID(int=31),
                candidate_ids=(CANDIDATE_A, CANDIDATE_B),
                relation_kind="combined",
                explanation="把规范与资源机制作为明确组合使用",
                premise_compatibility="分析层次不同且前提相容",
                supporting_evidence=("规范与资源共同变化",),
                excluding_evidence=("只有单一机制变化",),
                distinguishing_evidence=("跨情境机制比较",),
            ),
        ),
    )

    assert validate_theory_plan_confirmation(
        decision_set,
        (_candidate(CANDIDATE_A), _candidate(CANDIDATE_B)),
    ) == (CANDIDATE_A, CANDIDATE_B)


def test_confirmation_gate_rejects_ineligible_or_unjudged_adoption() -> None:
    decision_set = _decision_set(
        decisions=(_decision(CANDIDATE_A, TheoryDecisionAction.ADOPT),),
        assignments=(
            TheoryUseAssignment(CANDIDATE_A, "primary", "解释规范形成"),
        ),
    )

    with pytest.raises(TheoryPlanGateViolation) as caught:
        validate_theory_plan_confirmation(
            decision_set,
            (
                _candidate(
                    CANDIDATE_A,
                    eligible=False,
                    verdict=TheoryJudgementVerdict.INSUFFICIENT,
                ),
            ),
        )

    assert "every adopted theory must pass formal-adoption eligibility" in (
        caught.value.violations
    )
    assert "every adopted theory needs an applicable or conditional judgement" in (
        caught.value.violations
    )
