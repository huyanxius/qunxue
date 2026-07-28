from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite import ResearchTaskRow
from qunxue_api.modules.research_intake import EntryType, ResearchTask, ResearchTaskStatus


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class SqliteResearchTaskRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, task_id: UUID) -> ResearchTask | None:
        row = self._session.get(ResearchTaskRow, str(task_id))
        return self._to_domain(row) if row is not None else None

    def get_by_idempotency_key(self, idempotency_key: str) -> ResearchTask | None:
        row = self._session.scalar(
            select(ResearchTaskRow).where(
                ResearchTaskRow.idempotency_key == idempotency_key
            )
        )
        return self._to_domain(row) if row is not None else None

    def add(self, task: ResearchTask) -> None:
        self._session.add(
            ResearchTaskRow(
                task_id=str(task.task_id),
                entry_type=task.entry_type.value,
                status=task.status.value,
                version=task.version,
                idempotency_key=task.idempotency_key,
                created_at=task.created_at,
                updated_at=task.updated_at,
            )
        )
        self._session.flush()

    @staticmethod
    def _to_domain(row: ResearchTaskRow) -> ResearchTask:
        return ResearchTask(
            task_id=UUID(row.task_id),
            entry_type=EntryType(row.entry_type),
            status=ResearchTaskStatus(row.status),
            version=row.version,
            idempotency_key=row.idempotency_key,
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
        )
