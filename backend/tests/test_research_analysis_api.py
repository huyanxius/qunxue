from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from qunxue_api.modules.research_analysis import (
    ComparisonFinding,
    ComparisonFindingKind,
    NextResearchStep,
)


def _authenticate(client: TestClient, *, email: str | None = None) -> str:
    response = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "email": email or f"{uuid4()}@example.com",
            "password": "research-passphrase",
        },
    )
    assert response.status_code == 201
    return response.json()["user"]["user_id"]


def _task(client: TestClient) -> str:
    response = client.post(
        "/api/research-tasks",
        headers={"Idempotency-Key": str(uuid4())},
        json={"entry_type": "direct_input"},
    )
    assert response.status_code == 201
    return response.json()["task_id"]


def _material(
    client: TestClient,
    task_id: str,
    *,
    filename: str = "访谈.txt",
    text: str = "迁移以后，姐姐承担了大部分照护，弟弟主要提供经济支持。",
):
    response = client.post(
        f"/api/research-tasks/{task_id}/materials",
        headers={"Idempotency-Key": str(uuid4())},
        data={"material_kind": "interview_transcript"},
        files={
            "file": (
                filename,
                text.encode(),
                "text/plain",
            )
        },
    )
    assert response.status_code == 201
    material = response.json()
    detail = client.get(f"/api/research-tasks/{task_id}/materials/{material['material_id']}")
    assert detail.status_code == 200
    return material, detail.json()["segments"][0]


def _annotation(
    client: TestClient,
    task_id: str,
    material,
    segment,
    *,
    idempotency_key: str | None = None,
    quote: str = "姐姐承担了大部分照护",
    case_label: str = "家庭 A",
    observed_at: str = "迁移后",
):
    start = segment["text"].index(quote)
    response = client.post(
        f"/api/research-tasks/{task_id}/analysis/annotations",
        headers={"Idempotency-Key": idempotency_key or str(uuid4())},
        json={
            "material_id": material["material_id"],
            "parse_id": segment["parse_id"],
            "segment_id": segment["segment_id"],
            "quote_start": start,
            "quote_end": start + len(quote),
            "annotation_kind": "descriptive",
            "note": "照护责任集中到姐姐",
            "reflection": "需要避免把性别分工当作先验解释。",
            "case_label": case_label,
            "observed_at": observed_at,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_analysis_api_marks_source_and_keeps_description_reflection_separate(
    client: TestClient,
) -> None:
    _authenticate(client)
    task_id = _task(client)
    material, segment = _material(client, task_id)

    annotation = _annotation(client, task_id, material, segment)

    assert annotation["quote"] == "姐姐承担了大部分照护"
    assert annotation["segment_content_hash"]
    assert annotation["locator"]["line_start"] == 1
    assert annotation["note"] == "照护责任集中到姐姐"
    assert annotation["reflection"].startswith("需要避免")


def test_analysis_api_creates_confirmed_user_code_and_memo(
    client: TestClient,
) -> None:
    _authenticate(client)
    task_id = _task(client)
    material, segment = _material(client, task_id)
    annotation = _annotation(client, task_id, material, segment)

    code_response = client.post(
        f"/api/research-tasks/{task_id}/analysis/codes",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "label": "照护责任性别化",
            "definition": "照护劳动按性别集中分配。",
            "annotation_ids": [annotation["annotation_id"]],
            "rationale": "研究者核对原文后建立。",
        },
    )
    assert code_response.status_code == 201, code_response.text
    code = code_response.json()
    assert code["status"] == "confirmed"
    assert code["source"] == "user"

    memo_response = client.post(
        f"/api/research-tasks/{task_id}/analysis/memos",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "title": "性别分工并非唯一解释",
            "content": "经济资源差异也可能解释家庭内责任安排。",
            "memo_kind": "analytic",
            "annotation_ids": [annotation["annotation_id"]],
            "code_ids": [code["code_id"]],
        },
    )
    assert memo_response.status_code == 201, memo_response.text
    memo = memo_response.json()
    assert memo["status"] == "confirmed"

    snapshot = client.get(f"/api/research-tasks/{task_id}/analysis")
    assert snapshot.status_code == 200
    assert [item["code_id"] for item in snapshot.json()["codes"]] == [code["code_id"]]
    assert [item["memo_id"] for item in snapshot.json()["memos"]] == [memo["memo_id"]]
    assert snapshot.json()["comparisons"] == []


