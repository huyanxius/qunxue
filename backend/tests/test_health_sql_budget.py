from contextlib import closing
from sqlite3 import sqlite_version
from time import perf_counter

from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import event

from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.bootstrap import create_app
from qunxue_api.settings import Settings

# The first request on the audit's freshly migrated database dispatched 2,869 statements.
MAX_COLD_HEALTH_SQL_DISPATCHES = 2869


def test_first_health_request_stays_within_sql_budget(
    tmp_path, monkeypatch, alembic_config, capsys,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'health.db'}"
    monkeypatch.setenv("QUNXUE_DATABASE_URL", database_url)
    command.upgrade(alembic_config, "head")
    settings = Settings(
        _env_file=None,
        database_url=database_url,
        runtime_mode="mock",
        model_api_key=None,
        account_initial_admin_password=None,
    )
    database = Database(database_url)
    dispatches = 0

    def count_dispatch(*_args) -> None:
        nonlocal dispatches
        dispatches += 1

    try:
        app = create_app(settings=settings, database=database, require_email_verification=False)
        # A client without a lifespan context measures only the first request.
        # An executemany call is one cursor dispatch, regardless of its row count.
        with closing(TestClient(app)) as client:
            event.listen(database.engine, "before_cursor_execute", count_dispatch)
            try:
                started = perf_counter()
                response = client.get("/api/health")
                elapsed = perf_counter() - started
            finally:
                event.remove(database.engine, "before_cursor_execute", count_dispatch)
    finally:
        database.engine.dispose()

    assert response.status_code == 200, response.text
    assert response.json()["runtime_mode"] == "mock"
    with capsys.disabled():
        print(
            f"\nCold GET /api/health: {dispatches} SQL dispatches "
            f"(limit {MAX_COLD_HEALTH_SQL_DISPATCHES}, SQLite {sqlite_version}, {elapsed:.3f} s)"
        )
    assert dispatches <= MAX_COLD_HEALTH_SQL_DISPATCHES
