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


def test_research_project_lifecycle_upgrade_preserves_task_conversation_and_material(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    alembic_config: Config,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'research-project-lifecycle.db'}"
    monkeypatch.setenv("QUNXUE_DATABASE_URL", database_url)
    command.upgrade(alembic_config, "20260831_0001")

    database = Database(database_url)
    try:
        with database.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO users (
                        user_id, email, password_hash, display_name, role, status,
                        version, created_at, updated_at
                    ) VALUES (
                        'user-lifecycle', 'lifecycle@example.com', 'hash', 'Researcher',
                        'member', 'active', 1, :created_at, :created_at
                    )
                    """
                ),
                {"created_at": "2026-08-30 09:00:00"},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO agent_conversations (
                        conversation_id, user_id, title, current_research_task_id,
                        version, created_at, updated_at
                    ) VALUES (
                        'conversation-lifecycle', 'user-lifecycle', '社区照护研究', NULL,
                        1, :created_at, :created_at
                    )
                    """
                ),
                {"created_at": "2026-08-30 09:01:00"},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO research_tasks (
                        task_id, user_id, entry_type, status, version, idempotency_key,
                        phenomenon_summary, adopted_theory_count, conversation_id,
                        created_at, updated_at
                    ) VALUES (
                        'task-lifecycle', 'user-lifecycle', 'material_input',
                        'phenomenon_confirmed', 4, 'legacy-lifecycle-task',
                        '社区照护中的代际协作', 0, 'conversation-lifecycle',
                        :created_at, :created_at
                    )
                    """
                ),
                {"created_at": "2026-08-30 09:02:00"},
            )
            connection.execute(
                text(
                    """
                    UPDATE agent_conversations
                    SET current_research_task_id = 'task-lifecycle'
                    WHERE conversation_id = 'conversation-lifecycle'
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO research_materials (
                        material_id, user_id, task_id, idempotency_key,
                        original_filename, display_name, media_type, material_format,
                        material_kind, size_bytes, content_hash, status,
                        processing_policy_version, created_at, updated_at
                    ) VALUES (
                        'material-lifecycle', 'user-lifecycle', 'task-lifecycle',
                        'legacy-lifecycle-material', 'interview.txt', 'interview.txt',
                        'text/plain', 'txt', 'interview_transcript', 12,
                        'content-hash', 'ready', 'v1', :created_at, :created_at
                    )
                    """
                ),
                {"created_at": "2026-08-30 09:03:00"},
            )
    finally:
        database.engine.dispose()

    command.upgrade(alembic_config, "20260831_0002")
    database = Database(database_url)
    try:
        with database.engine.connect() as connection:
            task = connection.execute(
                text(
                    """
                    SELECT task_id, entry_mode, lifecycle_status, project_title
                    FROM research_tasks WHERE task_id = 'task-lifecycle'
                    """
                )
            ).mappings().one()
            assert dict(task) == {
                "task_id": "task-lifecycle",
                "entry_mode": "legacy",
                "lifecycle_status": "in_progress",
                "project_title": "社区照护中的代际协作",
            }
            assert connection.scalar(
                text(
                    "SELECT current_research_task_id FROM agent_conversations "
                    "WHERE conversation_id = 'conversation-lifecycle'"
                )
            ) == "task-lifecycle"
            assert connection.scalar(
                text(
                    "SELECT task_id FROM research_materials "
                    "WHERE material_id = 'material-lifecycle'"
                )
            ) == "task-lifecycle"
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


def test_m4_upgrade_converges_duplicate_task_plans_before_adding_uniqueness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    alembic_config: Config,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'm4-upgrade-convergence.db'}"
    monkeypatch.setenv("QUNXUE_DATABASE_URL", database_url)
    command.upgrade(alembic_config, "20260820_0005")

    database = Database(database_url)
    try:
        with database.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO research_tasks (
                        task_id, entry_type, status, version, idempotency_key,
                        created_at, updated_at
                    ) VALUES (
                        :task_id, 'phenomenon', 'theory_plan_confirmed', 1,
                        :idempotency_key, :created_at, :created_at
                    )
                    """
                ),
                [
                    {
                        "task_id": "task-current-pointer",
                        "idempotency_key": "task-current-pointer-key",
                        "created_at": "2026-08-20 09:00:00",
                    },
                    {
                        "task_id": "task-latest-fallback",
                        "idempotency_key": "task-latest-fallback-key",
                        "created_at": "2026-08-20 09:00:00",
                    },
                ],
            )
            connection.execute(
                text(
                    """
                    INSERT INTO match_runs (
                        match_run_id, task_id, version, status, snapshot, created_at
                    ) VALUES (
                        :match_run_id, :task_id, 1, 'completed', '{}', :created_at
                    )
                    """
                ),
                [
                    {
                        "match_run_id": "run-pointer-old",
                        "task_id": "task-current-pointer",
                        "created_at": "2026-08-20 10:00:00",
                    },
                    {
                        "match_run_id": "run-pointer-new",
                        "task_id": "task-current-pointer",
                        "created_at": "2026-08-21 10:00:00",
                    },
                    {
                        "match_run_id": "run-fallback-old",
                        "task_id": "task-latest-fallback",
                        "created_at": "2026-08-20 10:00:00",
                    },
                    {
                        "match_run_id": "run-fallback-z",
                        "task_id": "task-latest-fallback",
                        "created_at": "2026-08-21 10:00:00",
                    },
                ],
            )
            connection.execute(
                text(
                    """
                    INSERT INTO theory_decision_sets (
                        decision_set_id, match_run_id, version, snapshot, created_at
                    ) VALUES (
                        :decision_set_id, :match_run_id, 1, '{}', :created_at
                    )
                    """
                ),
                [
                    {
                        "decision_set_id": "decision-pointer-old",
                        "match_run_id": "run-pointer-old",
                        "created_at": "2026-08-20 10:30:00",
                    },
                    {
                        "decision_set_id": "decision-pointer-new",
                        "match_run_id": "run-pointer-new",
                        "created_at": "2026-08-21 10:30:00",
                    },
                    {
                        "decision_set_id": "decision-fallback-old",
                        "match_run_id": "run-fallback-old",
                        "created_at": "2026-08-20 10:30:00",
                    },
                    {
                        "decision_set_id": "decision-fallback-z",
                        "match_run_id": "run-fallback-z",
                        "created_at": "2026-08-21 10:30:00",
                    },
                ],
            )
            connection.execute(
                text(
                    """
                    INSERT INTO confirmed_theory_plans (
                        theory_plan_id, task_id, match_run_id, decision_set_id,
                        version, adopted_candidate_ids, confirmed_at
                    ) VALUES (
                        :theory_plan_id, :task_id, :match_run_id, :decision_set_id,
                        1, '[]', :confirmed_at
                    )
                    """
                ),
                [
                    {
                        "theory_plan_id": "plan-pointer-old",
                        "task_id": "task-current-pointer",
                        "match_run_id": "run-pointer-old",
                        "decision_set_id": "decision-pointer-old",
                        "confirmed_at": "2026-08-20 11:00:00",
                    },
                    {
                        "theory_plan_id": "plan-pointer-new",
                        "task_id": "task-current-pointer",
                        "match_run_id": "run-pointer-new",
                        "decision_set_id": "decision-pointer-new",
                        "confirmed_at": "2026-08-21 11:00:00",
                    },
                    {
                        "theory_plan_id": "plan-fallback-old",
                        "task_id": "task-latest-fallback",
                        "match_run_id": "run-fallback-old",
                        "decision_set_id": "decision-fallback-old",
                        "confirmed_at": "2026-08-20 11:00:00",
                    },
                    {
                        "theory_plan_id": "plan-fallback-z",
                        "task_id": "task-latest-fallback",
                        "match_run_id": "run-fallback-z",
                        "decision_set_id": "decision-fallback-z",
                        "confirmed_at": "2026-08-21 11:00:00",
                    },
                ],
            )
            connection.execute(
                text(
                    """
                    UPDATE research_tasks
                    SET current_theory_plan_id = 'plan-pointer-old'
                    WHERE task_id = 'task-current-pointer'
                    """
                )
            )

        command.upgrade(alembic_config, "20260822_0006")

        with database.engine.connect() as connection:
            plans = connection.execute(
                text(
                    """
                    SELECT task_id, theory_plan_id
                    FROM confirmed_theory_plans
                    ORDER BY task_id
                    """
                )
            ).all()
            current_plan_id = connection.execute(
                text(
                    """
                    SELECT current_theory_plan_id
                    FROM research_tasks
                    WHERE task_id = 'task-current-pointer'
                    """
                )
            ).scalar_one()

        assert plans == [
            ("task-current-pointer", "plan-pointer-old"),
            ("task-latest-fallback", "plan-fallback-z"),
        ]
        assert current_plan_id == "plan-pointer-old"
    finally:
        database.engine.dispose()


