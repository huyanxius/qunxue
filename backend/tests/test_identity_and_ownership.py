from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from qunxue_api.adapters.sqlite import ModelInvocationRow, ResearchTaskRow, UserRow
from qunxue_api.adapters.sqlite.research_task_repository import SqliteResearchTaskRepository
from qunxue_api.modules.research_intake import (
    ResearchTaskStatus,
)


def register(
    client: TestClient,
    email: str,
    *,
    password: str = "research-passphrase",
) -> dict[str, object]:
    response = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": email, "password": password},
    )
    assert response.status_code == 201
    return response.json()


def test_register_uses_an_http_only_cookie_and_hashes_the_password(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": "Researcher@Example.com", "password": "research-passphrase"},
    )

    assert response.status_code == 201
    assert response.json()["user"]["email"] == "researcher@example.com"
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "research-passphrase" not in cookie
    assert "research-passphrase" not in response.text

    with client.app.state.database.session() as session:
        user = session.scalar(select(UserRow))
        assert user is not None
        assert user.password_hash != "research-passphrase"
        assert user.password_hash.startswith("$argon2")


def test_login_failure_does_not_reveal_whether_the_account_exists(
    client: TestClient,
) -> None:
    register(client, "known@example.com")
    client.cookies.clear()

    unknown = client.post(
        "/api/session/login",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": "unknown@example.com", "password": "wrong-password"},
    )
    wrong_password = client.post(
        "/api/session/login",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": "known@example.com", "password": "wrong-password"},
    )

    assert unknown.status_code == 401
    assert wrong_password.status_code == 401
    assert unknown.json()["error"]["code"] == "unauthenticated"
    assert wrong_password.json()["error"]["code"] == "unauthenticated"
    assert unknown.json()["error"]["message"] == wrong_password.json()["error"]["message"]


def test_registering_the_same_email_again_returns_a_stable_client_error(
    client: TestClient,
) -> None:
    register(client, "duplicate@example.com")
    client.cookies.clear()

    duplicate = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": "DUPLICATE@example.com", "password": "another-passphrase"},
    )

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "validation_error"


