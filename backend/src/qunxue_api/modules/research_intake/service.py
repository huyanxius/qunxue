from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from qunxue_api.modules.research_intake.domain import EntryType, ResearchTask
from qunxue_api.modules.research_intake.errors import ResearchTaskNotFound
from qunxue_api.modules.research_intake.ports import ResearchTaskRepository


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

    def create(self, *, entry_type: EntryType, idempotency_key: str) -> ResearchTask:
        existing = self._repository.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            return existing

        task = ResearchTask.create(
            task_id=self._id_factory(),
            entry_type=entry_type,
            idempotency_key=idempotency_key,
            now=self._clock(),
        )
        self._repository.add(task)
        return task

    def get(self, task_id: UUID) -> ResearchTask:
        task = self._repository.get(task_id)
        if task is None:
            raise ResearchTaskNotFound(str(task_id))
        return task
