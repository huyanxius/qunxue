import os
from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import (
    CheckConstraint,
    Column,
    Integer,
    MetaData,
    Table,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.schema import CreateIndex

from qunxue_api.adapters.sqlite import Base
from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.settings import BACKEND_ROOT, Settings


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.strip().removesuffix(";").split())


def _metadata_check_constraints(
    metadata: MetaData,
    table_name: str,
    engine: Engine,
) -> set[tuple[str | None, str]]:
    table = metadata.tables[table_name]
    constraints = [
        *table.constraints,
        *(constraint for column in table.columns for constraint in column.constraints),
    ]
    return {
        (
            constraint.name,
            _normalize_sql(
                str(
                    constraint.sqltext.compile(
                        dialect=engine.dialect,
                        compile_kwargs={
                            "include_table": False,
                            "literal_binds": True,
                        },
                    )
                )
            ),
        )
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


def _primary_key_mismatches(
    inspector: Inspector,
    metadata: MetaData,
) -> dict[str, tuple[tuple[str, ...], tuple[str, ...]]]:
    mismatches: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}
    database_tables = set(inspector.get_table_names()) - {"alembic_version"}
    for table_name in sorted(database_tables & set(metadata.tables)):
        reflected_columns = tuple(
            inspector.get_pk_constraint(table_name).get("constrained_columns") or ()
        )
        metadata_columns = tuple(
            column.name for column in metadata.tables[table_name].primary_key.columns
        )
        if reflected_columns != metadata_columns:
            mismatches[table_name] = (reflected_columns, metadata_columns)
    return mismatches


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
        return {str(row.name): _normalize_sql(str(row.sql)) for row in rows}


def test_default_database_url_is_independent_of_working_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("QUNXUE_DATABASE_URL", raising=False)
    monkeypatch.chdir(BACKEND_ROOT.parent)
    settings_from_repository_root = Settings(_env_file=None)
    monkeypatch.chdir(BACKEND_ROOT)
    settings_from_backend = Settings(_env_file=None)

    expected_path = (BACKEND_ROOT / "var" / "qunxue.db").resolve()
    assert settings_from_repository_root.database_url == settings_from_backend.database_url
    assert make_url(settings_from_backend.database_url).database == str(expected_path)


def test_backend_env_file_is_independent_of_working_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("QUNXUE_RUNTIME_MODE=sft\n", encoding="utf-8")
    monkeypatch.delenv("QUNXUE_RUNTIME_MODE", raising=False)

    assert Settings.model_config["env_file"] == BACKEND_ROOT / ".env"
    monkeypatch.setitem(Settings.model_config, "env_file", dotenv_path)
    monkeypatch.chdir(BACKEND_ROOT.parent)
    settings_from_repository_root = Settings()
    monkeypatch.chdir(BACKEND_ROOT)
    settings_from_backend = Settings()

    assert settings_from_repository_root.runtime_mode == "sft"
    assert settings_from_backend.runtime_mode == "sft"


def test_relative_database_override_is_independent_of_working_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    alembic_config: Config,
) -> None:
    database_path = tmp_path / "relative-override.db"
    relative_database_path = os.path.relpath(database_path, BACKEND_ROOT)
    monkeypatch.setenv(
        "QUNXUE_DATABASE_URL",
        f"sqlite:///{relative_database_path}",
    )
    monkeypatch.chdir(BACKEND_ROOT.parent)
    settings_from_repository_root = Settings()
    command.upgrade(alembic_config, "head")

    monkeypatch.chdir(BACKEND_ROOT)
    settings_from_backend = Settings()

    assert settings_from_repository_root.database_url == settings_from_backend.database_url
    assert make_url(settings_from_backend.database_url).database == str(database_path)

    database = Database(settings_from_backend.database_url)
    try:
        assert database_path.is_file()
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


