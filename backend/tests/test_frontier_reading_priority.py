import pytest
from frontier_reading_fixtures import import_real_corpus

from qunxue_api.modules.frontier_knowledge import value


def record_fixture():
    record = {
        "id": "paper",
        "title": "Paper",
        "version": 2,
        "content_hash": "sha256:record",
        "snapshot_id": "snapshot",
        "url": "https://example.org/paper",
        "analysis_scope": "abstract",
        "research_question": "What?",
        "methods": None,
        "data": None,
        "sample": None,
        "findings": ["Result"],
        "limitations": None,
        "evidence": [
            {
                "block_id": "b1",
                "locator": "Abstract paragraph 1",
                "snippet": "Question and result",
                "supports": ["research_question", "findings"],
                "url": "https://example.org/paper",
            }
        ],
    }
    snapshot = {
        "snapshot_id": "snapshot",
        "content_hash": "sha256:record",
        "source_verified": True,
        "scope": "metadata_and_short_excerpt",
        "blocks": [
            {
                "block_id": "b1",
                "locator": "Abstract paragraph 1",
                "text": "Question and result",
                "url": "https://example.org/paper",
            }
        ],
    }
    return record, snapshot


def evaluate(record, snapshot):
    evaluator = getattr(value, "assess_record_value", None)
    assert callable(evaluator), "record-bound value assessment is not wired"
    return evaluator(record, snapshot)


def test_source_abstract_supports_reading_without_fabricating_quality():
    record, snapshot = record_fixture()
    result = evaluate(record, snapshot)
    assert result["reading_priority"] == "abstract_supported"
    assert result["supported_fields"] == ["research_question", "findings"]
    assert result["assessment"]["status"] == "unassessed"
    assert result["assessment"]["academic_value"] is None
    assert "methods" in result["missing_fields"]
    assert result["basis"][0]["locator"] == "Abstract paragraph 1"
    assert not result["assessment"]["authorizes_publication"]


@pytest.mark.parametrize("break_binding", ["snapshot_hash", "snapshot_id", "locator", "snippet"])
def test_unbound_or_unlocated_evidence_cannot_improve_reading_priority(break_binding):
    record, snapshot = record_fixture()
    if break_binding == "snapshot_hash":
        snapshot["content_hash"] = "other"
    elif break_binding == "snapshot_id":
        snapshot["snapshot_id"] = "other"
    elif break_binding == "locator":
        record["evidence"][0]["locator"] = "invented location"
    else:
        record["evidence"][0]["snippet"] = "invented content"
    result = evaluate(record, snapshot)
    assert result["reading_priority"] == "metadata_only"
    assert result["basis"] == []
    assert result["assessment"]["academic_value"] is None


def reviewed_record():
    record, snapshot = record_fixture()
    record["analysis_scope"] = "full_text"
    snapshot["scope"] = "full_text"
    record["value_assessment"] = {
        "track": "empirical",
        "evidence_readiness": "human_reviewed",
        "ratings": {
            key: {
                "score": 3,
                "rationale": "Reviewed passage rationale",
                "evidence": [
                    {
                        "record_id": "paper",
                        "version": 2,
                        "snapshot_hash": "sha256:record",
                        "locator": "Abstract paragraph 1",
                        "reviewed_by": "test-reviewer",
                    }
                ],
            }
            for key in value.WEIGHTS
        },
    }
    return record, snapshot


def test_reviewed_fixture_exposes_weights_and_reasons_and_version_binding():
    record, snapshot = reviewed_record()
    result = evaluate(record, snapshot)
    assert result["assessment"]["status"] == "assessed"
    assert result["assessment"]["academic_value"] == 75
    assert result["assessment"]["criteria"]["contribution_increment"]["weight"] == 30
    assert result["assessment"]["criteria"]["contribution_increment"]["rationale"]
    record["version"] = 3
    stale = evaluate(record, snapshot)
    assert stale["assessment"]["academic_value"] is None
    assert (
        stale["assessment"]["missing_reasons"]["warrantedness"]
        == "record_snapshot_binding_required"
    )


def test_partial_ratings_do_not_renormalize_and_abstract_ratings_are_rejected():
    record, snapshot = reviewed_record()
    record["value_assessment"]["ratings"].pop("warrantedness")
    result = evaluate(record, snapshot)
    assert result["assessment"]["status"] == "partial"
    assert result["assessment"]["academic_value"] is None
    record["analysis_scope"] = "abstract"
    snapshot["scope"] = "metadata_and_short_excerpt"
    result = evaluate(record, snapshot)
    assert result["assessment"]["status"] == "unassessed"
    assert result["assessment"]["academic_value"] is None


def test_missing_snapshot_and_malformed_stored_ratings_fall_back():
    record, _ = reviewed_record()
    record["value_assessment"]["ratings"]["warrantedness"]["score"] = "4"
    assert evaluate(record, None)["assessment"]["academic_value"] is None


def test_reading_routes_search_before_paginating_and_apply_as_of(plain_client):
    import_real_corpus(plain_client)
    response = plain_client.get(
        "/api/frontier/reading-priorities",
        params={"as_of": "2026-10-01", "readiness": "abstract_supported", "limit": 1},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] > 1
    assert len(body["items"]) == 1
    assert body["items"][0]["assessment"]["academic_value"] is None
    record_id = body["items"][0]["record_id"]
    detail = plain_client.get(
        f"/api/frontier/records/{record_id}/reading-priority", params={"as_of": "2026-10-01"}
    )
    assert detail.status_code == 200
    assert detail.json()["record_id"] == record_id
    assert (
        plain_client.get(
            f"/api/frontier/records/{record_id}/reading-priority", params={"as_of": "1900-01-01"}
        ).status_code
        == 404
    )
    assert (
        plain_client.get(
            "/api/frontier/reading-priorities", params={"readiness": "quality"}
        ).status_code
        == 422
    )
    assert plain_client.post("/api/frontier/reading-priorities").status_code == 405


