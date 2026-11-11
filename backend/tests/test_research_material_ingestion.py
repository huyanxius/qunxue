from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from io import BytesIO
from multiprocessing import get_context
from multiprocessing.connection import Connection
from signal import SIGKILL
from threading import Event
from time import monotonic, sleep
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from qunxue_api.adapters.sqlite.research_material_repository import SqliteResearchMaterialRepository
from qunxue_api.bootstrap import create_app
from qunxue_api.modules.research_materials import (
    MaterialIngestionJob,
    MaterialKind,
    MaterialParseError,
)
from qunxue_api.settings import Settings


def _authenticate(client: TestClient) -> UUID:
    response = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": f"{uuid4()}@example.com", "password": "research-passphrase"},
    )
    assert response.status_code == 201
    return UUID(response.json()["user"]["user_id"])


def _task(client: TestClient) -> str:
    response = client.post(
        "/api/research-tasks",
        headers={"Idempotency-Key": str(uuid4())},
        json={"entry_type": "direct_input"},
    )
    assert response.status_code == 201
    return response.json()["task_id"]


def _upload_queued_material(client: TestClient, task_id: str) -> dict:
    response = client.post(
        f"/api/research-tasks/{task_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "field_note", "defer_processing": "true"},
        files={"file": ("合成笔记.txt", "合成材料的第一段。".encode(), "text/plain")},
    )
    assert response.status_code == 201, response.text
    assert response.json()["ingestion_status"] == "queued"
    return response.json()


