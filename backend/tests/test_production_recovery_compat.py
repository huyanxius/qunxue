from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text


@pytest.mark.parametrize("starting_revision", ["base", "20260928_0460", "20261001_0460"])
def test_published_migration_paths_converge(tmp_path, monkeypatch, starting_revision):
    url = f"sqlite:///{tmp_path / 'compat.db'}"
    monkeypatch.setenv("QUNXUE_DATABASE_URL", url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    assert len(ScriptDirectory.from_config(config).get_heads()) == 1
    command.upgrade(config, starting_revision)
    engine = create_engine(url)
    if starting_revision == "20260928_0460":
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO password_reset_rate_limits VALUES "
                    "('preserved', '2026-10-01', 3, '2026-10-01', '2026-10-01')"
                )
            )
    command.upgrade(config, "head")
    tables = inspect(engine).get_table_names()
    assert "password_reset_rate_limits" in tables
    assert {"frontier_sources", "frontier_items"} <= set(tables)
    if starting_revision == "20260928_0460":
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT request_count FROM password_reset_rate_limits "
                        "WHERE scope_key='preserved'"
                    )
                ).scalar_one()
                == 3
            )
    engine.dispose()
