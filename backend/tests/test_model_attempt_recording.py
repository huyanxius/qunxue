from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from qunxue_api.adapters.model.attempt_recording import SqliteModelAttemptRecorder
from qunxue_api.adapters.model.routing import ModelAttemptRecord, ModelRouteContext
from qunxue_api.adapters.sqlite import Base
from qunxue_api.adapters.sqlite.database import Database


def _attempt(*, agent_run_id: UUID | None = None) -> ModelAttemptRecord:
    started_at = datetime(2026, 9, 5, 3, 40, tzinfo=UTC)
    return ModelAttemptRecord(
        attempt_id=UUID(int=1),
        context=ModelRouteContext(
            trace_id=UUID(int=2),
            request_id=UUID(int=3),
            route_id=UUID(int=4),
            operation="build",
            task_id=UUID(int=5),
            agent_run_id=agent_run_id,
            capability="research_build",
        ),
        endpoint_id="backup",
        route_id=UUID(int=4),
        task_id=UUID(int=5),
        agent_run_id=agent_run_id,
        capability="research_build",
        provider="openai-compatible",
        model="backup-model",
        fallback=True,
        attempt_number=2,
        success=True,
        selected=True,
        input_tokens=4,
        output_tokens=2,
        failure_code=None,
        failure_retryable=None,
        started_at=started_at,
        completed_at=started_at + timedelta(milliseconds=125),
    )


def test_sqlite_attempt_recorder_persists_safe_route_telemetry(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'attempts.db'}")
    try:
        Base.metadata.create_all(database.engine)
        recorder = SqliteModelAttemptRecorder(database)
        recorder.record(_attempt(agent_run_id=UUID(int=9)))

        persisted = recorder.list_for_agent_run(UUID(int=9))

        assert len(persisted) == 1
        assert persisted[0].endpoint_id == "backup"
        assert persisted[0].input_tokens == 4
        assert persisted[0].completed_at - persisted[0].started_at == timedelta(
            milliseconds=125
        )
        assert not hasattr(persisted[0], "prompt")
        assert not hasattr(persisted[0], "api_key")
    finally:
        database.engine.dispose()


def test_sqlite_attempt_recorder_lists_route_attempts_in_attempt_order(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'attempt-order.db'}")
    try:
        Base.metadata.create_all(database.engine)
        recorder = SqliteModelAttemptRecorder(database)
        first = _attempt(agent_run_id=UUID(int=9))
        second = replace(
            first,
            attempt_id=UUID(int=10),
            attempt_number=1,
            endpoint_id="primary",
            fallback=False,
            success=False,
            selected=False,
            input_tokens=None,
            output_tokens=None,
            failure_code="model_rate_limited",
            failure_retryable=True,
        )
        recorder.record(first)
        recorder.record(second)

        persisted = recorder.list_for_route(UUID(int=4))

        assert [item.attempt_number for item in persisted] == [1, 2]
        assert persisted[0].failure_code == "model_rate_limited"
        assert persisted[0].failure_retryable is True
    finally:
        database.engine.dispose()