def test_hash_bound_assistant_reading_note_can_support_reading_without_quality():
    import hashlib

    record, snapshot = record_fixture()
    record["evidence"][0].pop("snippet")
    record["evidence"][0]["supports"] = ["abstract"]
    snapshot["blocks"][0]["text"] = ""
    source = "Synthetic source abstract used only in this test."
    record["internal_source_content"] = {"abstract": source}
    snapshot["original_input"] = {"internal_source_content": {"abstract": source}}
    record["reading_note_review_type"] = "assistant_abstract_reading"
    record["reading_note_basis_sha256"] = hashlib.sha256(source.encode()).hexdigest()
    record["analysis_evidence"] = [
        {"field": "research_question", "statement": "What?", "evidence_indexes": [0]}
    ]
    result = evaluate(record, snapshot)
    assert result["reading_priority"] == "abstract_supported"
    assert result["supported_fields"] == ["research_question"]
    assert result["basis"][0]["basis_type"] == "assistant_abstract_reading"
    assert result["basis"][0]["snippet"] == ""
    assert source not in str(result)
    assert result["assessment"]["academic_value"] is None
    record["reading_note_basis_sha256"] = "outdated"
    assert evaluate(record, snapshot)["reading_priority"] == "metadata_only"


def test_value_threshold_never_treats_unassessed_as_a_scored_candidate(plain_client):
    import_real_corpus(plain_client)
    response = plain_client.get(
        "/api/frontier/reading-priorities", params={"as_of": "2026-10-01", "min_academic_value": 50}
    )
    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert (
        plain_client.get(
            "/api/frontier/reading-priorities", params={"min_academic_value": 101}
        ).status_code
        == 422
    )


def test_closeout_real_note_and_unassessed_metadata_paths(plain_client):
    import os

    if not os.environ.get("QUNXUE_READING_CORPUS"):
        pytest.skip("optional closeout corpus integration; set QUNXUE_READING_CORPUS")
    import_real_corpus(plain_client)
    store = plain_client.app.state.frontier_store
    positive = next(r for r in store.list_records() if "shxyj-121906" in r["id"])
    negative = next(r for r in store.list_records() if "shxyj-117819" in r["id"])
    for record, expected in [(positive, "abstract_supported"), (negative, "metadata_only")]:
        response = plain_client.get(
            f"/api/frontier/records/{record['id']}/reading-priority", params={"as_of": "2026-10-02"}
        )
        assert response.status_code == 200
        result = response.json()
        assert result["reading_priority"] == expected
        assert result["assessment"]["academic_value"] is None
        assert result["assessment"]["status"] == "unassessed"
        assert "internal_source_content" not in result
        internal = record["internal_source_content"].get("abstract")
        if internal:
            assert internal not in str(result)
    assert positive["reading_note_review_type"] == "assistant_abstract_reading"


@pytest.mark.parametrize(
    "source",
    [
        "完整内部摘要：仅供内部核验，不应成为公开接口的摘录。" * 10,
        " ".join(f"privateword{i}" for i in range(100)),
        '{"private_original_response": "' + "internal-response-content-" * 50 + '"}',
    ],
    ids=["chinese_abstract", "english_abstract", "raw_response"],
)
def test_complete_private_source_in_evidence_is_not_exported_as_a_public_snippet(source):
    record, snapshot = record_fixture()
    record["internal_source_content"] = {"abstract": source}
    record["evidence"][0]["snippet"] = source
    snapshot["blocks"][0]["text"] = source
    snapshot["original_input"] = {"internal_source_content": {"abstract": source}}
    result = evaluate(record, snapshot)
    assert result["reading_priority"] == "abstract_supported"
    assert result["supported_fields"] == ["research_question", "findings"]
    assert result["basis"][0]["url"] == "https://example.org/paper"
    assert result["basis"][0]["locator"] == "Abstract paragraph 1"
    assert result["basis"][0]["snippet"] == ""
    assert source not in str(result)
    # The internal source evidence remains intact for the domain's verification.
    assert value.reading_basis(record, snapshot)[0]["snippet"] == source


def test_public_reading_endpoint_retains_citations_without_returning_a_private_abstract():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from qunxue_api.api.routes.frontier import router
    from qunxue_api.application.frontier_reading_priority import FrontierReadingPriority
    from qunxue_api.modules.frontier_knowledge import FrontierService

    source = "Synthetic private abstract. " * 100
    record, snapshot = record_fixture()
    record.update(
        {
            "eligibility": {"browse": True},
            "is_current": True,
            "published_at": "2026-01-01",
            "published_at_precision": "day",
            "internal_source_content": {"abstract": source},
        }
    )
    record["evidence"][0]["snippet"] = source
    snapshot["blocks"][0]["text"] = source

    class Store:
        def get_record(self, record_id):
            return record if record_id == "paper" else None

        def get_snapshot(self, snapshot_id):
            return snapshot

    app = FastAPI()
    store = Store()
    app.state.frontier_reading_priority = FrontierReadingPriority(store, FrontierService(store))
    app.include_router(router)
    with TestClient(app) as client:
        response = client.get(
            "/api/frontier/records/paper/reading-priority", params={"as_of": "2026-10-01"}
        )
    assert response.status_code == 200
    assert source not in response.text
    assert response.json()["basis"][0]["snippet"] == ""
    assert response.json()["reading_priority"] == "abstract_supported"
    assert record["evidence"][0]["snippet"] == source
