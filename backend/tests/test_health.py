import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from qunxue_api.adapters.retrieval import (
    RETRIEVAL_CORPUS_SCHEMA_VERSION,
    RetrievalChunk,
    SqliteRetrievalIndex,
)
from qunxue_api.bootstrap import create_app
from qunxue_api.modules.knowledge_catalog import KnowledgeUsePurpose
from qunxue_api.settings import SILICONFLOW_EMBEDDING_MODEL, Settings


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
    if runtime_mode != "mock":
        _seed_ready_retrieval_index(app, index_path=tmp_path / "retrieval.db")

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["runtime_mode"] == runtime_mode
    assert response.json()["capability"] == runtime_mode
    assert app.state.model_gateway.descriptor.provider == (
        "deterministic-mock" if runtime_mode == "mock" else "openai-compatible"
    )


@pytest.mark.parametrize("runtime_mode", ["base", "sft"])
def test_health_rejects_non_mock_runtime_without_a_ready_match_index(
    runtime_mode: str,
    client: TestClient,
    tmp_path: Path,
) -> None:
    app = create_app(
        settings=Settings(
            database_url=client.app.state.settings.database_url,
            runtime_mode=runtime_mode,
            **_retrieval_settings(tmp_path),
            model_base_url="http://127.0.0.1:9/v1",
            model_name=f"local-{runtime_mode}-model",
        ),
        database=client.app.state.database,
    )

    with TestClient(app) as health_client:
        response = health_client.get("/api/health")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "retrieval_unavailable"
    assert response.json()["error"]["message"] == (
        "当前 MATCH 知识发布没有身份一致的 ready 检索索引。"
    )


@pytest.mark.parametrize(
    ("embedding_model", "chunk_schema_version"),
    [
        ("legacy-embedding", RETRIEVAL_CORPUS_SCHEMA_VERSION),
        (SILICONFLOW_EMBEDDING_MODEL, "retrieval-corpus-v0"),
    ],
)
def test_health_rejects_a_ready_index_with_stale_retrieval_identity(
    embedding_model: str,
    chunk_schema_version: str,
    client: TestClient,
    tmp_path: Path,
) -> None:
    app = create_app(
        settings=Settings(
            database_url=client.app.state.settings.database_url,
            runtime_mode="base",
            **_retrieval_settings(tmp_path),
            model_base_url="http://127.0.0.1:9/v1",
            model_name="local-base-model",
        ),
        database=client.app.state.database,
    )
    _seed_ready_retrieval_index(
        app,
        index_path=tmp_path / "retrieval.db",
        embedding_model=embedding_model,
        chunk_schema_version=chunk_schema_version,
    )

    with TestClient(app) as health_client:
        response = health_client.get("/api/health")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "retrieval_unavailable"


def test_health_rejects_a_ready_manifest_without_its_index_points(
    client: TestClient,
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "retrieval.db"
    app = create_app(
        settings=Settings(
            database_url=client.app.state.settings.database_url,
            runtime_mode="base",
            **_retrieval_settings(tmp_path),
            model_base_url="http://127.0.0.1:9/v1",
            model_name="local-base-model",
        ),
        database=client.app.state.database,
    )
    _seed_ready_retrieval_index(app, index_path=index_path)
    with sqlite3.connect(index_path) as connection:
        connection.execute("DELETE FROM retrieval_points")

    with TestClient(app) as health_client:
        response = health_client.get("/api/health")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "retrieval_unavailable"


def test_health_maps_corrupt_index_storage_to_retrieval_unavailable(
    client: TestClient,
    tmp_path: Path,
) -> None:
    index_path = tmp_path / "retrieval.db"
    app = create_app(
        settings=Settings(
            database_url=client.app.state.settings.database_url,
            runtime_mode="base",
            **_retrieval_settings(tmp_path),
            model_base_url="http://127.0.0.1:9/v1",
            model_name="local-base-model",
        ),
        database=client.app.state.database,
    )
    _seed_ready_retrieval_index(app, index_path=index_path)
    index_path.write_bytes(b"not-a-sqlite-index")

    with TestClient(app, raise_server_exceptions=False) as health_client:
        response = health_client.get("/api/health")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "retrieval_unavailable"


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


def _seed_ready_retrieval_index(
    app,
    *,
    index_path: Path,
    embedding_model: str = SILICONFLOW_EMBEDDING_MODEL,
    chunk_schema_version: str = RETRIEVAL_CORPUS_SCHEMA_VERSION,
) -> None:
    release = app.state.knowledge_catalog.current_release(
        purpose=KnowledgeUsePurpose.MATCH
    )
    SqliteRetrievalIndex(index_path).rebuild(
        knowledge_release_id=release.knowledge_release_id,
        release_content_hash=release.content_hash,
        embedding_model=embedding_model,
        chunk_schema_version=chunk_schema_version,
        chunks=(
            RetrievalChunk(
                chunk_id="theory-profile:health-check:v1",
                document_kind="theory_profile",
                knowledge_id="D2:P001",
                theory_id="health-check",
                content_version=1,
                content_hash="sha256:health-check",
                title="健康检查理论条目",
                text="用于验证 release-bound ready 检索索引。",
                source_ids=("source:health-check",),
            ),
        ),
        vectors=((1.0, 0.0),),
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
