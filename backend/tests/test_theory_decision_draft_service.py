from dataclasses import replace
from uuid import UUID

import pytest
from test_theory_matching_service_decisions import (
    NoopEvidence,
    NoopJudge,
    _run,
)

from qunxue_api.modules.theory_matching import (
    MatchCompletionBasis,
    MatchRunRepository,
    MatchRunStatus,
    TheoryDecisionAction,
    TheoryDecisionCommand,
    TheoryDecisionDraftSnapshot,
    TheoryDecisionSetSnapshot,
    TheoryMatchingService,
    TheoryUseAssignment,
)


class DraftRuns(MatchRunRepository):
    def __init__(self) -> None:
        self.run = _run()
        self.draft: TheoryDecisionDraftSnapshot | None = None
        self.draft_replays: dict[str, tuple[str, TheoryDecisionDraftSnapshot]] = {}
        self.decision_sets: dict[UUID, TheoryDecisionSetSnapshot] = {}
        self.plans: dict[UUID, object] = {}

    def add(self, snapshot):
        self.run = snapshot
        return snapshot

    def get(self, match_run_id):
        return self.run if match_run_id == self.run.match_run_id else None

    def save(self, snapshot):
        self.run = snapshot
        return snapshot

    def delete(self, match_run_id):
        return None

    def get_decision_draft(self, match_run_id):
        return self.draft if match_run_id == self.run.match_run_id else None

    def get_decision_draft_replay(self, *, match_run_id, idempotency_key):
        return self.draft_replays.get(idempotency_key)

    def save_decision_draft(
        self,
        snapshot,
        *,
        expected_version,
        idempotency_key,
        request_hash,
        request_record_id,
    ):
        replay = self.draft_replays.get(idempotency_key)
        if replay is not None:
            if replay[0] != request_hash:
                raise ValueError("Idempotency-Key was already used for another draft")
            return replay[1]
        actual = 0 if self.draft is None else self.draft.version
        if actual != expected_version:
            raise ValueError("stale theory decision draft version")
        self.draft = snapshot
        self.draft_replays[idempotency_key] = (request_hash, snapshot)
        return snapshot

    def add_decision_set(self, snapshot):
        existing = next(
            (
                item
                for item in self.decision_sets.values()
                if item.match_run_id == snapshot.match_run_id
                and item.draft_version == snapshot.draft_version
            ),
            None,
        )
        if existing is not None:
            return existing
        self.decision_sets[snapshot.decision_set_id] = snapshot
        return snapshot

    def get_decision_set(self, decision_set_id):
        return self.decision_sets.get(decision_set_id)

    def get_decision_set_for_match_run(self, match_run_id, draft_version=None):
        return next(
            (
                item
                for item in self.decision_sets.values()
                if item.match_run_id == match_run_id
                and (draft_version is None or item.draft_version == draft_version)
            ),
            None,
        )

    def list_decision_sets(self, match_run_id):
        return tuple(
            item for item in self.decision_sets.values() if item.match_run_id == match_run_id
        )

    def add_confirmed_plan(self, snapshot):
        existing = self.get_confirmed_plan_for_task(snapshot.task_id)
        if existing is not None:
            return existing
        self.plans[snapshot.theory_plan_id] = snapshot
        return snapshot

    def get_confirmed_plan(self, theory_plan_id):
        return self.plans.get(theory_plan_id)

    def get_confirmed_plan_for_decision_set(self, decision_set_id):
        return next(
            (item for item in self.plans.values() if item.decision_set_id == decision_set_id),
            None,
        )

    def get_confirmed_plan_for_task(self, task_id):
        return next((item for item in self.plans.values() if item.task_id == task_id), None)


def _service(repository: DraftRuns) -> TheoryMatchingService:
    return TheoryMatchingService(
        evidence_source=NoopEvidence(),
        judge=NoopJudge(),
        repository=repository,
        provider="provider",
        model_version="model",
        capability="base",
        contract_version="v1",
    )


def _draft_payload(reason: str = "用户认为该理论能解释持续互动与互助变化") -> dict:
    return {
        "completion_basis": MatchCompletionBasis.COMPLETE,
        "decisions": (
            TheoryDecisionCommand(
                UUID(int=1),
                1,
                TheoryDecisionAction.ADOPT,
                reason,
                related_source_ids=("source-1",),
            ),
        ),
        "use_assignments": (
            TheoryUseAssignment(UUID(int=1), "primary", "解释互助变化的关系机制"),
        ),
        "relations": (),
        "acknowledged_candidate_ids": (),
        "failed_candidate_ids": (),
        "partial_completion_acknowledgement_reason": None,
    }