def test_analysis_api_persistently_replays_writes_and_rejects_key_reuse(
    client: TestClient,
) -> None:
    _authenticate(client)
    task_id = _task(client)
    material, segment = _material(client, task_id)
    key = "analysis-write-request-1"

    first = _annotation(
        client,
        task_id,
        material,
        segment,
        idempotency_key=key,
    )
    replay = _annotation(
        client,
        task_id,
        material,
        segment,
        idempotency_key=key,
    )
    assert replay["annotation_id"] == first["annotation_id"]

    conflict = client.post(
        f"/api/research-tasks/{task_id}/analysis/codes",
        headers={"Idempotency-Key": key},
        json={
            "label": "照护责任性别化",
            "definition": "照护劳动按性别集中分配。",
            "annotation_ids": [first["annotation_id"]],
            "rationale": "研究者核对原文后建立。",
        },
    )
    assert conflict.status_code == 409


def test_analysis_api_requires_explicit_reflection_and_redacts_deleted_quote(
    client: TestClient,
) -> None:
    _authenticate(client)
    task_id = _task(client)
    material, segment = _material(client, task_id)
    quote = "姐姐承担了大部分照护"
    start = segment["text"].index(quote)

    missing_reflection = client.post(
        f"/api/research-tasks/{task_id}/analysis/annotations",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "material_id": material["material_id"],
            "parse_id": segment["parse_id"],
            "segment_id": segment["segment_id"],
            "quote_start": start,
            "quote_end": start + len(quote),
            "annotation_kind": "researcher_reflection",
            "note": "受访者描述了姐姐承担照护。",
            "reflection": "   ",
        },
    )
    assert missing_reflection.status_code == 422

    annotation = _annotation(client, task_id, material, segment)
    deleted = client.delete(
        f"/api/research-tasks/{task_id}/materials/{material['material_id']}",
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert deleted.status_code == 204

    snapshot = client.get(f"/api/research-tasks/{task_id}/analysis")
    assert snapshot.status_code == 200
    tombstone = snapshot.json()["annotations"][0]
    assert tombstone["quote"] is None
    assert tombstone["quote_hash"] == annotation["quote_hash"]
    assert tombstone["locator"] == annotation["locator"]
    assert tombstone["source_available"] is False
    assert tombstone["unavailable_reason"] == "source_deleted"


def test_analysis_api_hides_other_users_task_and_has_stable_operation_ids(
    client: TestClient,
) -> None:
    _authenticate(client, email=f"first-{uuid4()}@example.com")
    task_id = _task(client)
    client.post("/api/session/logout", headers={"Idempotency-Key": str(uuid4())})
    _authenticate(client, email=f"second-{uuid4()}@example.com")

    assert client.get(f"/api/research-tasks/{task_id}/analysis").status_code == 404
    paths = client.app.openapi()["paths"]
    assert (
        paths["/api/research-tasks/{task_id}/analysis"]["get"]["operationId"]
        == "get_research_analysis"
    )
    assert (
        paths["/api/research-tasks/{task_id}/analysis/annotations"]["post"]["operationId"]
        == "create_research_analysis_annotation"
    )


def test_case_comparison_api_is_idempotent_reachable_and_uses_cas_decisions(
    client: TestClient,
) -> None:
    user_id = UUID(_authenticate(client))
    task_id = _task(client)
    material_a, segment_a = _material(
        client,
        task_id,
        filename="家庭 A 访谈.txt",
        text="迁移前，母亲和姐姐共同照护，责任分配相对平均。",
    )
    material_b, segment_b = _material(
        client,
        task_id,
        filename="家庭 B 访谈.txt",
        text="迁移后，兄弟共同承担照护，并由邻里网络补位。",
    )
    annotation_a = _annotation(
        client,
        task_id,
        material_a,
        segment_a,
        quote="母亲和姐姐共同照护",
        case_label="家庭 A",
        observed_at="迁移前",
    )
    annotation_b = _annotation(
        client,
        task_id,
        material_b,
        segment_b,
        quote="兄弟共同承担照护",
        case_label="家庭 B",
        observed_at="迁移后",
    )
    payload = {
        "title": "迁移前后两个家庭的照护比较",
        "question": "迁移是否必然强化性别化照护？",
        "case_labels": ["家庭 A", "家庭 B"],
        "time_labels": ["迁移前", "迁移后"],
        "findings": [
            {
                "kind": "support",
                "statement": "家庭 A 的照护仍集中于女性。",
                "annotation_ids": [annotation_a["annotation_id"]],
            },
            {
                "kind": "counterexample",
                "statement": "家庭 B 的兄弟共同承担照护。",
                "annotation_ids": [annotation_b["annotation_id"]],
            },
            {
                "kind": "competing_explanation",
                "statement": "邻里网络可能比迁移本身更能解释责任变化。",
                "annotation_ids": [annotation_b["annotation_id"]],
            },
            {
                "kind": "evidence_gap",
                "statement": "缺少家庭 B 迁移前的连续记录。",
                "annotation_ids": [],
            },
        ],
        "competing_explanations": ["邻里互助网络"],
        "evidence_gaps": ["缺少家庭 B 迁移前的连续记录"],
        "next_steps": [
            {
                "kind": "interview",
                "action": "补访家庭 B 的迁移前照护安排",
                "priority": "high",
            }
        ],
        "theory_implication": "性别分工解释需要与邻里网络解释竞争检验。",
    }
    key = "case-comparison-api-1"

    first = client.post(
        f"/api/research-tasks/{task_id}/analysis/comparisons",
        headers={"Idempotency-Key": key},
        json=payload,
    )
    replay = client.post(
        f"/api/research-tasks/{task_id}/analysis/comparisons",
        headers={"Idempotency-Key": key},
        json=payload,
    )

    assert first.status_code == replay.status_code == 201, first.text
    assert replay.json()["comparison_id"] == first.json()["comparison_id"]
    assert first.json()["status"] == "confirmed"
    conflict = client.post(
        f"/api/research-tasks/{task_id}/analysis/comparisons",
        headers={"Idempotency-Key": key},
        json={**payload, "question": "复用键但改变问题"},
    )
    assert conflict.status_code == 409

    with client.app.state.research_analysis_application_scope() as application:
        candidate = application.propose_comparison_from_agent(
            user_id=user_id,
            task_id=UUID(task_id),
            title="Agent 候选比较",
            question=payload["question"],
            case_labels=tuple(payload["case_labels"]),
            time_labels=tuple(payload["time_labels"]),
            findings=(
                ComparisonFinding(
                    kind=ComparisonFindingKind.SUPPORT,
                    statement="家庭 A 的照护仍集中于女性。",
                    annotation_ids=(UUID(annotation_a["annotation_id"]),),
                ),
                ComparisonFinding(
                    kind=ComparisonFindingKind.COUNTEREXAMPLE,
                    statement="家庭 B 的兄弟共同承担照护。",
                    annotation_ids=(UUID(annotation_b["annotation_id"]),),
                ),
            ),
            competing_explanations=tuple(payload["competing_explanations"]),
            evidence_gaps=tuple(payload["evidence_gaps"]),
            next_steps=(
                NextResearchStep(
                    kind="interview",
                    action="补访家庭 B 的迁移前照护安排",
                    priority="high",
                ),
            ),
            theory_implication=payload["theory_implication"],
            conversation_id=uuid4(),
            agent_run_id=uuid4(),
            agent_turn_id=uuid4(),
            tool_call_id="case-comparison-api-candidate",
        )
    decision = client.post(
        f"/api/research-tasks/{task_id}/analysis/comparisons/{candidate.comparison_id}/decision",
        json={
            "expected_version": 1,
            "decision": "confirmed",
            "reason": "研究者核对两个案例后确认",
        },
    )
    assert decision.status_code == 200, decision.text
    assert decision.json()["status"] == "confirmed"
    assert decision.json()["tool_call_id"] == "case-comparison-api-candidate"
    stale = client.post(
        f"/api/research-tasks/{task_id}/analysis/comparisons/{candidate.comparison_id}/decision",
        json={
            "expected_version": 1,
            "decision": "rejected",
            "reason": "重复决定",
        },
    )
    assert stale.status_code == 409
    paths = client.app.openapi()["paths"]
    assert (
        paths["/api/research-tasks/{task_id}/analysis/comparisons"]["post"]["operationId"]
        == "create_research_case_comparison"
    )
