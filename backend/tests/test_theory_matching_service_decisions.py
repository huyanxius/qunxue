from dataclasses import replace
from uuid import UUID

import pytest

from qunxue_api.modules.knowledge_catalog import KnowledgeReleaseLevel, KnowledgeReleaseRef
from qunxue_api.modules.research_intake import ConfirmedPhenomenonSnapshot
from qunxue_api.modules.theory_matching import (
    CandidateContentStatus,
    CandidateOrigin,
    EvidenceBundleSnapshot,
    MatchCompletionBasis,
    MatchRunModelSnapshot,
    MatchRunRepository,
    MatchRunSnapshot,
    MatchRunStatus,
    TheoryCandidateContentSnapshot,
    TheoryCandidateJudge,
    TheoryCandidateSnapshot,
    TheoryDecisionAction,
    TheoryDecisionCommand,
    TheoryDecisionSetSnapshot,
    TheoryEvidenceSource,
    TheoryJudgementBatchResult,
    TheoryJudgementDraft,
    TheoryJudgementVerdict,
    TheoryMatchingService,
    TheoryUseAssignment,
)


class MemoryRuns(MatchRunRepository):
    def __init__(self) -> None:
        self.items: dict[UUID, MatchRunSnapshot] = {}
        self.decisions: dict[UUID, TheoryDecisionSetSnapshot] = {}
        self.plans: dict[UUID, object] = {}

    def add(self, snapshot: MatchRunSnapshot) -> MatchRunSnapshot:
        self.items[snapshot.match_run_id] = snapshot
        return snapshot

    def get(self, match_run_id: UUID) -> MatchRunSnapshot | None:
        return self.items.get(match_run_id)

    def add_decision_set(self, snapshot: TheoryDecisionSetSnapshot) -> TheoryDecisionSetSnapshot:
        self.decisions[snapshot.decision_set_id] = snapshot
        return snapshot

    def get_decision_set(self, decision_set_id: UUID) -> TheoryDecisionSetSnapshot | None:
        return self.decisions.get(decision_set_id)

    def get_decision_set_for_match_run(
        self, match_run_id: UUID
    ) -> TheoryDecisionSetSnapshot | None:
        return next(
            (item for item in self.decisions.values() if item.match_run_id == match_run_id),
            None,
        )

    def list_decision_sets(self, match_run_id: UUID):
        return tuple(
            item for item in self.decisions.values() if item.match_run_id == match_run_id
        )

    def save(self, snapshot: MatchRunSnapshot) -> MatchRunSnapshot:
        self.items[snapshot.match_run_id] = snapshot
        return snapshot

    def add_confirmed_plan(self, snapshot):
        self.plans[snapshot.theory_plan_id] = snapshot
        return snapshot

    def get_confirmed_plan(self, theory_plan_id):
        return self.plans.get(theory_plan_id)

    def get_confirmed_plan_for_decision_set(self, decision_set_id):
        return next(
            (item for item in self.plans.values() if item.decision_set_id == decision_set_id),
            None,
        )


def _run() -> MatchRunSnapshot:
    release = KnowledgeReleaseRef("release-1", KnowledgeReleaseLevel.FINAL, "sha256:r")
    candidate = TheoryCandidateSnapshot(
        candidate_id=UUID(int=1),
        candidate_version=1,
        content=TheoryCandidateContentSnapshot(
            theory_id="theory-1",
            title="关系机制",
            origin=CandidateOrigin.REVIEWED_KNOWLEDGE,
            problem_focus="解释互助变化",
            core_claims=("关系持续性影响互助",),
            analysis_levels=("关系",),
            source_ids=("source-1",),
            reviewed_profile=None,
            formal_adoption_eligible=True,
            adoption_blockers=(),
            knowledge_id="D1:C001",
            content_status=CandidateContentStatus.REVIEWED,
        ),
        judgement=TheoryJudgementDraft(
            verdict=TheoryJudgementVerdict.CONDITIONAL,
            match_rationale="有条件适配",
            applicable_conditions=("存在持续互动",),
            limitations=("缺少跨情境材料",),
            material_requirements=("互动记录",),
            evidence_gaps=(),
            alternative_explanations=("资源变化",),
            evidence_ref_ids=("evidence-1",),
        ),
        trace_id=UUID(int=2),
        request_id=UUID(int=3),
        contract_version="v1",
    )
    phenomenon = ConfirmedPhenomenonSnapshot(
        task_id=UUID(int=10),
        phenomenon_query_id=UUID(int=11),
        version=1,
        phenomenon="社区互助减少",
        research_intent="解释机制",
        context="社区",
        content_hash="sha256:p",
        evidence_refs=(),
    )
    return MatchRunSnapshot(
        match_run_id=UUID(int=12),
        task_id=phenomenon.task_id,
        version=1,
        status=MatchRunStatus.AWAITING_DECISION,
        phenomenon=phenomenon,
        knowledge_release=release,
        evidence_bundle=EvidenceBundleSnapshot(
            evidence_bundle_id="bundle-1",
            version=1,
            content_hash="sha256:b",
            release=release,
            theory_profiles=(),
            evidence_items=(),
        ),
        candidates=(candidate,),
        stable_candidate_order=(candidate.candidate_id,),
        model=MatchRunModelSnapshot(
            "provider", "model", "base", False, "release-1", UUID(int=4), UUID(int=5), "v1"
        ),
    )


