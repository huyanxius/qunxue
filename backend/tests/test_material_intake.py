import base64
from io import BytesIO
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient


def _headers() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid4())}


def _register_and_create_task(client: TestClient) -> str:
    registered = client.post(
        "/api/session/register",
        headers=_headers(),
        json={"email": f"{uuid4()}@example.com", "password": "research-passphrase"},
    )
    assert registered.status_code == 201
    created = client.post(
        "/api/research-tasks",
        headers=_headers(),
        json={"entry_type": "material_input"},
    )
    assert created.status_code == 201
    return str(created.json()["task_id"])


def _consents() -> dict[str, object]:
    return {
        "deidentification_confirmed": True,
        "processing_rights_confirmed": True,
        "external_processing_acknowledged": True,
        "processing_policy_version": "2026-08-08",
    }


@pytest.mark.parametrize(
    "missing_field",
    [
        "deidentification_confirmed",
        "processing_rights_confirmed",
        "external_processing_acknowledged",
        "processing_policy_version",
    ],
)
def test_material_intake_rejects_each_missing_processing_confirmation(
    client: TestClient,
    missing_field: str,
) -> None:
    task_id = _register_and_create_task(client)
    payload = {
        "filename": "field-notes.txt",
        "media_type": "text/plain",
        "pasted_text": "第一段观察。\n\n第二段观察。\n\n第三段观察。",
        **_consents(),
    }
    payload.pop(missing_field)

    response = client.post(
        f"/api/research-tasks/{task_id}/material-intakes",
        headers=_headers(),
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_pasted_material_returns_traceable_candidates_and_restores_the_run(
    client: TestClient,
) -> None:
    task_id = _register_and_create_task(client)
    submitted = client.post(
        f"/api/research-tasks/{task_id}/material-intakes",
        headers=_headers(),
        json={
            "filename": "community-notes.txt",
            "media_type": "text/plain",
            "pasted_text": (
                "成员更替后，原先固定的互助小组逐渐停止活动。\n\n"
                "新成员更常在临时群聊中求助，但回应通常只持续一两天。\n\n"
                "社区组织了三次见面会，参与者仍很少继续保持联系。"
            ),
            **_consents(),
        },
    )

    assert submitted.status_code == 201
    run = submitted.json()
    assert run["status"] == "completed"
    assert 3 <= len(run["candidates"]) <= 5
    for candidate in run["candidates"]:
        assert candidate["evidence_refs"][0]["excerpt"]
        assert candidate["evidence_refs"][0]["locator"].startswith("第")
        assert candidate["missing_information"]
        assert candidate["source_traceability"] == "traceable"

    restored = client.get(f"/api/material-intake-runs/{run['run_id']}")
    assert restored.status_code == 200
    assert restored.json() == run


def test_docx_material_is_parsed_without_persisting_the_original_file(
    client: TestClient,
) -> None:
    task_id = _register_and_create_task(client)
    document = BytesIO()
    with ZipFile(document, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:body>
                <w:p><w:r><w:t>第一段访谈摘要。</w:t></w:r></w:p>
                <w:p><w:r><w:t>第二段访谈摘要。</w:t></w:r></w:p>
                <w:p><w:r><w:t>第三段访谈摘要。</w:t></w:r></w:p>
              </w:body>
            </w:document>""",
        )

    response = client.post(
        f"/api/research-tasks/{task_id}/material-intakes",
        headers=_headers(),
        json={
            "filename": "interview.docx",
            "media_type": (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            "content_base64": base64.b64encode(document.getvalue()).decode(),
            **_consents(),
        },
    )

    assert response.status_code == 201
    assert len(response.json()["candidates"]) == 3
