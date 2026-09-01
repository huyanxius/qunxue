from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite.research_project_audit_model import (
    ResearchProjectAuditEventRow,
    ResearchProjectExchangeRunRow,
)
from qunxue_api.modules.research_exchange import (
    AuditActorType,
    ResearchAuditEvent,
    ResearchAuditEventType,
    ResearchExchangeDirection,
    ResearchExchangeRun,
    ResearchExchangeStatus,
)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class SqliteResearchProjectAuditRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append_event(self, event: ResearchAuditEvent) -> ResearchAuditEvent:
        self._session.add(
            ResearchProjectAuditEventRow(
                event_id=str(event.event_id),
                user_id=str(event.user_id),
                task_id=str(event.task_id),
                event_type=event.event_type.value,
                object_type=event.object_type,
                object_id=event.object_id,
                object_version=event.object_version,
                actor_type=event.actor_type.value,
                actor_id=event.actor_id,
                payload=event.payload,
                occurred_at=event.occurred_at,
            )
        )
        self._session.flush()
        return event

    def list_events(self, *, user_id: UUID, task_id: UUID) -> tuple[ResearchAuditEvent, ...]:
        rows = self._session.scalars(
            select(ResearchProjectAuditEventRow)
            .where(
                ResearchProjectAuditEventRow.user_id == str(user_id),
                ResearchProjectAuditEventRow.task_id == str(task_id),
            )
            .order_by(
                ResearchProjectAuditEventRow.occurred_at,
                ResearchProjectAuditEventRow.event_id,
            )
        ).all()
        return tuple(
            ResearchAuditEvent(
                event_id=UUID(row.event_id),
                user_id=UUID(row.user_id),
                task_id=UUID(row.task_id),
                event_type=ResearchAuditEventType(row.event_type),
                object_type=row.object_type,
                object_id=row.object_id,
                object_version=row.object_version,
                actor_type=AuditActorType(row.actor_type),
                actor_id=row.actor_id,
                payload=dict(row.payload),
                occurred_at=_utc(row.occurred_at),
            )
            for row in rows
        )

    def save_exchange(self, value: ResearchExchangeRun) -> ResearchExchangeRun:
        row = self._session.get(ResearchProjectExchangeRunRow, str(value.exchange_id))
        if row is None:
            row = ResearchProjectExchangeRunRow(exchange_id=str(value.exchange_id))
            self._session.add(row)
        row.user_id = str(value.user_id)
        row.task_id = str(value.task_id)
        row.direction = value.direction.value
        row.format = value.format
        row.format_version = value.format_version
        row.idempotency_key = value.idempotency_key
        row.status = value.status.value
        row.artifact_sha256 = value.artifact_sha256
        row.loss_report = value.loss_report
        row.created_at = value.created_at
        row.completed_at = value.completed_at
        row.error_code = value.error_code
        self._session.flush()
        return value

    def get_exchange(
        self, *, exchange_id: UUID, user_id: UUID, task_id: UUID
    ) -> ResearchExchangeRun | None:
        row = self._session.scalar(
            select(ResearchProjectExchangeRunRow).where(
                ResearchProjectExchangeRunRow.exchange_id == str(exchange_id),
                ResearchProjectExchangeRunRow.user_id == str(user_id),
                ResearchProjectExchangeRunRow.task_id == str(task_id),
            )
        )
        if row is None:
            return None
        return ResearchExchangeRun(
            exchange_id=UUID(row.exchange_id),
            user_id=UUID(row.user_id),
            task_id=UUID(row.task_id),
            direction=ResearchExchangeDirection(row.direction),
            format=row.format,
            format_version=row.format_version,
            idempotency_key=row.idempotency_key,
            status=ResearchExchangeStatus(row.status),
            artifact_sha256=row.artifact_sha256,
            loss_report=dict(row.loss_report) if row.loss_report is not None else None,
            created_at=_utc(row.created_at),
            completed_at=_utc(row.completed_at),
            error_code=row.error_code,
        )

    def get_exchange_by_idempotency(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        direction: ResearchExchangeDirection,
        idempotency_key: str,
    ) -> ResearchExchangeRun | None:
        row = self._session.scalar(
            select(ResearchProjectExchangeRunRow).where(
                ResearchProjectExchangeRunRow.user_id == str(user_id),
                ResearchProjectExchangeRunRow.task_id == str(task_id),
                ResearchProjectExchangeRunRow.direction == direction.value,
                ResearchProjectExchangeRunRow.idempotency_key == idempotency_key,
            )
        )
        if row is None:
            return None
        return self.get_exchange(
            exchange_id=UUID(row.exchange_id),
            user_id=user_id,
            task_id=task_id,
        )
