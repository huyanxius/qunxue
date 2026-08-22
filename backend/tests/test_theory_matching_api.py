from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_pre_reviewed_theory_release import _write_bundle

from qunxue_api.adapters.sqlite import (
    MatchRunRow,
    TheoryDecisionSetRow,
    TheoryMatchingRequestRow,
)
from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.adapters.sqlite.theory_matching import SqliteMatchRunRepository
from qunxue_api.bootstrap import create_app
from qunxue_api.modules.knowledge_catalog import KnowledgeUsePurpose
from qunxue_api.modules.theory_matching import (
    CandidateJudgementRunStatus,
    MatchCompletionBasis,
)


def _idempotency_headers(value: str | None = None) -> dict[str, str]:
    return {"Idempotency-Key": value or str(uuid4())}


def _install_pre_reviewed_release(client: TestClient) -> str:
    catalog = client.app.state.knowledge_catalog
    preview = catalog.current_release(purpose=KnowledgeUsePurpose.BROWSE)
    with TemporaryDirectory(prefix="qunxue-pre-reviewed-test-") as directory:
        bundle = _write_bundle(
            Path(directory) / "pre-reviewed-theories.json",
            base_release_id=preview.knowledge_release_id,
        )
        return catalog.install_pre_reviewed_bundle(bundle).release.knowledge_release_id


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


