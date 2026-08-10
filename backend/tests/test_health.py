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
    model_settings = (
        {}
        if runtime_mode == "mock"
        else {
            "model_base_url": "http://127.0.0.1:9/v1",
            "model_name": f"local-{runtime_mode}-model",
        }
    )
    app = create_app(
        settings=Settings(
            database_url=client.app.state.settings.database_url,
            runtime_mode=runtime_mode,
            **model_settings,
        ),
        database=client.app.state.database,
    )

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["runtime_mode"] == runtime_mode
    assert response.json()["capability"] == runtime_mode
    assert app.state.model_gateway.descriptor.provider == (
        "deterministic-mock" if runtime_mode == "mock" else "openai-compatible"
    )


@pytest.mark.parametrize("runtime_mode", ["base", "sft"])
def test_non_mock_runtime_requires_an_endpoint_and_model(runtime_mode: str) -> None:
    with pytest.raises(ValueError, match="model_base_url.*model_name"):
        create_app(
            settings=Settings(
                database_url="sqlite+pysqlite:///:memory:",
                runtime_mode=runtime_mode,
            )
        )


def test_model_credentials_are_secret_values_in_runtime_settings() -> None:
    settings = Settings(
        model_api_key="local-test-api-key",
        model_extra_headers={"X-Tenant-Token": "local-test-tenant-token"},
        model_sft_resource_id="local-test-lora-id",
    )

    rendered = repr(settings)
    assert settings.model_api_key is not None
    assert settings.model_api_key.get_secret_value() == "local-test-api-key"
    assert "local-test-api-key" not in rendered
    assert "local-test-tenant-token" not in rendered
    assert "local-test-lora-id" not in rendered
