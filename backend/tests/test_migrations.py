from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import CheckConstraint, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.schema import CreateIndex

from qunxue_api.adapters.sqlite import Base
from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.settings import Settings


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.strip().removesuffix(";").split())


def _metadata_check_constraints(
    table_name: str,
) -> set[tuple[str | None, str]]:
    table = Base.metadata.tables[table_name]
    constraints = [
        *table.constraints,
        *(
            constraint
            for column in table.columns
            for constraint in column.constraints
        ),
    ]
    return {
        (constraint.name, _normalize_sql(str(constraint.sqltext)))
        for constraint in constraints
        if isinstance(constraint, CheckConstraint)
    }


def _database_check_constraints(
    inspector: Inspector,
    table_name: str,
) -> set[tuple[str | None, str]]:
    return {
        (
            constraint["name"],
            _normalize_sql(str(constraint["sqltext"])),
        )
        for constraint in inspector.get_check_constraints(table_name)
    }


def _metadata_indexes(
    table_name: str,
    engine: Engine,
) -> dict[str, str]:
    table = Base.metadata.tables[table_name]
    indexes: dict[str, str] = {}
    for index in table.indexes:
        if index.name is None:
            raise AssertionError(f"{table_name} has an unnamed index")
        indexes[index.name] = _normalize_sql(
            str(CreateIndex(index).compile(dialect=engine.dialect))
        )
    return indexes


def _database_indexes(
    database: Database,
    table_name: str,
) -> dict[str, str]:
    with database.engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT name, sql
                FROM sqlite_master
                WHERE type = 'index'
                  AND tbl_name = :table_name
                  AND sql IS NOT NULL
                """
            ),
            {"table_name": table_name},
        )
        return {
            str(row.name): _normalize_sql(str(row.sql))
            for row in rows
        }


def test_default_settings_drive_application_and_alembic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    alembic_config: Config,
) -> None:
    monkeypatch.delenv("QUNXUE_DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    settings = Settings()

    command.upgrade(alembic_config, "head")

    database = Database(settings.database_url)
    try:
        assert settings.database_url == "sqlite:///./var/qunxue.db"
        assert (tmp_path / "var" / "qunxue.db").is_file()
        assert "research_tasks" in inspect(database.engine).get_table_names()
    finally:
        database.engine.dispose()


def test_database_url_override_drives_application_and_alembic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    alembic_config: Config,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'override.db'}"
    monkeypatch.setenv("QUNXUE_DATABASE_URL", database_url)
    settings = Settings()

    command.upgrade(alembic_config, "head")

    database = Database(settings.database_url)
    try:
        assert settings.database_url == database_url
        assert (tmp_path / "override.db").is_file()
        assert "research_tasks" in inspect(database.engine).get_table_names()
    finally:
        database.engine.dispose()


def test_database_url_override_drives_offline_migrations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    alembic_config: Config,
) -> None:
    database_path = tmp_path / "offline.db"
    database_url = f"sqlite:///{database_path}"
    resolved_urls: list[str] = []

    def recording_settings() -> Settings:
        settings = Settings()
        resolved_urls.append(settings.database_url)
        return settings

    monkeypatch.setenv("QUNXUE_DATABASE_URL", database_url)
    monkeypatch.setattr("qunxue_api.settings.Settings", recording_settings)
    output = StringIO()
    alembic_config.output_buffer = output

    command.upgrade(alembic_config, "head", sql=True)

    assert resolved_urls == [database_url]
    assert "CREATE TABLE research_tasks" in output.getvalue()
    assert not database_path.exists()


def test_alembic_head_matches_orm_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    alembic_config: Config,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'schema-drift.db'}"
    monkeypatch.setenv("QUNXUE_DATABASE_URL", database_url)
    command.upgrade(alembic_config, "head")

    database = Database(Settings().database_url)
    try:
        inspector = inspect(database.engine)
        database_tables = set(inspector.get_table_names()) - {"alembic_version"}
        metadata_tables = set(Base.metadata.tables)
        assert database_tables == metadata_tables

        # Alembic covers foreign keys, server defaults, types, uniqueness, and
        # reflectable indexes; SQLite expression indexes need the SQL check below.
        with database.engine.connect() as connection:
            migration_context = MigrationContext.configure(
                connection,
                opts={
                    "compare_server_default": True,
                    "compare_type": True,
                },
            )
            assert compare_metadata(migration_context, Base.metadata) == []

        for table_name in metadata_tables:
            assert _database_check_constraints(
                inspector,
                table_name,
            ) == _metadata_check_constraints(table_name)

            # SQLite stores SQL only for user-created indexes. Table-level
            # UNIQUE autoindexes have NULL SQL and stay in Alembic's comparison.
            assert _database_indexes(
                database,
                table_name,
            ) == _metadata_indexes(table_name, database.engine)
    finally:
        database.engine.dispose()
