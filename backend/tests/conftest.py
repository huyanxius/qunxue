from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.bootstrap import create_app
from qunxue_api.settings import Settings


@pytest.fixture
def alembic_config() -> Config:
    return Config(str(Path(__file__).parents[1] / "alembic.ini"))


@pytest.fixture
def client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    alembic_config: Config,
) -> Iterator[TestClient]:
    database_url = f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("QUNXUE_DATABASE_URL", database_url)
    settings = Settings(
        _env_file=None,
        database_url=database_url,
        runtime_mode="mock",
        model_base_url=None,
        model_api_key=None,
        model_name=None,
        model_extra_headers={},
        model_sft_resource_id=None,
    )
    command.upgrade(alembic_config, "head")
    database = Database(settings.database_url)
    app = create_app(
        settings=settings,
        database=database,
        require_email_verification=False,
    )

    with TestClient(app) as test_client:
        yield test_client

    database.engine.dispose()
