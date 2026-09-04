import asyncio
import json
import sqlite3
from dataclasses import FrozenInstanceError
from pathlib import Path
from threading import Event, Lock
from time import monotonic

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from qunxue_api.adapters.model import (
    InMemoryModelAttemptRecorder,
    ModelEndpoint,
    ModelProviderFailure,
    ModelRouteExecutor,
    OpenAICompatibleModelProvider,
    RoutedModelProvider,
    SqliteModelAttemptRecorder,
)
from qunxue_api.adapters.retrieval import (
    RETRIEVAL_CORPUS_SCHEMA_VERSION,
    RetrievalChunk,
    SqliteRetrievalIndex,
)
from qunxue_api.bootstrap import create_app
from qunxue_api.modules.knowledge_catalog import KnowledgeUsePurpose
from qunxue_api.settings import SILICONFLOW_EMBEDDING_MODEL, Settings


def _probe_completion() -> dict[str, object]:
    return {"choices": [{"message": {}}]}


@pytest.fixture
def healthy_probe_transport() -> httpx.MockTransport:
    return httpx.MockTransport(
        lambda request: httpx.Response(200, json=_probe_completion(), request=request)
    )


class _BlockingProbeTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.started = Event()
        self.cancelled = Event()
        self.finished = Event()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        del request
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        finally:
            self.finished.set()


def test_health_reports_runtime_contract(client: TestClient) -> None:
    current_release = client.get("/api/knowledge/releases/current")
    response = client.get("/api/health")

    assert current_release.status_code == 200
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "群学致知 API",
        "runtime_mode": "mock",
        "provider": "deterministic-mock",
        "model_version": "mock-sociology-v1",
        "persistence": "sqlite",
        "contract_version": "2026-07-foundation",
        "capability": "mock",
        "knowledge_release_id": current_release.json()["knowledge_release_id"],
        "model_status": "healthy",
        "model_checked_at": None,
        "release_revision": "unreleased",
    }


def test_health_reports_unknown_before_a_real_model_has_been_checked(
    client: TestClient,
    tmp_path: Path,
) -> None:
    app = create_app(
        settings=Settings(
            _env_file=None,
            database_url=client.app.state.settings.database_url,
            runtime_mode="base",
            **_retrieval_settings(tmp_path),
            model_base_url="https://primary.internal.test/v1",
            model_api_key="health-secret-key",
            model_name="private-model-name",
        ),
        database=client.app.state.database,
    )
    _seed_ready_retrieval_index(app, index_path=tmp_path / "retrieval.db")
    health_client = TestClient(app)
    try:
        response = health_client.get("/api/health")
    finally:
        health_client.close()

    assert response.status_code == 200
    assert response.json()["model_status"] == "unknown"
    assert response.json()["model_checked_at"] is None


def test_health_reports_degraded_model_without_leaking_endpoint_details(
    client: TestClient,
    tmp_path: Path,
    healthy_probe_transport: httpx.MockTransport,
) -> None:
    app = create_app(
        settings=Settings(
            _env_file=None,
            database_url=client.app.state.settings.database_url,
            runtime_mode="base",
            **_retrieval_settings(tmp_path),
            model_base_url="https://primary.internal.test/v1",
            model_api_key="health-secret-key",
            model_name="private-model-name",
            model_extra_headers={"X-Private-Tenant": "tenant-secret"},
        ),
        database=client.app.state.database,
        model_probe_transport=healthy_probe_transport,
    )
    _seed_ready_retrieval_index(app, index_path=tmp_path / "retrieval.db")

    with TestClient(app) as health_client:
        app.state.model_router.note_failure(endpoint_id="primary", retryable=True)
        response = health_client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["model_status"] == "degraded"
    assert not {
        "primary.internal.test",
        "health-secret-key",
        "tenant-secret",
        "primary",
    } & set(response.text.split())
    assert all(
        secret not in response.text
        for secret in (
            "primary.internal.test",
            "health-secret-key",
            "tenant-secret",
            "primary",
        )
    )
    assert response.json()["model_version"] == "private-model-name"


