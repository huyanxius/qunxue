from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from qunxue_api.modules.research_materials import MaterialParseError


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


def test_deferred_upload_persists_job_and_can_resume_after_request(client: TestClient) -> None:
    _authenticate(client)
    task_id = _task(client)
    scheduled: list[UUID] = []
    client.app.state.schedule_research_material_ingestion = scheduled.append

    uploaded = client.post(
        f"/api/research-tasks/{task_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "field_note", "defer_processing": "true"},
        files={"file": ("田野笔记.txt", "照护安排发生变化。".encode(), "text/plain")},
    )

    assert uploaded.status_code == 201
    body = uploaded.json()
    assert body["ingestion_status"] == "queued"
    assert body["ingestion_job_id"] == str(scheduled[0])
    status = client.get(
        f"/api/research-tasks/{task_id}/materials/{body['material_id']}/ingestion"
    )
    assert status.status_code == 200
    assert status.json()["attempt_count"] == 0

    with client.app.state.research_material_application_scope() as application:
        application.process_ingestion(scheduled[0])

    completed = client.get(
        f"/api/research-tasks/{task_id}/materials/{body['material_id']}/ingestion"
    )
    assert completed.json()["ingestion_status"] == "ready"
    assert completed.json()["attempt_count"] == 1


def test_stale_processing_job_is_recoverable(client: TestClient) -> None:
    _authenticate(client)
    task_id = _task(client)
    client.app.state.schedule_research_material_ingestion = lambda _job_id: None
    uploaded = client.post(
        f"/api/research-tasks/{task_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "paper", "defer_processing": "true"},
        files={"file": ("论文.txt", b"recoverable", "text/plain")},
    ).json()
    job_id = UUID(uploaded["ingestion_job_id"])

    with client.app.state.research_material_application_scope() as application:
        job = application.claim_ingestion(
            job_id,
            lease_duration=timedelta(seconds=-1),
            now=datetime.now(UTC),
        )
        assert job is not None
        assert job.ingestion_status.value == "processing"
        assert job_id in application.recoverable_ingestion_ids(now=datetime.now(UTC))


def test_deferred_upload_idempotency_reuses_one_material_and_job(client: TestClient) -> None:
    _authenticate(client)
    task_id = _task(client)
    scheduled: list[UUID] = []
    client.app.state.schedule_research_material_ingestion = scheduled.append
    request_key = str(uuid4())
    payload = {
        "headers": {"Idempotency-Key": request_key},
        "data": {"material_kind": "field_note", "defer_processing": "true"},
        "files": {"file": ("笔记.txt", b"same material", "text/plain")},
    }

    first = client.post(f"/api/research-tasks/{task_id}/materials", **payload)
    second = client.post(f"/api/research-tasks/{task_id}/materials", **payload)

    assert first.status_code == second.status_code == 201
    assert first.json()["material_id"] == second.json()["material_id"]
    assert first.json()["ingestion_job_id"] == second.json()["ingestion_job_id"]
    assert scheduled == [UUID(first.json()["ingestion_job_id"])] * 2


def test_scanned_pdf_records_ocr_required_instead_of_ready(client: TestClient) -> None:
    _authenticate(client)
    task_id = _task(client)
    scheduled: list[UUID] = []
    client.app.state.schedule_research_material_ingestion = scheduled.append
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(output)
    uploaded = client.post(
        f"/api/research-tasks/{task_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "paper", "defer_processing": "true"},
        files={"file": ("扫描件.pdf", output.getvalue(), "application/pdf")},
    ).json()

    with (
        client.app.state.research_material_application_scope() as application,
        pytest.raises(MaterialParseError, match="ocr_required"),
    ):
        application.process_ingestion(scheduled[0])

    status = client.get(
        f"/api/research-tasks/{task_id}/materials/{uploaded['material_id']}/ingestion"
    ).json()
    assert status["ingestion_status"] == "failed"
    assert status["unavailable_reason"] == "ocr_required"


def test_untranscribed_media_reports_provider_boundary(client: TestClient) -> None:
    _authenticate(client)
    task_id = _task(client)
    uploaded = client.post(
        f"/api/research-tasks/{task_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "interview_transcript"},
        files={"file": ("访谈.wav", b"RIFF-test", "audio/wav")},
    )

    assert uploaded.status_code == 201
    assert uploaded.json()["ingestion_status"] == "failed"
    assert uploaded.json()["unavailable_reason"] == "transcription_unavailable"


def test_retry_uses_a_new_parse_id_after_an_unexpected_worker_failure(
    client: TestClient,
) -> None:
    _authenticate(client)
    task_id = _task(client)
    scheduled: list[UUID] = []
    client.app.state.schedule_research_material_ingestion = scheduled.append
    client.post(
        f"/api/research-tasks/{task_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "field_note", "defer_processing": "true"},
        files={"file": ("笔记.txt", b"retry succeeds", "text/plain")},
    ).json()

    with client.app.state.research_material_application_scope() as application:
        original_parser = application._parser
        failed_at = datetime(2026, 9, 5, tzinfo=UTC)
        application._clock = lambda: failed_at
        application._parser = lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
        with pytest.raises(RuntimeError, match="boom"):
            application.process_ingestion(scheduled[0])
        failed = application._materials.get_ingestion(scheduled[0])
        assert failed is not None
        first_parse_id = failed.parse_id
        assert failed.ingestion_status.value == "failed"
        assert failed.completed_at is None

        application._clock = lambda: failed.available_at + timedelta(seconds=1)
        application._parser = original_parser
        completed = application.process_ingestion(scheduled[0])

    assert completed is not None
    assert completed.ingestion_status.value == "ready"
    assert completed.attempt_count == 2
    assert completed.parse_id != first_parse_id


def test_expired_worker_cannot_complete_a_newer_ingestion_attempt(client: TestClient) -> None:
    _authenticate(client)
    task_id = _task(client)
    scheduled: list[UUID] = []
    client.app.state.schedule_research_material_ingestion = scheduled.append
    client.post(
        f"/api/research-tasks/{task_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "field_note", "defer_processing": "true"},
        files={"file": ("租约.txt", b"lease fencing", "text/plain")},
    )
    job_id = scheduled[0]
    first_at = datetime(2026, 9, 5, tzinfo=UTC)

    with client.app.state.research_material_application_scope() as application:
        first = application.claim_ingestion(
            job_id,
            lease_duration=timedelta(seconds=1),
            now=first_at,
        )
        assert first is not None
        second = application.claim_ingestion(
            job_id,
            lease_duration=timedelta(minutes=1),
            now=first_at + timedelta(seconds=2),
        )
        assert second is not None
        assert second.attempt_count == first.attempt_count + 1
        assert second.parse_id != first.parse_id

        stale_completion = application._materials.complete_ingestion(
            job_id,
            expected_attempt_count=first.attempt_count,
            expected_parse_id=first.parse_id,
            now=first_at + timedelta(seconds=3),
        )
        assert stale_completion is None
        active = application._materials.get_ingestion(job_id)
        assert active is not None
        assert active.ingestion_status.value == "processing"
        assert active.attempt_count == second.attempt_count
