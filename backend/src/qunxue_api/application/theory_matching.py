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
    MatchCompletionBasis,
    MatchRunSnapshot,
    TheoryDecisionCommand,
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


class TheoryMatchingApplication:
    """Owns HTTP request idempotency and cross-module matching coordination."""

    def __init__(
        self,
        *,
        catalog: KnowledgeCatalog,
        matching: TheoryMatching,
        matching_requests: MatchingRequestRepository,
        research_tasks: ResearchTaskRepository,
        rollback: Callable[[], None] | None = None,
        id_factory: Callable[[], UUID] = uuid4,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._catalog = catalog
        self._matching = matching
        self._matching_requests = matching_requests
        self._research_tasks = research_tasks
        self._rollback = rollback
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
        return self._start_impl(
            user_id=user_id, task=task, phenomenon=phenomenon,
            idempotency_key=idempotency_key,
            expected_task_version=expected_task_version,
            phenomenon_query_id=phenomenon_query_id,
            phenomenon_version=phenomenon_version,
            requested_knowledge_release_id=requested_knowledge_release_id,
        )

    def _start_impl(
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

        current_task = self._research_tasks.get(task.task_id, user_id)
        if current_task is None or current_task.version != expected_task_version:
            raise MatchingSnapshotConflict("Research task version is stale.")
        if (
            phenomenon.task_id != task.task_id
            or phenomenon.phenomenon_query_id != phenomenon_query_id
            or phenomenon.version != phenomenon_version
        ):
            raise MatchingSnapshotConflict("Confirmed phenomenon snapshot does not match request.")

        if current_task.knowledge_release_id is not None:
            if (
                requested_knowledge_release_id is not None
                and requested_knowledge_release_id != current_task.knowledge_release_id
            ):
                raise MatchingSnapshotConflict(
                    "Knowledge release does not match the release pinned to this research task."
                )
            get_manifest = getattr(self._catalog, "get_manifest", None)
            if not callable(get_manifest):
                raise MatchingSnapshotConflict(
                    "The pinned knowledge release cannot be resolved by this catalog."
                )
            try:
                release = get_manifest(current_task.knowledge_release_id).release
            except LookupError as error:
                raise MatchingSnapshotConflict(
                    "The knowledge release pinned to this research task is unavailable."
                ) from error
        else:
            release = self._catalog.current_release(purpose=KnowledgeUsePurpose.MATCH)
            if (
                requested_knowledge_release_id is not None
                and requested_knowledge_release_id != release.knowledge_release_id
            ):
                raise MatchingSnapshotConflict(
                    "Knowledge release is not the current match release."
                )

        match_run = self._matching.start(phenomenon=phenomenon, release=release)
        now = self._clock()
        saved_task = self._research_tasks.save_progress(
            replace(
                current_task,
                status=ResearchTaskStatus.MATCH_GENERATING,
                version=current_task.version + 1,
                updated_at=now,
                current_match_run_id=match_run.match_run_id,
            )
        )
        if saved_task is None:
            discard = getattr(self._matching, "discard", None)
            if discard is not None:
                discard(match_run.match_run_id)
            if self._rollback is not None:
                self._rollback()
            raise MatchingSnapshotConflict("Research task version is stale.")
        self._matching_requests.add(
            request_record_id=self._id_factory(),
            user_id=user_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            match_run_id=match_run.match_run_id,
            created_at=now,
        )
        claimed = self._matching_requests.get_by_idempotency_key(
            user_id=user_id,
            idempotency_key=idempotency_key,
        )
        if claimed is not None and claimed[1] != match_run.match_run_id:
            return self._matching.get(claimed[1])
        return match_run

    def get(self, match_run_id: UUID, *, user_id: UUID) -> MatchRunSnapshot:
        if not self._matching_requests.owns(user_id=user_id, match_run_id=match_run_id):
            raise LookupError(match_run_id)
        return self._matching.get(match_run_id)

    def record_decisions(
        self,
        *,
        user_id: UUID,
        match_run_id: UUID,
        expected_version: int,
        completion_basis: MatchCompletionBasis,
        decisions: tuple[TheoryDecisionCommand, ...],
        use_assignments: tuple[TheoryUseAssignment, ...],
        relations: tuple[TheoryRelationCommand, ...],
        idempotency_key: str,
    ) -> TheoryDecisionSetSnapshot:
        match_run = self.get(match_run_id, user_id=user_id)
        request_hash = _payload_hash(
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
                        "revised_applicability": item.revised_applicability,
                        "related_candidate_ids": [
                            str(value) for value in item.related_candidate_ids
                        ],
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
            }
        )
        snapshot = self._matching.record_decisions(
            match_run_id=match_run_id,
            expected_version=expected_version,
            decisions=decisions,
            use_assignments=use_assignments,
            relations=relations,
            completion_basis=completion_basis,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
        task = self._research_tasks.get(match_run.task_id, user_id)
        if task is None:
            raise RuntimeError("owned research task disappeared while recording decisions")
        if task.status is ResearchTaskStatus.MATCH_GENERATING:
            saved_task = self._research_tasks.save_progress(
                replace(
                    task,
                    status=ResearchTaskStatus.DECISIONS_RECORDED,
                    version=task.version + 1,
                    updated_at=self._clock(),
                )
            )
            if saved_task is None:
                if self._rollback is not None:
                    self._rollback()
                raise MatchingSnapshotConflict("Research task version is stale.")
        return snapshot

    def list_decisions(
        self, *, user_id: UUID, match_run_id: UUID
    ) -> tuple[TheoryDecisionSetSnapshot, ...]:
        self.get(match_run_id, user_id=user_id)
        return self._matching.list_decision_sets(match_run_id)

    def acknowledge_partial_completion(
        self,
        *,
        user_id: UUID,
        match_run_id: UUID,
        expected_version: int,
        acknowledged_candidate_ids: tuple[UUID, ...],
        failed_candidate_ids: tuple[UUID, ...],
        reason: str,
        idempotency_key: str,
    ) -> MatchRunSnapshot:
        self.get(match_run_id, user_id=user_id)
        request_hash = _payload_hash(
            {
                "match_run_id": str(match_run_id),
                "expected_version": expected_version,
                "acknowledged_candidate_ids": [
                    str(value) for value in acknowledged_candidate_ids
                ],
                "failed_candidate_ids": [str(value) for value in failed_candidate_ids],
                "reason": reason,
            }
        )
        return self._matching.acknowledge_partial_completion(
            match_run_id=match_run_id,
            expected_version=expected_version,
            acknowledged_candidate_ids=acknowledged_candidate_ids,
            failed_candidate_ids=failed_candidate_ids,
            reason=reason,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )

    def confirm_plan(
        self,
        *,
        user_id: UUID,
        decision_set_id: UUID,
        expected_version: int,
        idempotency_key: str,
    ) -> ConfirmedTheoryPlanSnapshot:
        decision_set = self._matching.get_decision_set(decision_set_id)
        self.get(decision_set.match_run_id, user_id=user_id)
        confirmed = self._matching.confirm_plan(
            decision_set_id=decision_set_id,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            request_hash=_payload_hash(
                {
                    "decision_set_id": str(decision_set_id),
                    "expected_version": expected_version,
                }
            ),
        )
        task = self._research_tasks.get(confirmed.task_id, user_id)
        if task is None:
            raise RuntimeError("owned research task disappeared while confirming theory plan")
        if task.status is ResearchTaskStatus.DECISIONS_RECORDED:
            saved_task = self._research_tasks.save_progress(
                replace(
                    task,
                    status=ResearchTaskStatus.THEORY_PLAN_CONFIRMED,
                    version=task.version + 1,
                    updated_at=self._clock(),
                    adopted_theory_count=len(confirmed.candidates),
                    current_theory_plan_id=confirmed.theory_plan_id,
                )
            )
            if saved_task is None:
                if self._rollback is not None:
                    self._rollback()
                raise MatchingSnapshotConflict("Research task version is stale.")
        return confirmed

    def get_confirmed_plan(
        self, *, user_id: UUID, theory_plan_id: UUID
    ) -> ConfirmedTheoryPlanSnapshot:
        snapshot = self._matching.get_confirmed_plan(theory_plan_id)
        self.get(snapshot.match_run_id, user_id=user_id)
        return snapshot


def _request_hash(
    *,
    task_id: UUID,
    expected_task_version: int,
    phenomenon_query_id: UUID,
    phenomenon_version: int,
    requested_knowledge_release_id: str | None,
) -> str:
    return _payload_hash(
        {
            "task_id": str(task_id),
            "expected_task_version": expected_task_version,
            "phenomenon_query_id": str(phenomenon_query_id),
            "phenomenon_version": phenomenon_version,
            "knowledge_release_id": requested_knowledge_release_id,
        }
    )


def _payload_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"sha256:{sha256(encoded.encode()).hexdigest()}"
