from fastapi.testclient import TestClient


def test_health_reports_runtime_contract(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "群学致知 API",
        "runtime_mode": "inline_demo",
        "persistence": "sqlite",
        "contract_version": "2026-07-foundation",
    }
