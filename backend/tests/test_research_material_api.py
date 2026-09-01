from io import BytesIO
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi.testclient import TestClient

from qunxue_api.adapters.sqlite.research_material_repository import (
    SqliteResearchMaterialRepository,
)
from qunxue_api.api.routes.research_materials import (
    MAX_DOCUMENT_BYTES,
    MAX_MEDIA_BYTES,
    _upload_limit,
)
from qunxue_api.modules.research_materials import MaterialVersionConflict


def test_media_uploads_use_a_larger_bounded_limit() -> None:
    assert _upload_limit(filename="访谈.wav", media_type="audio/wav") == MAX_MEDIA_BYTES
    assert _upload_limit(filename="访谈.pdf", media_type="application/pdf") == MAX_DOCUMENT_BYTES


def _authenticate(client: TestClient, *, email: str | None = None) -> dict[str, object]:
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


def _task(client: TestClient) -> str:
    response = client.post(
        "/api/research-tasks",
        headers={"Idempotency-Key": str(uuid4())},
        json={"entry_type": "direct_input"},
    )
    assert response.status_code == 201
    return response.json()["task_id"]


def _docx_bytes() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:body>
                <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>访谈主题</w:t></w:r></w:p>
                <w:p><w:r><w:t>受访者描述了迁移后的照护变化。</w:t></w:r></w:p>
              </w:body>
            </w:document>""",
        )
    return output.getvalue()


def _upload(client: TestClient, task_id: str, *, filename: str = "访谈.txt"):
    media_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if filename.endswith(".docx")
        else "text/plain"
    )
    content = (
        _docx_bytes() if filename.endswith(".docx") else "第一段访谈。\n\n第二段访谈。".encode()
    )
    return client.post(
        f"/api/research-tasks/{task_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "interview_transcript"},
        files={"file": (filename, content, media_type)},
    )


def test_upload_lists_and_reads_exact_segment(client: TestClient) -> None:
    _authenticate(client)
    task_id = _task(client)

    uploaded = _upload(client, task_id, filename="访谈.docx")

    assert uploaded.status_code == 201
    material = uploaded.json()
    assert material["status"] == "ready"
    assert material["material_kind"] == "interview_transcript"
    assert material["parse_version"] == 1
    assert material["segment_count"] == 2

    listing = client.get(f"/api/research-tasks/{task_id}/materials")
    assert listing.status_code == 200
    assert [item["material_id"] for item in listing.json()["items"]] == [material["material_id"]]

    detail = client.get(f"/api/research-tasks/{task_id}/materials/{material['material_id']}")
    assert detail.status_code == 200
    paragraph = detail.json()["segments"][1]
    assert paragraph["text"] == "受访者描述了迁移后的照护变化。"
    assert paragraph["locator"]["section_path"] == ["访谈主题"]
    assert paragraph["locator"]["page"] is None

    segment = client.get(
        f"/api/research-tasks/{task_id}/materials/{material['material_id']}"
        f"/segments/{paragraph['segment_id']}"
    )
    assert segment.status_code == 200
    assert segment.json() == paragraph


def test_material_routes_hide_other_users_tasks(client: TestClient) -> None:
    first = _authenticate(client, email=f"first-{uuid4()}@example.com")
    first_task = _task(client)
    material = _upload(client, first_task).json()
    client.post("/api/session/logout", headers={"Idempotency-Key": str(uuid4())})
    _authenticate(client, email=f"second-{uuid4()}@example.com")

    assert first["user"]["user_id"]
    assert client.get(f"/api/research-tasks/{first_task}/materials").status_code == 404
    assert (
        client.get(
            f"/api/research-tasks/{first_task}/materials/{material['material_id']}"
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/research-tasks/{first_task}/materials/{material['material_id']}/reparse",
            headers={"Idempotency-Key": str(uuid4())},
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/research-tasks/{first_task}/materials/{material['material_id']}",
            headers={"Idempotency-Key": str(uuid4())},
        ).status_code
        == 404
    )


def test_images_mismatches_and_no_text_pdf_return_stable_errors(client: TestClient) -> None:
    _authenticate(client)
    task_id = _task(client)

    image = client.post(
        f"/api/research-tasks/{task_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "other"},
        files={"file": ("现场.png", b"image", "image/png")},
    )
    assert image.status_code == 422
    assert image.json()["error"]["code"] == "unsupported_material_format"

    mismatch = client.post(
        f"/api/research-tasks/{task_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "paper"},
        files={
            "file": (
                "论文.pdf",
                b"not a docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "unsupported_material_format"

    no_text = client.post(
        f"/api/research-tasks/{task_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "paper"},
        files={"file": ("scan.pdf", b"not a pdf", "application/pdf")},
    )
    assert no_text.status_code == 422
    assert no_text.json()["error"]["code"] == "no_extractable_text"


def test_reparse_and_delete_invalidate_material_content(client: TestClient) -> None:
    _authenticate(client)
    task_id = _task(client)
    material = _upload(client, task_id).json()

    reparsed = client.post(
        f"/api/research-tasks/{task_id}/materials/{material['material_id']}/reparse",
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert reparsed.status_code == 200
    assert reparsed.json()["parse_version"] == 2

    deleted = client.delete(
        f"/api/research-tasks/{task_id}/materials/{material['material_id']}",
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert deleted.status_code == 204
    assert (
        client.get(f"/api/research-tasks/{task_id}/materials/{material['material_id']}").status_code
        == 404
    )
    assert client.get(f"/api/research-tasks/{task_id}/materials").json()["items"] == []


def test_reparse_replays_the_same_idempotency_key_without_a_new_parse(
    client: TestClient,
) -> None:
    _authenticate(client)
    task_id = _task(client)
    material = _upload(client, task_id).json()
    reparse_key = str(uuid4())

    first = client.post(
        f"/api/research-tasks/{task_id}/materials/{material['material_id']}/reparse",
        headers={"Idempotency-Key": reparse_key},
    )
    replay = client.post(
        f"/api/research-tasks/{task_id}/materials/{material['material_id']}/reparse",
        headers={"Idempotency-Key": reparse_key},
    )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert first.json()["parse_id"] == replay.json()["parse_id"]
    assert first.json()["parse_version"] == replay.json()["parse_version"] == 2


def test_reparse_rejects_an_idempotency_key_reused_for_another_material(
    client: TestClient,
) -> None:
    _authenticate(client)
    task_id = _task(client)
    first = _upload(client, task_id, filename="first.txt").json()
    second = _upload(client, task_id, filename="second.txt").json()
    reparse_key = str(uuid4())

    first_result = client.post(
        f"/api/research-tasks/{task_id}/materials/{first['material_id']}/reparse",
        headers={"Idempotency-Key": reparse_key},
    )
    conflict = client.post(
        f"/api/research-tasks/{task_id}/materials/{second['material_id']}/reparse",
        headers={"Idempotency-Key": reparse_key},
    )

    assert first_result.status_code == 200
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "research_material_idempotency_conflict"
    second_detail = client.get(
        f"/api/research-tasks/{task_id}/materials/{second['material_id']}"
    )
    assert second_detail.status_code == 200
    assert second_detail.json()["parse_version"] == 1


def test_delete_replays_only_the_same_material_idempotently(client: TestClient) -> None:
    _authenticate(client)
    task_id = _task(client)
    first = _upload(client, task_id, filename="first.txt").json()
    second = _upload(client, task_id, filename="second.txt").json()
    delete_key = str(uuid4())

    first_delete = client.delete(
        f"/api/research-tasks/{task_id}/materials/{first['material_id']}",
        headers={"Idempotency-Key": delete_key},
    )
    replay = client.delete(
        f"/api/research-tasks/{task_id}/materials/{first['material_id']}",
        headers={"Idempotency-Key": delete_key},
    )
    reused_for_another_material = client.delete(
        f"/api/research-tasks/{task_id}/materials/{second['material_id']}",
        headers={"Idempotency-Key": delete_key},
    )
    new_request_for_deleted_material = client.delete(
        f"/api/research-tasks/{task_id}/materials/{first['material_id']}",
        headers={"Idempotency-Key": str(uuid4())},
    )

    assert first_delete.status_code == 204
    assert replay.status_code == 204
    assert reused_for_another_material.status_code == 409
    assert (
        reused_for_another_material.json()["error"]["code"]
        == "research_material_idempotency_conflict"
    )
    assert new_request_for_deleted_material.status_code == 404
    assert client.get(
        f"/api/research-tasks/{task_id}/materials/{second['material_id']}"
    ).status_code == 200


def test_segment_route_can_open_a_persisted_historical_parse(client: TestClient) -> None:
    _authenticate(client)
    task_id = _task(client)
    uploaded = _upload(client, task_id, filename="访谈.txt")
    assert uploaded.status_code == 201
    first = uploaded.json()
    first_segment = client.get(
        f"/api/research-tasks/{task_id}/materials/{first['material_id']}"
    ).json()["segments"][0]

    reparsed = client.post(
        f"/api/research-tasks/{task_id}/materials/{first['material_id']}/reparse",
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert reparsed.status_code == 200
    assert reparsed.json()["parse_version"] == 2

    historical = client.get(
        f"/api/research-tasks/{task_id}/materials/{first['material_id']}"
        f"/segments/{first_segment['segment_id']}?parse_id={first_segment['parse_id']}"
    )

    assert historical.status_code == 200
    assert historical.json()["parse_id"] == first_segment["parse_id"]
    assert historical.json()["text"] == first_segment["text"]


def test_reparsed_material_can_resolve_a_historical_segment_by_parse_id(
    client: TestClient,
) -> None:
    _authenticate(client)
    task_id = _task(client)
    material = _upload(client, task_id).json()
    first_segment = client.get(
        f"/api/research-tasks/{task_id}/materials/{material['material_id']}"
    ).json()["segments"][0]

    reparsed = client.post(
        f"/api/research-tasks/{task_id}/materials/{material['material_id']}/reparse",
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert reparsed.status_code == 200
    current_detail = client.get(
        f"/api/research-tasks/{task_id}/materials/{material['material_id']}"
    ).json()
    assert current_detail["segments"][0]["parse_id"] != first_segment["parse_id"]

    historical = client.get(
        f"/api/research-tasks/{task_id}/materials/{material['material_id']}"
        f"/segments/{first_segment['segment_id']}",
        params={"parse_id": first_segment["parse_id"]},
    )

    assert historical.status_code == 200
    assert historical.json() == first_segment


def test_material_detail_reports_the_requested_parse_metadata(client: TestClient) -> None:
    _authenticate(client)
    task_id = _task(client)
    uploaded = _upload(client, task_id).json()
    first_detail = client.get(
        f"/api/research-tasks/{task_id}/materials/{uploaded['material_id']}"
    ).json()
    first_parse_id = first_detail["segments"][0]["parse_id"]

    reparsed = client.post(
        f"/api/research-tasks/{task_id}/materials/{uploaded['material_id']}/reparse",
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert reparsed.status_code == 200

    current = client.get(
        f"/api/research-tasks/{task_id}/materials/{uploaded['material_id']}"
    ).json()
    historical = client.get(
        f"/api/research-tasks/{task_id}/materials/{uploaded['material_id']}",
        params={"parse_id": first_parse_id},
    ).json()

    assert current["parse_id"] != first_parse_id
    assert current["parse_version"] == 2
    assert current["is_current_parse"] is True
    assert historical["parse_id"] == first_parse_id
    assert historical["parse_version"] == 1
    assert historical["is_current_parse"] is False
    assert {segment["parse_id"] for segment in historical["segments"]} == {
        first_parse_id
    }


def test_material_contract_has_stable_operation_ids_and_delete_204(client: TestClient) -> None:
    schema = client.app.openapi()
    paths = schema["paths"]
    assert (
        paths["/api/research-tasks/{task_id}/materials"]["post"]["operationId"]
        == "upload_research_material"
    )
    assert (
        paths["/api/research-tasks/{task_id}/materials"]["get"]["operationId"]
        == "list_research_materials"
    )
    assert (
        paths["/api/research-tasks/{task_id}/materials/{material_id}"]["get"]["operationId"]
        == "get_research_material"
    )
    assert (
        paths["/api/research-tasks/{task_id}/materials/{material_id}/segments/{segment_id}"]["get"][
            "operationId"
        ]
        == "get_research_material_segment"
    )
    assert (
        paths["/api/research-tasks/{task_id}/materials/{material_id}/reparse"]["post"][
            "operationId"
        ]
        == "reparse_research_material"
    )
    assert (
        paths["/api/research-tasks/{task_id}/materials/{material_id}"]["delete"]["operationId"]
        == "delete_research_material"
    )
    assert (
        "204"
        in paths["/api/research-tasks/{task_id}/materials/{material_id}"]["delete"]["responses"]
    )


def test_material_upload_accepts_generic_or_missing_text_mime_by_extension(
    client: TestClient,
) -> None:
    _authenticate(client)
    task_id = _task(client)
    content = "# 田野记录\n\n参与者在临时群聊中求助。".encode()

    for index, media_type in enumerate((None, "", "application/octet-stream", "text/plain")):
        response = client.post(
            f"/api/research-tasks/{task_id}/materials",
            headers={"Idempotency-Key": str(uuid4())},
            data={"material_kind": "observation"},
            files={"file": (f"notes-{index}.md", content, media_type)},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["material_format"] == "markdown"
        assert body["material_kind"] == "observation_record"


def test_material_upload_rejects_explicit_mime_extension_conflicts(client: TestClient) -> None:
    _authenticate(client)
    task_id = _task(client)

    response = client.post(
        f"/api/research-tasks/{task_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "paper"},
        files={"file": ("paper.pdf", b"plain text", "text/plain")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unsupported_material_format"


def test_empty_material_returns_stable_no_text_error(client: TestClient) -> None:
    _authenticate(client)
    task_id = _task(client)

    response = client.post(
        f"/api/research-tasks/{task_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "field_note"},
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "no_extractable_text"


def test_delete_preflight_allows_cors_delete_method(client: TestClient) -> None:
    response = client.options(
        "/api/research-tasks/test/materials/test",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "Idempotency-Key",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-methods"]
    assert "DELETE" in response.headers["access-control-allow-methods"]


def test_material_upload_normalizes_legacy_kind_and_generic_text_mime(client: TestClient) -> None:
    _authenticate(client)
    task_id = _task(client)

    response = client.post(
        f"/api/research-tasks/{task_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "observation"},
        files={"file": ("观察.md", "# 现场\n\n参与者停留。".encode(), "text/plain")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["material_kind"] == "observation_record"
    assert body["material_format"] == "markdown"
    assert body["media_type"] == "text/markdown"


def test_material_upload_uses_filename_when_mime_is_missing_or_octet_stream(
    client: TestClient,
) -> None:
    _authenticate(client)
    task_id = _task(client)

    for filename, content_type in (
        ("记录.txt", None),
        ("记录.markdown", "application/octet-stream"),
    ):
        response = client.post(
            f"/api/research-tasks/{task_id}/materials",
            headers={"Idempotency-Key": str(uuid4())},
            data={"material_kind": "field_note"},
            files={"file": (filename, "一段可读记录。".encode(), content_type)},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["material_format"] == ("txt" if filename.endswith(".txt") else "markdown")


def test_upload_maps_an_active_parse_conflict_to_stable_409(
    client: TestClient,
    monkeypatch,
) -> None:
    """A visible parse race must remain a retryable API conflict, not a 500."""

    _authenticate(client)
    task_id = _task(client)

    def raise_active_parse_conflict(self, *args, **kwargs):
        del self, args, kwargs
        raise MaterialVersionConflict("another parse attempt is already active")

    monkeypatch.setattr(
        SqliteResearchMaterialRepository,
        "begin_reparse",
        raise_active_parse_conflict,
    )

    response = client.post(
        f"/api/research-tasks/{task_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "interview_transcript"},
        files={"file": ("访谈.txt", "并发上传。".encode(), "text/plain")},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "research_material_version_conflict"
