from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite import ResearchTaskRow
from qunxue_api.modules.research_intake import (
    PhenomenonQuery,
    PhenomenonSource,
    ResearchTask,
    ResearchTaskRepository,
)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class SqliteResearchTaskRepository(ResearchTaskRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, task_id: UUID) -> ResearchTask | None:
        row = self._session.get(ResearchTaskRow, str(task_id))
        return self._to_domain(row) if row is not None else None

    def add(self, task: ResearchTask) -> ResearchTask:
        row = ResearchTaskRow(
            task_id=str(task.task_id),
            phenomenon=task.phenomenon,
            research_intent=task.research_intent,
            context=task.context,
            source=task.source.value,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )
        self._session.add(row)
        self._session.flush()
        return self._to_domain(row)

    @staticmethod
    def _to_domain(row: ResearchTaskRow) -> ResearchTask:
        return ResearchTask(
            task_id=UUID(row.task_id),
            phenomenon_query=PhenomenonQuery(
                phenomenon=row.phenomenon,
                research_intent=row.research_intent,
                context=row.context,
                source=PhenomenonSource(row.source),
            ),
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
        )