def test_m4_downgrade_converges_decision_revisions_before_restoring_uniqueness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    alembic_config: Config,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'm4-downgrade-convergence.db'}"
    monkeypatch.setenv("QUNXUE_DATABASE_URL", database_url)
    command.upgrade(alembic_config, "20260822_0006")

    database = Database(database_url)
    try:
        with database.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO research_tasks (
                        task_id, entry_type, status, version, idempotency_key,
                        created_at, updated_at
                    ) VALUES (
                        :task_id, 'phenomenon', 'theory_plan_confirmed', 1,
                        :idempotency_key, :created_at, :created_at
                    )
                    """
                ),
                [
                    {
                        "task_id": "task-referenced-decision",
                        "idempotency_key": "task-referenced-decision-key",
                        "created_at": "2026-08-20 09:00:00",
                    },
                    {
                        "task_id": "task-decision-fallback",
                        "idempotency_key": "task-decision-fallback-key",
                        "created_at": "2026-08-20 09:00:00",
                    },
                ],
            )
            connection.execute(
                text(
                    """
                    INSERT INTO match_runs (
                        match_run_id, task_id, version, status, snapshot, created_at
                    ) VALUES (
                        :match_run_id, :task_id, 1, 'completed', '{}', :created_at
                    )
                    """
                ),
                [
                    {
                        "match_run_id": "run-referenced-decision",
                        "task_id": "task-referenced-decision",
                        "created_at": "2026-08-20 10:00:00",
                    },
                    {
                        "match_run_id": "run-decision-fallback",
                        "task_id": "task-decision-fallback",
                        "created_at": "2026-08-20 10:00:00",
                    },
                ],
            )
            connection.execute(
                text(
                    """
                    INSERT INTO theory_decision_sets (
                        decision_set_id, match_run_id, version, draft_version,
                        snapshot, created_at
                    ) VALUES (
                        :decision_set_id, :match_run_id, 1, :draft_version,
                        '{}', :created_at
                    )
                    """
                ),
                [
                    {
                        "decision_set_id": "decision-referenced",
                        "match_run_id": "run-referenced-decision",
                        "draft_version": 1,
                        "created_at": "2026-08-20 10:30:00",
                    },
                    {
                        "decision_set_id": "decision-unreferenced-newer",
                        "match_run_id": "run-referenced-decision",
                        "draft_version": 99,
                        "created_at": "2026-08-22 10:30:00",
                    },
                    {
                        "decision_set_id": "decision-fallback-old",
                        "match_run_id": "run-decision-fallback",
                        "draft_version": 4,
                        "created_at": "2026-08-20 10:30:00",
                    },
                    {
                        "decision_set_id": "decision-fallback-a",
                        "match_run_id": "run-decision-fallback",
                        "draft_version": 5,
                        "created_at": "2026-08-21 10:30:00",
                    },
                    {
                        "decision_set_id": "decision-fallback-z",
                        "match_run_id": "run-decision-fallback",
                        "draft_version": 6,
                        "created_at": "2026-08-19 10:30:00",
                    },
                ],
            )
            connection.execute(
                text(
                    """
                    INSERT INTO confirmed_theory_plans (
                        theory_plan_id, task_id, match_run_id, decision_set_id,
                        version, adopted_candidate_ids, confirmed_at
                    ) VALUES (
                        'plan-referenced', 'task-referenced-decision',
                        'run-referenced-decision', 'decision-referenced',
                        1, '[]', '2026-08-20 11:00:00'
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    UPDATE research_tasks
                    SET current_theory_plan_id = 'plan-referenced'
                    WHERE task_id = 'task-referenced-decision'
                    """
                )
            )

        command.downgrade(alembic_config, "20260820_0005")

        with database.engine.connect() as connection:
            decisions = connection.execute(
                text(
                    """
                    SELECT match_run_id, decision_set_id
                    FROM theory_decision_sets
                    ORDER BY match_run_id
                    """
                )
            ).all()
            plan_decision_id = connection.execute(
                text(
                    """
                    SELECT decision_set_id
                    FROM confirmed_theory_plans
                    WHERE theory_plan_id = 'plan-referenced'
                    """
                )
            ).scalar_one()

        assert decisions == [
            ("run-decision-fallback", "decision-fallback-z"),
            ("run-referenced-decision", "decision-referenced"),
        ]
        assert plan_decision_id == "decision-referenced"
    finally:
        database.engine.dispose()


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
                and not table_name.startswith("research_material_search")
        }
        metadata_tables = set(Base.metadata.tables)
        assert database_tables == metadata_tables
        assert _primary_key_mismatches(inspector, Base.metadata) == {}

        # Alembic covers foreign keys, server defaults, types, uniqueness, and
        # reflectable indexes; primary keys, check constraints, and SQLite
        # expression indexes need the explicit checks below.
        def include_schema_object(
            schema_object: object,
            name: str | None,
            object_type: str,
            reflected: bool,
            _compare_to: object,
        ) -> bool:
            if (
                reflected
                and object_type == "table"
                and name is not None
                    and name.startswith(("knowledge_search_fts", "research_material_search"))
            ):
                return False
            if object_type == "foreign_key_constraint":
                columns = tuple(
                    column.name
                    for column in getattr(schema_object, "columns", ())
                )
                table_name = getattr(getattr(schema_object, "table", None), "name", None)
                if (
                    (
                        table_name == "agent_conversations"
                        and columns == ("current_research_task_id",)
                    )
                    or (
                        table_name == "research_tasks"
                        and columns in {("conversation_id",), ("source_agent_run_id",)}
                    )
                ):
                    return False
            if object_type == "index" and name == "uq_research_tasks_conversation":
                return False
            if object_type == "unique_constraint" and not reflected:
                columns = tuple(
                    column.name
                    for column in getattr(schema_object, "columns", ())
                )
                table_name = getattr(getattr(schema_object, "table", None), "name", None)
                if table_name == "research_tasks" and columns == ("conversation_id",):
                    return False
            return True

        with database.engine.connect() as connection:
            migration_context = MigrationContext.configure(
                connection,
                opts={
                    # Account defaults are required while adding non-null
                    # columns to existing SQLite rows, but remain ORM-side
                    # defaults after the migration has populated those rows.
                    "compare_server_default": False,
                    "compare_type": True,
                    "include_object": include_schema_object,
                },
            )
            assert compare_metadata(migration_context, Base.metadata) == []

        for table_name in metadata_tables:
            database_checks = _database_check_constraints(inspector, table_name)
            metadata_checks = _metadata_check_constraints(
                Base.metadata,
                table_name,
                database.engine,
            )
            if table_name == "users":
                # The account migration adds these columns in place on SQLite
                # to avoid rebuilding the users table and cascading existing
                # sessions/tasks. The service validates the same values at
                # write time; the old table cannot gain these checks in place.
                metadata_checks = {
                    item for item in metadata_checks if not item[0].startswith("ck_users_")
                }
            assert database_checks == metadata_checks

            # SQLite stores SQL only for user-created indexes. Table-level
            # UNIQUE autoindexes have NULL SQL and stay in Alembic's comparison.
            database_indexes = _database_indexes(database, table_name)
            if table_name == "research_tasks":
                # SQLite keeps this unique pointer as an index because the
                # migration adds it in place; ORM metadata reflects it as a
                # table-level unique constraint.
                database_indexes.pop("uq_research_tasks_conversation", None)
            assert database_indexes == _metadata_indexes(table_name, database.engine)
    finally:
        database.engine.dispose()
