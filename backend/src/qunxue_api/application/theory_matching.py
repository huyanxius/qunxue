import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol
from uuid import UUID, uuid4

from qunxue_api.modules.knowledge_catalog import KnowledgeCatalog, KnowledgeUsePurpose
from qunxue_api.modules.research_intake import (
    ConfirmedPhenomenonSnapshot,
    ResearchTask,
    ResearchTaskRepository,
    ResearchTaskStatus,
)
from qunxue_api.modules.theory_matching import (
    ConfirmedTheoryPlanSnapshot,
    DeferredTheoryPlanSnapshot,
    MatchCompletionBasis,
    MatchRunSnapshot,
    TheoryDecisionCommand,
    TheoryDecisionService,
    TheoryDecisionSetSnapshot,
    TheoryMatching,
    TheoryRelationCommand,
    TheoryUseAssignment,
)


class MatchingRequestConflict(ValueError):
    pass


class MatchingSnapshotConflict(ValueError):
    pass


class MatchingRequestRepository(Protocol):
    def get_by_idempotency_key(
        self,
        *,
        user_id: UUID,
        idempotency_key: str,
    ) -> tuple[str, UUID] | None: ...

    def add(
        self,
        *,
        request_record_id: UUID,
        user_id: UUID,
        idempotency_key: str,
        request_hash: str,
        match_run_id: UUID,
        created_at: datetime,
    ) -> None: ...

    def owns(self, *, user_id: UUID, match_run_id: UUID) -> bool: ...


class TheoryDecisionRequestRepository(Protocol):
    def get_by_idempotency_key(
        self, *, user_id: UUID, idempotency_key: str
    ) -> tuple[str, UUID] | None: ...

    def add(
        self,
        *,
        request_record_id: UUID,
        user_id: UUID,
        idempotency_key: str,
        request_hash: str,
        decision_set_id: UUID,
        created_at: datetime,
    ) -> None: ...


