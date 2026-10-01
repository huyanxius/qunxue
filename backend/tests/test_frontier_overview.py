# ruff: noqa: F811
import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_frontier_store import SEED, store  # noqa: F401

from qunxue_api.adapters.sqlite.frontier_repository import SqliteFrontierStore
from qunxue_api.api.routes.frontier import router
from qunxue_api.json_shards import load_json
from qunxue_api.modules.frontier_knowledge import FrontierService, visible_corpus_records


@pytest.fixture
def analyzed(store):
    corpus = deepcopy(SEED)
    for record in corpus["records"]:
        record.update(
            summary_method="assistant_evidence_synthesis",
            extraction_method="assistant_evidence_synthesis",
            analysis_evidence=[
                {"field": "summary", "statement": record["summary"], "evidence_indexes": [0]}
            ],
        )
    store.import_seed(corpus)
    return store, corpus


def make_overview(store):
    records = [
        r
        for r in visible_corpus_records(store.list_records())
        if r["material_type"] != "official_practice"
    ]
    ids = [r["id"] for r in records]
    return {
        "headline": "测试语料共同关注",
        "summary": "测试用全量综述",
        "scope": {
            "stream": "research",
            "coverage_record_ids": ids,
            "systematic_review_method": "逐篇审读摘要及结构化证据",
        },
        "reviewed_record_ids": ids,
        "review_index": [
            {"record_id": r["id"], "summary_sha256": sha256(r["summary"].encode()).hexdigest()}
            for r in records
        ],
        "generated_by": "assistant_evidence_synthesis",
        "sections": [
            {
                "id": key,
                "title": key,
                "statements": [{"text": "测试陈述", "evidence_record_ids": ids[:2]}],
            }
            for key in (
                "shared_focus",
                "change",
                "methods",
                "differences",
                "research_opportunities",
            )
        ],
    }


def test_overview_persisted_public_api_uses_complete_scope_and_no_models(analyzed):
    store, _ = analyzed
    assert store.import_corpus_overview(make_overview(store))["analyzed_record_count"] == 9
    reopened = SqliteFrontierStore(store.database)

    class PaidProviderMustNotRun:
        status = "ready"

        def search(self, *args):
            raise AssertionError("public overview must not call a provider")

    app = FastAPI()
    app.state.frontier_service = FrontierService(reopened, PaidProviderMustNotRun())
    app.include_router(router)
    response = TestClient(app).get("/api/frontier/overview?as_of=2026-10-01")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["statistics"]["research_count"] == 9
    assert body["statistics"]["practice_count"] == 3
    assert body["overview"]["scope"]["analyzed_record_count"] == 9
    assert len(body["overview"]["source_hashes"]) == 9
    assert len(body["overview"]["basis_content_hash"]) == 64
    assert "review_index" not in body["overview"]
    assert store.list_briefs() == []


@pytest.mark.parametrize(
    "bad",
    [
        "coverage",
        "reviewed",
        "hash",
        "index",
        "claims",
        "single",
        "sections",
        "practice",
        "provenance",
    ],
)
def test_overview_rejects_false_coverage_or_untraceable_claims(analyzed, bad):
    store, _ = analyzed
    value = make_overview(store)
    if bad == "coverage":
        value["scope"]["coverage_record_ids"] = value["scope"]["coverage_record_ids"][:-1]
    elif bad == "reviewed":
        value["reviewed_record_ids"] = []
    elif bad == "hash":
        value["review_index"][0]["summary_sha256"] = "not-current"
    elif bad == "index":
        value["review_index"][0] = value["review_index"][1]
    elif bad == "claims":
        value["sections"][0]["statements"][0]["evidence_record_ids"] = ["missing"]
    elif bad == "single":
        value["sections"][0]["statements"][0]["evidence_record_ids"] = value["reviewed_record_ids"][
            :1
        ]
    elif bad == "sections":
        value["sections"] = value["sections"][:-1]
    elif bad == "practice":
        value["scope"]["stream"] = "practice"
    else:
        value["generated_by"] = "guessed_from_titles"
    with pytest.raises(ValueError):
        store.import_corpus_overview(value)
    assert store.get_corpus_overview() is None


@pytest.mark.parametrize("change", ["withdraw", "version", "addition"])
def test_overview_invalidates_on_any_research_corpus_drift(analyzed, change):
    store, corpus = analyzed
    store.import_corpus_overview(make_overview(store))
    record = deepcopy(corpus["records"][0])
    if change == "withdraw":
        store.withdraw(record["id"])
    else:
        if change == "version":
            record["summary"] += "新版本"
        else:
            record["id"] += "-new-study"
            record["title"] += "不同研究"
        store.import_seed({**corpus, "records": [record]})
    body = FrontierService(store).overview()
    assert body["status"] == "stale"
    assert body["overview"] is None


def test_unconfigured_overview_still_returns_actual_statistics(analyzed):
    store, _ = analyzed
    body = FrontierService(store).overview()
    assert body["status"] == "not_configured" and body["overview"] is None
    assert body["statistics"]["research_count"] == 9


def test_practice_changes_do_not_invalidate_research_only_overview(analyzed):
    store, corpus = analyzed
    store.import_corpus_overview(make_overview(store))
    practice = next(r for r in corpus["records"] if r["material_type"] == "official_practice")
    store.withdraw(practice["id"])
    body = FrontierService(store).overview()
    assert body["status"] == "ready"
    assert body["statistics"]["practice_count"] == 2


def test_overview_cannot_claim_unanalyzed_metadata_as_full_coverage(store):
    store.import_seed(SEED)
    with pytest.raises(ValueError, match="evidence-linked assistant summaries"):
        store.import_corpus_overview(make_overview(store))


def test_overview_deduplicates_reprints_but_keeps_practice_separate(analyzed):
    store, corpus = analyzed
    reprint = deepcopy(corpus["records"][0])
    reprint["id"] += "-reprint"
    assert store.import_seed({**corpus, "records": [reprint]})["duplicates"] == 1
    store.import_corpus_overview(make_overview(store))
    body = FrontierService(store).overview()
    assert body["overview"]["scope"]["analyzed_record_count"] == 9
    assert body["statistics"]["research_count"] == 9
    assert body["statistics"]["practice_count"] == 3


def test_shipped_overview_matches_all_analyzed_research_and_current_hashes(store):
    folder = Path(__file__).parents[1] / "data"
    store.import_seed(load_json(folder / "frontier-corpus.json"))
    records = [r for r in store.list_records() if r["material_type"] != "official_practice"]
    assert len(records) >= 150
    assert all(
        r.get("summary_method") == "assistant_evidence_synthesis" and r.get("analysis_evidence")
        for r in records
    )
    value = json.loads((folder / "frontier-corpus-overview.json").read_text())
    store.import_corpus_overview(value)
    response = FrontierService(store).overview()
    assert response["status"] == "ready"
    assert response["overview"]["scope"]["analyzed_record_count"] == len(records)
    assert set(response["overview"]["scope"]["coverage_record_ids"]) == {r["id"] for r in records}
    assert response["overview"]["source_hashes"] == sorted(
        ({"record_id": r["id"], "content_hash": r["content_hash"]} for r in records),
        key=lambda row: row["record_id"],
    )
