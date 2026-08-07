from uuid import uuid4

from fastapi.testclient import TestClient


def _request_headers() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid4())}


def _register_and_create_task(client: TestClient) -> dict[str, object]:
    registered = client.post(
        "/api/session/register",
        headers=_request_headers(),
        json={
            "email": "phenomenon@example.com",
            "password": "research-passphrase",
        },
    )
    assert registered.status_code == 201
    created = client.post(
        "/api/research-tasks",
        headers=_request_headers(),
        json={"entry_type": "direct_input"},
    )
    assert created.status_code == 201
    return created.json()


def _submit_and_extract(client: TestClient, task_id: str) -> dict[str, object]:
    submitted = client.post(
        f"/api/research-tasks/{task_id}/inputs/direct",
        headers=_request_headers(),
        json={
            "phenomenon": "同一社区中的互助为何逐渐减少？",
            "research_intent": "理解互助关系的变化",
            "context": "社区观察",
        },
    )
    assert submitted.status_code == 200
    assert submitted.json()["allowed_actions"] == [
        "extract_phenomenon_candidates"
    ]

    extracted = client.post(
        f"/api/research-tasks/{task_id}/phenomenon-candidates",
        headers=_request_headers(),
        json={"expected_task_version": 1, "requested_count": 1},
    )
    assert extracted.status_code == 200
    page = extracted.json()
    assert page["model"]["provider"] == "deterministic-mock"
    assert page["model"]["capability"] == "mock"
    assert page["model"]["degraded"] is False
    assert len(page["candidates"]) == 1
    return page["candidates"][0]


def test_direct_input_can_be_edited_confirmed_and_restored(
    client: TestClient,
) -> None:
    task = _register_and_create_task(client)
    task_id = str(task["task_id"])
    candidate = _submit_and_extract(client, task_id)

    assert candidate["status"] == "proposed"
    assert candidate["evidence_refs"] == [
        {
            "evidence_ref_id": "input:direct",
            "excerpt": "同一社区中的互助为何逐渐减少？",
            "source_ref_id": "input:direct",
            "source_description": "用户直接输入",
            "locator": None,
            "verification_status": "user_attested",
            "use_boundary": "仅代表用户陈述，尚未经外部来源核验。",
        }
    ]

    candidate_id = str(candidate["candidate_id"])
    edited = client.patch(
        f"/api/research-tasks/{task_id}/phenomenon-candidates/{candidate_id}",
        headers=_request_headers(),
        json={
            "expected_version": candidate["version"],
            "phenomenon": "社区互助在成员流动后为何持续减少？",
            "research_intent": "理解关系持续性的变化",
            "context": "社区观察与成员流动",
        },
    )
    assert edited.status_code == 200
    edited_candidate = edited.json()
    assert edited_candidate["status"] == "edited"
    assert edited_candidate["version"] == candidate["version"] + 1

    confirmed = client.post(
        (
            f"/api/research-tasks/{task_id}/phenomenon-candidates/"
            f"{candidate_id}/confirm"
        ),
        headers=_request_headers(),
        json={"expected_version": edited_candidate["version"]},
    )
    assert confirmed.status_code == 200
    snapshot = confirmed.json()
    assert snapshot["phenomenon"] == "社区互助在成员流动后为何持续减少？"
    assert snapshot["status"] == "confirmed"

    restored_candidate = client.get(
        f"/api/research-tasks/{task_id}/phenomenon-candidates/{candidate_id}"
    )
    restored_snapshots = client.get(
        f"/api/research-tasks/{task_id}/phenomenon-snapshots"
    )
    navigation = client.get(f"/api/research-tasks/{task_id}/navigation")
    my_research = client.get("/api/research-tasks")

    assert restored_candidate.status_code == 200
    assert restored_candidate.json()["status"] == "confirmed"
    assert restored_snapshots.status_code == 200
    assert restored_snapshots.json()["snapshots"] == [snapshot]
    assert navigation.status_code == 200
    assert navigation.json()["current_stage"] == "theory_matching"
    assert navigation.json()["allowed_actions"] == ["start_matching"]
    assert navigation.json()["current_phenomenon_candidate_id"] == candidate_id
    assert navigation.json()["phenomenon_summary"]["phenomenon"] == snapshot[
        "phenomenon"
    ]
    assert my_research.status_code == 200
    assert my_research.json()["items"][0]["current_stage"] == "theory_matching"


def test_matching_is_blocked_until_the_phenomenon_is_confirmed(
    client: TestClient,
) -> None:
    task = _register_and_create_task(client)
    task_id = str(task["task_id"])
    candidate = _submit_and_extract(client, task_id)

    blocked = client.post(
        f"/api/research-tasks/{task_id}/match-runs",
        headers=_request_headers(),
        json={
            "expected_task_version": 1,
            "phenomenon_query_id": str(uuid4()),
            "phenomenon_version": candidate["version"],
        },
    )

    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "phenomenon_unconfirmed"
