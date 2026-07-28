from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from qunxue_api.adapters.sqlite import Base
from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.bootstrap import create_app
from qunxue_api.settings import Settings


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    database_url = f"sqlite:///{tmp_path / 'test.db'}"
    settings = Settings(database_url=database_url)
    database = Database(database_url)
    Base.metadata.create_all(database.engine)
    app = create_app(settings=settings, database=database)

    with TestClient(app) as test_client:
        yield test_client

    database.engine.dispose()
