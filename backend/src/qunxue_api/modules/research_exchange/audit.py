"""Stable audit and exchange-run identities for research-project recovery."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class AuditActorType(StrEnum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class ResearchAuditEventType(StrEnum):
    MATERIAL_DELETED = "material.deleted"
    MATERIAL_PERMISSION_CHANGED = "material.permission_changed"
    MATERIAL_PARSED = "material.parsed"
    TRANSCRIPT_VERSION_CREATED = "transcript.version_created"
    ANALYSIS_CANDIDATE_CREATED = "analysis.candidate_created"
    ANALYSIS_CONFIRMED = "analysis.confirmed"
    ANALYSIS_REJECTED = "analysis.rejected"
    CITATION_CREATED = "citation.created"
    CITATION_STATE_CHANGED = "citation.state_changed"
    DOCUMENT_VERSION_CREATED = "document.version_created"
    PROJECT_EXPORTED = "project.exported"
    PROJECT_IMPORTED = "project.imported"
    PROJECT_IMPORT_PREVIEWED = "project.import_previewed"


class ResearchExchangeDirection(StrEnum):
    IMPORT = "import"
    EXPORT = "export"


class ResearchExchangeStatus(StrEnum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ResearchAuditEvent:
    event_id: UUID
    user_id: UUID
    task_id: UUID
    event_type: ResearchAuditEventType
    object_type: str
    object_id: str
    object_version: str | None
    actor_type: AuditActorType
    actor_id: str | None
    payload: dict[str, object]
    occurred_at: datetime

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        task_id: UUID,
        event_type: ResearchAuditEventType,
        object_type: str,
        object_id: str,
        actor_type: AuditActorType,
        payload: dict[str, object],
        occurred_at: datetime,
        event_id: UUID | None = None,
        object_version: str | None = None,
        actor_id: str | None = None,
    ) -> ResearchAuditEvent:
        normalized_type = object_type.strip()
        normalized_id = object_id.strip()
        if not normalized_type or not normalized_id:
            raise ValueError("audited object type and ID are required")
        return cls(
            event_id=event_id or uuid4(),
            user_id=user_id,
            task_id=task_id,
            event_type=ResearchAuditEventType(event_type),
            object_type=normalized_type,
            object_id=normalized_id,
            object_version=object_version.strip() if object_version else None,
            actor_type=AuditActorType(actor_type),
            actor_id=actor_id.strip() if actor_id else None,
            payload=dict(payload),
            occurred_at=_utc(occurred_at),
        )


@dataclass(frozen=True, slots=True)
class ResearchExchangeRun:
    exchange_id: UUID
    user_id: UUID
    task_id: UUID
    direction: ResearchExchangeDirection
    format: str
    format_version: str
    idempotency_key: str
    status: ResearchExchangeStatus
    artifact_sha256: str | None
    loss_report: dict[str, object] | None
    created_at: datetime
    completed_at: datetime | None = None
    error_code: str | None = None

    @classmethod
    def start(
        cls,
        *,
        user_id: UUID,
        task_id: UUID,
        direction: ResearchExchangeDirection,
        format: str,
        format_version: str,
        idempotency_key: str,
        now: datetime,
        exchange_id: UUID | None = None,
    ) -> ResearchExchangeRun:
        values = (format.strip(), format_version.strip(), idempotency_key.strip())
        if not all(values):
            raise ValueError("exchange format, version, and idempotency key are required")
        return cls(
            exchange_id=exchange_id or uuid4(),
            user_id=user_id,
            task_id=task_id,
            direction=ResearchExchangeDirection(direction),
            format=values[0],
            format_version=values[1],
            idempotency_key=values[2],
            status=ResearchExchangeStatus.PROCESSING,
            artifact_sha256=None,
            loss_report=None,
            created_at=_utc(now),
        )

    def complete(
        self,
        *,
        artifact_sha256: str,
        loss_report: dict[str, object],
        now: datetime,
    ) -> ResearchExchangeRun:
        digest = artifact_sha256.strip().lower()
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("artifact SHA-256 is invalid")
        return replace(
            self,
            status=ResearchExchangeStatus.COMPLETED,
            artifact_sha256=digest,
            loss_report=dict(loss_report),
            completed_at=_utc(now),
            error_code=None,
        )

    def fail(self, *, error_code: str, now: datetime) -> ResearchExchangeRun:
        normalized = error_code.strip()
        if not normalized:
            raise ValueError("exchange error code is required")
        return replace(
            self,
            status=ResearchExchangeStatus.FAILED,
            completed_at=_utc(now),
            error_code=normalized,
        )


class ResearchProjectAuditRepository(Protocol):
    def append_event(self, event: ResearchAuditEvent) -> ResearchAuditEvent: ...

    def list_events(self, *, user_id: UUID, task_id: UUID) -> tuple[ResearchAuditEvent, ...]: ...

    def save_exchange(self, value: ResearchExchangeRun) -> ResearchExchangeRun: ...

    def get_exchange(
        self, *, exchange_id: UUID, user_id: UUID, task_id: UUID
    ) -> ResearchExchangeRun | None: ...

    def get_exchange_by_idempotency(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        direction: ResearchExchangeDirection,
        idempotency_key: str,
    ) -> ResearchExchangeRun | None: ...
