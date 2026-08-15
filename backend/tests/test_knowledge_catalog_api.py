from fastapi.testclient import TestClient

from qunxue_api.adapters.sqlite import KnowledgeEntryRevisionRow, KnowledgeRelationRow


def test_current_knowledge_release_is_a_stable_markdown_preview(client: TestClient) -> None:
    first = client.get("/api/knowledge/releases/current")
    second = client.get("/api/knowledge/releases/current")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["knowledge_release_id"].startswith("knowledge-preview-")
    assert first.json()["level"] == "preview"
    assert first.json()["content_hash"].startswith("sha256:")


def test_knowledge_browse_keeps_search_and_detail_on_one_release(
    client: TestClient,
) -> None:
    release_id = client.get("/api/knowledge/releases/current").json()["knowledge_release_id"]

    first_page = client.get(
        "/api/knowledge/entries",
        params={
            "knowledge_release_id": release_id,
            "dimension_id": "D2",
            "limit": 1,
        },
    )
    search = client.get(
        "/api/knowledge/entries",
        params={
            "knowledge_release_id": release_id,
            "query": "生命史",
            "dimension_id": "D2",
        },
    )
    detail = client.get(
        "/api/knowledge/entries/D2:P087",
        params={"knowledge_release_id": release_id},
    )

    assert first_page.status_code == 200
    assert first_page.json()["knowledge_release_id"] == release_id
    assert first_page.json()["total_count"] > len(first_page.json()["entries"])
    assert first_page.json()["next_cursor"]
    assert first_page.json()["entries"][0]["dimension_id"] == "D2"
    assert first_page.json()["entries"][0]["directory_path"]
    assert search.status_code == 200
    assert search.json()["total_count"] == 3
    assert "D2:P087" in [entry["knowledge_id"] for entry in search.json()["entries"]]
    assert detail.status_code == 200
    assert detail.json()["knowledge_release_id"] == release_id
    assert detail.json()["review_status"] == "pending"
    assert detail.json()["eligibility"] == {
        "browse_eligible": True,
        "rag_eligible": False,
        "training_candidate_eligible": False,
        "match_eligible": False,
        "review_record_ids": [],
    }
    assert detail.json()["relations"] == []
    assert detail.json()["theory_profile"] is None
    assert detail.json()["sources"][0]["verification_status"] == "pending"
    assert detail.json()["sources"][0]["source_type"] == "repository_markdown"


def test_knowledge_directory_summary_is_release_bound_and_hides_ineligible_entries(
    client: TestClient,
) -> None:
    release_id = client.get("/api/knowledge/releases/current").json()[
        "knowledge_release_id"
    ]

    before = client.get(
        "/api/knowledge/directory",
        params={"knowledge_release_id": release_id},
    )
    assert before.status_code == 200
    assert before.headers["cache-control"] == "private, max-age=31536000, immutable"
    payload = before.json()
    assert payload["knowledge_release_id"] == release_id
    assert len([node for node in payload["nodes"] if node["node_type"] == "dimension"]) == 7
    assert all("knowledge_id" not in node for node in payload["nodes"])
    d2_before = next(node for node in payload["nodes"] if node["node_id"] == "D2")
    class_struggle_leaf = next(
        node
        for node in payload["nodes"]
        if node["node_id"].endswith("C001 历史唯物主义（Historical Materialism）/T4 当代发展")
    )
    assert class_struggle_leaf["title"] == "阶级斗争（Class Struggle）"

    with client.app.state.database.session() as session:
        row = session.get(KnowledgeEntryRevisionRow, (release_id, "D2:P087"))
        assert row is not None
        row.browse_eligible = False

    after = client.get(
        "/api/knowledge/directory",
        params={"knowledge_release_id": release_id},
    )
    assert after.status_code == 200
    d2_after = next(
        node for node in after.json()["nodes"] if node["node_id"] == "D2"
    )
    assert d2_after["entry_count"] == d2_before["entry_count"] - 1


def test_knowledge_entry_cursor_cannot_be_reused_with_different_filters(
    client: TestClient,
) -> None:
    release_id = client.get("/api/knowledge/releases/current").json()[
        "knowledge_release_id"
    ]
    first = client.get(
        "/api/knowledge/entries",
        params={
            "knowledge_release_id": release_id,
            "dimension_id": "D2",
            "limit": 1,
        },
    )
    assert first.status_code == 200
    assert first.json()["next_cursor"]

    wrong_scope = client.get(
        "/api/knowledge/entries",
        params={
            "knowledge_release_id": release_id,
            "dimension_id": "D1",
            "cursor": first.json()["next_cursor"],
            "limit": 1,
        },
    )
    assert wrong_scope.status_code == 422


def test_knowledge_browse_hides_entries_without_browse_eligibility(
    client: TestClient,
) -> None:
    release_id = client.get("/api/knowledge/releases/current").json()["knowledge_release_id"]
    with client.app.state.database.session() as session:
        row = session.get(KnowledgeEntryRevisionRow, (release_id, "D2:P087"))
        assert row is not None
        row.browse_eligible = False

    search = client.get(
        "/api/knowledge/entries",
        params={"knowledge_release_id": release_id, "query": "生命史"},
    )
    detail = client.get(
        "/api/knowledge/entries/D2:P087",
        params={"knowledge_release_id": release_id},
    )

    assert search.status_code == 200
    assert "D2:P087" not in [entry["knowledge_id"] for entry in search.json()["entries"]]
    assert detail.status_code == 404


