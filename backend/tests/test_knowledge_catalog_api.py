from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from qunxue_api.adapters.sqlite import KnowledgeRelationRow
from qunxue_api.adapters.sqlite.knowledge_catalog_model import (
    KnowledgeEntryRevisionRow,
    KnowledgeReleaseRow,
)
from qunxue_api.modules.knowledge_catalog import KnowledgeReleaseLevel, KnowledgeUsePurpose


def test_current_knowledge_release_is_a_stable_markdown_preview(client: TestClient) -> None:
    first = client.get("/api/knowledge/releases/current")
    second = client.get("/api/knowledge/releases/current")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["knowledge_release_id"].startswith("knowledge-preview-")
    assert first.json()["level"] == "preview"
    assert first.json()["content_hash"].startswith("sha256:")


def test_match_uses_latest_final_release_even_when_browse_preview_is_current(
    client: TestClient,
) -> None:
    preview = client.app.state.knowledge_catalog.current_release(
        purpose=KnowledgeUsePurpose.BROWSE
    )
    with client.app.state.database.session() as session:
        session.add(
            KnowledgeReleaseRow(
                knowledge_release_id="knowledge-final-reviewed-v1",
                level=KnowledgeReleaseLevel.FINAL.value,
                content_hash="sha256:knowledge-final-reviewed-v1",
                build_config_version="pre-reviewed-theory-release/v1",
                manifest={"theory_ids": ["theory:example"]},
                is_current=True,
                built_at=datetime.now(UTC),
            )
        )

    match = client.app.state.knowledge_catalog.current_release(
        purpose=KnowledgeUsePurpose.MATCH
    )

    assert preview.level is KnowledgeReleaseLevel.PREVIEW
    assert match.knowledge_release_id == "knowledge-final-reviewed-v1"
    assert match.level is KnowledgeReleaseLevel.FINAL


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
                    source_knowledge_id="D1:C003",
                    target_knowledge_id="D1:C004",
                    relation_type="extends",
                    direction="outbound",
                    description="已审核关系二",
                    evidence_source_ids=["source:D1:C003"],
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


@pytest.mark.parametrize("query", ["社会资本", "social"])
def test_search_ranks_title_matches_before_body_matches_across_pages(
    client: TestClient,
    query: str,
) -> None:
    release_id = client.get("/api/knowledge/releases/current").json()["knowledge_release_id"]
    params = {"knowledge_release_id": release_id, "query": query, "limit": 1}
    matches = client.get("/api/knowledge/entries", params={**params, "limit": 100}).json()[
        "entries"
    ]
    assert len(matches) >= 2
    # The fixture contains one source chapter. Promote its last matching IDs to
    # explicit titles so the test distinguishes ranking from ordinary ID order.
    ids = sorted(item["knowledge_id"] for item in matches)[-1:]
    with client.app.state.database.session() as session:
        for knowledge_id in ids:
            row = session.get(KnowledgeEntryRevisionRow, (release_id, knowledge_id))
            row.title = query.upper()
    first = client.get("/api/knowledge/entries", params=params)
    assert first.status_code == 200
    assert first.json()["entries"][0]["title"].casefold() == query.casefold()
    cursor = first.json()["next_cursor"]
    assert cursor
    second = client.get("/api/knowledge/entries", params={**params, "cursor": cursor})
    assert second.status_code == 200
    assert first.json()["entries"][0]["knowledge_id"] != second.json()["entries"][0]["knowledge_id"]
    assert client.get("/api/knowledge/entries", params=params).json() == first.json()
