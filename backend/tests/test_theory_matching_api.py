from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from qunxue_api.adapters.sqlite import (
    KnowledgeEntryRevisionRow,
    KnowledgeSourceRow,
    KnowledgeTheoryProfileRow,
    MatchRunRow,
    TheoryMatchingRequestRow,
)
from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.bootstrap import create_app


def _idempotency_headers(value: str | None = None) -> dict[str, str]:
    return {"Idempotency-Key": value or str(uuid4())}


def _create_confirmed_task(client: TestClient) -> tuple[dict[str, object], dict[str, object]]:
    registered = client.post(
        "/api/session/register",
        headers=_idempotency_headers(),
        json={
            "email": f"{uuid4()}@example.com",
            "password": "research-passphrase",
        },
    )
    assert registered.status_code == 201
    created = client.post(
        "/api/research-tasks",
        headers=_idempotency_headers(),
        json={"entry_type": "direct_input"},
    )
    assert created.status_code == 201
    task_id = created.json()["task_id"]

    submitted = client.post(
        f"/api/research-tasks/{task_id}/inputs/direct",
        headers=_idempotency_headers(),
        json={
            "phenomenon": "社区互助为何随成员流动逐渐减少？",
            "research_intent": "比较关系与制度解释",
            "context": "社区成员持续流动",
        },
    )
    assert submitted.status_code == 200
    extracted = client.post(
        f"/api/research-tasks/{task_id}/phenomenon-candidates",
        headers=_idempotency_headers(),
        json={"expected_task_version": 1, "requested_count": 1},
    )
    assert extracted.status_code == 200
    candidate = extracted.json()["candidates"][0]
    confirmed = client.post(
        (
            f"/api/research-tasks/{task_id}/phenomenon-candidates/"
            f"{candidate['candidate_id']}/confirm"
        ),
        headers=_idempotency_headers(),
        json={"expected_version": candidate["version"]},
    )
    assert confirmed.status_code == 200
    navigation = client.get(f"/api/research-tasks/{task_id}/navigation")
    assert navigation.status_code == 200
    return navigation.json(), confirmed.json()


def _start_payload(
    navigation: dict[str, object],
    phenomenon: dict[str, object],
    *,
    knowledge_release_id: str,
) -> dict[str, object]:
    return {
        "expected_task_version": navigation["version"],
        "phenomenon_query_id": phenomenon["phenomenon_query_id"],
        "phenomenon_version": phenomenon["version"],
        "knowledge_release_id": knowledge_release_id,
    }


def test_current_release_without_profiles_persists_an_honest_empty_match_run(
    client: TestClient,
) -> None:
    navigation, phenomenon = _create_confirmed_task(client)
    release = client.get("/api/knowledge/releases/current").json()

    started = client.post(
        f"/api/research-tasks/{navigation['task_id']}/match-runs",
        headers=_idempotency_headers(),
        json=_start_payload(
            navigation,
            phenomenon,
            knowledge_release_id=release["knowledge_release_id"],
        ),
    )

    assert started.status_code == 200
    body = started.json()
    assert body["status"] == "no_reliable_candidate"
    assert body["knowledge_release_id"] == release["knowledge_release_id"]
    assert body["total_candidate_count"] == 0
    assert body["candidate_page"]["candidates"] == []
    assert body["model"] is None
    assert [
        record.capability.value
        for record in client.app.state.model_invocation_recorder.list_for_task(
            UUID(str(navigation["task_id"]))
        )
    ] == ["phenomenon_extraction"]

    restored = client.get(f"/api/match-runs/{body['match_run_id']}")
    assert restored.status_code == 200
    assert restored.json() == body