def test_connection_candidate_and_reviewed_relation_layers_are_distinct_and_bounded(
    client: TestClient,
) -> None:
    release_id = client.get("/api/knowledge/releases/current").json()[
        "knowledge_release_id"
    ]

    connections = client.get(
        "/api/knowledge/connections",
        params={"knowledge_release_id": release_id, "limit": 5},
    )
    candidates = client.get(
        "/api/knowledge/relation-candidates",
        params={"knowledge_release_id": release_id, "limit": 5},
    )
    relations = client.get(
        "/api/knowledge/relations",
        params={"knowledge_release_id": release_id, "limit": 5},
    )

    assert connections.status_code == 200
    assert connections.json()["knowledge_release_id"] == release_id
    assert len(connections.json()["connections"]) == 5
    assert connections.json()["total_count"] >= 2860
    assert connections.json()["next_cursor"]
    assert {
        item["connection_kind"] for item in connections.json()["connections"]
    } == {"structure"}

    assert candidates.status_code == 200
    assert candidates.json()["knowledge_release_id"] == release_id
    assert candidates.json()["total_count"] > 0
    assert candidates.json()["candidates"]
    assert {item["review_status"] for item in candidates.json()["candidates"]} == {
        "pending"
    }
    assert all("evidence_excerpt" in item for item in candidates.json()["candidates"])
    assert all("evidence_locator" in item for item in candidates.json()["candidates"])

    assert relations.status_code == 200
    assert relations.json() == {
        "knowledge_release_id": release_id,
        "relations": [],
        "stable_order": [],
        "total_count": 0,
        "next_cursor": None,
    }


def test_connections_can_page_one_source_node_without_scanning_the_global_feed(
    client: TestClient,
) -> None:
    release_id = client.get("/api/knowledge/releases/current").json()[
        "knowledge_release_id"
    ]

    first_page = client.get(
        "/api/knowledge/connections",
        params={
            "knowledge_release_id": release_id,
            "source_node_id": "D1",
            "limit": 1,
        },
    )

    assert first_page.status_code == 200
    payload = first_page.json()
    assert payload["total_count"] > 1
    assert payload["next_cursor"]
    assert {item["source_node_id"] for item in payload["connections"]} == {"D1"}

    wrong_scope = client.get(
        "/api/knowledge/connections",
        params={
            "knowledge_release_id": release_id,
            "source_node_id": "D2",
            "cursor": payload["next_cursor"],
            "limit": 1,
        },
    )
    assert wrong_scope.status_code == 422


def test_relation_candidates_can_be_filtered_to_incident_knowledge(
    client: TestClient,
) -> None:
    release_id = client.get("/api/knowledge/releases/current").json()[
        "knowledge_release_id"
    ]
    global_page = client.get(
        "/api/knowledge/relation-candidates",
        params={"knowledge_release_id": release_id, "limit": 1},
    ).json()
    candidate = global_page["candidates"][0]

    incident = client.get(
        "/api/knowledge/relation-candidates",
        params={
            "knowledge_release_id": release_id,
            "knowledge_id": candidate["target_knowledge_id"],
        },
    )
    missing = client.get(
        "/api/knowledge/relation-candidates",
        params={
            "knowledge_release_id": release_id,
            "knowledge_id": "missing:knowledge",
        },
    )

    assert incident.status_code == 200
    assert incident.json()["candidates"]
    assert all(
        candidate["target_knowledge_id"]
        in (item["source_knowledge_id"], item["target_knowledge_id"])
        for item in incident.json()["candidates"]
    )
    assert missing.status_code == 200
    assert missing.json()["total_count"] == 0


def test_reviewed_relations_can_be_filtered_to_incident_knowledge(
    client: TestClient,
) -> None:
    release_id = client.get("/api/knowledge/releases/current").json()[
        "knowledge_release_id"
    ]
    with client.app.state.database.session() as session:
        session.add_all(
            [
                KnowledgeRelationRow(
                    knowledge_release_id=release_id,
                    relation_id="relation:one",
                    source_knowledge_id="D1:C001",
                    target_knowledge_id="D1:C002",
                    relation_type="contrasts_with",
                    direction="outbound",
                    description="已审核关系一",
                    evidence_source_ids=["source:D1:C001"],
                    evidence_grade="reviewed",
                    content_version=1,
                    review_status="reviewed",
                ),
                KnowledgeRelationRow(
                    knowledge_release_id=release_id,
                    relation_id="relation:two",
                    source_knowledge_id="D2:P001",
                    target_knowledge_id="D2:P002",
                    relation_type="extends",
                    direction="outbound",
                    description="已审核关系二",
                    evidence_source_ids=["source:D2:P001"],
                    evidence_grade="reviewed",
                    content_version=1,
                    review_status="reviewed",
                ),
            ]
        )

    response = client.get(
        "/api/knowledge/relations",
        params={
            "knowledge_release_id": release_id,
            "knowledge_id": "D1:C002",
        },
    )

    assert response.status_code == 200
    assert [item["relation_id"] for item in response.json()["relations"]] == [
        "relation:one"
    ]
    assert response.json()["total_count"] == 1
