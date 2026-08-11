from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from test_research_framework_service import _input

from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.bootstrap import create_app
from qunxue_api.settings import Settings


class FixedTheoryPlanReader:
    def __init__(self) -> None:
        self.plan = _input().theory_plan
        self.enabled = True

    def get_confirmed(self, theory_plan_id: UUID):
        if self.enabled and theory_plan_id == self.plan.theory_plan_id:
            return self.plan
        return None


def _headers() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid4())}


@pytest.fixture
def framework_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    alembic_config: Config,
) -> Iterator[tuple[TestClient, FixedTheoryPlanReader]]:
    database_url = f"sqlite:///{tmp_path / 'framework.db'}"
    monkeypatch.setenv("QUNXUE_DATABASE_URL", database_url)
    settings = Settings(
        _env_file=None,
        database_url=database_url,
        runtime_mode="mock",
        model_base_url=None,
        model_api_key=None,
        model_name=None,
        model_extra_headers={},
        model_sft_resource_id=None,
    )
    command.upgrade(alembic_config, "head")
    database = Database(database_url)
    reader = FixedTheoryPlanReader()
    app = create_app(
        settings=settings,
        database=database,
        confirmed_theory_plan_reader=reader,
    )
    with TestClient(app) as client:
        yield client, reader
    database.engine.dispose()