class NoopEvidence(TheoryEvidenceSource):
    def retrieve(self, *, phenomenon, release):
        raise AssertionError("start is not part of this test")


class NoopJudge(TheoryCandidateJudge):
    def judge_and_rerank(self, *, input: object) -> TheoryJudgementBatchResult:
        raise AssertionError("start is not part of this test")


def test_decision_set_is_saved_and_confirmed_plan_is_a_persisted_snapshot() -> None:
    repository = MemoryRuns()
    match_run = _run()
    repository.add(match_run)
    service = TheoryMatchingService(
        evidence_source=NoopEvidence(),
        judge=NoopJudge(),
        repository=repository,
        provider="provider",
        model_version="model",
        capability="base",
        contract_version="v1",
    )

    decision_set = service.record_decisions(
        match_run_id=match_run.match_run_id,
        expected_version=1,
        decisions=(
            TheoryDecisionCommand(
                UUID(int=1),
                1,
                TheoryDecisionAction.ADOPT,
                "采用，因为有条件适配",
                related_source_ids=("source-1",),
            ),
        ),
        use_assignments=(TheoryUseAssignment(UUID(int=1), "primary", "解释互助变化"),),
        relations=(),
    )

    assert repository.get_decision_set(decision_set.decision_set_id) == decision_set
    confirmed = service.confirm_plan(
        decision_set_id=decision_set.decision_set_id, expected_version=1
    )
    assert confirmed.decision_set_id == decision_set.decision_set_id
    assert confirmed.knowledge_release.knowledge_release_id == "release-1"
    assert confirmed.candidates[0].candidate_id == UUID(int=1)
    assert service.get_confirmed_plan(confirmed.theory_plan_id) == confirmed
    assert (
        service.confirm_plan(
            decision_set_id=decision_set.decision_set_id,
            expected_version=1,
        ).theory_plan_id
        == confirmed.theory_plan_id
    )


def test_confirmation_rejects_stale_decision_set_version() -> None:
    repository = MemoryRuns()
    repository.add(_run())
    service = TheoryMatchingService(
        evidence_source=NoopEvidence(),
        judge=NoopJudge(),
        repository=repository,
        provider="provider",
        model_version="model",
        capability="base",
        contract_version="v1",
    )
    decision_set = service.record_decisions(
        match_run_id=UUID(int=12),
        expected_version=1,
        decisions=(TheoryDecisionCommand(UUID(int=1), 1, TheoryDecisionAction.ADOPT, "采用"),),
        use_assignments=(TheoryUseAssignment(UUID(int=1), "primary", "解释"),),
        relations=(),
    )

    with pytest.raises(ValueError, match="stale"):
        service.confirm_plan(decision_set_id=decision_set.decision_set_id, expected_version=2)


def test_confirmation_rejects_an_empty_adopted_theory_assignment() -> None:
    repository = MemoryRuns()
    repository.add(_run())
    service = TheoryMatchingService(
        evidence_source=NoopEvidence(),
        judge=NoopJudge(),
        repository=repository,
        provider="provider",
        model_version="model",
        capability="base",
        contract_version="v1",
    )
    decision_set = service.record_decisions(
        match_run_id=UUID(int=12),
        expected_version=1,
        decisions=(
            TheoryDecisionCommand(
                UUID(int=1),
                1,
                TheoryDecisionAction.ADOPT,
                "采用",
            ),
        ),
        use_assignments=(TheoryUseAssignment(UUID(int=1), "", ""),),
        relations=(),
    )

    with pytest.raises(ValueError, match="non-empty role and responsibility"):
        service.confirm_plan(
            decision_set_id=decision_set.decision_set_id,
            expected_version=1,
        )


