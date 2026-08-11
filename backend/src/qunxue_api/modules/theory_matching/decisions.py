from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from qunxue_api.modules.theory_matching.public import (
    ConfirmedTheoryPlanSnapshot,
    DeferredTheoryPlanSnapshot,
    MatchCompletionBasis,
    MatchRunSnapshot,
    TheoryDecisionAction,
    TheoryDecisionCommand,
    TheoryDecisionRecord,
    TheoryDecisionRepository,
    TheoryDecisionSetSnapshot,
    TheoryRelationCommand,
    TheoryRelationSnapshot,
    TheoryUseAssignment,
)
from qunxue_api.modules.theory_matching.rules import validate_theory_plan_confirmation


class TheoryDecisionConflict(ValueError):
    pass


class TheoryDecisionService:
    """Records user-owned decisions and freezes a validated handoff snapshot."""

    def __init__(
        self,
        repository: TheoryDecisionRepository,
        *,
        id_factory: Callable[[], UUID] = uuid4,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._id_factory = id_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def record(
        self,
        *,
        match_run: MatchRunSnapshot,
        expected_version: int,
        completion_basis: MatchCompletionBasis,
        decisions: tuple[TheoryDecisionCommand, ...],
        use_assignments: tuple[TheoryUseAssignment, ...],
        relations: tuple[TheoryRelationCommand, ...],
    ) -> TheoryDecisionSetSnapshot:
        if match_run.version != expected_version:
            raise TheoryDecisionConflict("Match run version is stale.")
        if match_run.completion_basis is not completion_basis:
            raise TheoryDecisionConflict("Match completion basis is stale.")
        candidates = {item.candidate_id: item for item in match_run.candidates}
        if not decisions:
            raise TheoryDecisionConflict("At least one user decision is required.")
        seen: set[UUID] = set()
        records: list[TheoryDecisionRecord] = []
        now = self._clock()
        for command in decisions:
            candidate = candidates.get(command.candidate_id)
            if candidate is None or command.candidate_id in seen:
                raise TheoryDecisionConflict(
                    "Each decision must reference one unique candidate in the match run."
                )
            if candidate.candidate_version != command.candidate_version:
                raise TheoryDecisionConflict("Candidate version is stale.")
            if not command.reason.strip():
                raise TheoryDecisionConflict("Every decision requires a user reason.")
            if (
                command.action is TheoryDecisionAction.REVISE_APPLICABILITY
                and not (command.revised_applicability or "").strip()
            ):
                raise TheoryDecisionConflict(
                    "An applicability revision requires the revised boundary."
                )
            if command.action is not TheoryDecisionAction.REVISE_APPLICABILITY and (
                command.revised_applicability is not None
            ):
                raise TheoryDecisionConflict(
                    "Only an applicability revision may include a revised boundary."
                )
            if not set(command.related_source_ids) <= set(candidate.content.source_ids):
                raise TheoryDecisionConflict(
                    "Decision evidence must belong to the selected candidate."
                )
            if not set(command.related_candidate_ids) <= set(candidates):
                raise TheoryDecisionConflict(
                    "Related candidates must belong to the same match run."
                )
            seen.add(command.candidate_id)
            records.append(
                TheoryDecisionRecord(
                    decision_id=self._id_factory(),
                    candidate_id=command.candidate_id,
                    candidate_version=command.candidate_version,
                    action=command.action,
                    reason=command.reason.strip(),
                    related_source_ids=command.related_source_ids,
                    related_candidate_ids=command.related_candidate_ids,
                    revised_applicability=(
                        command.revised_applicability.strip()
                        if command.revised_applicability
                        else None
                    ),
                    recorded_at=now,
                )
            )

        for assignment in use_assignments:
            if assignment.candidate_id not in candidates:
                raise TheoryDecisionConflict(
                    "Theory assignments must belong to the same match run."
                )
            if not assignment.role_code.strip() or not assignment.responsibility.strip():
                raise TheoryDecisionConflict(
                    "Theory assignments require a role and responsibility."
                )
        relation_snapshots: list[TheoryRelationSnapshot] = []
        for relation in relations:
            if len(set(relation.candidate_ids)) < 2 or not set(
                relation.candidate_ids
            ) <= set(candidates):
                raise TheoryDecisionConflict(
                    "A theory relation requires distinct candidates from the match run."
                )
            relation_snapshots.append(
                TheoryRelationSnapshot(
                    relation_id=self._id_factory(),
                    candidate_ids=relation.candidate_ids,
                    relation_kind=relation.relation_kind.strip(),
                    explanation=relation.explanation.strip(),
                    premise_compatibility=relation.premise_compatibility.strip(),
                    supporting_evidence=relation.supporting_evidence,
                    excluding_evidence=relation.excluding_evidence,
                    distinguishing_evidence=relation.distinguishing_evidence,
                )
            )

        snapshot = TheoryDecisionSetSnapshot(
            decision_set_id=self._id_factory(),
            match_run_id=match_run.match_run_id,
            version=1,
            decisions=tuple(records),
            use_assignments=use_assignments,
            relations=tuple(relation_snapshots),
            recorded_at=now,
        )
        return self._repository.add_decision_set(snapshot)

    def list(self, match_run_id: UUID) -> tuple[TheoryDecisionSetSnapshot, ...]:
        return self._repository.list_decision_sets(match_run_id)

    def get(self, decision_set_id: UUID) -> TheoryDecisionSetSnapshot:
        snapshot = self._repository.get_decision_set(decision_set_id)
        if snapshot is None:
            raise LookupError(decision_set_id)
        return snapshot

    def confirm(
        self,
        *,
        decision_set_id: UUID,
        expected_version: int,
        match_run: MatchRunSnapshot,
    ) -> ConfirmedTheoryPlanSnapshot:
        existing = self._repository.get_confirmed_plan(match_run.match_run_id)
        if existing is not None:
            if existing.decision_set_id != decision_set_id:
                raise TheoryDecisionConflict("A different theory plan is already confirmed.")
            return existing
        decision_set = self._repository.get_decision_set(decision_set_id)
        if decision_set is None or decision_set.match_run_id != match_run.match_run_id:
            raise LookupError(decision_set_id)
        if decision_set.version != expected_version:
            raise TheoryDecisionConflict("Decision set version is stale.")
        if (
            match_run.completion_basis is not MatchCompletionBasis.COMPLETE
            and not match_run.partial_completion_acknowledged
        ):
            raise TheoryDecisionConflict(
                "Partial matching must be acknowledged before confirmation."
            )
        validate_theory_plan_confirmation(decision_set, match_run.candidates)
        snapshot = ConfirmedTheoryPlanSnapshot(
            theory_plan_id=self._id_factory(),
            task_id=match_run.task_id,
            match_run_id=match_run.match_run_id,
            decision_set_id=decision_set.decision_set_id,
            version=1,
            phenomenon=match_run.phenomenon,
            knowledge_release=match_run.knowledge_release,
            evidence_bundle=match_run.evidence_bundle,
            candidates=match_run.candidates,
            decisions=decision_set.decisions,
            use_assignments=decision_set.use_assignments,
            relations=decision_set.relations,
            confirmed_at=self._clock(),
        )
        return self._repository.add_confirmed_plan(snapshot)

    def confirmed(self, match_run_id: UUID) -> ConfirmedTheoryPlanSnapshot | None:
        return self._repository.get_confirmed_plan(match_run_id)

    def defer(
        self, *, match_run: MatchRunSnapshot, expected_version: int, reason: str
    ) -> DeferredTheoryPlanSnapshot:
        if match_run.version != expected_version:
            raise TheoryDecisionConflict("Match run version is stale.")
        snapshot = DeferredTheoryPlanSnapshot(
            task_id=match_run.task_id,
            match_run_id=match_run.match_run_id,
            version=1,
            reason=reason.strip(),
            deferred_at=self._clock(),
        )
        return self._repository.add_deferred_plan(snapshot)

    def deferred(self, match_run_id: UUID) -> DeferredTheoryPlanSnapshot | None:
        return self._repository.get_deferred_plan(match_run_id)