def _register_and_seed_owned_task(client: TestClient, database: Database) -> dict[str, object]:
    email = f"{uuid4()}@example.com"
    password = "research-passphrase"
    registered = client.post(
        "/api/session/register",
        headers=_headers(),
        json={
            "email": email,
            "password": password,
        },
    )
    assert registered.status_code == 201
    user_id = registered.json()["user"]["user_id"]
    plan = _input().theory_plan
    from datetime import UTC, datetime

    from qunxue_api.adapters.sqlite import ResearchTaskRow

    with database.session() as session:
        session.add(
            ResearchTaskRow(
                task_id=str(plan.task_id),
                user_id=user_id,
                entry_type="direct_input",
                status="decisions_recorded",
                version=4,
                idempotency_key=str(uuid4()),
                phenomenon_query_id=str(plan.phenomenon.phenomenon_query_id),
                phenomenon_version=plan.phenomenon.version,
                phenomenon_summary=plan.phenomenon.phenomenon,
                phenomenon_research_intent=plan.phenomenon.research_intent,
                adopted_theory_count=1,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
    return {
        "task_id": str(plan.task_id),
        "task_version": 4,
        "email": email,
        "password": password,
    }


def _create_payload(task_version: int, theory_plan_id: UUID) -> dict[str, object]:
    return {
        "expected_task_version": task_version,
        "theory_plan_id": str(theory_plan_id),
        "theory_plan_version": 1,
        "original_research_question": "社区互助为什么减少？",
        "confirmed_research_question": "成员流动如何影响社区互助？",
        "question_adjustment_reason": "收窄为可检验的关系",
        "research_object": "社区成员",
        "analysis_unit": "成员关系",
        "context": "社区成员持续流动",
        "method_intent": {
            "method_kind": "访谈",
            "constraints": ["仅使用去标识化摘要"],
            "source": "user_confirmed",
        },
    }


def test_unconfirmed_theory_plan_is_rejected_by_the_server(
    framework_client: tuple[TestClient, FixedTheoryPlanReader],
) -> None:
    client, reader = framework_client
    task = _register_and_seed_owned_task(client, client.app.state.database)
    reader.enabled = False

    response = client.post(
        f"/api/research-tasks/{task['task_id']}/frameworks",
        headers=_headers(),
        json=_create_payload(task["task_version"], reader.plan.theory_plan_id),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "no_adopted_theory"


def test_framework_generation_rejects_an_empty_research_question(
    framework_client: tuple[TestClient, FixedTheoryPlanReader],
) -> None:
    client, reader = framework_client
    task = _register_and_seed_owned_task(client, client.app.state.database)
    payload = _create_payload(task["task_version"], reader.plan.theory_plan_id)
    payload["confirmed_research_question"] = ""

    response = client.post(
        f"/api/research-tasks/{task['task_id']}/frameworks",
        headers=_headers(),
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_framework_versions_reviews_and_confirmation_are_persisted(
    framework_client: tuple[TestClient, FixedTheoryPlanReader],
) -> None:
    client, reader = framework_client
    task = _register_and_seed_owned_task(client, client.app.state.database)
    created = client.post(
        f"/api/research-tasks/{task['task_id']}/frameworks",
        headers=_headers(),
        json=_create_payload(task["task_version"], reader.plan.theory_plan_id),
    )
    assert created.status_code == 201
    framework = created.json()
    assert framework["content_origin"] == "system_generated"
    assert framework["status"] == "draft"
    assert framework["input"]["confirmed_research_question"]
    assert framework["input"]["theory_plan"]["theory_plan_id"]
    assert "concept_mappings" in framework["draft"]
    assert "evidence_requirements" in framework["draft"]
    assert framework["draft"]["alternative_explanations"]
    assert framework["draft"]["ethical_boundaries"]
    assert framework["draft"]["next_actions"]

    review = client.post(
        f"/api/frameworks/{framework['framework_id']}/reviews",
        headers=_headers(),
        json={
            "expected_revision_id": framework["revision_id"],
            "expected_version": 1,
        },
    )
    assert review.status_code == 201
    finding = review.json()["audit"]["findings"][0]
    assert finding["severity"] == "blocking"
    assert finding["finding_id"]
    assert finding["reason"]
    assert finding["impact"]

    deferred = client.post(
        f"/api/frameworks/{framework['framework_id']}/audit-resolutions",
        headers=_headers(),
        json={
            "expected_revision_id": framework["revision_id"],
            "expected_version": 1,
            "audit_id": review.json()["audit"]["audit_id"],
            "resolutions": [{
                "finding_id": finding["finding_id"],
                "action": "defer",
                "reason": "等待补充区分性材料",
            }],
        },
    )
    assert deferred.status_code == 200
    assert deferred.json()["resolutions"][0]["action"] == "defer"
    assert deferred.json()["unresolved_blocking"] is True

    draft = framework["draft"]
    draft["unresolved_items"] = []
    updated = client.patch(
        f"/api/frameworks/{framework['framework_id']}",
        headers=_headers(),
        json={
            "expected_revision_id": framework["revision_id"],
            "expected_version": 1,
            "draft": draft,
            "revision_reason": "补充竞争解释区分计划",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["content_origin"] == "user_modified"
    assert updated.json()["version"] == 2

    stale_review = client.get(
        f"/api/frameworks/{framework['framework_id']}/reviews/{review.json()['review_run_id']}"
    )
    assert stale_review.status_code == 200
    assert stale_review.json()["audit"]["is_stale"] is True

    versions = client.get(f"/api/frameworks/{framework['framework_id']}/versions")
    assert versions.status_code == 200
    assert [item["content_origin"] for item in versions.json()["versions"]] == [
        "system_generated",
        "user_modified",
    ]

    second_review = client.post(
        f"/api/frameworks/{framework['framework_id']}/reviews",
        headers=_headers(),
        json={
            "expected_revision_id": updated.json()["revision_id"],
            "expected_version": 2,
        },
    )
    assert second_review.status_code == 201
    assert second_review.json()["audit"]["findings"] == []

    confirmed = client.post(
        f"/api/frameworks/{framework['framework_id']}/confirm",
        headers=_headers(),
        json={
            "expected_revision_id": updated.json()["revision_id"],
            "expected_version": 2,
            "audit_id": second_review.json()["audit"]["audit_id"],
            "resolutions": [],
        },
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"

    assert client.post("/api/session/logout", headers=_headers()).status_code == 200
    assert client.post(
        "/api/session/login",
        headers=_headers(),
        json={"email": task["email"], "password": task["password"]},
    ).status_code == 200

    navigation = client.get(f"/api/research-tasks/{task['task_id']}/navigation")
    assert navigation.status_code == 200
    assert navigation.json()["current_framework_id"] == framework["framework_id"]
    assert navigation.json()["current_stage"] == "completed"

    restored = client.get(f"/api/frameworks/{framework['framework_id']}")
    assert restored.status_code == 200
    assert restored.json()["status"] == "confirmed"
    assert restored.json()["version"] == 2
    assert restored.json()["audit"]["audit_id"] == second_review.json()["audit"]["audit_id"]


def test_framework_restore_is_scoped_to_the_authenticated_user(
    framework_client: tuple[TestClient, FixedTheoryPlanReader],
) -> None:
    client, reader = framework_client
    task = _register_and_seed_owned_task(client, client.app.state.database)
    created = client.post(
        f"/api/research-tasks/{task['task_id']}/frameworks",
        headers=_headers(),
        json=_create_payload(task["task_version"], reader.plan.theory_plan_id),
    )
    assert created.status_code == 201

    assert client.post("/api/session/logout", headers=_headers()).status_code == 200
    assert client.post(
        "/api/session/register",
        headers=_headers(),
        json={
            "email": f"{uuid4()}@example.com",
            "password": "research-passphrase",
        },
    ).status_code == 201

    response = client.get(f"/api/frameworks/{created.json()['framework_id']}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
