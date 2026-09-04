"""Durable, content-free persistence for individual model-route attempts."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from qunxue_api.adapters.model.routing import ModelAttemptRecord
from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.adapters.sqlite.model_attempt_model import ModelRouteAttemptRow


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class PersistedModelRouteAttempt:
    """A content-free audit projection containing only persisted table fields."""

    attempt_id: UUID
    route_id: UUID
    trace_id: UUID
    request_id: UUID
    task_id: UUID | None
    agent_run_id: UUID | None
    capability: str
    endpoint_id: str
    provider: str
    model: str
    attempt_number: int
    fallback: bool
    started_at: datetime
    completed_at: datetime
    latency_ms: int
    success: bool
    selected: bool
    failure_retryable: bool | None
    failure_code: str | None
    input_tokens: int | None
    output_tokens: int | None


class SqliteModelAttemptRecorder:
    def __init__(self, database: Database) -> None:
        self._database = database

    def record(self, attempt: ModelAttemptRecord) -> None:
        route_id = _required_uuid(attempt.route_id, "route_id")
        capability = _required_text(attempt.capability, "capability")
        provider = _required_text(attempt.provider, "provider")
        latency_ms = max(
            0,
            int((attempt.completed_at - attempt.started_at).total_seconds() * 1000),
        )
        with self._database.session() as session:
            session.add(
                ModelRouteAttemptRow(
                    attempt_id=str(attempt.attempt_id),
                    route_id=str(route_id),
                    trace_id=str(attempt.context.trace_id),
                    request_id=str(attempt.context.request_id),
                    task_id=_optional_uuid(attempt.task_id),
                    agent_run_id=_optional_uuid(attempt.agent_run_id),
                    capability=capability,
                    endpoint_id=attempt.endpoint_id,
                    provider=provider,
                    model=attempt.model,
                    attempt_number=attempt.attempt_number,
                    fallback=attempt.fallback,
                    started_at=attempt.started_at,
                    completed_at=attempt.completed_at,
                    latency_ms=latency_ms,
                    success=attempt.success,
                    selected=attempt.selected,
                    failure_retryable=attempt.failure_retryable,
                    failure_code=attempt.failure_code,
                    input_tokens=attempt.input_tokens,
                    output_tokens=attempt.output_tokens,
                )
            )

    def list_for_route(self, route_id: UUID) -> tuple[PersistedModelRouteAttempt, ...]:
        with self._database.session() as session:
            rows = session.scalars(
                select(ModelRouteAttemptRow)
                .where(ModelRouteAttemptRow.route_id == str(route_id))
                .order_by(ModelRouteAttemptRow.attempt_number, ModelRouteAttemptRow.attempt_id)
            )
            return tuple(self._to_persisted(row) for row in rows)

    def list_for_agent_run(
        self,
        agent_run_id: UUID,
    ) -> tuple[PersistedModelRouteAttempt, ...]:
        with self._database.session() as session:
            rows = session.scalars(
                select(ModelRouteAttemptRow)
                .where(ModelRouteAttemptRow.agent_run_id == str(agent_run_id))
                .order_by(
                    ModelRouteAttemptRow.started_at,
                    ModelRouteAttemptRow.attempt_number,
                    ModelRouteAttemptRow.attempt_id,
                )
            )
            return tuple(self._to_persisted(row) for row in rows)

    @staticmethod
    def _to_persisted(row: ModelRouteAttemptRow) -> PersistedModelRouteAttempt:
        return PersistedModelRouteAttempt(
            attempt_id=UUID(row.attempt_id),
            route_id=UUID(row.route_id),
            trace_id=UUID(row.trace_id),
            request_id=UUID(row.request_id),
            task_id=_to_optional_uuid(row.task_id),
            agent_run_id=_to_optional_uuid(row.agent_run_id),
            capability=row.capability,
            endpoint_id=row.endpoint_id,
            provider=row.provider,
            model=row.model,
            fallback=row.fallback,
            attempt_number=row.attempt_number,
            started_at=_as_utc(row.started_at),
            completed_at=_as_utc(row.completed_at),
            latency_ms=row.latency_ms,
            success=row.success,
            selected=row.selected,
            failure_retryable=row.failure_retryable,
            failure_code=row.failure_code,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
        )


def _required_uuid(value: UUID | None, name: str) -> UUID:
    if value is None:
        raise ValueError(f"model attempt {name} is required")
    return value


def _optional_uuid(value: UUID | None) -> str | None:
    return str(value) if value is not None else None


def _to_optional_uuid(value: str | None) -> UUID | None:
    return UUID(value) if value is not None else None


def _required_text(value: str | None, name: str) -> str:
    if value is None:
        raise ValueError(f"model attempt {name} is required")
    return value