def test_health_returns_health_contract_when_all_real_endpoints_are_unavailable(
    client: TestClient,
    tmp_path: Path,
    healthy_probe_transport: httpx.MockTransport,
) -> None:
    app = create_app(
        settings=Settings(
            _env_file=None,
            database_url=client.app.state.settings.database_url,
            runtime_mode="base",
            **_retrieval_settings(tmp_path),
            model_base_url="https://primary.internal.test/v1",
            model_name="private-model-name",
        ),
        database=client.app.state.database,
        model_probe_transport=healthy_probe_transport,
    )
    _seed_ready_retrieval_index(app, index_path=tmp_path / "retrieval.db")

    with TestClient(app) as health_client:
        for _ in range(3):
            app.state.model_router.note_failure(endpoint_id="primary", retryable=True)
        response = health_client.get("/api/health")

    assert response.status_code == 503
    assert response.json()["status"] == "ok"
    assert response.json()["model_status"] == "unavailable"
    assert "error" not in response.json()


def test_health_exposes_configured_release_revision(client: TestClient) -> None:
    app = create_app(
        settings=Settings(
            _env_file=None,
            database_url=client.app.state.settings.database_url,
            release_revision="7e48edff",
        ),
        database=client.app.state.database,
    )

    with TestClient(app) as release_client:
        response = release_client.get("/api/health")

    assert response.json()["release_revision"] == "7e48edff"


def test_routed_probe_uses_audited_shared_route_without_request_identity() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_probe_completion(), request=request)

    endpoint = ModelEndpoint(
        endpoint_id="primary",
        base_url="https://primary.internal.test/v1",
        api_key="health-secret-key",
        model="private-model-name",
        timeout_seconds=1,
        provider="openai-compatible",
    )
    attempts = InMemoryModelAttemptRecorder()
    router = ModelRouteExecutor(endpoints=(endpoint,), recorder=attempts)
    provider = OpenAICompatibleModelProvider(
        base_url=endpoint.base_url,
        api_key=endpoint.api_key,
        model=endpoint.model,
        timeout_seconds=endpoint.timeout_seconds,
        capability_tier="base",
        extra_headers={"X-Private-Tenant": "tenant-secret"},
        probe_transport=httpx.MockTransport(handle),
    )
    routed = RoutedModelProvider(providers=(provider,), router=router)

    asyncio.run(routed.probe())

    request_body = json.loads(requests[-1].content)
    attempt = attempts.list_all()[0]
    assert request_body["max_tokens"] == 1
    assert requests[-1].headers["Authorization"] == "Bearer health-secret-key"
    assert requests[-1].headers["X-Private-Tenant"] == "tenant-secret"
    assert attempt.context.capability == "health_probe"
    assert attempt.context.task_id is None
    assert attempt.context.agent_run_id is None
    assert attempt.success is True
    assert router.health_snapshot().status == "healthy"
    assert routed.health_checked_at is not None


@pytest.mark.parametrize(
    "response",
    [
        (401, {"private": "denial"}),
        (200, "not-json"),
        (200, []),
        (200, {}),
        (200, {"choices": []}),
        (200, {"choices": [None]}),
        (200, {"choices": [{}]}),
    ],
)
def test_failed_probe_is_sanitized_and_opens_the_endpoint_circuit(
    response: tuple[int, object],
) -> None:
    status_code, payload = response

    def handle(request: httpx.Request) -> httpx.Response:
        if isinstance(payload, str):
            return httpx.Response(status_code, text=payload, request=request)
        return httpx.Response(status_code, json=payload, request=request)

    endpoint = ModelEndpoint(
        endpoint_id="primary",
        base_url="https://private-endpoint.test/v1",
        api_key="private-probe-key",
        model="private-model-name",
        timeout_seconds=1,
        provider="openai-compatible",
    )
    attempts = InMemoryModelAttemptRecorder()
    router = ModelRouteExecutor(endpoints=(endpoint,), recorder=attempts)
    provider = OpenAICompatibleModelProvider(
        base_url=endpoint.base_url,
        api_key=endpoint.api_key,
        model=endpoint.model,
        timeout_seconds=endpoint.timeout_seconds,
        capability_tier="base",
        probe_transport=httpx.MockTransport(handle),
    )
    routed = RoutedModelProvider(providers=(provider,), router=router)

    for attempt_number in range(1, 4):
        with pytest.raises(ModelProviderFailure) as raised:
            asyncio.run(routed.probe())
        expected_status = "degraded" if attempt_number < 3 else "unhealthy"
        assert router.health_snapshot().status == expected_status
        assert raised.value.code == "model_probe_unavailable"
        assert "private" not in str(raised.value)

    assert {attempt.failure_code for attempt in attempts.list_all()} == {
        "model_probe_unavailable"
    }
    assert all(attempt.failure_retryable is True for attempt in attempts.list_all())
    assert routed.health_checked_at is not None


