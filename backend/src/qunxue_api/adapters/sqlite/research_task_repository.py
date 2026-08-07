from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite import ResearchTaskRow
from qunxue_api.modules.research_intake import (
    EntryType,
    ResearchTask,
    ResearchTaskRepository,
    ResearchTaskStatus,
)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class SqliteResearchTaskRepository(ResearchTaskRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, task_id: UUID, user_id: UUID) -> ResearchTask | None:
        row = self._session.scalar(
            select(ResearchTaskRow).where(
                ResearchTaskRow.task_id == str(task_id),
                ResearchTaskRow.user_id == str(user_id),
            )
        )
        return self._to_domain(row) if row is not None else None

    def list_for_user(self, user_id: UUID, *, limit: int) -> list[ResearchTask]:
        rows = self._session.scalars(
            select(ResearchTaskRow)
            .where(ResearchTaskRow.user_id == str(user_id))
            .order_by(ResearchTaskRow.updated_at.desc(), ResearchTaskRow.task_id.desc())
            .limit(limit)
        )
        return [self._to_domain(row) for row in rows]

    def delete(self, task_id: UUID, user_id: UUID) -> ResearchTask | None:
        row = self._session.scalar(
            select(ResearchTaskRow).where(
                ResearchTaskRow.task_id == str(task_id),
                ResearchTaskRow.user_id == str(user_id),
            )
        )
        if row is None:
            return None
        task = self._to_domain(row)
        self._session.delete(row)
        self._session.flush()
        return task

    def add_or_get_by_idempotency_key(self, task: ResearchTask) -> ResearchTask:
        statement = (
            insert(ResearchTaskRow)
            .values(
                task_id=str(task.task_id),
                user_id=str(task.user_id),
                entry_type=task.entry_type.value,
                status=task.status.value,
                version=task.version,
                idempotency_key=task.idempotency_key,
                created_at=task.created_at,
                updated_at=task.updated_at,
            )
            .on_conflict_do_nothing(index_elements=["user_id", "idempotency_key"])
        )
        self._session.execute(statement)

        row = self._session.scalar(
            select(ResearchTaskRow).where(
                ResearchTaskRow.user_id == str(task.user_id),
                ResearchTaskRow.idempotency_key == task.idempotency_key,
            )
        )
        if row is None:
            raise RuntimeError("research task insert did not return a persisted row")
        return self._to_domain(row)

    @staticmethod
    def _to_domain(row: ResearchTaskRow) -> ResearchTask:
        if row.user_id is None:
            raise RuntimeError("legacy research task has no owner and cannot enter the domain")
        return ResearchTask(
            task_id=UUID(row.task_id),
            user_id=UUID(row.user_id),
            entry_type=EntryType(row.entry_type),
            status=ResearchTaskStatus(row.status),
            version=row.version,
            idempotency_key=row.idempotency_key,
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
        )