def _patch_first_match_as_partial(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = client.app.state.model_gateway
    original = gateway.judge_and_rerank
    first_batch = True

    def judge_and_rerank(*, input):
        nonlocal first_batch
        result = original(input=input)
        if not first_batch:
            return result
        first_batch = False
        assert len(result.results) == 3
        succeeded = result.results[0]
        failed = tuple(
            replace(
                item,
                status=CandidateJudgementRunStatus.TIMED_OUT,
                judgement=None,
                failure_code="model_timeout",
            )
            for item in result.results[1:]
        )
        return replace(
            result,
            results=(succeeded, *failed),
            ranked_candidate_order=(succeeded.candidate_id,),
            completion_basis=MatchCompletionBasis.PARTIAL,
            retryable_candidate_ids=tuple(item.candidate_id for item in failed),
        )

    monkeypatch.setattr(gateway, "judge_and_rerank", judge_and_rerank)


def _patch_all_matches_as_failure(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    *,
    failure_code: str,
    status: CandidateJudgementRunStatus,
    retryable: bool,
) -> None:
    gateway = client.app.state.model_gateway
    original = gateway.judge_and_rerank

    def judge_and_rerank(*, input):
        result = original(input=input)
        failed = tuple(
            replace(
                item,
                status=status,
                judgement=None,
                failure_code=failure_code,
            )
            for item in result.results
        )
        return replace(
            result,
            results=failed,
            ranked_candidate_order=(),
            completion_basis=MatchCompletionBasis.PARTIAL,
            retryable_candidate_ids=(
                tuple(item.candidate_id for item in failed) if retryable else ()
            ),
        )

    monkeypatch.setattr(gateway, "judge_and_rerank", judge_and_rerank)


def test_missing_final_release_returns_an_explicit_catalog_not_ready_conflict(
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

    assert started.status_code == 409
    assert started.json()["error"]["code"] == "catalog_not_ready"
    assert [
        record.capability.value
        for record in client.app.state.model_invocation_recorder.list_for_task(
            UUID(str(navigation["task_id"]))
        )
    ] == ["phenomenon_extraction"]
    with client.app.state.database.session() as session:
        assert len(list(session.scalars(select(MatchRunRow)))) == 0


def test_stale_task_version_is_rejected_before_creating_a_match_run(
    client: TestClient,
) -> None:
    navigation, phenomenon = _create_confirmed_task(client)
    release_id = client.get("/api/knowledge/releases/current").json()[
        "knowledge_release_id"
    ]
    payload = _start_payload(navigation, phenomenon, knowledge_release_id=release_id)
    payload["expected_task_version"] = int(navigation["version"]) - 1

    response = client.post(
        f"/api/research-tasks/{navigation['task_id']}/match-runs",
        headers=_idempotency_headers(),
        json=payload,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "validation_error"


def test_wrong_confirmed_phenomenon_snapshot_is_rejected(client: TestClient) -> None:
    navigation, phenomenon = _create_confirmed_task(client)
    release_id = client.get("/api/knowledge/releases/current").json()[
        "knowledge_release_id"
    ]
    payload = _start_payload(navigation, phenomenon, knowledge_release_id=release_id)
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
    release_id = _install_pre_reviewed_release(client)
    started = client.post(
        f"/api/research-tasks/{navigation['task_id']}/match-runs",
        headers=_idempotency_headers(),
        json=_start_payload(navigation, phenomenon, knowledge_release_id=release_id),
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
    release_id = _install_pre_reviewed_release(client)
    started = client.post(
        f"/api/research-tasks/{navigation['task_id']}/match-runs",
        headers=_idempotency_headers(),
        json=_start_payload(navigation, phenomenon, knowledge_release_id=release_id),
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
            restored = restarted.get(f"/api/match-runs/{started.json()['match_run_id']}")
            assert restored.status_code == 200
            assert restored.json() == started.json()
    finally:
        restarted_database.engine.dispose()


def test_matching_request_is_idempotent_and_rejects_changed_payload(
    client: TestClient,
) -> None:
    navigation, phenomenon = _create_confirmed_task(client)
    release_id = _install_pre_reviewed_release(client)
    headers = _idempotency_headers()
    payload = _start_payload(navigation, phenomenon, knowledge_release_id=release_id)

    first = client.post(
        f"/api/research-tasks/{navigation['task_id']}/match-runs",
        headers=headers,
        json=payload,
    )
    replayed = client.post(
        f"/api/research-tasks/{navigation['task_id']}/match-runs",
        headers=headers,
        json=payload,
    )
    changed = client.post(
        f"/api/research-tasks/{navigation['task_id']}/match-runs",
        headers=headers,
        json={**payload, "knowledge_release_id": "another-release"},
    )

    assert first.status_code == 200
    assert replayed.status_code == 200
    assert replayed.json() == first.json()
    assert changed.status_code == 409
    with client.app.state.database.session() as session:
        assert len(list(session.scalars(select(MatchRunRow)))) == 1
        assert len(list(session.scalars(select(TheoryMatchingRequestRow)))) == 1


def test_partial_match_acknowledgement_is_persisted_and_idempotent(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    navigation, phenomenon = _create_confirmed_task(client)
    release_id = _install_pre_reviewed_release(client)
    _patch_first_match_as_partial(client, monkeypatch)

    response = client.post(
        f"/api/research-tasks/{navigation['task_id']}/match-runs",
        headers=_idempotency_headers(),
        json=_start_payload(navigation, phenomenon, knowledge_release_id=release_id),
    )
    assert response.status_code == 200
    started = response.json()
    assert started["status"] == "partial_failure"
    assert started["completed_candidate_count"] == 1
    assert started["failed_candidate_count"] == 2
    assert all(
        item["failure_code"] == "model_timeout"
        and item["retryable"] is True
        and item["attempt"] == 1
        for item in started["failed_candidates"]
    )

    acknowledgement_reason = (
        "先以成功候选继续，并保留两条模型超时记录等待后续核验。"
    )
    acknowledged_candidate_ids = [
        item["candidate_id"] for item in started["candidate_page"]["candidates"]
    ]
    draft_url = f"/api/match-runs/{started['match_run_id']}/decision-draft"
    incomplete_draft = client.put(
        draft_url,
        headers=_idempotency_headers("partial-draft-before-ack"),
        json={
            "expected_match_run_version": started["version"],
            "expected_draft_version": 0,
            "completion_basis": "partial",
            "decisions": [
                {
                    "candidate_id": acknowledged_candidate_ids[0],
                    "candidate_version": started["candidate_page"]["candidates"][0][
                        "version"
                    ],
                    "action": None,
                    "reason": "",
                    "related_source_ids": [],
                    "related_candidate_ids": [],
                    "revised_applicability": None,
                }
            ],
            "use_assignments": [
                {
                    "candidate_id": acknowledged_candidate_ids[0],
                    "role_code": "",
                    "responsibility": "",
                }
            ],
            "relations": [],
            "acknowledged_candidate_ids": acknowledged_candidate_ids,
            "failed_candidate_ids": started["failed_candidate_ids"],
            "partial_completion_acknowledgement_reason": acknowledgement_reason,
        },
    )
    assert incomplete_draft.status_code == 200
    assert incomplete_draft.json()["decisions"][0]["action"] is None
    assert incomplete_draft.json()["decisions"][0]["reason"] == ""
    assert incomplete_draft.json()["use_assignments"][0]["role_code"] == ""

    headers = _idempotency_headers()
    payload = {
        "expected_version": started["version"],
        "acknowledged_candidate_ids": acknowledged_candidate_ids,
        "failed_candidate_ids": started["failed_candidate_ids"],
        "reason": acknowledgement_reason,
    }
    url = f"/api/match-runs/{started['match_run_id']}/partial-completion-acknowledgements"
    with ThreadPoolExecutor(max_workers=2) as executor:
        acknowledged, replayed = list(
            executor.map(
                lambda _: client.post(url, headers=headers, json=payload),
                range(2),
            )
        )

    assert acknowledged.status_code == 200
    assert replayed.status_code == 200
    assert replayed.json() == acknowledged.json()
    assert acknowledged.json()["status"] == "awaiting_decision"
    assert acknowledged.json()["completion_basis"] == "partial_with_user_ack"
    assert acknowledged.json()["partial_completion_acknowledged"] is True
    restored_draft = client.get(draft_url)
    assert restored_draft.status_code == 200
    assert restored_draft.json()["version"] == incomplete_draft.json()["version"] + 1
    assert (
        restored_draft.json()["expected_match_run_version"]
        == acknowledged.json()["version"]
    )
    assert restored_draft.json()["completion_basis"] == "partial_with_user_ack"
    assert (
        restored_draft.json()["partial_completion_acknowledgement_reason"]
        == acknowledgement_reason
    )
    conflicting = client.post(url, headers=_idempotency_headers(), json=payload)
    assert conflicting.status_code == 409
    restored = client.get(f"/api/match-runs/{started['match_run_id']}")
    assert restored.json() == acknowledged.json()


def test_retry_recovers_each_failed_candidate_without_losing_provenance(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    navigation, phenomenon = _create_confirmed_task(client)
    release_id = _install_pre_reviewed_release(client)
    _patch_first_match_as_partial(client, monkeypatch)
    started = client.post(
        f"/api/research-tasks/{navigation['task_id']}/match-runs",
        headers=_idempotency_headers(),
        json=_start_payload(navigation, phenomenon, knowledge_release_id=release_id),
    ).json()

    current = started
    retry_keys: list[str] = []
    for index, failure in enumerate(list(started["failed_candidates"])):
        retry_key = f"retry-failed-candidate-{index}"
        retry_keys.append(retry_key)
        retried = client.post(
            (
                f"/api/match-runs/{started['match_run_id']}/candidates/"
                f"{failure['candidate_id']}/retry"
            ),
            headers=_idempotency_headers(retry_key),
            json={
                "expected_match_run_version": current["version"],
                "expected_candidate_version": failure["version"],
            },
        )
        assert retried.status_code == 200
        current = retried.json()

    assert current["status"] == "awaiting_decision"
    assert current["completion_basis"] == "complete"
    assert current["failed_candidates"] == []
    assert current["completed_candidate_count"] == 3
    assert {
        item["knowledge_id"] for item in current["candidate_page"]["candidates"]
    } == {"D1:C001", "D1:C002", "D1:C003"}
    replayed = client.post(
        (
            f"/api/match-runs/{started['match_run_id']}/candidates/"
            f"{started['failed_candidates'][0]['candidate_id']}/retry"
        ),
        headers=_idempotency_headers(retry_keys[0]),
        json={
            "expected_match_run_version": started["version"],
            "expected_candidate_version": started["failed_candidates"][0]["version"],
        },
    )
    assert replayed.status_code == 200
    assert replayed.json() == current
    changed_replay = client.post(
        (
            f"/api/match-runs/{started['match_run_id']}/candidates/"
            f"{started['failed_candidates'][0]['candidate_id']}/retry"
        ),
        headers=_idempotency_headers(retry_keys[0]),
        json={
            "expected_match_run_version": current["version"],
            "expected_candidate_version": started["failed_candidates"][0]["version"],
        },
    )
    assert changed_replay.status_code == 409


def test_no_reliable_candidate_and_transient_model_failure_have_distinct_exits(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    navigation, phenomenon = _create_confirmed_task(client)
    release_id = _install_pre_reviewed_release(client)
    _patch_all_matches_as_failure(
        client,
        monkeypatch,
        failure_code="no_reliable_candidate",
        status=CandidateJudgementRunStatus.INSUFFICIENT_SOURCES,
        retryable=False,
    )
    no_candidate = client.post(
        f"/api/research-tasks/{navigation['task_id']}/match-runs",
        headers=_idempotency_headers(),
        json=_start_payload(navigation, phenomenon, knowledge_release_id=release_id),
    )

    assert no_candidate.status_code == 200
    assert no_candidate.json()["status"] == "no_reliable_candidate"
    assert no_candidate.json()["candidate_page"]["candidates"] == []
    assert "create_decision" not in no_candidate.json()["allowed_actions"]
    assert "retry_candidate" not in no_candidate.json()["allowed_actions"]


def test_transient_model_failure_remains_retryable_with_attempt_provenance(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    navigation, phenomenon = _create_confirmed_task(client)
    release_id = _install_pre_reviewed_release(client)
    _patch_all_matches_as_failure(
        client,
        monkeypatch,
        failure_code="model_timeout",
        status=CandidateJudgementRunStatus.TIMED_OUT,
        retryable=True,
    )
    started = client.post(
        f"/api/research-tasks/{navigation['task_id']}/match-runs",
        headers=_idempotency_headers(),
        json=_start_payload(navigation, phenomenon, knowledge_release_id=release_id),
    ).json()
    failure = started["failed_candidates"][0]

    retried = client.post(
        (
            f"/api/match-runs/{started['match_run_id']}/candidates/"
            f"{failure['candidate_id']}/retry"
        ),
        headers=_idempotency_headers(),
        json={
            "expected_match_run_version": started["version"],
            "expected_candidate_version": failure["version"],
        },
    )

    assert retried.status_code == 200
    body = retried.json()
    assert body["status"] == "failed"
    updated = next(
        item
        for item in body["failed_candidates"]
        if item["candidate_id"] == failure["candidate_id"]
    )
    assert updated["version"] == failure["version"] + 1
    assert updated["attempt"] == 2
    assert updated["failure_code"] == "model_timeout"
    assert updated["retryable"] is True


def test_pre_reviewed_fixture_profiles_return_three_traceable_candidates(
    client: TestClient,
) -> None:
    navigation, phenomenon = _create_confirmed_task(client)
    release_id = _install_pre_reviewed_release(client)
    started = client.post(
        f"/api/research-tasks/{navigation['task_id']}/match-runs",
        headers=_idempotency_headers(),
        json=_start_payload(navigation, phenomenon, knowledge_release_id=release_id),
    )

    assert started.status_code == 200
    body = started.json()
    candidates = body["candidate_page"]["candidates"]
    assert body["status"] == "awaiting_decision"
    assert body["total_candidate_count"] == 3
    assert [item["knowledge_id"] for item in candidates] == [
        "D1:C001",
        "D1:C002",
        "D1:C003",
    ]
    for item in candidates:
        assert item["origin"] == "pre_reviewed_knowledge"
        assert item["content_status"] == "pre_review_completed"
        assert item["formal_adoption_eligible"] is True
        assert item["prerequisites"]
        assert item["supporting_evidence"]
        source_types = {
            evidence["source"]["source_type"]
            for evidence in item["supporting_evidence"]
            if evidence["source"] is not None
        }
        assert "confirmed_phenomenon_evidence" in source_types
        assert "book" in source_types
        sources = client.app.state.knowledge_catalog.get_sources(
            source_ids=tuple(item["source_ids"]),
            release_id=release_id,
        )
        assert sources
        assert all(source.verification_status.value == "verified" for source in sources)
        assert all(source.locator for source in sources)
        assert item["missing_evidence"]
        assert item["limitations"]
        assert item["misuse_boundaries"]
        assert item["competing_theories"]
    restored = client.get(f"/api/match-runs/{body['match_run_id']}")
    assert restored.json() == body


def test_decision_draft_can_be_restored_edited_and_confirmed_once(
    client: TestClient,
) -> None:
    navigation, phenomenon = _create_confirmed_task(client)
    release_id = _install_pre_reviewed_release(client)
    started = client.post(
        f"/api/research-tasks/{navigation['task_id']}/match-runs",
        headers=_idempotency_headers(),
        json=_start_payload(navigation, phenomenon, knowledge_release_id=release_id),
    ).json()
    candidates = started["candidate_page"]["candidates"]

    def decision_items(primary_reason: str) -> list[dict[str, object]]:
        return [
            {
                "candidate_id": candidate["candidate_id"],
                "candidate_version": candidate["version"],
                "action": "adopt" if index == 0 else "exclude",
                "reason": (
                    primary_reason
                    if index == 0
                    else "其分析层级与当前社区互动材料不一致，暂不纳入。"
                ),
                "related_source_ids": candidate["source_ids"],
                "related_candidate_ids": [],
            }
            for index, candidate in enumerate(candidates)
        ]

    def draft_payload(version: int, reason: str) -> dict[str, object]:
        return {
            "expected_match_run_version": started["version"],
            "expected_draft_version": version,
            "completion_basis": started["completion_basis"],
            "decisions": decision_items(reason),
            "use_assignments": [
                {
                    "candidate_id": candidates[0]["candidate_id"],
                    "role_code": "primary",
                    "responsibility": "解释成员流动如何削弱持续互动与互助关系。",
                }
            ],
            "relations": [],
            "acknowledged_candidate_ids": [],
            "failed_candidate_ids": [],
            "partial_completion_acknowledgement_reason": None,
        }

    draft_url = f"/api/match-runs/{started['match_run_id']}/decision-draft"
    first_reason = "该理论能连接持续互动前提与互助减少现象，但需保留制度解释。"
    first = client.put(
        draft_url,
        headers=_idempotency_headers("draft-initial"),
        json=draft_payload(0, first_reason),
    )
    assert first.status_code == 200
    assert first.json()["version"] == 1
    assert client.get(draft_url).json() == first.json()

    revised_reason = "采用该理论作为主解释，同时把资源与制度变化列为竞争解释。"
    revised_payload = draft_payload(1, revised_reason)
    revised = client.put(
        draft_url,
        headers=_idempotency_headers("draft-revised"),
        json=revised_payload,
    )
    assert revised.status_code == 200
    assert revised.json()["version"] == 2
    assert revised.json()["decisions"][0]["reason"] == revised_reason
    assert client.get(draft_url).json() == revised.json()
    stale = client.put(
        draft_url,
        headers=_idempotency_headers(),
        json={**revised_payload, "decisions": decision_items("过期覆盖")},
    )
    assert stale.status_code == 409

    decision_url = f"/api/match-runs/{started['match_run_id']}/decisions"
    finalize_payload = {
        "expected_match_run_version": started["version"],
        "expected_draft_version": 2,
        "completion_basis": started["completion_basis"],
        "decisions": decision_items(revised_reason),
        "use_assignments": revised_payload["use_assignments"],
        "relations": [],
    }
    decision_headers = _idempotency_headers("finalize-draft-v2")
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda _: client.post(
                    decision_url,
                    headers=decision_headers,
                    json=finalize_payload,
                ),
                range(2),
            )
        )
    assert [response.status_code for response in responses] == [200, 200]
    old_decision_set = responses[0].json()
    assert {response.json()["decision_set_id"] for response in responses} == {
        old_decision_set["decision_set_id"]
    }
    assert old_decision_set["draft_version"] == 2

    final_reason = "补充核对来源定位后采用；制度变化仍作为必须检验的竞争解释。"
    final_draft = client.put(
        draft_url,
        headers=_idempotency_headers("draft-final"),
        json=draft_payload(2, final_reason),
    )
    assert final_draft.status_code == 200
    assert final_draft.json()["version"] == 3
    invalid_old_confirmation = client.post(
        f"/api/decision-sets/{old_decision_set['decision_set_id']}/confirm",
        headers=_idempotency_headers(),
        json={"expected_decision_set_version": old_decision_set["version"]},
    )
    assert invalid_old_confirmation.status_code == 409

    final_decision = client.post(
        decision_url,
        headers=_idempotency_headers("finalize-draft-v3"),
        json={
            **finalize_payload,
            "expected_draft_version": 3,
            "decisions": decision_items(final_reason),
        },
    )
    assert final_decision.status_code == 200
    saved = final_decision.json()
    assert saved["draft_version"] == 3
    assert saved["decision_set_id"] != old_decision_set["decision_set_id"]
    with client.app.state.database.session() as session:
        assert len(list(session.scalars(select(TheoryDecisionSetRow)))) == 2

    confirmation_url = f"/api/decision-sets/{saved['decision_set_id']}/confirm"
    with ThreadPoolExecutor(max_workers=2) as executor:
        confirmations = list(
            executor.map(
                lambda key: client.post(
                    confirmation_url,
                    headers=_idempotency_headers(key),
                    json={"expected_decision_set_version": saved["version"]},
                ),
                ("confirm-plan-a", "confirm-plan-b"),
            )
        )
    assert [response.status_code for response in confirmations] == [200, 200]
    confirmed = confirmations[0].json()
    assert {response.json()["theory_plan_id"] for response in confirmations} == {
        confirmed["theory_plan_id"]
    }
    assert confirmed["knowledge_release_id"] == release_id
    assert confirmed["adopted_candidate_ids"] == [candidates[0]["candidate_id"]]
    assert confirmed["decisions"][0]["reason"] == final_reason
    assert client.get(f"/api/theory-plans/{confirmed['theory_plan_id']}").json() == confirmed
    task = client.get(f"/api/research-tasks/{navigation['task_id']}")
    assert task.status_code == 200
    assert task.json()["status"] == "theory_plan_confirmed"
    post_confirmation_edit = client.put(
        draft_url,
        headers=_idempotency_headers("draft-after-confirmation"),
        json=draft_payload(3, "确认后不允许再改写理论方案依据。"),
    )
    assert post_confirmation_edit.status_code == 409
    assert "confirmed theory plan" in post_confirmation_edit.json()["error"]["message"]

    restarted_database = Database(client.app.state.settings.database_url)
    try:
        with restarted_database.session() as session:
            restored = SqliteMatchRunRepository(session).get_confirmed_plan(
                UUID(confirmed["theory_plan_id"])
            )
            assert restored is not None
            assert str(restored.theory_plan_id) == confirmed["theory_plan_id"]
            assert restored.knowledge_release.knowledge_release_id == release_id
            assert [str(item.candidate_id) for item in restored.candidates] == [
                candidates[0]["candidate_id"]
            ]
            assert restored.decisions[0].reason == final_reason
    finally:
        restarted_database.engine.dispose()