def test_session_survives_a_refresh_and_logout_revokes_it(client: TestClient) -> None:
    registered = register(client, "session@example.com")

    current = client.get("/api/session")
    assert current.status_code == 200
    assert current.json()["session_id"] == registered["session_id"]

    logged_out = client.post(
        "/api/session/logout",
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert logged_out.status_code == 200
    assert logged_out.json()["status"] == "logged_out"
    assert client.get("/api/session").status_code == 401


def test_research_tasks_are_scoped_to_the_current_user_and_hard_deleted(
    client: TestClient,
) -> None:
    first_user = register(client, "first@example.com")
    created = client.post(
        "/api/research-tasks",
        headers={"Idempotency-Key": str(uuid4())},
        json={"entry_type": "direct_input"},
    )
    assert created.status_code == 201
    task_id = created.json()["task_id"]
    trace_id = str(uuid4())
    now = datetime.now(UTC)
    with client.app.state.database.session() as session:
        session.add(
            ModelInvocationRow(
                trace_id=trace_id,
                request_id=str(uuid4()),
                task_id=task_id,
                contract_version="test",
                capability="phenomenon_extraction",
                provider="test",
                model_version="test",
                capability_tier="base",
                demonstration=False,
                scenario="default",
                input_evidence={},
                output={},
                knowledge_release_id=None,
                degraded=False,
                degradation_reason=None,
                error_code=None,
                started_at=now,
                completed_at=now,
            )
        )

    client.cookies.clear()
    register(client, "second@example.com")
    assert client.get(f"/api/research-tasks/{task_id}").status_code == 404
    assert client.get(f"/api/research-tasks/{task_id}/navigation").status_code == 404
    assert (
        client.post(
            f"/api/research-tasks/{task_id}/inputs/direct",
            headers={"Idempotency-Key": str(uuid4())},
            json={"phenomenon": "看不见的他人材料", "research_intent": None, "context": None},
        ).status_code
        == 404
    )
    assert client.get("/api/research-tasks").json()["items"] == []

    client.cookies.clear()
    login = client.post(
        "/api/session/login",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": "first@example.com", "password": "research-passphrase"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["user_id"] == first_user["user"]["user_id"]

    listed = client.get("/api/research-tasks")
    assert listed.status_code == 200
    assert [item["task_id"] for item in listed.json()["items"]] == [task_id]
    assert listed.json()["items"][0]["status"] == "draft"
    assert listed.json()["items"][0]["current_stage"] == "phenomenon_input"
    assert listed.json()["items"][0]["allowed_actions"] == ["submit_phenomenon"]

    navigation = client.get(f"/api/research-tasks/{task_id}/navigation")
    assert navigation.status_code == 200
    assert navigation.json() == listed.json()["items"][0]

    deleted = client.delete(
        f"/api/research-tasks/{task_id}",
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get(f"/api/research-tasks/{task_id}").status_code == 404
    with client.app.state.database.session() as session:
        assert session.get(ModelInvocationRow, trace_id) is None


def test_protected_research_endpoints_require_a_session(client: TestClient) -> None:
    task_id = uuid4()

    response = client.get(f"/api/research-tasks/{task_id}")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_repository_restores_the_persisted_progress_projection(client: TestClient) -> None:
    registered = register(client, "projection@example.com")
    created = client.post(
        "/api/research-tasks",
        headers={"Idempotency-Key": str(uuid4())},
        json={"entry_type": "direct_input"},
    ).json()
    task_id = UUID(created["task_id"])
    user_id = UUID(registered["user"]["user_id"])
    phenomenon_query_id = uuid4()
    candidate_id = uuid4()
    match_run_id = uuid4()
    framework_id = uuid4()

    with client.app.state.database.session() as session:
        row = session.get(ResearchTaskRow, created["task_id"])
        assert row is not None
        row.status = ResearchTaskStatus.FRAMEWORK_DRAFT.value
        row.version = 5
        row.phenomenon_query_id = str(phenomenon_query_id)
        row.phenomenon_version = 2
        row.phenomenon_summary = "成员流动后，社区互助为何持续减少？"
        row.phenomenon_research_intent = "比较不同理论的解释边界"
        row.adopted_theory_count = 2
        row.current_phenomenon_candidate_id = str(candidate_id)
        row.current_match_run_id = str(match_run_id)
        row.current_framework_id = str(framework_id)
        session.flush()

        restored = SqliteResearchTaskRepository(session).get(
            task_id,
            user_id=user_id,
        )

    assert restored is not None
    assert restored.status is ResearchTaskStatus.FRAMEWORK_DRAFT
    assert getattr(restored, "phenomenon_query_id", None) == phenomenon_query_id
    assert getattr(restored, "phenomenon_version", None) == 2
    assert getattr(restored, "phenomenon_summary", None) == "成员流动后，社区互助为何持续减少？"
    assert getattr(restored, "phenomenon_research_intent", None) == "比较不同理论的解释边界"
    assert getattr(restored, "adopted_theory_count", None) == 2
    assert getattr(restored, "current_phenomenon_candidate_id", None) == candidate_id
    assert getattr(restored, "current_match_run_id", None) == match_run_id
    assert getattr(restored, "current_framework_id", None) == framework_id


def test_repository_persists_progress_without_a_public_test_endpoint(
    client: TestClient,
) -> None:
    registered = register(client, "progress-writer@example.com")
    created = client.post(
        "/api/research-tasks",
        headers={"Idempotency-Key": str(uuid4())},
        json={"entry_type": "direct_input"},
    ).json()
    task_id = UUID(created["task_id"])
    user_id = UUID(registered["user"]["user_id"])
    phenomenon_query_id = uuid4()
    match_run_id = uuid4()

    with client.app.state.database.session() as session:
        repository = SqliteResearchTaskRepository(session)
        task = repository.get(task_id, user_id)
        assert task is not None
        progressed = replace(
            task,
            status=ResearchTaskStatus.MATCH_GENERATING,
            version=task.version + 1,
            updated_at=task.updated_at + timedelta(minutes=5),
            phenomenon_query_id=phenomenon_query_id,
            phenomenon_version=1,
            phenomenon_summary="社区互助为何随成员流动持续减少？",
            adopted_theory_count=1,
            current_match_run_id=match_run_id,
        )

        saved = repository.save_progress(progressed)

        assert saved == progressed

    with client.app.state.database.session() as session:
        restored = SqliteResearchTaskRepository(session).get(task_id, user_id)

    assert restored == progressed


def test_real_persisted_tasks_restore_all_six_stages_and_projection_fields(
    client: TestClient,
) -> None:
    registered = register(client, "six-stages@example.com")
    user_id = UUID(registered["user"]["user_id"])
    cases = [
        (
            ResearchTaskStatus.DRAFT,
            "draft",
            "phenomenon_input",
            "submit_phenomenon",
        ),
        (
            ResearchTaskStatus.PHENOMENON_CONFIRMED,
            "in_progress",
            "theory_matching",
            "start_matching",
        ),
        (
            ResearchTaskStatus.MATCH_GENERATING,
            "in_progress",
            "theory_matching",
            "review_theory_candidates",
        ),
        (
            ResearchTaskStatus.DECISIONS_RECORDED,
            "in_progress",
            "theory_decision",
            "confirm_theory_plan",
        ),
        (
            ResearchTaskStatus.FRAMEWORK_DRAFT,
            "in_progress",
            "framework_drafting",
            "review_framework",
        ),
        (
            ResearchTaskStatus.FRAMEWORK_CONFIRMED,
            "in_progress",
            "method_design",
            "design_method",
        ),
    ]
    persisted: list[dict[str, object]] = []
    task_ids = [
        UUID(
            client.post(
                "/api/research-tasks",
                headers={"Idempotency-Key": str(uuid4())},
                json={"entry_type": "direct_input"},
            ).json()["task_id"]
        )
        for _case in cases
    ]

    with client.app.state.database.session() as session:
        repository = SqliteResearchTaskRepository(session)
        for index, ((task_status, lifecycle, stage, action), task_id) in enumerate(
            zip(cases, task_ids, strict=True)
        ):
            task = repository.get(task_id, user_id)
            assert task is not None
            has_phenomenon = task_status is not ResearchTaskStatus.DRAFT
            has_match = task_status in {
                ResearchTaskStatus.MATCH_GENERATING,
                ResearchTaskStatus.DECISIONS_RECORDED,
                ResearchTaskStatus.FRAMEWORK_DRAFT,
                ResearchTaskStatus.FRAMEWORK_CONFIRMED,
            }
            has_framework = task_status in {
                ResearchTaskStatus.FRAMEWORK_DRAFT,
                ResearchTaskStatus.FRAMEWORK_CONFIRMED,
            }
            phenomenon_query_id = uuid4() if has_phenomenon else None
            candidate_id = uuid4() if has_phenomenon else None
            match_run_id = uuid4() if has_match else None
            framework_id = uuid4() if has_framework else None
            updated_at = datetime(2026, 8, 8, index, tzinfo=UTC)
            progressed = replace(
                task,
                status=task_status,
                version=index + 1,
                updated_at=updated_at,
                phenomenon_query_id=phenomenon_query_id,
                phenomenon_version=1 if has_phenomenon else None,
                phenomenon_summary=(
                    f"阶段 {index} 的真实持久化现象摘要" if has_phenomenon else None
                ),
                phenomenon_research_intent=("比较理论解释边界" if has_phenomenon else None),
                adopted_theory_count=2
                if task_status
                in {
                    ResearchTaskStatus.DECISIONS_RECORDED,
                    ResearchTaskStatus.FRAMEWORK_DRAFT,
                    ResearchTaskStatus.FRAMEWORK_CONFIRMED,
                }
                else 0,
                current_phenomenon_candidate_id=candidate_id,
                current_match_run_id=match_run_id,
                current_framework_id=framework_id,
            )
            assert repository.save_progress(progressed) == progressed
            persisted.append(
                {
                    "task_id": task_id,
                    "domain_status": task_status.value,
                    "lifecycle": lifecycle,
                    "stage": stage,
                    "action": action,
                    "updated_at": updated_at,
                    "phenomenon_query_id": phenomenon_query_id,
                    "candidate_id": candidate_id,
                    "match_run_id": match_run_id,
                    "framework_id": framework_id,
                    "adopted_theory_count": progressed.adopted_theory_count,
                    "summary": progressed.phenomenon_summary,
                }
            )

    listed = client.get("/api/research-tasks")

    assert listed.status_code == 200
    items = listed.json()["items"]
    assert [item["task_id"] for item in items] == [
        str(case["task_id"]) for case in reversed(persisted)
    ]
    for expected in persisted:
        task_id = expected["task_id"]
        item = next(item for item in items if item["task_id"] == str(task_id))
        assert item["status"] == expected["lifecycle"]
        assert item["current_stage"] == expected["stage"]
        assert item["allowed_actions"] == [expected["action"]]
        assert item["adopted_theory_count"] == expected["adopted_theory_count"]
        assert item["current_phenomenon_candidate_id"] == _uuid_text(expected["candidate_id"])
        assert item["current_match_run_id"] == _uuid_text(expected["match_run_id"])
        assert item["current_framework_id"] == _uuid_text(expected["framework_id"])
        assert datetime.fromisoformat(item["updated_at"]) == expected["updated_at"]
        if expected["phenomenon_query_id"] is None:
            assert item["phenomenon_summary"] is None
        else:
            assert item["phenomenon_summary"] == {
                "phenomenon_query_id": str(expected["phenomenon_query_id"]),
                "version": 1,
                "phenomenon": expected["summary"],
                "research_intent": "比较理论解释边界",
            }

        restored = client.get(f"/api/research-tasks/{task_id}")
        navigation = client.get(f"/api/research-tasks/{task_id}/navigation")
        assert restored.status_code == 200
        assert restored.json()["status"] == expected["domain_status"]
        assert navigation.status_code == 200
        assert navigation.json() == item


def _uuid_text(value: object) -> str | None:
    return str(value) if isinstance(value, UUID) else None
