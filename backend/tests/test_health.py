import pytest
from fastapi.testclient import TestClient

from qunxue_api.bootstrap import create_app
from qunxue_api.settings import Settings


def test_health_reports_runtime_contract(client: TestClient) -> None:
    current_release = client.get("/api/knowledge/releases/current")
    response = client.get("/api/health")

    assert current_release.status_code == 200
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "群学致知 API",
        "runtime_mode": "mock",
        "persistence": "sqlite",
        "contract_version": "2026-07-foundation",
        "capability": "mock",
        "knowledge_release_id": current_release.json()["knowledge_release_id"],
    }


@pytest.mark.parametrize("runtime_mode", ["mock", "base", "sft"])
def test_health_reports_each_configured_runtime_mode(
    runtime_mode: str,
    client: TestClient,
) -> None:
    app = create_app(
        settings=Settings(
            database_url=client.app.state.settings.database_url,
            runtime_mode=runtime_mode,
        ),
        database=client.app.state.database,
    )

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["runtime_mode"] == runtime_mode
