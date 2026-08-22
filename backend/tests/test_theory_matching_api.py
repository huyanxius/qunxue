from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

import qunxue_api.adapters.sqlite as sqlite_adapters
import qunxue_api.modules.research_framework as research_framework
from qunxue_api.adapters.sqlite import (
    KnowledgeEntryRevisionRow,
    KnowledgeSourceRow,
    KnowledgeTheoryProfileRow,
    MatchRunRow,
    TheoryDecisionSetRow,
    TheoryMatchingRequestRow,
)
from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.adapters.sqlite.theory_matching import SqliteMatchRunRepository
from qunxue_api.bootstrap import create_app


def _idempotency_headers(value: str | None = None) -> dict[str, str]:
    return {"Idempotency-Key": value or str(uuid4())}


def _persist_agent_run(
    session,
    *,
    user_id: UUID,
    conversation_id: UUID,
    run_id: UUID,
    knowledge_release_id: str,
) -> None:
    now = datetime.now(UTC)
    session.add(
        sqlite_adapters.AgentConversationRow(
            conversation_id=str(conversation_id),
            user_id=str(user_id),
            title="研究文档协作",
            version=1,
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        sqlite_adapters.AgentRunRow(
            run_id=str(run_id),
            conversation_id=str(conversation_id),
            user_id=str(user_id),
            idempotency_key=f"proposal-{run_id}",
            status="completed",
            provider="test",
            model="test",
            knowledge_release_id=knowledge_release_id,
            usage={},
            tool_summary=[],
            started_at=now,
            completed_at=now,
        )
    )


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
    release_id = client.get("/api/knowledge/releases/current").json()["knowledge_release_id"]
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
    release_id = client.get("/api/knowledge/releases/current").json()["knowledge_release_id"]
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
    release_id = client.get("/api/knowledge/releases/current").json()["knowledge_release_id"]
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
    release_id = client.get("/api/knowledge/releases/current").json()["knowledge_release_id"]
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
            restored = restarted.get(f"/api/match-runs/{started.json()['match_run_id']}")

            assert restored.status_code == 200
            assert restored.json() == started.json()
    finally:
        restarted_database.engine.dispose()


def test_replaying_the_same_matching_request_does_not_create_another_run(
    client: TestClient,
) -> None:
    navigation, phenomenon = _create_confirmed_task(client)
    release_id = client.get("/api/knowledge/releases/current").json()["knowledge_release_id"]
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

    projected = client.get(f"/api/research-tasks/{navigation['task_id']}/navigation").json()
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
    release_id = client.get("/api/knowledge/releases/current").json()["knowledge_release_id"]
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


def test_partial_match_acknowledgement_is_persisted_and_idempotent(
    client: TestClient,
) -> None:
    navigation, phenomenon = _create_confirmed_task(client)
    release_id = client.get("/api/knowledge/releases/current").json()["knowledge_release_id"]
    started = client.post(
        f"/api/research-tasks/{navigation['task_id']}/match-runs",
        headers=_idempotency_headers(),
        json=_start_payload(navigation, phenomenon, knowledge_release_id=release_id),
    ).json()
    failed_candidate_id = uuid4()
    with client.app.state.database.session() as session:
        row = session.get(MatchRunRow, started["match_run_id"])
        assert row is not None
        snapshot = dict(row.snapshot)
        snapshot["completion_basis"] = "partial"
        snapshot["partial_completion_acknowledged"] = False
        snapshot["failed_candidate_ids"] = [str(failed_candidate_id)]
        row.snapshot = snapshot
        row.status = "partial_failure"

    partial = client.get(f"/api/match-runs/{started['match_run_id']}")
    assert partial.status_code == 200
    assert partial.json()["failed_candidate_ids"] == [str(failed_candidate_id)]
    assert "acknowledge_partial_completion" in partial.json()["allowed_actions"]

    headers = _idempotency_headers()
    payload = {
        "expected_version": started["version"],
        "acknowledged_candidate_ids": [],
        "failed_candidate_ids": [str(failed_candidate_id)],
        "reason": "确认当前没有成功候选，并保留失败记录",
    }
    acknowledgement_url = (
        f"/api/match-runs/{started['match_run_id']}/partial-completion-acknowledgements"
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda _: client.post(
                    acknowledgement_url,
                    headers=headers,
                    json=payload,
                ),
                range(2),
            )
        )
    acknowledged, replayed = responses

    assert acknowledged.status_code == 200
    assert replayed.status_code == 200
    assert replayed.json() == acknowledged.json()
    assert acknowledged.json()["version"] == started["version"] + 1
    assert acknowledged.json()["completion_basis"] == "partial_with_user_ack"
    assert acknowledged.json()["partial_completion_acknowledged"] is True
    conflicting = client.post(
        acknowledgement_url,
        headers=_idempotency_headers(),
        json=payload,
    )
    assert conflicting.status_code == 409
    restored = client.get(f"/api/match-runs/{started['match_run_id']}")
    assert restored.status_code == 200
    assert restored.json() == acknowledged.json()


