import pytest
from fastapi.testclient import TestClient

from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.bootstrap import create_app
from qunxue_api.settings import Settings


def test_health_reports_runtime_contract(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "群学致知 API",
        "runtime_mode": "mock",
        "persistence": "sqlite",
        "contract_version": "2026-07-foundation",
        "capability": "mock",
        "knowledge_release_id": "knowledge-demo-v1",
    }


@pytest.mark.parametrize("runtime_mode", ["mock", "base", "sft"])
def test_health_reports_each_configured_runtime_mode(runtime_mode: str) -> None:
    database = Database("sqlite:///:memory:")
    app = create_app(
        settings=Settings(
            database_url="sqlite:///:memory:",
            runtime_mode=runtime_mode,
        ),
        database=database,
    )

    with TestClient(app) as client:
        response = client.get("/api/health")

    database.engine.dispose()
    assert response.status_code == 200
    assert response.json()["runtime_mode"] == runtime_mode
