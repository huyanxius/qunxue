from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from qunxue_api.modules.research_intake.domain import (
    ConfirmedPhenomenonSnapshot,
    DirectPhenomenonInput,
    EntryType,
    PhenomenonCandidate,
    PhenomenonCandidateDraft,
    PhenomenonEvidenceRefSnapshot,
    PhenomenonModelSnapshot,
    PhenomenonProgress,
    ResearchTask,
    ResearchTaskStatus,
)
from qunxue_api.modules.research_intake.errors import ResearchTaskNotFound
from qunxue_api.modules.research_intake.ports import (
    PhenomenonRepository,
    ResearchTaskRepository,
)


class ResearchTaskService:
    def __init__(
        self,
        repository: ResearchTaskRepository,
        *,
        id_factory: Callable[[], UUID] = uuid4,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._id_factory = id_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def create(
        self,
        *,
        user_id: UUID,
        entry_type: EntryType,
        idempotency_key: str,
    ) -> ResearchTask:
        task = ResearchTask.create(
            task_id=self._id_factory(),
            user_id=user_id,
            entry_type=entry_type,
            idempotency_key=idempotency_key,
            now=self._clock(),
        )
        return self._repository.add_or_get_by_idempotency_key(task)

    def get(self, task_id: UUID, *, user_id: UUID) -> ResearchTask:
        task = self._repository.get(task_id, user_id)
        if task is None:
            raise ResearchTaskNotFound(str(task_id))
        return task

    def list_for_user(self, user_id: UUID, *, limit: int) -> list[ResearchTask]:
        return self._repository.list_for_user(user_id, limit=limit)

    def delete(self, task_id: UUID, *, user_id: UUID) -> ResearchTask:
        task = self._repository.delete(task_id, user_id)
        if task is None:
            raise ResearchTaskNotFound(str(task_id))
        return task

    def save_progress(self, task: ResearchTask) -> ResearchTask | None:
        return self._repository.save_progress(task)


class PhenomenonService:
    def __init__(
        self,
        repository: PhenomenonRepository,
        research_tasks: ResearchTaskRepository,
        *,
        id_factory: Callable[[], UUID] = uuid4,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._research_tasks = research_tasks
        self._id_factory = id_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def submit_direct(
        self,
        *,
        task_id: UUID,
        phenomenon: str,
        research_intent: str | None,
        context: str | None,
    ) -> DirectPhenomenonInput:
        return self._repository.submit_direct(
            task_id=task_id,
            phenomenon=phenomenon.strip(),
            research_intent=research_intent,
            context=context,
            now=self._clock(),
            input_id=self._id_factory(),
        )

    def input_for_task(self, task_id: UUID) -> DirectPhenomenonInput | None:
        return self._repository.input_for_task(task_id)

    def save_candidate(
        self,
        *,
        task_id: UUID,
        draft: PhenomenonCandidateDraft,
        evidence_refs: tuple[PhenomenonEvidenceRefSnapshot, ...],
        model: PhenomenonModelSnapshot,
    ) -> PhenomenonCandidate:
        return self._repository.save_candidate(
            task_id=task_id,
            candidate_id=self._id_factory(),
            draft=draft,
            evidence_refs=evidence_refs,
            model=model,
            now=self._clock(),
        )

    def get_candidate(
        self, task_id: UUID, candidate_id: UUID, version: int | None = None
    ) -> PhenomenonCandidate | None:
        return self._repository.get_candidate(task_id, candidate_id, version)

    def update_candidate(
        self,
        *,
        task_id: UUID,
        candidate_id: UUID,
        expected_version: int,
        phenomenon: str,
        research_intent: str | None,
        context: str | None,
    ) -> PhenomenonCandidate | None:
        return self._repository.update_candidate(
            task_id=task_id,
            candidate_id=candidate_id,
            expected_version=expected_version,
            phenomenon=phenomenon,
            research_intent=research_intent,
            context=context,
            now=self._clock(),
        )

    def confirm_candidate(
        self,
        *,
        task_id: UUID,
        candidate_id: UUID,
        expected_version: int,
        task: ResearchTask,
    ) -> tuple[ConfirmedPhenomenonSnapshot, datetime] | None:
        result = self._repository.confirm_candidate(
            task_id=task_id,
            candidate_id=candidate_id,
            expected_version=expected_version,
            query_id=self._id_factory(),
            now=self._clock(),
        )
        if result is None:
            return None
        snapshot, confirmed_at = result
        saved_task = self._research_tasks.save_progress(
            replace(
                task,
                status=ResearchTaskStatus.PHENOMENON_CONFIRMED,
                version=task.version + 1,
                updated_at=confirmed_at,
                phenomenon_query_id=snapshot.phenomenon_query_id,
                phenomenon_version=snapshot.version,
                phenomenon_summary=snapshot.phenomenon,
                phenomenon_research_intent=snapshot.research_intent,
                current_phenomenon_candidate_id=candidate_id,
            )
        )
        if saved_task is None:
            raise RuntimeError("owned research task disappeared during confirmation")
        return result

    def progress(self, task_id: UUID) -> PhenomenonProgress:
        return self._repository.progress(task_id)