class TheoryMatchingApplication:
    """Owns HTTP request idempotency and cross-module matching coordination."""

    def __init__(
        self,
        *,
        catalog: KnowledgeCatalog,
        matching: TheoryMatching,
        decisions: TheoryDecisionService,
        matching_requests: MatchingRequestRepository,
        decision_requests: TheoryDecisionRequestRepository,
        research_tasks: ResearchTaskRepository,
        id_factory: Callable[[], UUID] = uuid4,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._catalog = catalog
        self._matching = matching
        self._decisions = decisions
        self._matching_requests = matching_requests
        self._decision_requests = decision_requests
        self._research_tasks = research_tasks
        self._id_factory = id_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def start(
        self,
        *,
        user_id: UUID,
        task: ResearchTask,
        phenomenon: ConfirmedPhenomenonSnapshot,
        idempotency_key: str,
        expected_task_version: int,
        phenomenon_query_id: UUID,
        phenomenon_version: int,
        requested_knowledge_release_id: str | None,
    ) -> MatchRunSnapshot:
        request_hash = _request_hash(
            task_id=task.task_id,
            expected_task_version=expected_task_version,
            phenomenon_query_id=phenomenon_query_id,
            phenomenon_version=phenomenon_version,
            requested_knowledge_release_id=requested_knowledge_release_id,
        )
        existing = self._matching_requests.get_by_idempotency_key(
            user_id=user_id,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            existing_request_hash, existing_match_run_id = existing
            if existing_request_hash != request_hash:
                raise MatchingRequestConflict(
                    "Idempotency-Key was already used for a different matching request."
                )
            return self._matching.get(existing_match_run_id)

        if task.user_id != user_id or task.version != expected_task_version:
            raise MatchingSnapshotConflict("Research task version is stale.")
        if (
            phenomenon.task_id != task.task_id
            or phenomenon.phenomenon_query_id != phenomenon_query_id
            or phenomenon.version != phenomenon_version
        ):
            raise MatchingSnapshotConflict("Confirmed phenomenon snapshot does not match request.")

        release = self._catalog.current_release(purpose=KnowledgeUsePurpose.MATCH)
        if (
            requested_knowledge_release_id is not None
            and requested_knowledge_release_id != release.knowledge_release_id
        ):
            raise MatchingSnapshotConflict("Knowledge release is not the current match release.")

        match_run = self._matching.start(phenomenon=phenomenon, release=release)
        now = self._clock()
        saved_task = self._research_tasks.save_progress(
            replace(
                task,
                status=ResearchTaskStatus.MATCH_GENERATING,
                version=task.version + 1,
                updated_at=now,
                current_match_run_id=match_run.match_run_id,
            )
        )
        if saved_task is None:
            raise RuntimeError("owned research task disappeared during theory matching")
        self._matching_requests.add(
            request_record_id=self._id_factory(),
            user_id=user_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            match_run_id=match_run.match_run_id,
            created_at=now,
        )
        return match_run

    def get(self, match_run_id: UUID, *, user_id: UUID) -> MatchRunSnapshot:
        if not self._matching_requests.owns(user_id=user_id, match_run_id=match_run_id):
            raise LookupError(match_run_id)
        return self._matching.get(match_run_id)

    def record_decisions(
        self,
        *,
        match_run_id: UUID,
        user_id: UUID,
        idempotency_key: str,
        expected_version: int,
        completion_basis: MatchCompletionBasis,
        decisions: tuple[TheoryDecisionCommand, ...],
        use_assignments: tuple[TheoryUseAssignment, ...],
        relations: tuple[TheoryRelationCommand, ...],
    ) -> TheoryDecisionSetSnapshot:
        match_run = self.get(match_run_id, user_id=user_id)
        request_hash = _decision_request_hash(
            match_run_id=match_run_id,
            expected_version=expected_version,
            completion_basis=completion_basis,
            decisions=decisions,
            use_assignments=use_assignments,
            relations=relations,
        )
        existing = self._decision_requests.get_by_idempotency_key(
            user_id=user_id, idempotency_key=idempotency_key
        )
        if existing is not None:
            existing_hash, decision_set_id = existing
            if existing_hash != request_hash:
                raise MatchingRequestConflict(
                    "Idempotency-Key was already used for a different theory decision request."
                )
            return self._decisions.get(decision_set_id)
        snapshot = self._decisions.record(
            match_run=match_run,
            expected_version=expected_version,
            completion_basis=completion_basis,
            decisions=decisions,
            use_assignments=use_assignments,
            relations=relations,
        )
        self._decision_requests.add(
            request_record_id=self._id_factory(),
            user_id=user_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            decision_set_id=snapshot.decision_set_id,
            created_at=self._clock(),
        )
        return snapshot

    def list_decisions(
        self, match_run_id: UUID, *, user_id: UUID
    ) -> tuple[TheoryDecisionSetSnapshot, ...]:
        self.get(match_run_id, user_id=user_id)
        return self._decisions.list(match_run_id)

    def confirmed_plan(
        self, match_run_id: UUID, *, user_id: UUID
    ) -> ConfirmedTheoryPlanSnapshot | None:
        self.get(match_run_id, user_id=user_id)
        return self._decisions.confirmed(match_run_id)

    def deferred_plan(
        self, match_run_id: UUID, *, user_id: UUID
    ) -> DeferredTheoryPlanSnapshot | None:
        self.get(match_run_id, user_id=user_id)
        return self._decisions.deferred(match_run_id)

    def confirm_plan(
        self,
        *,
        decision_set_id: UUID,
        user_id: UUID,
        expected_version: int,
    ) -> ConfirmedTheoryPlanSnapshot:
        decision_set = self._decisions.get(decision_set_id)
        match_run = self.get(decision_set.match_run_id, user_id=user_id)
        existing = self._decisions.confirmed(match_run.match_run_id)
        if existing is not None:
            if existing.decision_set_id != decision_set_id:
                raise MatchingRequestConflict(
                    "A different theory plan is already confirmed."
                )
            return existing
        confirmed = self._decisions.confirm(
            decision_set_id=decision_set_id,
            expected_version=expected_version,
            match_run=match_run,
        )
        task = self._research_tasks.get(match_run.task_id, user_id)
        if task is None:
            raise RuntimeError("owned research task disappeared during confirmation")
        adopted_count = sum(
            item.action.value in {"adopt", "combine"} for item in confirmed.decisions
        )
        saved = self._research_tasks.save_progress(
            replace(
                task,
                status=ResearchTaskStatus.DECISIONS_RECORDED,
                version=task.version + 1,
                adopted_theory_count=adopted_count,
                updated_at=self._clock(),
            )
        )
        if saved is None:
            raise RuntimeError("owned research task disappeared during confirmation")
        return confirmed

    def defer_plan(
        self,
        *,
        match_run_id: UUID,
        user_id: UUID,
        expected_version: int,
        reason: str,
    ) -> DeferredTheoryPlanSnapshot:
        match_run = self.get(match_run_id, user_id=user_id)
        return self._decisions.defer(
            match_run=match_run,
            expected_version=expected_version,
            reason=reason,
        )


def _request_hash(
    *,
    task_id: UUID,
    expected_task_version: int,
    phenomenon_query_id: UUID,
    phenomenon_version: int,
    requested_knowledge_release_id: str | None,
) -> str:
    payload = json.dumps(
        {
            "task_id": str(task_id),
            "expected_task_version": expected_task_version,
            "phenomenon_query_id": str(phenomenon_query_id),
            "phenomenon_version": phenomenon_version,
            "knowledge_release_id": requested_knowledge_release_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"sha256:{sha256(payload.encode()).hexdigest()}"


def _decision_request_hash(
    *,
    match_run_id: UUID,
    expected_version: int,
    completion_basis: MatchCompletionBasis,
    decisions: tuple[TheoryDecisionCommand, ...],
    use_assignments: tuple[TheoryUseAssignment, ...],
    relations: tuple[TheoryRelationCommand, ...],
) -> str:
    payload = json.dumps(
        {
            "match_run_id": str(match_run_id),
            "expected_version": expected_version,
            "completion_basis": completion_basis.value,
            "decisions": [
                {
                    "candidate_id": str(item.candidate_id),
                    "candidate_version": item.candidate_version,
                    "action": item.action.value,
                    "reason": item.reason,
                    "related_source_ids": list(item.related_source_ids),
                    "related_candidate_ids": [str(value) for value in item.related_candidate_ids],
                    "revised_applicability": item.revised_applicability,
                }
                for item in decisions
            ],
            "use_assignments": [
                {
                    "candidate_id": str(item.candidate_id),
                    "role_code": item.role_code,
                    "responsibility": item.responsibility,
                }
                for item in use_assignments
            ],
            "relations": [
                {
                    "candidate_ids": [str(value) for value in item.candidate_ids],
                    "relation_kind": item.relation_kind,
                    "explanation": item.explanation,
                    "premise_compatibility": item.premise_compatibility,
                    "supporting_evidence": list(item.supporting_evidence),
                    "excluding_evidence": list(item.excluding_evidence),
                    "distinguishing_evidence": list(item.distinguishing_evidence),
                }
                for item in relations
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"sha256:{sha256(payload.encode()).hexdigest()}"
