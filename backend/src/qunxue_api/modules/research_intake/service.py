from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from qunxue_api.modules.research_intake.domain import PhenomenonQuery, ResearchTask
from qunxue_api.modules.research_intake.errors import (
    ResearchIntakeValidationError,
    ResearchTaskNotFound,
)
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
        phenomenon: str,
        research_intent: str | None,
        context: str | None,
    ) -> ResearchTask:
        self._validate_phenomenon(phenomenon)
        task = ResearchTask.create(
            task_id=self._id_factory(),
            phenomenon_query=PhenomenonQuery(
                phenomenon=phenomenon,
                research_intent=research_intent,
                context=context,
            ),
            now=self._clock(),
        )
        return self._repository.add(task)

    def get(self, task_id: UUID) -> ResearchTask:
        task = self._repository.get(task_id)
        if task is None:
            raise ResearchTaskNotFound(str(task_id))
        return task

    @staticmethod
    def _validate_phenomenon(phenomenon: str) -> None:
        if phenomenon.strip() == "":
            raise ResearchIntakeValidationError(
                "phenomenon must not be empty or whitespace-only"
            )
