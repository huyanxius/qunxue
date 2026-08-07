from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qunxue_api.adapters.model import ModelInvocationError


def test_bootstrap_is_the_only_composition_point_for_the_model_gateway(
    client: TestClient,
) -> None:
    descriptor = client.app.state.model_gateway.descriptor

    assert descriptor.provider == "deterministic-mock"
    assert descriptor.model_version == "mock-sociology-v1"
    assert descriptor.capability_tier == "mock"
    assert descriptor.demonstration is True
    assert client.app.state.builtin_case_catalog.get("success").case_id == "success"


def test_health_reports_the_actual_model_capability_and_demo_release(
    client: TestClient,
) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["capability"] == "mock"
    assert response.json()["knowledge_release_id"] == "knowledge-demo-v1"


def test_builtin_cases_are_served_from_the_backend_with_opaque_pagination(
    client: TestClient,
) -> None:
    first = client.get("/api/knowledge/cases", params={"limit": 3})

    assert first.status_code == 200
    assert first.json()["knowledge_release_id"] == "knowledge-demo-v1"
    assert [case["case_id"] for case in first.json()["cases"]] == [
        "success",
        "no-reliable-candidate",
        "timeout",
    ]
    cursor = first.json()["next_cursor"]
    assert cursor and "case" not in cursor

    second = client.get(
        "/api/knowledge/cases",
        params={"limit": 3, "cursor": cursor},
    )
    assert second.status_code == 200
    assert [case["case_id"] for case in second.json()["cases"]] == [
        "insufficient-sources",
        "user-deferred",
    ]
    assert second.json()["next_cursor"] is None
    assert all(
        case["content_status"] == "demonstration"
        for case in (*first.json()["cases"], *second.json()["cases"])
    )


def test_invalid_builtin_case_cursor_uses_the_stable_error_envelope(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/knowledge/cases",
        params={"cursor": "not-a-valid-cursor"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["trace_id"]


@pytest.mark.parametrize(
    ("code", "expected_status"),
    [
        ("model_timeout", 503),
        ("no_reliable_candidate", 409),
        ("insufficient_sources", 409),
    ],
)
def test_model_failures_use_recoverable_http_errors_instead_of_500(
    client: TestClient,
    code: str,
    expected_status: int,
) -> None:
    trace_id = UUID(int=901)

    def fail() -> None:
        raise ModelInvocationError(
            code=code,
            message="Recoverable model invocation failure.",
            trace_id=trace_id,
            request_id=UUID(int=902),
            provider="deterministic-mock",
        )

    app = client.app
    assert isinstance(app, FastAPI)
    path = f"/_test/model-failure/{code}"
    app.add_api_route(path, fail, methods=["GET"])

    response = client.get(path)

    assert response.status_code == expected_status
    assert response.json() == {
        "error": {
            "code": code,
            "message": "Recoverable model invocation failure.",
            "trace_id": str(trace_id),
        }
    }