def test_reviewed_fixture_profiles_return_three_traceable_candidates(
    client: TestClient,
) -> None:
    navigation, phenomenon = _create_confirmed_task(client)
    release_id = client.get("/api/knowledge/releases/current").json()["knowledge_release_id"]
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
        and candidate["supporting_evidence"][0]["source"]["verification_status"] == "verified"
        for candidate in body["candidate_page"]["candidates"]
    )

    restored = client.get(f"/api/match-runs/{body['match_run_id']}")
    assert restored.status_code == 200
    assert restored.json() == body


def test_user_decision_is_persisted_and_can_be_confirmed_for_m5(
    client: TestClient,
) -> None:
    navigation, phenomenon = _create_confirmed_task(client)
    release_id = client.get("/api/knowledge/releases/current").json()["knowledge_release_id"]
    with client.app.state.database.session() as session:
        rows = list(
            session.scalars(
                select(KnowledgeEntryRevisionRow)
                .where(KnowledgeEntryRevisionRow.knowledge_release_id == release_id)
                .order_by(KnowledgeEntryRevisionRow.knowledge_id)
                .limit(3)
            )
        )
        for index, row in enumerate(rows, start=1):
            source_id = f"source:{row.knowledge_id}"
            source = session.get(KnowledgeSourceRow, (release_id, source_id))
            assert source is not None
            source.verification_status = "verified"
            row.review_status = "reviewed"
            row.match_eligible = True
            row.review_record_ids = [f"review-{index}"]
            session.add(
                KnowledgeTheoryProfileRow(
                    knowledge_release_id=release_id,
                    theory_id=f"theory-{index}",
                    related_knowledge_ids=[row.knowledge_id],
                    title=f"理论 {index}",
                    core_propositions=[f"命题 {index}"],
                    applicable_phenomena=["社区互动"],
                    analysis_levels=["关系"],
                    prerequisites=["存在互动"],
                    exclusion_signals=["没有互动"],
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
        json=_start_payload(navigation, phenomenon, knowledge_release_id=release_id),
    ).json()
    candidates = started["candidate_page"]["candidates"]
    decisions = [
        {
            "candidate_id": candidate["candidate_id"],
            "candidate_version": candidate["version"],
            "action": "adopt" if index == 0 else "exclude",
            "reason": "用户比较证据后决定",
            "related_source_ids": candidate["source_ids"],
            "related_candidate_ids": [],
        }
        for index, candidate in enumerate(candidates)
    ]
    decision_payload = {
        "expected_match_run_version": started["version"],
        "completion_basis": started["completion_basis"],
        "decisions": decisions,
        "use_assignments": [
            {
                "candidate_id": candidates[0]["candidate_id"],
                "role_code": "primary",
                "responsibility": "解释社区互动变化",
            }
        ],
        "relations": [],
    }
    decision_headers = _idempotency_headers()
    decision_url = f"/api/match-runs/{started['match_run_id']}/decisions"
    with ThreadPoolExecutor(max_workers=2) as executor:
        decision_responses = list(
            executor.map(
                lambda _: client.post(
                    decision_url,
                    headers=decision_headers,
                    json=decision_payload,
                ),
                range(2),
            )
        )
    saved = decision_responses[0]
    assert saved.status_code == 200
    assert [response.status_code for response in decision_responses] == [200, 200]
    assert {response.json()["decision_set_id"] for response in decision_responses} == {
        saved.json()["decision_set_id"]
    }
    assert saved.json()["knowledge_release_id"] == release_id
    replayed_decision = client.post(
        f"/api/match-runs/{started['match_run_id']}/decisions",
        headers=decision_headers,
        json=decision_payload,
    )
    changed_decision = client.post(
        f"/api/match-runs/{started['match_run_id']}/decisions",
        headers=decision_headers,
        json={
            **decision_payload,
            "decisions": [{**decisions[0], "reason": "改变后的决定理由"}],
        },
    )
    second_submission = client.post(
        f"/api/match-runs/{started['match_run_id']}/decisions",
        headers=_idempotency_headers(),
        json=decision_payload,
    )
    assert replayed_decision.status_code == 200
    assert replayed_decision.json()["decision_set_id"] == saved.json()["decision_set_id"]
    assert changed_decision.status_code == 409
    assert second_submission.status_code == 409
    with client.app.state.database.session() as session:
        assert len(list(session.scalars(select(TheoryDecisionSetRow)))) == 1

    confirmed = client.post(
        f"/api/decision-sets/{saved.json()['decision_set_id']}/confirm",
        headers=_idempotency_headers(),
        json={"expected_decision_set_version": saved.json()["version"]},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["adopted_candidate_ids"] == [candidates[0]["candidate_id"]]
    assert confirmed.json()["knowledge_release_id"] == release_id
    restored_decisions = client.get(
        f"/api/match-runs/{started['match_run_id']}/decisions"
    )
    assert restored_decisions.status_code == 200
    assert [item["decision_set_id"] for item in restored_decisions.json()["decision_sets"]] == [
        saved.json()["decision_set_id"]
    ]
    restored_plan = client.get(f"/api/theory-plans/{confirmed.json()['theory_plan_id']}")
    assert restored_plan.status_code == 200
    assert restored_plan.json() == confirmed.json()
    owner_id = UUID(client.get("/api/session").json()["user"]["user_id"])
    with client.app.state.research_document_application_scope() as document_application:
        agent_plan = document_application.get_theory_plan_for_agent(
            user_id=owner_id,
            theory_plan_id=UUID(confirmed.json()["theory_plan_id"]),
        )
        assert agent_plan.phenomenon.phenomenon == phenomenon["phenomenon"]
        try:
            document_application.get_theory_plan_for_agent(
                user_id=uuid4(),
                theory_plan_id=UUID(confirmed.json()["theory_plan_id"]),
            )
        except LookupError:
            pass
        else:
            raise AssertionError("another user must not read the confirmed-plan handoff")
    with ThreadPoolExecutor(max_workers=2) as executor:
        concurrent_confirmations = list(
            executor.map(
                lambda value: client.post(
                    f"/api/decision-sets/{saved.json()['decision_set_id']}/confirm",
                    headers=_idempotency_headers(value),
                    json={"expected_decision_set_version": saved.json()["version"]},
                ),
                ("confirm-plan-a", "confirm-plan-b"),
            )
        )
    assert [response.status_code for response in concurrent_confirmations] == [200, 200]
    assert {
        response.json()["theory_plan_id"] for response in concurrent_confirmations
    } == {confirmed.json()["theory_plan_id"]}
    after_theory_confirmation = client.get(
        f"/api/research-tasks/{navigation['task_id']}/navigation"
    ).json()
    assert after_theory_confirmation["current_stage"] == "framework_drafting"
    assert after_theory_confirmation["adopted_theory_count"] == 1
    assert (
        after_theory_confirmation["current_theory_plan_id"]
        == confirmed.json()["theory_plan_id"]
    )
    assert after_theory_confirmation["allowed_actions"] == ["create_framework"]

    section_titles = (
        ("research_question", "研究问题"),
        ("research_object_and_field", "研究对象与场域"),
        ("theoretical_perspective", "理论视角"),
        ("core_concepts", "核心概念"),
        ("mechanisms", "作用机制"),
        ("questions_or_hypotheses", "研究假设与质性问题"),
        ("methodology", "研究方法"),
        ("sample_and_sources", "样本与资料来源"),
        ("analysis_steps", "分析步骤"),
        ("ethics", "伦理风险"),
        ("limitations", "局限"),
        ("evidence_gaps", "证据缺口"),
    )
    provenance_required = {
        "theoretical_perspective",
        "core_concepts",
        "mechanisms",
        "questions_or_hypotheses",
        "methodology",
        "analysis_steps",
    }
    supporting_evidence = candidates[0]["supporting_evidence"][0]
    sections = [
        {
            "section_id": key,
            "key": key,
            "title": title,
            "content": f"{title}的用户可编辑正文。",
            "status": "reviewed",
            "evidence_refs": (
                [
                    {
                        "evidence_ref_id": supporting_evidence["evidence_ref_id"],
                        "source_id": supporting_evidence["source"]["source_id"],
                        "knowledge_release_id": release_id,
                    }
                ]
                if key in provenance_required
                else []
            ),
        }
        for key, title in section_titles
    ]
    forged_sections = [dict(item) for item in sections]
    forged_sections[0] = {
        **forged_sections[0],
        "evidence_refs": [
            {
                "evidence_ref_id": "evidence-forged",
                "source_id": "source-forged",
                "knowledge_release_id": release_id,
            }
        ],
    }
    forged_document = client.post(
        f"/api/research-tasks/{navigation['task_id']}/research-documents",
        headers=_idempotency_headers(),
        json={
            "theory_plan_id": confirmed.json()["theory_plan_id"],
            "title": "伪造证据的研究框架",
            "sections": forged_sections,
        },
    )
    assert forged_document.status_code == 409

    create_url = f"/api/research-tasks/{navigation['task_id']}/research-documents"
    create_headers = _idempotency_headers("concurrent-create-a")
    competing_create_headers = _idempotency_headers("concurrent-create-b")
    create_payload = {
        "theory_plan_id": confirmed.json()["theory_plan_id"],
        "title": "社区互助研究框架",
        "sections": sections,
    }
    with ThreadPoolExecutor(max_workers=2) as executor:
        created_responses = list(
            executor.map(
                lambda headers: client.post(
                    create_url,
                    headers=headers,
                    json=create_payload,
                ),
                (create_headers, competing_create_headers),
            )
        )
    created_document = created_responses[0]
    assert created_document.status_code == 201
    document_id = created_document.json()["document_id"]
    assert [response.status_code for response in created_responses] == [201, 201]
    assert {response.json()["document_id"] for response in created_responses} == {
        document_id
    }
    assert created_document.json()["knowledge_release_id"] == release_id
    changed_create = client.post(
        create_url,
        headers=create_headers,
        json={**create_payload, "title": "同键下的另一份框架"},
    )
    assert changed_create.status_code == 409
    task_documents = client.get(
        f"/api/research-tasks/{navigation['task_id']}/research-documents"
    )
    assert task_documents.status_code == 200
    assert [item["document_id"] for item in task_documents.json()["items"]] == [document_id]
    replayed_with_a_new_key = client.post(
        create_url,
        headers=_idempotency_headers("create-framework-after-lost-response"),
        json=create_payload,
    )
    assert replayed_with_a_new_key.status_code == 201
    assert replayed_with_a_new_key.json()["document_id"] == document_id
    assert len(client.get(create_url).json()["items"]) == 1
    after_document_creation = client.get(
        f"/api/research-tasks/{navigation['task_id']}/navigation"
    ).json()
    assert after_document_creation["current_framework_id"] == document_id
    assert after_document_creation["current_stage"] == "framework_drafting"

    with client.app.state.database.session() as session:
        task_row = session.get(
            sqlite_adapters.ResearchTaskRow,
            str(navigation["task_id"]),
        )
        assert task_row is not None
        task_row.current_framework_id = str(uuid4())

    non_current_revision = client.patch(
        f"/api/research-documents/{document_id}",
        headers=_idempotency_headers("non-current-revision"),
        json={
            "expected_version": 1,
            "sections": sections,
            "change_summary": "不应写入非当前文档",
            "source": "user_edit",
        },
    )
    non_current_restore = client.post(
        f"/api/research-documents/{document_id}/restore",
        headers=_idempotency_headers("non-current-restore"),
        json={
            "source_version": 1,
            "expected_version": 1,
            "reason": "不应恢复非当前文档",
        },
    )
    non_current_confirmation = client.post(
        f"/api/research-documents/{document_id}/confirm",
        headers=_idempotency_headers("non-current-confirm"),
        json={"expected_version": 1},
    )
    assert non_current_revision.status_code == 409
    assert non_current_restore.status_code == 409
    assert non_current_confirmation.status_code == 409

    with client.app.state.database.session() as session:
        task_row = session.get(
            sqlite_adapters.ResearchTaskRow,
            str(navigation["task_id"]),
        )
        assert task_row is not None
        task_row.current_framework_id = document_id

    revised_sections = [dict(item) for item in sections]
    revised_sections[0] = {
        **revised_sections[0],
        "content": "成员流动如何影响社区互助的持续性？",
    }
    revise_headers = _idempotency_headers()
    revise_payload = {
        "expected_version": 1,
        "sections": revised_sections,
        "change_summary": "收窄研究问题",
        "source": "user_edit",
    }
    revised_document = client.patch(
        f"/api/research-documents/{document_id}",
        headers=revise_headers,
        json=revise_payload,
    )
    assert revised_document.status_code == 200
    assert revised_document.json()["version"] == 2
    replayed_revision = client.patch(
        f"/api/research-documents/{document_id}",
        headers=revise_headers,
        json=revise_payload,
    )
    assert replayed_revision.status_code == 200
    assert replayed_revision.json()["revision_id"] == revised_document.json()["revision_id"]

    versions = client.get(f"/api/research-documents/{document_id}/versions")
    assert versions.status_code == 200
    assert [item["version"] for item in versions.json()["items"]] == [2, 1]

    restore_headers = _idempotency_headers()
    restore_payload = {
        "source_version": 1,
        "expected_version": 2,
        "reason": "恢复首次草稿",
    }
    restored_document = client.post(
        f"/api/research-documents/{document_id}/restore",
        headers=restore_headers,
        json=restore_payload,
    )
    assert restored_document.status_code == 200
    assert restored_document.json()["version"] == 3
    assert restored_document.json()["sections"][0]["content"] == sections[0]["content"]
    replayed_restore = client.post(
        f"/api/research-documents/{document_id}/restore",
        headers=restore_headers,
        json=restore_payload,
    )
    assert replayed_restore.status_code == 200
    assert replayed_restore.json()["revision_id"] == restored_document.json()["revision_id"]

    confirm_headers = _idempotency_headers()
    confirm_payload = {"expected_version": 3}
    confirmed_document = client.post(
        f"/api/research-documents/{document_id}/confirm",
        headers=confirm_headers,
        json=confirm_payload,
    )
    assert confirmed_document.status_code == 200
    assert confirmed_document.json()["version"] == 4
    assert confirmed_document.json()["status"] == "confirmed"
    replayed_confirmation = client.post(
        f"/api/research-documents/{document_id}/confirm",
        headers=confirm_headers,
        json=confirm_payload,
    )
    assert replayed_confirmation.status_code == 200
    assert (
        replayed_confirmation.json()["revision_id"]
        == confirmed_document.json()["revision_id"]
    )

    exported_document = client.get(f"/api/research-documents/{document_id}/export?version=4")
    assert exported_document.status_code == 200
    assert exported_document.json()["version"] == 4
    assert exported_document.json()["knowledge_release_id"] == release_id
    assert "研究问题的用户可编辑正文。" in exported_document.json()["markdown"]

    restarted_database = Database(client.app.state.settings.database_url)
    user_id = UUID(client.get("/api/session").json()["user"]["user_id"])
    try:
        with restarted_database.session() as session:
            restored = SqliteMatchRunRepository(session).get_confirmed_plan(
                UUID(confirmed.json()["theory_plan_id"])
            )
            assert restored is not None
            assert str(restored.theory_plan_id) == confirmed.json()["theory_plan_id"]
            assert restored.knowledge_release.knowledge_release_id == release_id
            assert [str(item.candidate_id) for item in restored.candidates] == [
                candidates[0]["candidate_id"]
            ]
            repository_type = sqlite_adapters.SqliteResearchDocumentRepository
            persisted_document = repository_type(session).get_version(UUID(document_id), 4)
            assert persisted_document is not None
            assert persisted_document.status.value == "confirmed"
            assert persisted_document.knowledge_release_id == release_id
    finally:
        restarted_database.engine.dispose()

    reopened_document = client.post(
        f"/api/research-documents/{document_id}/restore",
        headers=_idempotency_headers(),
        json={
            "source_version": 4,
            "expected_version": 4,
            "reason": "继续审阅正式框架",
        },
    )
    assert reopened_document.status_code == 200
    assert reopened_document.json()["version"] == 5
    superseded_export = client.get(
        f"/api/research-documents/{document_id}/export?version=4"
    )
    assert superseded_export.status_code == 409

    approval_database = Database(client.app.state.settings.database_url)
    approval_proposal_id: UUID | None = None
    try:
        with approval_database.session() as session:
            _persist_agent_run(
                session,
                user_id=user_id,
                conversation_id=UUID(int=903),
                run_id=UUID(int=904),
                knowledge_release_id=release_id,
            )
            repository_type = sqlite_adapters.SqliteResearchDocumentRepository
            proposal_repository_type = sqlite_adapters.SqliteResearchDocumentProposalRepository
            documents = research_framework.ResearchDocumentService(
                repository=repository_type(session)
            )
            proposals = research_framework.ResearchDocumentProposalService(
                repository=proposal_repository_type(session),
                documents=documents,
            )
            proposal = proposals.propose_revision(
                user_id=user_id,
                conversation_id=UUID(int=903),
                agent_run_id=UUID(int=904),
                document_id=UUID(document_id),
                expected_version=5,
                section=research_framework.ResearchDocumentSection(
                    section_id="research_question",
                    key="research_question",
                    title="研究问题",
                    content="成员流动在什么时间范围内改变社区互助的持续性？",
                    status=research_framework.ResearchDocumentSectionStatus.REVIEWED,
                    evidence_refs=(),
                ),
                rationale="补充可观察的时间边界",
            )
            approval_proposal_id = proposal.proposal_id
    finally:
        approval_database.engine.dispose()

    assert approval_proposal_id is not None
    pending_proposal = client.get(f"/api/research-document-proposals/{approval_proposal_id}")
    assert pending_proposal.status_code == 200
    assert pending_proposal.json()["status"] == "pending"
    assert pending_proposal.json()["requires_user_approval"] is True
    assert pending_proposal.json()["model_provider"] == "test"
    assert pending_proposal.json()["model_name"] == "test"
    restored_proposals = client.get(
        f"/api/research-documents/{document_id}/proposals"
    )
    assert restored_proposals.status_code == 200
    assert [item["proposal_id"] for item in restored_proposals.json()["items"]] == [
        str(approval_proposal_id)
    ]
    blocked_gate = client.get(
        f"/api/research-documents/{document_id}/completion-gate"
    )
    assert blocked_gate.status_code == 200
    assert blocked_gate.json()["ready"] is False
    assert blocked_gate.json()["pending_proposal_count"] == 1
    blocked_confirmation = client.post(
        f"/api/research-documents/{document_id}/confirm",
        headers=_idempotency_headers("confirm-with-pending-proposal"),
        json={"expected_version": 5},
    )
    assert blocked_confirmation.status_code == 409
    assert "Agent" in blocked_confirmation.json()["error"]["message"]

    acceptance_headers = _idempotency_headers("accept-document-proposal")
    accepted_proposal = client.post(
        f"/api/research-document-proposals/{approval_proposal_id}/accept",
        headers=acceptance_headers,
        json={"expected_document_version": 5},
    )
    assert accepted_proposal.status_code == 200
    assert accepted_proposal.json()["proposal"]["status"] == "accepted"
    assert accepted_proposal.json()["document"]["version"] == 6
    assert (
        accepted_proposal.json()["document"]["sections"][0]["content"]
        == "成员流动在什么时间范围内改变社区互助的持续性？"
    )

    replayed_acceptance = client.post(
        f"/api/research-document-proposals/{approval_proposal_id}/accept",
        headers=acceptance_headers,
        json={"expected_document_version": 5},
    )
    assert replayed_acceptance.status_code == 200
    assert (
        replayed_acceptance.json()["document"]["revision_id"]
        == accepted_proposal.json()["document"]["revision_id"]
    )
    changed_acceptance = client.post(
        f"/api/research-document-proposals/{approval_proposal_id}/accept",
        headers=acceptance_headers,
        json={"expected_document_version": 6},
    )
    assert changed_acceptance.status_code == 409

    rejection_database = Database(client.app.state.settings.database_url)
    rejection_proposal_id: UUID | None = None
    try:
        with rejection_database.session() as session:
            _persist_agent_run(
                session,
                user_id=user_id,
                conversation_id=UUID(int=905),
                run_id=UUID(int=906),
                knowledge_release_id=release_id,
            )
            repository_type = sqlite_adapters.SqliteResearchDocumentRepository
            proposal_repository_type = sqlite_adapters.SqliteResearchDocumentProposalRepository
            documents = research_framework.ResearchDocumentService(
                repository=repository_type(session)
            )
            proposals = research_framework.ResearchDocumentProposalService(
                repository=proposal_repository_type(session),
                documents=documents,
            )
            proposal = proposals.propose_revision(
                user_id=user_id,
                conversation_id=UUID(int=905),
                agent_run_id=UUID(int=906),
                document_id=UUID(document_id),
                expected_version=6,
                section=research_framework.ResearchDocumentSection(
                    section_id="research_question",
                    key="research_question",
                    title="研究问题",
                    content="不应写入的 Agent 建议",
                    status=research_framework.ResearchDocumentSectionStatus.REVIEWED,
                    evidence_refs=(),
                ),
                rationale="用户将拒绝这条建议",
            )
            rejection_proposal_id = proposal.proposal_id
    finally:
        rejection_database.engine.dispose()

    assert rejection_proposal_id is not None
    rejection_headers = _idempotency_headers()
    rejected_proposal = client.post(
        f"/api/research-document-proposals/{rejection_proposal_id}/reject",
        headers=rejection_headers,
        json={"reason": "保留已经确认的时间边界"},
    )
    assert rejected_proposal.status_code == 200
    assert rejected_proposal.json()["status"] == "rejected"
    assert rejected_proposal.json()["requires_user_approval"] is False
    replayed_rejection = client.post(
        f"/api/research-document-proposals/{rejection_proposal_id}/reject",
        headers=rejection_headers,
        json={"reason": "保留已经确认的时间边界"},
    )
    assert replayed_rejection.status_code == 200
    assert replayed_rejection.json()["decided_at"] == rejected_proposal.json()["decided_at"]
    changed_rejection = client.post(
        f"/api/research-document-proposals/{rejection_proposal_id}/reject",
        headers=rejection_headers,
        json={"reason": "同一请求键下改变拒绝理由"},
    )
    assert changed_rejection.status_code == 409

    rejected_acceptance = client.post(
        f"/api/research-document-proposals/{rejection_proposal_id}/accept",
        headers=_idempotency_headers(),
        json={"expected_document_version": 6},
    )
    assert rejected_acceptance.status_code == 409
    unchanged_document = client.get(f"/api/research-documents/{document_id}")
    assert unchanged_document.status_code == 200
    assert unchanged_document.json()["version"] == 6

    concurrent_revision_payload = {
        "expected_version": 6,
        "sections": [
            {
                **item,
                "content": "两个不同请求不会同时写入同一个文档版本。"
                if item["section_id"] == "research_question"
                else item["content"],
            }
            for item in sections
        ],
        "change_summary": "并发版本竞争测试",
        "source": "user_edit",
    }
    with ThreadPoolExecutor(max_workers=2) as executor:
        concurrent_revisions = list(
            executor.map(
                lambda value: client.patch(
                    f"/api/research-documents/{document_id}",
                    headers=_idempotency_headers(value),
                    json=concurrent_revision_payload,
                ),
                ("concurrent-a", "concurrent-b"),
            )
        )
    assert sorted(response.status_code for response in concurrent_revisions) == [200, 409]
    current_after_race = client.get(f"/api/research-documents/{document_id}")
    assert current_after_race.status_code == 200
    assert current_after_race.json()["version"] == 7

    final_confirmation = client.post(
        f"/api/research-documents/{document_id}/confirm",
        headers=_idempotency_headers("confirm-final"),
        json={"expected_version": 7},
    )
    assert final_confirmation.status_code == 200
    replayed_create_after_completion = client.post(
        create_url,
        headers=_idempotency_headers("create-framework-after-completion"),
        json=create_payload,
    )
    assert replayed_create_after_completion.status_code == 201
    assert replayed_create_after_completion.json()["document_id"] == document_id
    assert replayed_create_after_completion.json()["version"] == 8
    navigation_after_create_replay = client.get(
        f"/api/research-tasks/{navigation['task_id']}/navigation"
    ).json()
    assert navigation_after_create_replay["current_stage"] == "completed"
    assert navigation_after_create_replay["current_framework_id"] == document_id
    duplicate_confirmation = client.post(
        f"/api/research-documents/{document_id}/confirm",
        headers=_idempotency_headers("confirm-again"),
        json={"expected_version": 8},
    )
    assert duplicate_confirmation.status_code == 409
    final_export = client.get(
        f"/api/research-documents/{document_id}/export?version=8"
    )
    assert final_export.status_code == 200
    export_body = final_export.json()
    manifest = export_body["manifest"]
    assert manifest["phenomenon"]["phenomenon"] == phenomenon["phenomenon"]
    assert manifest["knowledge_release"]["knowledge_release_id"] == release_id
    assert manifest["model"]["provider"] == started["model"]["provider"]
    assert manifest["model"]["model_version"] == started["model"]["model_version"]
    assert {item["title"] for item in manifest["theory_candidates"]} == {
        item["title"] for item in candidates
    }
    assert {item["action"] for item in manifest["theory_decisions"]} == {
        "adopt",
        "exclude",
    }
    assert {item["status"] for item in manifest["agent_proposals"]} == {
        "accepted",
        "rejected",
    }
    assert all(
        item["model_provider"] == "test" and item["model_name"] == "test"
        for item in manifest["agent_proposals"]
    )
    assert manifest["theory_assignments"] == [
        {
            "candidate_id": candidates[0]["candidate_id"],
            "candidate_title": candidates[0]["title"],
            "role_code": "primary",
            "responsibility": "解释社区互动变化",
        }
    ]
    assert manifest["theory_relations"] == []
    assert manifest["evidence"]
    assert all(
        item["source"]["title"]
        and item["verification_status"] == "verified"
        and item["use_boundary"]
        for item in manifest["evidence"]
        if item["source"] is not None
    )
    assert [item["version"] for item in manifest["document_versions"]] == list(
        range(8, 0, -1)
    )
    assert manifest["formal_document"]["version"] == 8
    assert {item["key"] for item in manifest["formal_document"]["sections"]} == {
        key for key, _title in section_titles
    }
    assert "## 研究过程与来源" in export_body["markdown"]
    assert "## 正式研究框架" in export_body["markdown"]

    logged_out = client.post(
        "/api/session/logout",
        headers=_idempotency_headers("m5-owner-logout"),
    )
    assert logged_out.status_code == 200
    other_user = client.post(
        "/api/session/register",
        headers=_idempotency_headers("m5-other-user-register"),
        json={
            "email": f"{uuid4()}@example.com",
            "password": "research-passphrase",
        },
    )
    assert other_user.status_code == 201
    assert client.get(f"/api/research-documents/{document_id}").status_code == 404
    assert (
        client.get(f"/api/research-documents/{document_id}/versions").status_code
        == 404
    )
    assert (
        client.get(f"/api/research-documents/{document_id}/completion-gate").status_code
        == 404
    )
    assert (
        client.get(f"/api/research-documents/{document_id}/export").status_code
        == 404
    )
    assert client.get(create_url).status_code == 404
    assert (
        client.get(
            f"/api/research-tasks/{navigation['task_id']}/research-document-proposals"
        ).status_code
        == 404
    )
    assert (
        client.get(f"/api/research-document-proposals/{approval_proposal_id}").status_code
        == 404
    )
