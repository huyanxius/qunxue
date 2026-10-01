from datetime import date

from frontier_reading_fixtures import import_real_corpus
from sqlalchemy import func, select

from qunxue_api.adapters.sqlite.frontier_models import FrontierRecordRow
from qunxue_api.adapters.sqlite.knowledge_catalog_model import KnowledgeReleaseRow
from qunxue_api.modules.knowledge_catalog import KnowledgeUsePurpose


def release_count(client):
    with client.app.state.database.session() as session:
        return session.scalar(select(func.count()).select_from(KnowledgeReleaseRow))


def available_record(client):
    import_real_corpus(client)
    rows = client.get("/api/frontier/search", params={"as_of": "2026-10-01"}).json()["items"]
    row = next(row for row in rows if row["material_type"] != "official_practice")
    return client.app.state.frontier_store.get_record(row["id"])


def test_no_release_links_are_read_only_and_do_not_create_preview(plain_client):
    row = available_record(plain_client)
    before = release_count(plain_client)
    assert before == 0
    response = plain_client.get(
        f"/api/frontier/records/{row['id']}/knowledge-links", params={"as_of": "2026-10-01"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "no_release"
    assert response.json()["knowledge_release_id"] is None
    assert response.json()["matches"] == []
    assert release_count(plain_client) == 0


def test_real_release_matches_detail_versions_and_low_evidence_fallback(client):
    catalog = client.app.state.knowledge_catalog
    release = catalog.current_release(purpose=KnowledgeUsePurpose.BROWSE)
    row = available_record(client)
    # The real corpus topic "社会" retrieves actual release entries; no fake catalog.
    row["topics"] = ["社会"]

    def save_row():
        with client.app.state.database.session() as session:
            stored = session.get(FrontierRecordRow, row["id"])
            stored.structured_json = dict(row)

    save_row()
    service = client.app.state.frontier_knowledge_links
    result = service.for_record(row["id"], as_of=date(2026, 10, 1))
    assert result["knowledge_release_id"] == release.knowledge_release_id
    assert result["knowledge_release_hash"] == release.content_hash
    assert result["record_version"] == row["version"]
    assert result["record_content_hash"] == row["content_hash"]
    assert result["matches"]
    for match in result["matches"]:
        detail = catalog.get_entry(
            knowledge_id=match["knowledge_id"], release_id=result["knowledge_release_id"]
        )
        assert detail.summary.content_version == match["content_version"]
        assert detail.summary.eligibility.browse_eligible
    row["topics"] = []
    save_row()
    assert service.for_record(row["id"])["status"] == "no_topics"
    row["topics"] = ["this_topic_does_not_exist_134"]
    save_row()
    assert service.for_record(row["id"])["status"] == "no_matches"
    row["topics"] = ["社会"]
    row["evidence"] = []
    save_row()
    low = service.for_record(row["id"])
    assert low["status"] == "low_evidence"
    assert low["relationship"] == "reading_lead"
    assert low["matches"]


def test_future_and_hidden_records_do_not_leak_links(plain_client):
    row = available_record(plain_client)
    url = f"/api/frontier/records/{row['id']}"
    assert plain_client.get(url, params={"as_of": "1900-01-01"}).status_code == 404
    assert (
        plain_client.get(url + "/knowledge-links", params={"as_of": "1900-01-01"}).status_code
        == 404
    )
    assert plain_client.get("/api/frontier/records/missing/knowledge-links").status_code == 404
    assert plain_client.post(url + "/knowledge-links").status_code == 405


def test_withdrawn_records_are_unavailable_to_all_read_only_insights(plain_client):
    row = available_record(plain_client)
    assert plain_client.app.state.frontier_store.withdraw(row["id"])
    for suffix in ["", "/knowledge-links", "/reading-priority"]:
        assert plain_client.get(f"/api/frontier/records/{row['id']}{suffix}").status_code == 404