def test_probe_falls_back_and_reports_degraded_when_backup_is_healthy() -> None:
    primary_calls: list[httpx.Request] = []
    backup_calls: list[httpx.Request] = []

    def primary(request: httpx.Request) -> httpx.Response:
        primary_calls.append(request)
        return httpx.Response(403, text="private denial", request=request)

    def backup(request: httpx.Request) -> httpx.Response:
        backup_calls.append(request)
        return httpx.Response(200, json=_probe_completion(), request=request)

    endpoints = (
        ModelEndpoint("primary", "https://primary.test/v1", "m1", "secret", 1),
        ModelEndpoint("fallback-1", "https://backup.test/v1", "m2", "secret", 1),
    )
    attempts = InMemoryModelAttemptRecorder()
    router = ModelRouteExecutor(endpoints=endpoints, recorder=attempts)
    providers = (
        OpenAICompatibleModelProvider(
            base_url=endpoints[0].base_url,
            api_key=endpoints[0].api_key,
            model=endpoints[0].model,
            timeout_seconds=1,
            capability_tier="base",
            probe_transport=httpx.MockTransport(primary),
        ),
        OpenAICompatibleModelProvider(
            base_url=endpoints[1].base_url,
            api_key=endpoints[1].api_key,
            model=endpoints[1].model,
            timeout_seconds=1,
            capability_tier="base",
            probe_transport=httpx.MockTransport(backup),
        ),
    )

    asyncio.run(RoutedModelProvider(providers=providers, router=router).probe())

    assert len(primary_calls) == 1
    assert len(backup_calls) == 1
    assert router.health_snapshot().status == "degraded"
    assert [attempt.failure_code for attempt in attempts.list_all()] == [
        "model_probe_unavailable",
        None,
    ]


def test_cancelled_probe_does_not_fall_back_or_mark_a_successful_check() -> None:
    blocking = _BlockingProbeTransport()
    backup_calls: list[httpx.Request] = []

    def backup(request: httpx.Request) -> httpx.Response:
        backup_calls.append(request)
        return httpx.Response(200, json=_probe_completion(), request=request)

    endpoints = (
        ModelEndpoint("primary", "https://primary.test/v1", "m1", None, 1),
        ModelEndpoint("fallback-1", "https://backup.test/v1", "m2", None, 1),
    )
    attempts = InMemoryModelAttemptRecorder()
    router = ModelRouteExecutor(endpoints=endpoints, recorder=attempts)
    providers = (
        OpenAICompatibleModelProvider(
            base_url=endpoints[0].base_url,
            api_key=None,
            model=endpoints[0].model,
            timeout_seconds=1,
            capability_tier="base",
            probe_transport=blocking,
        ),
        OpenAICompatibleModelProvider(
            base_url=endpoints[1].base_url,
            api_key=None,
            model=endpoints[1].model,
            timeout_seconds=1,
            capability_tier="base",
            probe_transport=httpx.MockTransport(backup),
        ),
    )
    routed = RoutedModelProvider(providers=providers, router=router)

    async def cancel_in_flight() -> None:
        task = asyncio.create_task(routed.probe())
        while not blocking.started.is_set():
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel_in_flight())

    assert blocking.cancelled.is_set()
    assert blocking.finished.is_set()
    assert backup_calls == []
    assert router.health_snapshot().status == "unknown"
    assert routed.health_checked_at is None
    assert [attempt.failure_code for attempt in attempts.list_all()] == [
        "model_attempt_cancelled"
    ]


