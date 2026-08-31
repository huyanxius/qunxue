from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_professional_material_archive_tables_follow_the_single_material_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    alembic_config: Config,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'professional-materials.db'}"
    monkeypatch.setenv("QUNXUE_DATABASE_URL", database_url)

    command.upgrade(alembic_config, "head")

    engine = create_engine(database_url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert {
        "research_material_archive_profiles",
        "research_material_batches",
        "research_material_collections",
        "research_literature_entries",
        "research_cases",
        "research_material_relations",
    } <= tables
