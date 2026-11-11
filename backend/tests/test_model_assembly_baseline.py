from contextlib import closing

import httpx
import pytest
from billing_test_support import configure_synthetic_billing
from fastapi.testclient import TestClient
from openai import AsyncOpenAI
from pydantic import SecretStr
from test_agent_memory import register, save, seed_learning_source
from test_memory_overview import overview
from test_shared_knowledge_api import create_library, upload

from qunxue_api.adapters.research_agent import course_knowledge, memory_extractor, memory_overview
from qunxue_api.bootstrap import create_app

pytestmark = pytest.mark.xfail(
    strict=True, raises=AssertionError, reason="AS-04: configured operation cannot reach transport",
)


@pytest.fixture
def assembled_model_app(plain_client, monkeypatch):
    requests: list[httpx.Request] = []

    def record_request(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        # The assertion concerns dispatch. No provider output needs to be persisted.
        return httpx.Response(503, json={"error": {"message": "offline test response"}})

    def model_client(**options) -> AsyncOpenAI:
        return AsyncOpenAI(
            **options,
            http_client=httpx.AsyncClient(
                transport=httpx.MockTransport(record_request), trust_env=False,
            ),
        )

    for adapter in (course_knowledge, memory_extractor, memory_overview):
        monkeypatch.setattr(adapter, "AsyncOpenAI", model_client)
    settings = plain_client.app.state.settings.model_copy(update={
        "runtime_mode": "base",
        "model_base_url": "https://model.example.invalid/v1",
        "model_api_key": SecretStr("test-key"),
        "model_name": "test-model",
        "model_fallbacks": [],
        "memory_learning_enabled": True,
    })
    app = create_app(
        settings=settings,
        database=plain_client.app.state.database,
        require_email_verification=False,
    )
    # Workers are ticked explicitly so the ASGI lifespan cannot race the assertion.
    with closing(TestClient(app)) as client:
        yield client, requests


def test_bootstrap_memory_overview_reaches_model_transport(assembled_model_app):
    client, requests = assembled_model_app
    configure_synthetic_billing(client.app, phase="memory_overview")
    register(client)
    assert save(client, content="合成偏好：先概括材料。").status_code == 201

    result = overview(client)

    assert len(requests) == 1, result.text


def test_bootstrap_memory_learning_reaches_model_transport(assembled_model_app):
    client, requests = assembled_model_app
    configure_synthetic_billing(client.app, phase="memory_learning")
    user_id = register(client)
    seed_learning_source(client, user_id, content="合成偏好：先概括材料。")

    assert client.app.state.memory_worker.run_once()
    assert len(requests) == 1


def test_bootstrap_course_knowledge_reaches_model_transport(assembled_model_app):
    client, requests = assembled_model_app
    configure_synthetic_billing(client.app, phase="course_knowledge")
    register(client)
    library = create_library(client)
    upload(client, library["id"], text="合成课程资料：访谈题目以开放式问题为主。")

    assert client.app.state.course_organization_worker.run_once()
    assert len(requests) == 1
