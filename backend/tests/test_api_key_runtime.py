from fastapi.testclient import TestClient

from qunxue_api.bootstrap import create_app
from qunxue_api.modules.knowledge_catalog import KnowledgeUsePurpose
from qunxue_api.settings import Settings


def _settings(
    client: TestClient,
    *,
    api_key: str | None,
    runtime_mode: str = "mock",
) -> Settings:
    return Settings(
        _env_file=None,
        database_url=client.app.state.settings.database_url,
        runtime_mode=runtime_mode,
        model_base_url=None,
        model_api_key=api_key,
        model_name=None,
        model_extra_headers={},
        model_sft_resource_id=None,
    )


def test_api_key_only_selects_real_defaults_and_catalog_matching(client: TestClient) -> None:
    app = create_app(
        settings=_settings(client, api_key="test-api-key"),
        database=client.app.state.database,
    )

    descriptor = app.state.model_gateway.descriptor

    assert descriptor.provider == "openai-compatible"
    assert descriptor.model_version == "deepseek-v4-flash"
    assert descriptor.capability_tier == "base"
    assert app.state.knowledge_retriever is not None

    release = app.state.knowledge_catalog.current_release(purpose=KnowledgeUsePurpose.MATCH)
    result = app.state.knowledge_retriever.search(
        query="历史唯物主义",
        knowledge_release_id=release.knowledge_release_id,
        release_content_hash=release.content_hash,
        document_kind="theory_profile",
        limit=5,
    )
    assert result.mode == "catalog_lexical"
    assert result.retrieval_index_id.startswith("catalog-lexical:")
    assert len(result.hits) >= 3

    with TestClient(app) as api:
        response = api.get("/api/health")

    assert response.status_code == 200
    assert response.json()["runtime_mode"] == "base"
    assert response.json()["provider"] == "openai-compatible"
    assert response.json()["model_version"] == "deepseek-v4-flash"


def test_blank_api_key_keeps_deterministic_mock_runtime(client: TestClient) -> None:
    app = create_app(
        settings=_settings(client, api_key="   "),
        database=client.app.state.database,
    )

    descriptor = app.state.model_gateway.descriptor

    assert descriptor.provider == "deterministic-mock"
    assert descriptor.capability_tier == "mock"
    assert app.state.knowledge_retriever is None


def test_explicit_base_with_only_model_key_uses_catalog_fallback(client: TestClient) -> None:
    app = create_app(
        settings=_settings(
            client,
            api_key="test-api-key",
            runtime_mode="base",
        ),
        database=client.app.state.database,
    )

    assert app.state.model_gateway.descriptor.capability_tier == "base"
    assert app.state.knowledge_retriever is not None
