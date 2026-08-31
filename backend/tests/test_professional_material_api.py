from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

from fastapi.testclient import TestClient

from qunxue_api.modules.research_materials import DoiMetadataUnavailable


def _authenticate(client: TestClient) -> None:
    response = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": f"{uuid4()}@example.com", "password": "research-passphrase"},
    )
    assert response.status_code == 201


def _task(client: TestClient) -> str:
    response = client.post(
        "/api/research-tasks",
        headers={"Idempotency-Key": str(uuid4())},
        json={"entry_type": "direct_input"},
    )
    assert response.status_code == 201
    return response.json()["task_id"]


def _upload(client: TestClient, task_id: str, filename: str = "访谈.txt") -> dict[str, object]:
    response = client.post(
        f"/api/research-tasks/{task_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "interview_transcript"},
        files={"file": (filename, "受访者谈到迁移后的照护。".encode(), "text/plain")},
    )
    assert response.status_code == 201
    return response.json()


def test_upload_creates_restricted_archive_profile_then_explicit_policy_unlocks_agent_use(
    client: TestClient,
) -> None:
    _authenticate(client)
    task_id = _task(client)
    material = _upload(client, task_id)

    archive = client.get(f"/api/research-tasks/{task_id}/material-archive")

    assert archive.status_code == 200
    profile = archive.json()["profiles"][0]
    assert profile["material_id"] == material["material_id"]
    assert profile["model_processing_scope"] == "not_assessed"
    assert archive.json()["inventory"]["restricted_material_ids"] == [material["material_id"]]

    updated = client.patch(
        f"/api/research-tasks/{task_id}/material-archive/materials/{material['material_id']}",
        json={
            "research_role": "empirical_material",
            "specific_type": "interview_transcript",
            "stage": "collection",
            "batch_id": None,
            "tags": ["迁移", "照护"],
            "collection_ids": [],
            "sensitivity": "sensitive",
            "consent_scope": "project_only",
            "deidentification_status": "complete",
            "model_processing_scope": "external_allowed",
        },
    )

    assert updated.status_code == 200
    assert updated.json()["allows_external_model_processing"] is True
    refreshed = client.get(f"/api/research-tasks/{task_id}/material-archive").json()
    assert refreshed["inventory"]["restricted_material_ids"] == []


def test_archive_keeps_many_to_many_cases_collections_and_literature_duplicates_reviewable(
    client: TestClient,
) -> None:
    _authenticate(client)
    task_id = _task(client)
    first = _upload(client, task_id, "访谈一.txt")
    second = _upload(client, task_id, "访谈二.txt")
    root = f"/api/research-tasks/{task_id}/material-archive"
    collection = client.post(
        f"{root}/collections", json={"name": "照护", "description": "相关经验材料"}
    )
    assert collection.status_code == 201
    collection_id = collection.json()["collection_id"]
    case = client.post(
        f"{root}/cases",
        json={
            "name": "家庭 A", "attributes": {"迁移阶段": "两年内"},
            "material_ids": [first["material_id"], second["material_id"]],
        },
    )
    assert case.status_code == 201
    relation = client.post(
        f"{root}/relations",
        json={
            "source_material_id": second["material_id"],
            "target_material_id": first["material_id"],
            "relation_type": "supplements", "note": "后续访谈",
        },
    )
    assert relation.status_code == 201
    for title in ("Care after Migration", "Imported title differs"):
        response = client.post(
            f"{root}/literature",
            json={
                "item_type": "article-journal", "title": title, "doi": "10.1234/ABC.1",
                "csl_data": {}, "attachment_material_ids": [first["material_id"]],
                "collection_ids": [collection_id],
            },
        )
        assert response.status_code == 201

    snapshot = client.get(root).json()
    assert snapshot["cases"][0]["material_ids"] == [first["material_id"], second["material_id"]]
    assert len(snapshot["literature"]) == 2
    assert snapshot["duplicate_hints"][0]["reasons"] == ["same_doi"]
    assert len(snapshot["inventory"]["suspected_duplicate_literature_ids"]) == 2


def test_batch_upload_is_partial_success_and_literature_exchange_round_trips(
    client: TestClient,
) -> None:
    _authenticate(client)
    task_id = _task(client)
    root = f"/api/research-tasks/{task_id}/material-archive"
    batch = client.post(f"{root}/batches", json={"name": "春季田野"})
    assert batch.status_code == 201
    batch_id = batch.json()["batch_id"]

    uploaded = client.post(
        f"{root}/batches/{batch_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "field_note"},
        files=[
            ("files", ("田野.txt", "真实田野记录".encode(), "text/plain")),
            ("files", ("图片.png", b"not-an-image", "image/png")),
        ],
    )
    assert uploaded.status_code == 207
    assert [item["status"] for item in uploaded.json()["items"]] == ["created", "failed"]
    assert len(client.get(f"/api/research-tasks/{task_id}/materials").json()["items"]) == 1

    imported = client.post(
        f"{root}/literature/import",
        data={"exchange_format": "ris"},
        files={
            "file": (
                "references.ris",
                b"TY  - JOUR\nTI  - Care after Migration\n"
                b"DO  - 10.1234/abc.1\nER  -\n",
                "application/x-research-info-systems",
            )
        },
    )
    assert imported.status_code == 201
    exported = client.get(f"{root}/literature/export?exchange_format=csl_json")
    assert exported.status_code == 200
    assert exported.json()[0]["DOI"] == "10.1234/abc.1"


def test_doi_upstream_failure_returns_stable_service_unavailable(client: TestClient) -> None:
    _authenticate(client)
    task_id = _task(client)

    class _UnavailableDoiApplication:
        def resolve_doi(self, **_kwargs):
            raise DoiMetadataUnavailable("Crossref metadata service is unavailable")

    @contextmanager
    def unavailable_scope() -> Iterator[_UnavailableDoiApplication]:
        yield _UnavailableDoiApplication()

    original_scope = client.app.state.professional_materials_application_scope
    client.app.state.professional_materials_application_scope = unavailable_scope
    try:
        response = client.get(
            f"/api/research-tasks/{task_id}/material-archive/doi",
            params={"doi": "10.1234/abc.1"},
        )
    finally:
        client.app.state.professional_materials_application_scope = original_scope

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "doi_metadata_unavailable"