def test_decision_rejects_sources_outside_the_candidate_evidence_closure() -> None:
    repository = MemoryRuns()
    match_run = _run()
    repository.add(match_run)
    service = TheoryMatchingService(
        evidence_source=NoopEvidence(),
        judge=NoopJudge(),
        repository=repository,
        provider="provider",
        model_version="model",
        capability="base",
        contract_version="v1",
    )

    with pytest.raises(ValueError, match="source"):
        service.record_decisions(
            match_run_id=match_run.match_run_id,
            expected_version=1,
            decisions=(
                TheoryDecisionCommand(
                    UUID(int=1),
                    1,
                    TheoryDecisionAction.ADOPT,
                    "不能绑定未返回的来源",
                    related_source_ids=("source-forged",),
                ),
            ),
            use_assignments=(
                TheoryUseAssignment(UUID(int=1), "primary", "解释互助变化"),
            ),
            relations=(),
        )


def test_match_run_accepts_only_one_final_decision_set() -> None:
    repository = MemoryRuns()
    match_run = _run()
    repository.add(match_run)
    service = TheoryMatchingService(
        evidence_source=NoopEvidence(),
        judge=NoopJudge(),
        repository=repository,
        provider="provider",
        model_version="model",
        capability="base",
        contract_version="v1",
    )
    command = TheoryDecisionCommand(
        UUID(int=1),
        1,
        TheoryDecisionAction.ADOPT,
        "采用",
        related_source_ids=("source-1",),
    )
    service.record_decisions(
        match_run_id=match_run.match_run_id,
        expected_version=1,
        decisions=(command,),
        use_assignments=(TheoryUseAssignment(UUID(int=1), "primary", "解释"),),
        relations=(),
    )

    with pytest.raises(ValueError, match="already has a final decision set"):
        service.record_decisions(
            match_run_id=match_run.match_run_id,
            expected_version=1,
            decisions=(command,),
            use_assignments=(TheoryUseAssignment(UUID(int=1), "primary", "解释"),),
            relations=(),
        )


def test_partial_match_requires_persisted_user_acknowledgement_before_decisions() -> None:
    repository = MemoryRuns()
    failed_candidate_id = UUID(int=99)
    partial = replace(
        _run(),
        status=MatchRunStatus.PARTIAL_FAILURE,
        completion_basis=MatchCompletionBasis.PARTIAL,
        failed_candidate_ids=(failed_candidate_id,),
    )
    repository.add(partial)
    service = TheoryMatchingService(
        evidence_source=NoopEvidence(),
        judge=NoopJudge(),
        repository=repository,
        provider="provider",
        model_version="model",
        capability="base",
        contract_version="v1",
    )
    command = TheoryDecisionCommand(UUID(int=1), 1, TheoryDecisionAction.ADOPT, "采用")

    with pytest.raises(ValueError, match="acknowledge partial completion"):
        service.record_decisions(
            match_run_id=partial.match_run_id,
            expected_version=1,
            decisions=(command,),
            use_assignments=(TheoryUseAssignment(UUID(int=1), "primary", "解释"),),
            relations=(),
        )

    acknowledged = service.acknowledge_partial_completion(
        match_run_id=partial.match_run_id,
        expected_version=1,
        acknowledged_candidate_ids=(UUID(int=1),),
        failed_candidate_ids=(failed_candidate_id,),
        reason="接受已完成候选并记录失败项",
    )

    assert acknowledged.version == 2
    assert acknowledged.partial_completion_acknowledged is True
    assert acknowledged.completion_basis.value == "partial_with_user_ack"
    assert acknowledged.partial_completion_acknowledgement_reason == "接受已完成候选并记录失败项"
    assert repository.get(partial.match_run_id) == acknowledged

    saved = service.record_decisions(
        match_run_id=partial.match_run_id,
        expected_version=2,
        decisions=(command,),
        use_assignments=(TheoryUseAssignment(UUID(int=1), "primary", "解释"),),
        relations=(),
    )
    assert saved.match_run_id == partial.match_run_id
