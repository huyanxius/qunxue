from pathlib import Path

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
    tmp_path: Path,
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
            **(_retrieval_settings(tmp_path) if runtime_mode != "mock" else {}),
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
def test_non_mock_runtime_requires_an_endpoint_and_model(
    runtime_mode: str,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="model_base_url.*model_name"):
        create_app(
            settings=Settings(
                database_url="sqlite+pysqlite:///:memory:",
                runtime_mode=runtime_mode,
                **_retrieval_settings(tmp_path),
            )
        )


def _retrieval_settings(tmp_path: Path) -> dict[str, object]:
    return {
        "retrieval_index_path": tmp_path / "retrieval.db",
        "embedding_base_url": "http://127.0.0.1:9/v1",
        "embedding_api_key": "embedding-test-key",
        "embedding_model": "Pro/BAAI/bge-m3",
        "reranker_base_url": "http://127.0.0.1:9/v1",
        "reranker_api_key": "reranker-test-key",
        "reranker_model": "Pro/BAAI/bge-reranker-v2-m3",
    }


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


def test_configured_frontend_origin_can_preflight_agent_requests(client: TestClient) -> None:
    app = create_app(
        settings=Settings(
            _env_file=None,
            database_url=client.app.state.settings.database_url,
            cors_allowed_origins=("https://frontend.example.test",),
        ),
        database=client.app.state.database,
    )

    with TestClient(app) as cross_origin_client:
        response = cross_origin_client.options(
            "/api/agent/turns",
            headers={
                "Origin": "https://frontend.example.test",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,idempotency-key",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://frontend.example.test"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cross_site_session_cookie_uses_secure_none_when_configured(client: TestClient) -> None:
    app = create_app(
        settings=Settings(
            _env_file=None,
            database_url=client.app.state.settings.database_url,
            session_cookie_secure=True,
            session_cookie_samesite="none",
        ),
        database=client.app.state.database,
    )

    with TestClient(app) as cross_origin_client:
        response = cross_origin_client.post(
            "/api/session/register",
            json={
                "email": "cross-site-cookie@example.com",
                "password": "password-123",
                "display_name": "跨站验收",
            },
            headers={"Idempotency-Key": "cross-site-cookie"},
        )

    assert response.status_code == 201
    cookie = response.headers["set-cookie"].lower()
    assert "samesite=none" in cookie
    assert "secure" in cookie
