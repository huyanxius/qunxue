from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.adapters.sqlite.research_project_audit import SqliteResearchProjectAuditRepository
from qunxue_api.modules.research_exchange import (
    AuditActorType,
    ResearchAuditEvent,
    ResearchAuditEventType,
    ResearchExchangeDirection,
    ResearchExchangeRun,
    ResearchExchangeStatus,
)

NOW = datetime(2026, 9, 1, 9, 30, tzinfo=UTC)
USER_ID = UUID("20000000-0000-4000-8000-000000000001")
TASK_ID = UUID("20000000-0000-4000-8000-000000000002")
EVENT_ID = UUID("20000000-0000-4000-8000-000000000003")
EXCHANGE_ID = UUID("20000000-0000-4000-8000-000000000004")


def _migrated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Database:
    database_url = f"sqlite:///{tmp_path / 'audit.db'}"
    monkeypatch.setenv("QUNXUE_DATABASE_URL", database_url)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    return Database(database_url)


def test_audit_migration_extends_the_single_head_with_append_only_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _migrated_database(tmp_path, monkeypatch)
    try:
        inspector = inspect(database.engine)
        assert {"research_project_audit_events", "research_project_exchange_runs"} <= set(
            inspector.get_table_names()
        )
        assert {
            "event_id",
            "user_id",
            "task_id",
            "event_type",
            "object_type",
            "object_id",
            "object_version",
            "actor_type",
            "actor_id",
            "payload",
            "occurred_at",
        } == {column["name"] for column in inspector.get_columns("research_project_audit_events")}
    finally:
        database.engine.dispose()


def test_repository_keeps_exact_event_versions_and_exchange_loss_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = _migrated_database(tmp_path, monkeypatch)
    event = ResearchAuditEvent.create(
        event_id=EVENT_ID,
        user_id=USER_ID,
        task_id=TASK_ID,
        event_type=ResearchAuditEventType.ANALYSIS_CONFIRMED,
        object_type="analysis_code",
        object_id="code-17",
        object_version="2",
        actor_type=AuditActorType.USER,
        actor_id=str(USER_ID),
        payload={"decision_reason": "研究者核对原文后确认"},
        occurred_at=NOW,
    )
    exchange = ResearchExchangeRun.start(
        exchange_id=EXCHANGE_ID,
        user_id=USER_ID,
        task_id=TASK_ID,
        direction=ResearchExchangeDirection.EXPORT,
        format="REFI-QDA Project",
        format_version="1.0",
        idempotency_key="export-2026-09-01",
        now=NOW,
    ).complete(
        artifact_sha256="a" * 64,
        loss_report={
            "losses": [
                {
                    "object_type": "analysis_code",
                    "object_id": "code-17",
                    "field": "version",
                    "disposition": "recovery_manifest",
                }
            ]
        },
        now=NOW,
    )

    try:
        with database.session() as session:
            repository = SqliteResearchProjectAuditRepository(session)
            assert repository.append_event(event) == event
            assert repository.save_exchange(exchange) == exchange
        with database.session() as session:
            repository = SqliteResearchProjectAuditRepository(session)
            assert repository.list_events(user_id=USER_ID, task_id=TASK_ID) == (event,)
            restored = repository.get_exchange(
                exchange_id=EXCHANGE_ID,
                user_id=USER_ID,
                task_id=TASK_ID,
            )
            assert restored == exchange
            assert restored.status is ResearchExchangeStatus.COMPLETED
    finally:
        database.engine.dispose()