def test_real_model_probe_starts_immediately_repeats_and_is_joined_on_shutdown(
    client: TestClient,
    tmp_path: Path,
) -> None:
    second_probe = Event()
    probe_lock = Lock()
    probe_count = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal probe_count
        with probe_lock:
            probe_count += 1
            current_count = probe_count
            if probe_count >= 2:
                second_probe.set()
        if current_count == 1:
            raise httpx.ConnectError("private transport failure", request=request)
        return httpx.Response(200, json=_probe_completion(), request=request)

    transport = httpx.MockTransport(handle)
    app = create_app(
        settings=Settings(
            _env_file=None,
            database_url=client.app.state.settings.database_url,
            runtime_mode="base",
            **_retrieval_settings(tmp_path),
            model_base_url="https://primary.internal.test/v1",
            model_name="private-model-name",
            model_probe_interval_seconds=0.01,
        ),
        database=client.app.state.database,
        model_probe_transport=transport,
    )
    _seed_ready_retrieval_index(app, index_path=tmp_path / "retrieval.db")

    with TestClient(app):
        assert second_probe.wait(timeout=1)
        probe_task = app.state.model_probe_task
        assert probe_task.done() is False

    assert probe_task.done() is True


def test_shutdown_cancels_an_in_flight_probe_without_orphan_work(
    client: TestClient,
    tmp_path: Path,
) -> None:
    transport = _BlockingProbeTransport()
    app = create_app(
        settings=Settings(
            _env_file=None,
            database_url=client.app.state.settings.database_url,
            runtime_mode="base",
            **_retrieval_settings(tmp_path),
            model_base_url="https://primary.internal.test/v1",
            model_name="private-model-name",
        ),
        database=client.app.state.database,
        model_probe_transport=transport,
    )
    _seed_ready_retrieval_index(app, index_path=tmp_path / "retrieval.db")

    with TestClient(app):
        assert transport.started.wait(timeout=1)
        probe_task = app.state.model_probe_task
        shutdown_started = monotonic()

    assert monotonic() - shutdown_started < 0.5
    assert transport.cancelled.is_set()
    assert transport.finished.is_set()
    assert probe_task.done() is True


@pytest.mark.parametrize("runtime_mode", ["mock", "base", "sft"])
def test_health_reports_each_configured_runtime_mode(
    runtime_mode: str,
    client: TestClient,
    tmp_path: Path,
    healthy_probe_transport: httpx.MockTransport,
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
        model_probe_transport=healthy_probe_transport,
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
    healthy_probe_transport: httpx.MockTransport,
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
        model_probe_transport=healthy_probe_transport,
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
    healthy_probe_transport: httpx.MockTransport,
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
        model_probe_transport=healthy_probe_transport,
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
    healthy_probe_transport: httpx.MockTransport,
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
        model_probe_transport=healthy_probe_transport,
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
    healthy_probe_transport: httpx.MockTransport,
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
        model_probe_transport=healthy_probe_transport,
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


def test_fallback_can_override_primary_model() -> None:
    settings = Settings(
        model_base_url="https://primary.test/v1",
        model_name="primary-model",
        model_fallbacks=[
            {
                "base_url": "https://backup.test/v1",
                "api_key": "fallback-key",
                "model": "backup-model",
            }
        ],
    )

    endpoints = settings.resolved_model_endpoints()

    assert [endpoint.endpoint_id for endpoint in endpoints] == [
        "primary",
        "fallback-1",
    ]
    assert endpoints[1].model == "backup-model"
    assert "fallback-key" not in repr(settings)


def test_resolved_model_endpoint_settings_are_immutable_and_secret_safe() -> None:
    settings = Settings(
        model_base_url="https://primary.test/v1",
        model_api_key="primary-secret",
        model_name="primary-model",
        model_fallbacks=[
            {
                "base_url": "https://backup.test/v1",
                "api_key": "fallback-secret",
            }
        ],
    )

    primary, fallback = settings.resolved_model_endpoints()

    assert primary.api_key is not None
    assert primary.api_key.get_secret_value() == "primary-secret"
    assert fallback.api_key is not None
    assert fallback.api_key.get_secret_value() == "fallback-secret"
    assert "primary-secret" not in repr((primary, fallback))
    assert "fallback-secret" not in repr((primary, fallback))
    with pytest.raises(FrozenInstanceError):
        primary.model = "changed-model"


def test_legacy_fallback_inherits_primary_model_from_json_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "QUNXUE_MODEL_FALLBACKS",
        json.dumps(
            [
                {
                    "base_url": "https://backup.test/v1",
                    "api_key": "fallback-key",
                }
            ]
        ),
    )

    settings = Settings(
        _env_file=None,
        model_base_url="https://primary.test/v1",
        model_name="primary-model",
    )

    assert settings.resolved_model_endpoints()[1].model == "primary-model"
    assert "fallback-key" not in repr(settings)