def test_research_task_progress_projection_is_persisted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    alembic_config: Config,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'projection.db'}"
    monkeypatch.setenv("QUNXUE_DATABASE_URL", database_url)
    command.upgrade(alembic_config, "head")

    database = Database(Settings().database_url)
    try:
        column_names = {
            column["name"] for column in inspect(database.engine).get_columns("research_tasks")
        }
        assert {
            "phenomenon_query_id",
            "phenomenon_version",
            "phenomenon_summary",
            "phenomenon_research_intent",
            "adopted_theory_count",
            "current_phenomenon_candidate_id",
            "current_match_run_id",
            "current_framework_id",
        } <= column_names
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


@pytest.mark.parametrize(
    "database_url",
    [
        "sqlite://",
        "sqlite:///:memory:",
        "sqlite:///file::memory:?cache=shared&uri=true",
        "sqlite:///file:shared-memory?mode=memory&cache=shared&uri=true",
    ],
)
def test_alembic_rejects_in_memory_sqlite(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    alembic_config: Config,
) -> None:
    monkeypatch.setenv("QUNXUE_DATABASE_URL", database_url)

    with pytest.raises(RuntimeError, match="file-backed SQLite database"):
        command.upgrade(alembic_config, "head")


def test_primary_key_guard_reports_missing_primary_key() -> None:
    database_metadata = MetaData()
    Table(
        "guard_probe",
        database_metadata,
        Column("id", Integer, nullable=False),
    )
    expected_metadata = MetaData()
    Table(
        "guard_probe",
        expected_metadata,
        Column("id", Integer, primary_key=True),
    )
    engine = create_engine("sqlite://")
    try:
        database_metadata.create_all(engine)

        assert _primary_key_mismatches(
            inspect(engine),
            expected_metadata,
        ) == {"guard_probe": ((), ("id",))}
    finally:
        engine.dispose()


def test_check_constraint_comparison_literalizes_bound_values() -> None:
    metadata = MetaData()
    table = Table(
        "constraint_probe",
        metadata,
        Column("value", Integer, nullable=False),
    )
    constraint = CheckConstraint(
        table.c.value >= 1,
        name="ck_constraint_probe_value",
    )
    table.append_constraint(constraint)
    engine = create_engine("sqlite://")
    try:
        metadata.create_all(engine)

        assert ":" in str(constraint.sqltext)
        assert _database_check_constraints(
            inspect(engine),
            table.name,
        ) == _metadata_check_constraints(metadata, table.name, engine)
    finally:
        engine.dispose()


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
        # SQLite FTS5 creates a virtual table plus private shadow tables. Search
        # behavior is covered at the catalog API boundary; these are not ORM rows.
        database_tables = {
            table_name
            for table_name in inspector.get_table_names()
            if table_name != "alembic_version"
            and not table_name.startswith("knowledge_search_fts")
        }
        metadata_tables = set(Base.metadata.tables)
        assert database_tables == metadata_tables
        assert _primary_key_mismatches(inspector, Base.metadata) == {}

        # Alembic covers foreign keys, server defaults, types, uniqueness, and
        # reflectable indexes; primary keys, check constraints, and SQLite
        # expression indexes need the explicit checks below.
        def include_schema_object(
            _object: object,
            name: str | None,
            object_type: str,
            reflected: bool,
            _compare_to: object,
        ) -> bool:
            return not (
                reflected
                and object_type == "table"
                and name is not None
                and name.startswith("knowledge_search_fts")
            )

        with database.engine.connect() as connection:
            migration_context = MigrationContext.configure(
                connection,
                opts={
                    "compare_server_default": True,
                    "compare_type": True,
                    "include_object": include_schema_object,
                },
            )
            assert compare_metadata(migration_context, Base.metadata) == []

        for table_name in metadata_tables:
            assert _database_check_constraints(
                inspector,
                table_name,
            ) == _metadata_check_constraints(
                Base.metadata,
                table_name,
                database.engine,
            )

            # SQLite stores SQL only for user-created indexes. Table-level
            # UNIQUE autoindexes have NULL SQL and stay in Alembic's comparison.
            assert _database_indexes(
                database,
                table_name,
            ) == _metadata_indexes(table_name, database.engine)
    finally:
        database.engine.dispose()
