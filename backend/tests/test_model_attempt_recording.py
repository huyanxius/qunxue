from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import inspect

from qunxue_api.adapters.model.attempt_recording import SqliteModelAttemptRecorder
from qunxue_api.adapters.model.routing import ModelAttemptRecord, ModelRouteContext
from qunxue_api.adapters.sqlite import Base
from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.adapters.sqlite.model_attempt_model import ModelRouteAttemptRow


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
        attempt = persisted[0]
        assert type(attempt).__name__ == "PersistedModelRouteAttempt"
        assert not hasattr(attempt, "context")
        assert attempt.attempt_id == UUID(int=1)
        assert attempt.route_id == UUID(int=4)
        assert attempt.trace_id == UUID(int=2)
        assert attempt.request_id == UUID(int=3)
        assert attempt.task_id == UUID(int=5)
        assert attempt.agent_run_id == UUID(int=9)
        assert attempt.capability == "research_build"
        assert attempt.endpoint_id == "backup"
        assert attempt.provider == "openai-compatible"
        assert attempt.model == "backup-model"
        assert attempt.attempt_number == 2
        assert attempt.fallback is True
        assert attempt.success is True
        assert attempt.selected is True
        assert attempt.failure_retryable is None
        assert attempt.failure_code is None
        assert attempt.input_tokens == 4
        assert attempt.output_tokens == 2
        assert attempt.started_at == datetime(2026, 9, 5, 3, 40, tzinfo=UTC)
        assert attempt.completed_at == datetime(
            2026,
            9,
            5,
            3,
            40,
            0,
            125000,
            tzinfo=UTC,
        )
        assert attempt.latency_ms == 125
        with pytest.raises(FrozenInstanceError):
            attempt.endpoint_id = "other"  # type: ignore[misc]
        assert not hasattr(attempt, "prompt")
        assert not hasattr(attempt, "api_key")
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
        assert persisted[0].input_tokens is None
        assert persisted[0].output_tokens is None
        assert persisted[0].latency_ms == 125
    finally:
        database.engine.dispose()


def test_model_route_attempt_schema_is_exact_and_content_free(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'attempt-schema.db'}")
    try:
        Base.metadata.create_all(database.engine)
        recorder = SqliteModelAttemptRecorder(database)
        recorder.record(_attempt(agent_run_id=None))
        recorder.record(
            replace(
                _attempt(agent_run_id=None),
                attempt_id=UUID(int=10),
                input_tokens=None,
                output_tokens=None,
            )
        )

        inspector = inspect(database.engine)
        columns = {
            column["name"]: column
            for column in inspector.get_columns("model_route_attempts")
        }
        assert set(columns) == {
            "attempt_id",
            "route_id",
            "trace_id",
            "request_id",
            "task_id",
            "agent_run_id",
            "capability",
            "endpoint_id",
            "provider",
            "model",
            "attempt_number",
            "fallback",
            "started_at",
            "completed_at",
            "latency_ms",
            "success",
            "selected",
            "failure_retryable",
            "failure_code",
            "input_tokens",
            "output_tokens",
        }
        assert not (set(columns) & {
            "prompt",
            "request_body",
            "response_body",
            "url",
            "headers",
            "api_key",
            "credentials",
            "exception",
            "operation",
        })
        for name in {"attempt_id", "route_id", "trace_id", "request_id"}:
            assert columns[name]["type"].length == 36
            assert columns[name]["nullable"] is False
        for name in {"task_id", "agent_run_id"}:
            assert columns[name]["type"].length == 36
            assert columns[name]["nullable"] is True
        assert columns["input_tokens"]["nullable"] is True
        assert columns["output_tokens"]["nullable"] is True
        assert {index["name"] for index in inspector.get_indexes("model_route_attempts")} == {
            "ix_model_route_attempts_agent_run_id",
            "ix_model_route_attempts_route_id",
            "ix_model_route_attempts_trace_id",
        }

        with database.session() as session:
            raw_row = session.get(ModelRouteAttemptRow, str(UUID(int=1)))
            null_token_row = session.get(ModelRouteAttemptRow, str(UUID(int=10)))
        assert raw_row is not None
        assert raw_row.latency_ms == 125
        assert null_token_row is not None
        assert null_token_row.input_tokens is None
        assert null_token_row.output_tokens is None
    finally:
        database.engine.dispose()