def test_deferred_upload_persists_job_and_can_resume_after_request(
    unstarted_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = Mock(spec=ThreadPoolExecutor)
    other_executor = Mock(spec=ThreadPoolExecutor)
    create_executor = Mock(side_effect=[executor, other_executor])
    monkeypatch.setattr("qunxue_api.bootstrap.ThreadPoolExecutor", create_executor)
    app = create_app(
        settings=unstarted_client.app.state.settings,
        database=unstarted_client.app.state.database,
        require_email_verification=False,
    )
    with TestClient(app) as assembled:
        with TestClient(app):
            pass
        _authenticate(assembled)
        task_id = _task(assembled)
        material = _upload_queued_material(assembled, task_id)
        process, job_id = executor.submit.call_args.args
        assert job_id == UUID(material["ingestion_job_id"])
        path = f"/api/research-tasks/{task_id}/materials/{material['material_id']}"
        pending = assembled.get(f"{path}/ingestion")
        assert pending.status_code == 200
        assert pending.json()["attempt_count"] == 0

        process(job_id)

        completed = assembled.get(f"{path}/ingestion")
        assert completed.status_code == 200
        assert completed.json()["ingestion_status"] == "ready"
        assert completed.json()["attempt_count"] == 1
        detail = assembled.get(path)

    assert detail.status_code == 200
    assert detail.json()["segments"][0]["text"] == "合成材料的第一段。"


@pytest.mark.parametrize("previous_attempts", [0, 1], ids=["queued", "expired-lease"])
def test_real_app_lifespan_recovers_queued_ingestions_and_shuts_down_worker(
    unstarted_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    previous_attempts: int,
) -> None:
    client = unstarted_client
    user_id = _authenticate(client)
    task_id = UUID(_task(client))
    with client.app.state.research_material_application_scope() as application:
        material = application.upload(
            user_id=user_id,
            task_id=task_id,
            idempotency_key=str(uuid4()),
            filename="合成笔记.txt",
            media_type="text/plain",
            content="合成材料的第一段。".encode(),
            material_kind=MaterialKind.FIELD_NOTE,
            defer_processing=True,
        )
        if previous_attempts:
            job = application.get_ingestion(
                user_id=user_id, task_id=task_id, material_id=material.material_id
            )
            assert job is not None
            claimed = application.claim_ingestion(job.job_id, lease_duration=timedelta(seconds=-1))
            assert claimed is not None

    with ThreadPoolExecutor(max_workers=2) as pool:
        executor = Mock(spec=ThreadPoolExecutor, wraps=pool)
        create_executor = Mock(return_value=executor)
        monkeypatch.setattr("qunxue_api.bootstrap.ThreadPoolExecutor", create_executor)
        restarted = create_app(
            settings=client.app.state.settings,
            database=client.app.state.database,
            require_email_verification=False,
        )
        created_during_assembly = create_executor.called
        with TestClient(restarted):
            pass

        path = f"/api/research-tasks/{task_id}/materials/{material.material_id}"
        response = client.get(f"{path}/ingestion")
        assert response.status_code == 200
        result = response.json()
        assert (result["ingestion_status"], result["attempt_count"]) == (
            "ready",
            previous_attempts + 1,
        )
        assert client.get(path).json()["segments"][0]["text"] == "合成材料的第一段。"
        assert not created_during_assembly
        executor.shutdown.assert_called_once_with(wait=True, cancel_futures=False)


def _interrupted_ingestion_worker(database_url: str, now: datetime, parsing: Connection) -> None:
    settings = Settings(
        _env_file=None,
        database_url=database_url,
        runtime_mode="mock",
        model_api_key=None,
        initial_admin_password=None,
        memory_learning_enabled=False,
    )
    release = Event()

    def hold_parser(**_kwargs):
        parsing.send("parsing")
        release.wait()

    with (
        patch("qunxue_api.application.research_materials.datetime", Mock(now=lambda _tz: now)),
        patch("qunxue_api.bootstrap.parse_material", hold_parser),
        TestClient(create_app(settings=settings, require_email_verification=False)),
    ):
        release.wait()


def _read_ingestion(client: TestClient, job_id: UUID) -> MaterialIngestionJob:
    with client.app.state.research_material_application_scope() as application:
        job = application.get_ingestion_job(job_id)
    assert job is not None
    return job


def _wait_for_ingestion(
    client: TestClient, job_id: UUID, *, status: str, attempts: int
) -> MaterialIngestionJob:
    expected = (status, attempts)
    deadline = monotonic() + 8
    while True:
        job = _read_ingestion(client, job_id)
        observed = (job.ingestion_status.value, job.attempt_count)
        if observed == expected or monotonic() >= deadline:
            assert observed == expected
            return job
        sleep(0.025)


@pytest.mark.parametrize(
    ("prior_attempts", "final_state", "final_attempts", "parse_count"),
    [(0, "ready", 2, 1), (2, "failed", 3, 0)],
    ids=["retryable", "exhausted"],
)
def test_real_lifespan_rescans_lease_that_expires_after_restart(
    unstarted_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    prior_attempts: int,
    final_state: str,
    final_attempts: int,
    parse_count: int,
) -> None:
    client = unstarted_client
    user_id = _authenticate(client)
    task_id = _task(client)
    client.app_state["schedule_research_material_ingestion"] = lambda _job_id: None
    uploaded = _upload_queued_material(client, task_id)
    job_id = UUID(uploaded["ingestion_job_id"])
    material_id = UUID(uploaded["material_id"])
    claimed_at = datetime.now(UTC) + timedelta(seconds=1)
    with client.app.state.research_material_application_scope() as application:
        for _ in range(prior_attempts):
            assert application.claim_ingestion(
                job_id, now=claimed_at, lease_duration=timedelta(0)
            ) is not None

    context = get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    child = context.Process(
        target=_interrupted_ingestion_worker,
        args=(client.app.state.settings.database_url, claimed_at, send),
    )
    child.start()
    send.close()
    with receive:
        try:
            assert receive.poll(20), "worker did not reach the parser"
            assert receive.recv() == "parsing"
        finally:
            if child.is_alive():
                child.kill()
            child.join(timeout=20)
    assert child.exitcode == -SIGKILL
    interrupted = _read_ingestion(client, job_id)
    expires_at = claimed_at + timedelta(minutes=10)
    assert interrupted.lease_expires_at == expires_at

    clock = Mock(now=Mock(return_value=claimed_at + timedelta(minutes=1)))
    monkeypatch.setattr("qunxue_api.application.research_materials.datetime", clock)
    path = f"/api/research-tasks/{task_id}/materials/{material_id}"
    with client:
        before_expiry = client.get(f"{path}/ingestion")
        assert before_expiry.status_code == 200
        state = before_expiry.json()
        assert (state["ingestion_status"], state["attempt_count"]) == (
            "processing",
            prior_attempts + 1,
        )
        clock.now.return_value = expires_at
        finished = _wait_for_ingestion(client, job_id, status=final_state, attempts=final_attempts)
        assert finished.completed_at == expires_at
        assert finished.lease_expires_at is None
        if parse_count:
            assert finished.parse_id != interrupted.parse_id
            assert client.get(path).json()["segments"][0]["text"] == "合成材料的第一段。"

    with client.app.state.database.session() as session:
        parses = SqliteResearchMaterialRepository(session).list_parses(
            material_id, user_id=user_id, task_id=UUID(task_id)
        )
    assert tuple(parse.parse_id for parse in parses) == (finished.parse_id,) * parse_count


def test_real_lifespan_retries_only_when_due_and_stops_at_attempt_limit(
    unstarted_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = unstarted_client
    user_id = _authenticate(client)
    task_id = UUID(_task(client))
    failed_at = datetime.now(UTC)
    clock = Mock(now=Mock(return_value=failed_at))
    monkeypatch.setattr("qunxue_api.application.research_materials.datetime", clock)
    monkeypatch.setattr(
        "qunxue_api.bootstrap.parse_material", Mock(side_effect=RuntimeError("parser unavailable"))
    )
    with client:
        with client.app.state.research_material_application_scope() as application:
            with pytest.raises(RuntimeError, match="parser unavailable"):
                application.upload(
                    user_id=user_id,
                    task_id=task_id,
                    idempotency_key=str(uuid4()),
                    filename="合成笔记.txt",
                    media_type="text/plain",
                    content=b"transient failure",
                    material_kind=MaterialKind.FIELD_NOTE,
                )
            material, = application.list(user_id=user_id, task_id=task_id)
            first = application.get_ingestion(
                user_id=user_id, task_id=task_id, material_id=material.material_id
            )
        assert first is not None
        assert (first.ingestion_status.value, first.attempt_count) == ("failed", 1)
        assert first.available_at == failed_at + timedelta(seconds=2)
        assert first.completed_at is None

        clock.now.return_value = first.available_at
        second = _wait_for_ingestion(client, first.job_id, status="failed", attempts=2)
        assert second.available_at == first.available_at + timedelta(seconds=4)
        assert second.completed_at is None
        assert second.parse_id != first.parse_id

        clock.now.return_value = second.available_at
        third = _wait_for_ingestion(client, first.job_id, status="failed", attempts=3)
        assert third.completed_at == second.available_at
        assert third.parse_id != second.parse_id
        with client.app.state.research_material_application_scope() as application:
            assert third.job_id not in application.recoverable_ingestion_ids(
                now=second.available_at + timedelta(minutes=10)
            )


def test_stale_processing_job_is_recoverable(unstarted_client: TestClient) -> None:
    client = unstarted_client
    _authenticate(client)
    task_id = _task(client)
    client.app_state["schedule_research_material_ingestion"] = lambda _job_id: None
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


def test_deferred_upload_idempotency_reuses_one_material_and_job(
    unstarted_client: TestClient,
) -> None:
    client = unstarted_client
    _authenticate(client)
    task_id = _task(client)
    scheduled: list[UUID] = []
    client.app_state["schedule_research_material_ingestion"] = scheduled.append
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


def test_scanned_pdf_records_ocr_required_instead_of_ready(unstarted_client: TestClient) -> None:
    client = unstarted_client
    _authenticate(client)
    task_id = _task(client)
    scheduled: list[UUID] = []
    client.app_state["schedule_research_material_ingestion"] = scheduled.append
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
    unstarted_client: TestClient,
) -> None:
    client = unstarted_client
    _authenticate(client)
    task_id = _task(client)
    scheduled: list[UUID] = []
    client.app_state["schedule_research_material_ingestion"] = scheduled.append
    client.post(
        f"/api/research-tasks/{task_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "field_note", "defer_processing": "true"},
        files={"file": ("笔记.txt", b"retry succeeds", "text/plain")},
    ).json()

    with client.app.state.research_material_application_scope() as application:
        original_parser = application._parser
        failed_at = datetime.now(UTC) + timedelta(seconds=1)
        application._clock = lambda: failed_at
        application._parser = lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
        with pytest.raises(RuntimeError, match="boom"):
            application.process_ingestion(scheduled[0])
        failed = application._materials.get_ingestion(scheduled[0])
        assert failed is not None
        first_parse_id = failed.parse_id
        assert failed.ingestion_status.value == "failed"
        assert failed.completed_at is None
        before_retry = failed.available_at - timedelta(microseconds=1)
        assert scheduled[0] not in application.recoverable_ingestion_ids(now=before_retry)
        assert scheduled[0] in application.recoverable_ingestion_ids(now=failed.available_at)

        application._clock = lambda: failed.available_at + timedelta(seconds=1)
        application._parser = original_parser
        completed = application.process_ingestion(scheduled[0])

    assert completed is not None
    assert completed.ingestion_status.value == "ready"
    assert completed.attempt_count == 2
    assert completed.parse_id != first_parse_id


def test_expired_worker_cannot_write_to_a_newer_ingestion_attempt(
    unstarted_client: TestClient,
) -> None:
    client = unstarted_client
    _authenticate(client)
    task_id = _task(client)
    scheduled: list[UUID] = []
    client.app_state["schedule_research_material_ingestion"] = scheduled.append
    client.post(
        f"/api/research-tasks/{task_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "field_note", "defer_processing": "true"},
        files={"file": ("租约.txt", b"lease fencing", "text/plain")},
    )
    job_id = scheduled[0]
    first_at = datetime.now(UTC) + timedelta(seconds=1)

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
        stale_failure = application._materials.fail_ingestion(
            job_id,
            expected_attempt_count=first.attempt_count,
            expected_parse_id=first.parse_id,
            error_code="ingestion_worker_error",
            retry_at=first_at + timedelta(seconds=4),
            now=first_at + timedelta(seconds=3),
        )
        assert stale_failure is None
        active = application._materials.get_ingestion(job_id)
        assert active is not None
        assert active.ingestion_status.value == "processing"
        assert active.attempt_count == second.attempt_count
        assert active.parse_id == second.parse_id
