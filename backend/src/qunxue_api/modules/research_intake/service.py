from collections.abc import Callable
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from qunxue_api.modules.research_intake.domain import PhenomenonQuery, ResearchTask
from qunxue_api.modules.research_intake.errors import (
    ResearchIntakeValidationError,
    ResearchTaskNotFound,
)
from qunxue_api.modules.research_intake.ports import ResearchTaskRepository


def _default_task_id_factory(idempotency_key: str) -> UUID:
    return uuid5(NAMESPACE_URL, idempotency_key)


class ResearchTaskService:
    def __init__(
        self,
        repository: ResearchTaskRepository,
        *,
        task_id_factory: Callable[[str], UUID] = _default_task_id_factory,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._task_id_factory = task_id_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def create(
        self,
        *,
        idempotency_key: str,
        phenomenon: str,
        research_intent: str | None,
        context: str | None,
    ) -> ResearchTask:
        self._validate_phenomenon(phenomenon)
        task_id = self._task_id_factory(idempotency_key)
        existing_task = self._repository.get(task_id)
        if existing_task is not None:
            return existing_task

        task = ResearchTask.create(
            task_id=task_id,
            phenomenon_query=PhenomenonQuery(
                phenomenon=phenomenon,
                research_intent=research_intent,
                context=context,
            ),
            now=self._clock(),
        )
        try:
            return self._repository.add(task)
        except Exception:
            existing_task = self._repository.get(task_id)
            if existing_task is not None:
                return existing_task
            raise

    def get(self, task_id: UUID) -> ResearchTask:
        task = self._repository.get(task_id)
        if task is None:
            raise ResearchTaskNotFound(str(task_id))
        return task

    @staticmethod
    def _validate_phenomenon(phenomenon: str) -> None:
        if phenomenon.strip() == '':
            raise ResearchIntakeValidationError('研究现象不能为空或纯空白。')