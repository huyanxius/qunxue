from logging.config import fileConfig

from alembic import context

from qunxue_api.adapters.sqlite import Base
from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.settings import Settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    return Settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    database = Database(_database_url())
    try:
        with database.engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        database.engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
