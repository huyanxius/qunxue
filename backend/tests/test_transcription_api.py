from io import BytesIO
from uuid import uuid4
from wave import open as open_wave

from fastapi.testclient import TestClient


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


def _wav_sample() -> bytes:
    output = BytesIO()
    with open_wave(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8_000)
        audio.writeframes(b"\x00\x00" * 800)
    return output.getvalue()


def _upload_media(client: TestClient, task_id: str) -> dict[str, object]:
    response = client.post(
        f"/api/research-tasks/{task_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "interview_transcript"},
        files={"file": ("真实访谈.wav", _wav_sample(), "audio/wav")},
    )
    assert response.status_code == 201
    return response.json()


def test_media_original_survives_when_automatic_transcription_is_unavailable(
    client: TestClient,
) -> None:
    _authenticate(client)
    task_id = _task(client)
    material = _upload_media(client, task_id)

    assert material["status"] == "uploaded"
    assert material["material_format"] == "wav"
    assert material["parse_id"] is None

    original = client.get(
        f"/api/research-tasks/{task_id}/materials/{material['material_id']}/content"
    )
    assert original.status_code == 200
    assert original.headers["content-type"] == "audio/wav"
    assert original.content == _wav_sample()

    ranged = client.get(
        f"/api/research-tasks/{task_id}/materials/{material['material_id']}/content",
        headers={"Range": "bytes=10-19"},
    )
    assert ranged.status_code == 206
    assert ranged.content == _wav_sample()[10:20]
    assert ranged.headers["accept-ranges"] == "bytes"
    assert ranged.headers["content-range"] == f"bytes 10-19/{len(_wav_sample())}"

    workspace = client.get(
        f"/api/research-tasks/{task_id}/materials/{material['material_id']}/transcription"
    )
    assert workspace.status_code == 200
    assert workspace.json()["status"] == "unavailable"
    assert workspace.json()["automatic_available"] is False
    assert workspace.json()["current_version"] is None


def test_import_edit_and_historical_material_citation_keep_timecodes(
    client: TestClient,
) -> None:
    _authenticate(client)
    task_id = _task(client)
    material = _upload_media(client, task_id)
    material_id = material["material_id"]

    imported = client.post(
        f"/api/research-tasks/{task_id}/materials/{material_id}/transcription/imports",
        headers={"Idempotency-Key": str(uuid4())},
        files={
            "file": (
                "真实访谈.srt",
                (
                    "1\n00:00:01,250 --> 00:00:03,800\n主持人：请先介绍一下自己。\n\n"
                    "2\n00:00:04,100 --> 00:00:06,900\n受访者：我在这里住了十年。\n"
                ).encode(),
                "application/x-subrip",
            )
        },
    )

    assert imported.status_code == 201
    first = imported.json()
    assert first["version"] == 1
    assert first["source"] == "imported"
    assert first["segments"][0] == {
        "segment_id": first["segments"][0]["segment_id"],
        "ordinal": 0,
        "speaker": "主持人",
        "start_ms": 1_250,
        "end_ms": 3_800,
        "text": "请先介绍一下自己。",
    }

    revised_segments = [dict(item) for item in first["segments"]]
    revised_segments[0]["speaker"] = "访谈员"
    revised_segments[0]["text"] = "请先简单介绍一下自己。"
    revised = client.post(
        f"/api/research-tasks/{task_id}/materials/{material_id}/transcription/versions",
        headers={"Idempotency-Key": str(uuid4())},
        json={"base_version_id": first["version_id"], "segments": revised_segments},
    )

    assert revised.status_code == 201
    assert revised.json()["version"] == 2
    assert revised.json()["source"] == "manual_correction"
    assert revised.json()["segments"][0]["speaker"] == "访谈员"

    historical = client.get(
        f"/api/research-tasks/{task_id}/materials/{material_id}",
        params={"parse_id": first["version_id"]},
    )
    assert historical.status_code == 200
    assert historical.json()["segments"][0]["text"] == "请先介绍一下自己。"
    assert historical.json()["segments"][0]["locator"] == {
        "page": None,
        "section_path": [],
        "paragraph": None,
        "line_start": None,
        "line_end": None,
        "char_start": None,
        "char_end": None,
        "block_index": 0,
        "time_start_ms": 1_250,
        "time_end_ms": 3_800,
        "speaker": "主持人",
    }

    workspace = client.get(
        f"/api/research-tasks/{task_id}/materials/{material_id}/transcription"
    ).json()
    assert [item["version"] for item in workspace["versions"]] == [2, 1]
    assert workspace["current_version"]["version_id"] == revised.json()["version_id"]
