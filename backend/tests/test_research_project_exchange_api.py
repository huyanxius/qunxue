from io import BytesIO
from urllib.parse import unquote
from uuid import uuid4
from zipfile import ZipFile

from fastapi.testclient import TestClient

from qunxue_api.modules.research_exchange import (
    import_qdpx,
    open_research_project_archive,
    validate_qdpx,
)


def _register(client: TestClient, *, email: str | None = None) -> dict[str, object]:
    response = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "email": email or f"{uuid4()}@example.com",
            "password": "research-passphrase",
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_existing_research(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/research-tasks",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "entry_mode": "existing_research",
            "project_title": "社区照护田野研究",
            "project_stage": "材料整理",
            "method_orientation": "质性访谈",
        },
    )
    assert response.status_code == 201
    return response.json()


def _upload_text(client: TestClient, task_id: str) -> dict[str, object]:
    response = client.post(
        f"/api/research-tasks/{task_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "interview_transcript"},
        files={
            "file": (
                "访谈01.txt",
                "受访者说，照护不只发生在家庭内部。".encode(),
                "text/plain",
            )
        },
    )
    assert response.status_code == 201
    return response.json()


def test_existing_research_exports_valid_archive_with_stable_ids_and_audit(
    client: TestClient,
) -> None:
    session = _register(client)
    task = _create_existing_research(client)
    material = _upload_text(client, str(task["task_id"]))

    exported = client.post(
        f"/api/research-tasks/{task['task_id']}/exchange/archive",
        headers={"Idempotency-Key": str(uuid4())},
    )

    assert exported.status_code == 200
    assert exported.headers["content-type"] == "application/zip"
    assert exported.headers["x-qunxue-exchange-id"]
    assert len(exported.headers["x-qunxue-artifact-sha256"]) == 64
    assert int(exported.headers["x-qunxue-exchange-loss-count"]) >= 1
    assert "社区照护田野研究" in unquote(exported.headers["content-disposition"])

    opened = open_research_project_archive(exported.content)
    assert opened.valid is True
    assert validate_qdpx(opened.qdpx).valid is True
    assert opened.recovery_manifest["task"]["task_id"] == task["task_id"]
    assert opened.recovery_manifest["task"]["version"] == task["version"]
    assert opened.recovery_manifest["materials"]["records"][0]["material_id"] == (
        material["material_id"]
    )
    assert opened.recovery_manifest["extensions"]["research_cycle_versions"] == []
    imported = import_qdpx(opened.qdpx)
    assert imported.project.name == "社区照护田野研究"
    assert str(imported.project.sources[0].source_id) == material["material_id"]
    assert any(event["event_type"] == "project.exported" for event in opened.audit_events)

    audit = client.get(f"/api/research-tasks/{task['task_id']}/exchange/audit")
    assert audit.status_code == 200
    event = audit.json()["items"][-1]
    assert event["event_type"] == "project.exported"
    assert event["actor_id"] == session["user"]["user_id"]
    assert event["object_id"] == task["task_id"]
    assert event["object_version"] == str(task["version"])

    with ZipFile(BytesIO(exported.content)) as archive:
        assert "data/reports/exchange-loss.json" in archive.namelist()
        assert "data/project.json" in archive.namelist()
        assert archive.read(f"data/materials/{material['material_id']}/original") == (
            "受访者说，照护不只发生在家庭内部。".encode()
        )


def test_exchange_routes_hide_another_users_research(client: TestClient) -> None:
    _register(client, email=f"first-{uuid4()}@example.com")
    task = _create_existing_research(client)
    _upload_text(client, str(task["task_id"]))
    client.post("/api/session/logout", headers={"Idempotency-Key": str(uuid4())})
    _register(client, email=f"second-{uuid4()}@example.com")

    assert client.get(f"/api/research-tasks/{task['task_id']}/exchange/audit").status_code == 404
    assert (
        client.post(
            f"/api/research-tasks/{task['task_id']}/exchange/archive",
            headers={"Idempotency-Key": str(uuid4())},
        ).status_code
        == 404
    )


def test_qdpx_import_is_an_audited_preview_without_mutating_the_project(
    client: TestClient,
) -> None:
    _register(client)
    task = _create_existing_research(client)
    _upload_text(client, str(task["task_id"]))
    exported = client.post(
        f"/api/research-tasks/{task['task_id']}/exchange/archive",
        headers={"Idempotency-Key": str(uuid4())},
    )
    qdpx = open_research_project_archive(exported.content).qdpx

    preview = client.post(
        f"/api/research-tasks/{task['task_id']}/exchange/qdpx-preview",
        headers={"Idempotency-Key": str(uuid4())},
        files={"file": ("community-care.qdpx", qdpx, "application/vnd.qdpx")},
    )

    assert preview.status_code == 200
    body = preview.json()
    assert body["valid"] is True
    assert body["validation_scope"] == "official-xsd"
    assert body["project"]["name"] == "社区照护田野研究"
    assert body["project"]["source_count"] == 1
    assert body["restored"] is False
    task_after = client.get(f"/api/research-tasks/{task['task_id']}").json()
    assert task_after["version"] == task["version"]
    audit = client.get(f"/api/research-tasks/{task['task_id']}/exchange/audit").json()
    assert audit["items"][-1]["event_type"] == "project.import_previewed"


def test_invalid_qdpx_preview_reports_validation_without_restoring(client: TestClient) -> None:
    _register(client)
    task = _create_existing_research(client)

    preview = client.post(
        f"/api/research-tasks/{task['task_id']}/exchange/qdpx-preview",
        headers={"Idempotency-Key": str(uuid4())},
        files={"file": ("broken.qdpx", b"not-a-zip", "application/vnd.qdpx")},
    )

    assert preview.status_code == 422
    assert preview.json()["error"]["code"] == "validation_error"


def test_exchange_contract_uses_stable_operations_and_shared_422_error(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    operations = (
        paths["/api/research-tasks/{task_id}/exchange/archive"]["post"],
        paths["/api/research-tasks/{task_id}/exchange/audit"]["get"],
        paths["/api/research-tasks/{task_id}/exchange/qdpx-preview"]["post"],
    )

    assert [operation["operationId"] for operation in operations] == [
        "export_research_project_archive",
        "list_research_project_audit_events",
        "preview_research_project_qdpx_import",
    ]
    for operation in operations:
        assert operation["responses"]["422"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorResponse"
        }
