from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_migration_builds_research_task_table(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    assert "research_tasks" in inspect(engine).get_table_names()
    engine.dispose()