def test_draft_autosave_has_cas_idempotent_replay_and_restart_shape() -> None:
    repository = DraftRuns()
    service = _service(repository)

    first = service.save_decision_draft(
        match_run_id=repository.run.match_run_id,
        expected_match_run_version=1,
        expected_draft_version=0,
        idempotency_key="draft-1",
        request_hash="sha256:first",
        **_draft_payload(),
    )
    replay = service.save_decision_draft(
        match_run_id=repository.run.match_run_id,
        expected_match_run_version=1,
        expected_draft_version=0,
        idempotency_key="draft-1",
        request_hash="sha256:first",
        **_draft_payload(),
    )

    assert first.version == 1
    assert replay == first
    assert service.get_decision_draft(repository.run.match_run_id) == first
    assert first.decisions[0].reason.startswith("用户认为")

    with pytest.raises(ValueError, match="stale theory decision draft version"):
        service.save_decision_draft(
            match_run_id=repository.run.match_run_id,
            expected_match_run_version=1,
            expected_draft_version=0,
            idempotency_key="draft-stale",
            request_hash="sha256:stale",
            **_draft_payload("过期修改"),
        )


def test_incomplete_user_input_is_recoverable_but_cannot_be_finalized() -> None:
    repository = DraftRuns()
    service = _service(repository)
    incomplete = _draft_payload("")
    incomplete["decisions"] = (
        TheoryDecisionCommand(
            UUID(int=1),
            1,
            None,
            "",
            related_source_ids=("source-1",),
        ),
    )
    incomplete["use_assignments"] = (
        TheoryUseAssignment(UUID(int=1), "", ""),
    )

    saved = service.save_decision_draft(
        match_run_id=repository.run.match_run_id,
        expected_match_run_version=1,
        expected_draft_version=0,
        idempotency_key="draft-incomplete",
        request_hash="sha256:incomplete",
        **incomplete,
    )

    assert saved.decisions[0].action is None
    assert saved.decisions[0].reason == ""
    assert saved.use_assignments[0].role_code == ""
    with pytest.raises(ValueError, match="final decision action"):
        service.finalize_decision_draft(
            match_run_id=repository.run.match_run_id,
            expected_match_run_version=1,
            expected_draft_version=saved.version,
            idempotency_key="final-incomplete",
            request_hash="sha256:final-incomplete",
        )


def test_editing_saved_draft_invalidates_old_final_decision_set() -> None:
    repository = DraftRuns()
    service = _service(repository)
    first = service.save_decision_draft(
        match_run_id=repository.run.match_run_id,
        expected_match_run_version=1,
        expected_draft_version=0,
        idempotency_key="draft-1",
        request_hash="sha256:first",
        **_draft_payload(),
    )
    decision_set = service.finalize_decision_draft(
        match_run_id=repository.run.match_run_id,
        expected_match_run_version=1,
        expected_draft_version=first.version,
        idempotency_key="final-1",
        request_hash="sha256:final-1",
    )
    second = service.save_decision_draft(
        match_run_id=repository.run.match_run_id,
        expected_match_run_version=1,
        expected_draft_version=first.version,
        idempotency_key="draft-2",
        request_hash="sha256:second",
        **_draft_payload("补充理由：只在存在持续互动记录时采用"),
    )

    assert second.version == 2
    with pytest.raises(ValueError, match="superseded by a newer draft"):
        service.confirm_plan(
            decision_set_id=decision_set.decision_set_id,
            expected_version=decision_set.version,
        )


def test_task_allows_only_one_confirmed_plan_and_replays_same_plan() -> None:
    repository = DraftRuns()
    service = _service(repository)
    first = service.save_decision_draft(
        match_run_id=repository.run.match_run_id,
        expected_match_run_version=1,
        expected_draft_version=0,
        idempotency_key="draft-1",
        request_hash="sha256:first",
        **_draft_payload(),
    )
    decision_set = service.finalize_decision_draft(
        match_run_id=repository.run.match_run_id,
        expected_match_run_version=1,
        expected_draft_version=first.version,
        idempotency_key="final-1",
        request_hash="sha256:final-1",
    )
    confirmed = service.confirm_plan(
        decision_set_id=decision_set.decision_set_id,
        expected_version=decision_set.version,
        idempotency_key="confirm-a",
        request_hash="sha256:confirm-current",
    )

    assert (
        service.confirm_plan(
            decision_set_id=decision_set.decision_set_id,
            expected_version=decision_set.version,
            idempotency_key="confirm-b",
            request_hash="sha256:confirm-current",
        ).theory_plan_id
        == confirmed.theory_plan_id
    )
    with pytest.raises(ValueError, match="confirmed theory plan"):
        service.save_decision_draft(
            match_run_id=repository.run.match_run_id,
            expected_match_run_version=1,
            expected_draft_version=first.version,
            idempotency_key="draft-after-confirmation",
            request_hash="sha256:draft-after-confirmation",
            **_draft_payload("确认后不应再改写的理由"),
        )


def test_zero_success_partial_run_cannot_be_acknowledged() -> None:
    repository = DraftRuns()
    repository.run = replace(
        repository.run,
        candidates=(),
        status=MatchRunStatus.PARTIAL_FAILURE,
        completion_basis=MatchCompletionBasis.PARTIAL,
        failed_candidate_ids=(UUID(int=91),),
    )
    service = _service(repository)

    with pytest.raises(ValueError, match="without a successful candidate"):
        service.acknowledge_partial_completion(
            match_run_id=repository.run.match_run_id,
            expected_version=1,
            acknowledged_candidate_ids=(),
            failed_candidate_ids=(UUID(int=91),),
            reason="不应允许空候选继续",
        )
