from fastapi.testclient import TestClient

from qunxue_api.adapters.sqlite import KnowledgeEntryRevisionRow


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
    assert first_page.json()["next_cursor"]
    assert first_page.json()["entries"][0]["dimension_id"] == "D2"
    assert first_page.json()["entries"][0]["directory_path"]
    assert search.status_code == 200
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
