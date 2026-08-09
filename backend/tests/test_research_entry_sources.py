from uuid import uuid4

from fastapi.testclient import TestClient

from qunxue_api.adapters.sqlite.knowledge_catalog_model import KnowledgeTheoryProfileRow


def _headers() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid4())}


def _register(client: TestClient) -> None:
    response = client.post(
        "/api/session/register",
        headers=_headers(),
        json={"email": "entry-sources@example.com", "password": "research-passphrase"},
    )
    assert response.status_code == 201


def _seed_theory_profile(client: TestClient) -> None:
    release = client.get("/api/knowledge/releases/current")

    assert release.status_code == 200
    with client.app.state.database.session() as session:
        session.add(
            KnowledgeTheoryProfileRow(
                knowledge_release_id=release.json()["knowledge_release_id"],
                theory_id="theory-social-capital",
                related_knowledge_ids=["D1:C001"],
                title="服务端确认的社会资本理论",
                core_propositions=[],
                applicable_phenomena=[],
                analysis_levels=[],
                prerequisites=[],
                exclusion_signals=[],
                observable_evidence=[],
                competing_or_complementary_theory_ids=[],
                source_ids=[],
                content_version=1,
                review_status="reviewed",
                match_eligible=True,
            )
        )


def test_direct_input_examples_come_from_persisted_seed_data(
    client: TestClient,
) -> None:
    response = client.get("/api/phenomenon-examples")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "example_id": "community-mutual-aid",
                "title": "社区互助变化",
                "phenomenon": "同一社区中的互助为何逐渐减少？",
                "research_intent": "理解互助关系的变化",
                "context": "社区持续更新，成员流动增加",
                "source_type": "built_in_example",
            },
            {
                "example_id": "event-participation",
                "title": "活动参与衰减",
                "phenomenon": "短期活动结束后参与热情为何迅速下降？",
                "research_intent": "理解参与持续性的条件",
                "context": "活动结束后缺少后续组织安排",
                "source_type": "built_in_example",
            },
            {
                "example_id": "cross-org-communication",
                "title": "跨组织沟通中断",
                "phenomenon": "跨组织协作中的沟通为何反复中断？",
                "research_intent": "比较结构与互动层面的解释",
                "context": "多个组织共同推进一项长期协作",
                "source_type": "built_in_example",
            },
        ]
    }


def test_seed_theory_name_is_resolved_from_the_current_knowledge_release(
    client: TestClient,
) -> None:
    _seed_theory_profile(client)
    _register(client)
    created = client.post(
        "/api/research-tasks",
        headers=_headers(),
        json={
            "entry_type": "direct_input",
            "seed_theory_id": "theory-social-capital",
        },
    )

    assert created.status_code == 201
    assert created.json()["seed_theory_id"] == "theory-social-capital"
    assert created.json()["seed_theory_name"] == "服务端确认的社会资本理论"

    task_id = created.json()["task_id"]
    navigation = client.get(f"/api/research-tasks/{task_id}/navigation")
    assert navigation.status_code == 200
    assert navigation.json()["seed_theory_id"] == "theory-social-capital"
    assert navigation.json()["seed_theory_name"] == "服务端确认的社会资本理论"


def test_unknown_seed_theory_id_is_rejected_even_with_an_old_name_field(
    client: TestClient,
) -> None:
    _register(client)

    response = client.post(
        "/api/research-tasks",
        headers=_headers(),
        json={
            "entry_type": "direct_input",
            "seed_theory_id": "theory-not-in-current-release",
            "seed_theory_name": "客户端伪造名称",
        },
    )

    assert response.status_code == 422
