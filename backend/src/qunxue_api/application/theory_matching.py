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
from qunxue_api.modules.theory_matching import MatchRunSnapshot, TheoryMatching


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
        id_factory: Callable[[], UUID] = uuid4,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._catalog = catalog
        self._matching = matching
        self._matching_requests = matching_requests
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