def test_stale_task_version_is_rejected_before_creating_a_match_run(
    client: TestClient,
) -> None:
    navigation, phenomenon = _create_confirmed_task(client)
    release_id = client.get("/api/knowledge/releases/current").json()[
        "knowledge_release_id"
    ]
    payload = _start_payload(
        navigation,
        phenomenon,
        knowledge_release_id=release_id,
    )
    payload["expected_task_version"] = int(navigation["version"]) - 1

    response = client.post(
        f"/api/research-tasks/{navigation['task_id']}/match-runs",
        headers=_idempotency_headers(),
        json=payload,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "validation_error"


def test_wrong_confirmed_phenomenon_snapshot_is_rejected(
    client: TestClient,
) -> None:
    navigation, phenomenon = _create_confirmed_task(client)
    release_id = client.get("/api/knowledge/releases/current").json()[
        "knowledge_release_id"
    ]
    payload = _start_payload(
        navigation,
        phenomenon,
        knowledge_release_id=release_id,
    )
    payload["phenomenon_query_id"] = str(uuid4())

    response = client.post(
        f"/api/research-tasks/{navigation['task_id']}/match-runs",
        headers=_idempotency_headers(),
        json=payload,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "validation_error"


def test_match_run_is_not_visible_to_another_user(client: TestClient) -> None:
    navigation, phenomenon = _create_confirmed_task(client)
    release_id = client.get("/api/knowledge/releases/current").json()[
        "knowledge_release_id"
    ]
    started = client.post(
        f"/api/research-tasks/{navigation['task_id']}/match-runs",
        headers=_idempotency_headers(),
        json=_start_payload(
            navigation,
            phenomenon,
            knowledge_release_id=release_id,
        ),
    )
    assert started.status_code == 200

    client.cookies.clear()
    registered = client.post(
        "/api/session/register",
        headers=_idempotency_headers(),
        json={
            "email": f"{uuid4()}@example.com",
            "password": "research-passphrase",
        },
    )
    assert registered.status_code == 201

    hidden = client.get(f"/api/match-runs/{started.json()['match_run_id']}")

    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "not_found"


def test_match_run_is_restored_after_application_restart(client: TestClient) -> None:
    navigation, phenomenon = _create_confirmed_task(client)
    release_id = client.get("/api/knowledge/releases/current").json()[
        "knowledge_release_id"
    ]
    started = client.post(
        f"/api/research-tasks/{navigation['task_id']}/match-runs",
        headers=_idempotency_headers(),
        json=_start_payload(
            navigation,
            phenomenon,
            knowledge_release_id=release_id,
        ),
    )
    assert started.status_code == 200
    settings = client.app.state.settings
    cookie_value = client.cookies.get(settings.session_cookie_name)
    assert cookie_value is not None
    restarted_database = Database(settings.database_url)
    restarted_app = create_app(settings=settings, database=restarted_database)

    try:
        with TestClient(restarted_app) as restarted:
            restarted.cookies.set(settings.session_cookie_name, cookie_value)
            restored = restarted.get(
                f"/api/match-runs/{started.json()['match_run_id']}"
            )

            assert restored.status_code == 200
            assert restored.json() == started.json()
    finally:
        restarted_database.engine.dispose()


def test_replaying_the_same_matching_request_does_not_create_another_run(
    client: TestClient,
) -> None:
    navigation, phenomenon = _create_confirmed_task(client)
    release_id = client.get("/api/knowledge/releases/current").json()[
        "knowledge_release_id"
    ]
    headers = _idempotency_headers()
    payload = _start_payload(
        navigation,
        phenomenon,
        knowledge_release_id=release_id,
    )

    first = client.post(
        f"/api/research-tasks/{navigation['task_id']}/match-runs",
        headers=headers,
        json=payload,
    )
    second = client.post(
        f"/api/research-tasks/{navigation['task_id']}/match-runs",
        headers=headers,
        json=payload,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["match_run_id"] == first.json()["match_run_id"]

    projected = client.get(
        f"/api/research-tasks/{navigation['task_id']}/navigation"
    ).json()
    assert projected["current_match_run_id"] == first.json()["match_run_id"]
    assert projected["version"] == navigation["version"] + 1
    assert projected["current_stage"] == "theory_matching"
    with client.app.state.database.session() as session:
        assert len(list(session.scalars(select(MatchRunRow)))) == 1
        assert len(list(session.scalars(select(TheoryMatchingRequestRow)))) == 1


def test_reusing_an_idempotency_key_for_another_payload_is_rejected(
    client: TestClient,
) -> None:
    navigation, phenomenon = _create_confirmed_task(client)
    release_id = client.get("/api/knowledge/releases/current").json()[
        "knowledge_release_id"
    ]
    headers = _idempotency_headers()
    payload = _start_payload(
        navigation,
        phenomenon,
        knowledge_release_id=release_id,
    )
    first = client.post(
        f"/api/research-tasks/{navigation['task_id']}/match-runs",
        headers=headers,
        json=payload,
    )
    assert first.status_code == 200
    changed_payload = {**payload, "knowledge_release_id": "another-release"}

    conflict = client.post(
        f"/api/research-tasks/{navigation['task_id']}/match-runs",
        headers=headers,
        json=changed_payload,
    )

    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "validation_error"
    with client.app.state.database.session() as session:
        assert len(list(session.scalars(select(MatchRunRow)))) == 1


def test_reviewed_fixture_profiles_return_three_traceable_candidates(
    client: TestClient,
) -> None:
    navigation, phenomenon = _create_confirmed_task(client)
    release_id = client.get("/api/knowledge/releases/current").json()[
        "knowledge_release_id"
    ]
    with client.app.state.database.session() as session:
        rows = list(
            session.scalars(
                select(KnowledgeEntryRevisionRow)
                .where(KnowledgeEntryRevisionRow.knowledge_release_id == release_id)
                .order_by(KnowledgeEntryRevisionRow.knowledge_id)
                .limit(3)
            )
        )
        assert len(rows) == 3
        expected_knowledge_ids = [row.knowledge_id for row in rows]
        for index, row in enumerate(rows, start=1):
            source_id = f"source:{row.knowledge_id}"
            source = session.get(KnowledgeSourceRow, (release_id, source_id))
            assert source is not None
            source.verification_status = "verified"
            source.use_boundary = "测试中的人类审校 fixture，仅验证匹配链。"
            row.review_status = "reviewed"
            row.match_eligible = True
            row.review_record_ids = [f"review-{index}"]
            session.add(
                KnowledgeTheoryProfileRow(
                    knowledge_release_id=release_id,
                    theory_id=f"theory-{index}",
                    related_knowledge_ids=[row.knowledge_id],
                    title=f"理论 {index}",
                    core_propositions=[f"理论 {index} 的已审校命题"],
                    applicable_phenomena=["社区互动"],
                    analysis_levels=["关系"],
                    prerequisites=["存在持续互动"],
                    exclusion_signals=["没有互动记录"],
                    observable_evidence=["互动频率"],
                    competing_or_complementary_theory_ids=[],
                    source_ids=[source_id],
                    content_version=1,
                    review_status="reviewed",
                    match_eligible=True,
                )
            )

    started = client.post(
        f"/api/research-tasks/{navigation['task_id']}/match-runs",
        headers=_idempotency_headers(),
        json=_start_payload(
            navigation,
            phenomenon,
            knowledge_release_id=release_id,
        ),
    )

    assert started.status_code == 200
    body = started.json()
    assert body["status"] == "awaiting_decision"
    assert body["total_candidate_count"] == 3
    assert [
        candidate["knowledge_id"] for candidate in body["candidate_page"]["candidates"]
    ] == expected_knowledge_ids
    assert all(
        candidate["origin"] == "reviewed_knowledge"
        and candidate["content_status"] == "reviewed"
        and candidate["formal_adoption_eligible"] is True
        and candidate["supporting_evidence"][0]["source"]["verification_status"]
        == "verified"
        for candidate in body["candidate_page"]["candidates"]
    )

    restored = client.get(f"/api/match-runs/{body['match_run_id']}")
    assert restored.status_code == 200
    assert restored.json() == body
