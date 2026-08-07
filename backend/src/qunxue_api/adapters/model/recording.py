from datetime import UTC, datetime
from threading import Lock
from uuid import UUID

from sqlalchemy import select

from qunxue_api.adapters.model.types import (
    ModelCapabilityName,
    ModelInvocationRecord,
    ModelScenario,
)
from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.adapters.sqlite.model_invocation_model import ModelInvocationRow


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class InMemoryModelInvocationRecorder:
    def __init__(self) -> None:
        self._records: list[ModelInvocationRecord] = []
        self._lock = Lock()

    def record(self, invocation: ModelInvocationRecord) -> None:
        with self._lock:
            self._records.append(invocation)

    def get(self, trace_id: UUID) -> ModelInvocationRecord | None:
        with self._lock:
            return next(
                (
                    record
                    for record in self._records
                    if record.trace_id == trace_id
                ),
                None,
            )

    def list_all(self) -> tuple[ModelInvocationRecord, ...]:
        with self._lock:
            return tuple(self._records)

    def list_for_task(self, task_id: UUID) -> tuple[ModelInvocationRecord, ...]:
        with self._lock:
            return tuple(
                record for record in self._records if record.task_id == task_id
            )


class SqliteModelInvocationRecorder:
    def __init__(self, database: Database) -> None:
        self._database = database

    def record(self, invocation: ModelInvocationRecord) -> None:
        with self._database.session() as session:
            session.add(
                ModelInvocationRow(
                    trace_id=str(invocation.trace_id),
                    request_id=str(invocation.request_id),
                    task_id=str(invocation.task_id),
                    contract_version=invocation.contract_version,
                    capability=invocation.capability.value,
                    provider=invocation.provider,
                    model_version=invocation.model_version,
                    capability_tier=invocation.capability_tier,
                    demonstration=invocation.demonstration,
                    scenario=invocation.scenario.value,
                    input_evidence=invocation.input_evidence,
                    output=invocation.output,
                    knowledge_release_id=invocation.knowledge_release_id,
                    degraded=invocation.degraded,
                    degradation_reason=invocation.degradation_reason,
                    error_code=invocation.error_code,
                    started_at=invocation.started_at,
                    completed_at=invocation.completed_at,
                )
            )

    def get(self, trace_id: UUID) -> ModelInvocationRecord | None:
        with self._database.session() as session:
            row = session.get(ModelInvocationRow, str(trace_id))
            return self._to_record(row) if row is not None else None

    def list_all(self) -> tuple[ModelInvocationRecord, ...]:
        with self._database.session() as session:
            rows = session.scalars(
                select(ModelInvocationRow).order_by(
                    ModelInvocationRow.started_at,
                    ModelInvocationRow.trace_id,
                )
            )
            return tuple(self._to_record(row) for row in rows)

    def list_for_task(self, task_id: UUID) -> tuple[ModelInvocationRecord, ...]:
        with self._database.session() as session:
            rows = session.scalars(
                select(ModelInvocationRow)
                .where(ModelInvocationRow.task_id == str(task_id))
                .order_by(
                    ModelInvocationRow.started_at,
                    ModelInvocationRow.trace_id,
                )
            )
            return tuple(self._to_record(row) for row in rows)

    @staticmethod
    def _to_record(row: ModelInvocationRow) -> ModelInvocationRecord:
        return ModelInvocationRecord(
            trace_id=UUID(row.trace_id),
            request_id=UUID(row.request_id),
            task_id=UUID(row.task_id),
            contract_version=row.contract_version,
            capability=ModelCapabilityName(row.capability),
            provider=row.provider,
            model_version=row.model_version,
            capability_tier=row.capability_tier,
            demonstration=row.demonstration,
            scenario=ModelScenario(row.scenario),
            input_evidence=dict(row.input_evidence),
            output=dict(row.output) if row.output is not None else None,
            knowledge_release_id=row.knowledge_release_id,
            degraded=row.degraded,
            degradation_reason=row.degradation_reason,
            error_code=row.error_code,
            started_at=_as_utc(row.started_at),
            completed_at=_as_utc(row.completed_at),
        )