def test_fallback_env_validation_hides_api_key_when_required_field_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "validation-test-secret-key"
    monkeypatch.setenv(
        "QUNXUE_MODEL_FALLBACKS",
        json.dumps([{"api_key": secret}]),
    )

    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=None)

    rendered = f"{caught.value!s}\n{caught.value!r}"
    if secret in rendered:
        pytest.fail("fallback validation error leaked an API key")


def test_fallback_env_validation_hides_credential_bearing_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credential_url = "https://validation-user:validation-pass@backup.test/v1"
    monkeypatch.setenv(
        "QUNXUE_MODEL_FALLBACKS",
        json.dumps(
            [
                {
                    "base_url": credential_url,
                    "api_key": "validation-test-secret-key",
                }
            ]
        ),
    )

    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=None)

    rendered = f"{caught.value!s}\n{caught.value!r}"
    if any(
        sensitive in rendered
        for sensitive in (credential_url, "validation-user", "validation-pass")
    ):
        pytest.fail("fallback validation error leaked URL credentials")


def test_fallback_env_validation_rejects_unknown_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "QUNXUE_MODEL_FALLBACKS",
        json.dumps(
            [
                {
                    "base_url": "https://backup.test/v1",
                    "api_key": "validation-test-secret-key",
                    "modle": "misspelled-model-field",
                }
            ]
        ),
    )

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    "fallback",
    [
        {
            "base_url": "https://user:password@backup.test/v1",
            "api_key": "fallback-key",
        },
        {
            "base_url": "https://backup.test/v1",
            "api_key": "fallback-key",
            "model": "   ",
        },
    ],
)
def test_fallback_settings_reject_credentials_and_empty_models(
    fallback: dict[str, str],
) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, model_fallbacks=[fallback])


@pytest.mark.parametrize(
    "settings_values",
    [
        {"model_base_url": "https://user:password@primary.test/v1"},
        {"model_name": "   "},
    ],
)
def test_primary_model_settings_reject_credentials_and_empty_model_names(
    settings_values: dict[str, str],
) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **settings_values)


def test_real_bootstrap_installs_one_business_router_for_all_endpoints(
    client: TestClient,
    tmp_path: Path,
) -> None:
    app = create_app(
        settings=Settings(
            _env_file=None,
            database_url=client.app.state.settings.database_url,
            runtime_mode="base",
            **_retrieval_settings(tmp_path),
            model_base_url="https://primary.test/v1",
            model_name="primary-model",
            model_fallbacks=[
                {
                    "base_url": "https://backup.test/v1",
                    "api_key": "fallback-key",
                    "model": "backup-model",
                }
            ],
        ),
        database=client.app.state.database,
    )

    assert app.state.model_router.endpoint_ids == ("primary", "fallback-1")
    assert isinstance(app.state.model_attempt_recorder, SqliteModelAttemptRecorder)
    assert app.state.model_gateway.descriptor.model_version == "primary-model"


def test_mock_bootstrap_does_not_install_a_routed_external_provider(
    client: TestClient,
) -> None:
    assert client.app.state.model_router is None
    assert client.app.state.model_gateway.descriptor.provider == "deterministic-mock"


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
        require_email_verification=False,
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
