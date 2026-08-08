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
