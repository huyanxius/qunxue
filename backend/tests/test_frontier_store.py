import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from qunxue_api.adapters.sqlite.base import Base
from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.adapters.sqlite.frontier_models import (
    FrontierItemRow,
    FrontierRecordRow,
    FrontierSnapshotRow,
)
from qunxue_api.adapters.sqlite.frontier_repository import SqliteFrontierStore
from qunxue_api.api.routes.frontier import router
from qunxue_api.modules.frontier_knowledge import FrontierService
from qunxue_api.settings import Settings

SEED = json.loads((Path(__file__).parents[1] / "data/frontier-seed.json").read_text())


@pytest.fixture
def store(tmp_path):
    db = Database(f"sqlite:///{tmp_path}/frontier.db")
    tables = [t for t in Base.metadata.tables.values() if t.name.startswith("frontier_")]
    Base.metadata.create_all(db.engine, tables=tables)
    result = SqliteFrontierStore(db)
    yield result
    db.engine.dispose()


@pytest.fixture
def seeded(store):
    store.import_seed(SEED)
    return store


def test_seed_idempotency_and_provenance(seeded):
    assert seeded.import_seed(SEED) == {
        "created": 0,
        "unchanged": 12,
        "versions": 0,
        "duplicates": 0,
    }
    records = seeded.list_records()
    assert len(records) == 12
    assert sum(r["verification_status"] == "lead_only" for r in records) == 9
    for r in records:
        snapshot = seeded.get_snapshot(r["snapshot_id"])
        assert snapshot["content_hash"] == r["content_hash"]
        assert snapshot["source_id"] == r["source_id"]
        assert not snapshot["full_text_retained"]
        assert not r["eligibility"]["match"]
        assert not r["eligibility"]["training_candidate"]
        if r["verification_status"] == "lead_only":
            assert not r["eligibility"]["rag"]
            assert r["published_at"] is None
        assert all(e["block_id"].startswith(r["snapshot_id"]) for e in r["evidence"])


def test_changed_content_is_version_not_duplicate(seeded):
    changed = deepcopy(SEED)
    changed["records"] = [changed["records"][0]]
    changed["records"][0]["summary"] += " 已修订。"
    result = seeded.import_seed(changed)
    assert result["versions"] == 1
    assert len(seeded.list_records()) == 12
    original = seeded.get_record(SEED["records"][0]["id"])
    assert original["is_current"] is False
    updated = seeded.get_record(original["id"] + "@v2")
    assert updated["canonical_study_id"] == original["canonical_study_id"]
    assert updated["content_hash"] != original["content_hash"]


@pytest.mark.parametrize("level", ["doi", "title_author", "body_hash"])
def test_four_stage_dedupe_preserves_reprint_provenance(store, level):
    original = deepcopy(SEED["records"][0])
    original["doi"] = "https://doi.org/10.1234/example" if level == "doi" else None
    if level == "body_hash":
        original["source_snapshot"]["full_text"] = "公开授权正文。" * 50
    copy = deepcopy(original)
    copy["id"] += "-reprint"
    if level == "doi":
        copy["doi"] = "DOI:10.1234/EXAMPLE"
        copy["title"] += "副标题"
    if level == "body_hash":
        copy["title"] += "另一个题名"
        copy["authors"] = ["另一个署名"]
    assert store.import_seed({**SEED, "records": [original, copy]})["duplicates"] == 1
    records = store.list_records()
    assert len(records) == 2
    assert len({r["canonical_study_id"] for r in records}) == 1
    assert records[1]["reprint_of"] == records[0]["id"]
    assert records[1]["dedupe_level"] == level
    assert FrontierService(store).search()["total"] == 1


def test_metadata_hash_not_full_body_hash(seeded):
    with seeded.database.session() as session:
        assert all(r.body_hash is None for r in session.scalars(select(FrontierItemRow)))


def test_bad_host_and_false_verification_roll_back(store):
    records = deepcopy(SEED)
    records["records"][1]["url"] = "https://unapproved.example/paper"
    with pytest.raises(ValueError, match="approved"):
        store.import_seed(records)
    assert store.list_records() == []
    records = deepcopy(SEED)
    records["records"][0]["verification_status"] = "verified_frontier"
    with pytest.raises(ValueError, match="cannot publish"):
        store.import_seed(records)


def test_concurrent_seed_import_produces_one_version(store):
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: store.import_seed(SEED), range(2)))
    with store.database.session() as session:
        assert session.scalar(select(func.count()).select_from(FrontierRecordRow)) == 12
        assert session.scalar(select(func.count()).select_from(FrontierSnapshotRow)) == 12


def test_job_recovery_and_stale_worker_cas(seeded):
    job_id = seeded.enqueue("TREND", "all", "trend:1")
    assert seeded.enqueue("TREND", "all", "trend:1") == job_id
    first = seeded.claim_job(now=100, lease_seconds=10)
    assert seeded.claim_job(now=109) is None
    second = seeded.claim_job(now=110)
    assert first.job_id == second.job_id
    assert first.lease_token != second.lease_token
    assert not seeded.finish_job(first, now=111)
    with pytest.raises(ValueError, match="stale_worker_lease"):
        seeded.enqueue("TREND", "all", "stale-chain", job=first, now=111)
    assert seeded.finish_job(second, now=111)
    assert seeded.list_jobs()[0]["status"] == "completed"


def test_retry_backoff_and_final_failure(store):
    store.enqueue("TREND", "all", "trend")
    now = 0
    for attempt, delay in enumerate([30, 120, 600, 600], start=1):
        job = store.claim_job(now=now)
        assert job.attempt == attempt
        assert store.finish_job(job, now=now, status="retry", reason="safe_failure")
        assert store.claim_job(now=now + delay - 1) is None
        now += delay
    assert store.list_jobs()[0]["status"] == "failed"


def test_blocked_jobs_require_explicit_resume(store):
    store.enqueue("EXTRACT", "snapshot", "extract")
    job = store.claim_job(now=0)
    store.finish_job(job, now=1, status="blocked", reason="NotConfigured")
    assert store.claim_job(now=10000) is None
    assert store.resume_blocked() == 1
    assert store.claim_job(now=10000).attempt == 1


def test_final_crashed_attempt_is_terminal(store):
    store.enqueue("TREND", "all", "trend")
    for now in [0, 10, 20, 30]:
        assert store.claim_job(now=now, lease_seconds=10)
    assert store.claim_job(now=40) is None
    assert store.list_jobs()[0]["status"] == "failed"


def test_editorial_briefs_validate_references_and_expire_on_version(seeded):
    topic = FrontierService(seeded).topics()[0]
    brief = {
        "topic_key": topic["topic_key"],
        "stream": topic["stream"],
        "title": "照护安排",
        "summary": "家庭与机构的责任安排值得对照阅读",
        "why_it_matters": "比较照护责任的分配",
        "evidence_record_ids": topic["record_ids"],
        "generated_by": "offline_editorial",
    }
    assert seeded.import_briefs([brief]) == 1
    result = FrontierService(seeded).topics()[0]
    assert result["editorial_brief"]["basis_content_hash"]
    assert result["summary"] == brief["summary"]
    with pytest.raises(ValueError, match="current records"):
        seeded.import_briefs([{**brief, "evidence_record_ids": ["missing"]}])
    changed = deepcopy(SEED)
    for r in changed["records"]:
        if r["id"] in topic["record_ids"]:
            r["summary"] += "新版本"
    seeded.import_seed(changed)
    assert seeded.list_briefs() == []


def test_agent_leads_are_not_conclusion_evidence(seeded):
    result = FrontierService(seeded).search_frontier("")
    assert len(result["leads"]) == 9
    assert len(result["evidence"]) == 3
    assert all(
        r["usage"] == "literature_discovery_only_not_conclusion_evidence" for r in result["leads"]
    )


def test_api_search_pagination_detail_sources_and_metrics(seeded):
    app = FastAPI()
    app.state.frontier_store = seeded
    app.state.frontier_service = FrontierService(seeded)
    app.state.settings = Settings(_env_file=None)
    app.include_router(router)
    with TestClient(app) as client:
        page = client.get("/api/frontier/search?limit=5").json()
        next_page = client.get(f"/api/frontier/search?limit=5&offset={page['next_offset']}").json()
        assert page["total"] == 12
        assert not set(r["id"] for r in page["items"]) & set(r["id"] for r in next_page["items"])
        assert client.get("/api/frontier/search?q=医院").json()["total"] == 1
        assert (
            client.get("/api/frontier/search?stream=research&since_days=180").json()["total"] == 0
        )
        assert client.get("/api/frontier/search?limit=201").status_code == 422
        assert client.get("/api/frontier/records/missing").status_code == 404
        assert client.get(f"/api/frontier/records/{page['items'][0]['id']}").status_code == 200
        status = client.get("/api/frontier/status").json()
        assert status["extractor_status"] == "not_configured"
        assert status["verifier_status"] == "not_configured"
        assert status["verified_research_count"] == 0
        assert not status["automatic_collection"]
        assert all(
            t["trend_status"] == "insufficient_evidence"
            for t in client.get("/api/frontier/trends?as_of=2026-10-01").json()["items"]
        )
        assert client.get("/api/frontier/trends?window=60").status_code == 422
        assert len(client.get("/api/frontier/sources").json()["items"]) >= 6
        assert client.post("/api/frontier/import", json=SEED).status_code == 404


def test_legacy_model_keys_cannot_configure_frontier():
    settings = Settings(
        _env_file=None,
        model_api_key="unrelated-existing-key",
        embedding_api_key="another-existing-key",
    )
    assert settings.frontier_extractor_status == "not_configured"
    assert settings.frontier_verifier_status == "not_configured"


def test_large_corpus_is_paginated_without_fixed_seed_limit(store):
    records = []
    for i in range(151):
        record = deepcopy(SEED["records"][0])
        record["id"] = f"test-only-record-{i}"
        record["title"] = f"测试用文章{i}"
        records.append(record)
    store.import_seed({**SEED, "records": records})
    service = FrontierService(store)
    first = service.search(limit=100)
    second = service.search(limit=100, offset=first["next_offset"])
    assert first["total"] == 151
    assert len(second["items"]) == 51
    assert second["next_offset"] is None
    topics = service.topics(as_of=date(2026, 10, 1))
    assert all(t["trend_status"] == "insufficient_evidence" for t in topics)


def test_withdrawal_removes_public_topics_search_and_editorial(seeded):
    service = FrontierService(seeded)
    topic = service.topics()[0]
    record_id = topic["record_ids"][0]
    seeded.import_briefs(
        [
            {
                "topic_key": topic["topic_key"],
                "stream": topic["stream"],
                "title": "撤回测试",
                "summary": "仅引用该材料",
                "why_it_matters": "用于撤回测试",
                "evidence_record_ids": [record_id],
                "generated_by": "offline_editorial",
            }
        ]
    )
    assert seeded.withdraw(record_id)
    assert record_id not in {r["id"] for r in service.search(limit=200)["items"]}
    assert all(record_id not in t["record_ids"] for t in service.topics())
    assert seeded.list_briefs() == []


def test_import_timing_alone_does_not_make_new_record_version(seeded):
    later = deepcopy(SEED)
    for record in later["records"]:
        record["discovered_at"] = "2026-10-02"
        record["source_snapshot"]["captured_at"] = "2026-10-02"
    assert seeded.import_seed(later)["unchanged"] == 12


def test_local_corpus_source_lifecycle_and_default_disabled_schedule(store):
    from qunxue_api.bootstrap import create_frontier_worker

    store.configure_sources()
    assert store.schedule_sources(now=1234) == []
    settings = Settings(_env_file=None)
    worker = create_frontier_worker(settings, store, SEED)
    store.enqueue("DISCOVER", "sociological-studies", "replay:test")
    count = 0
    while count < 100 and worker.run_once(now=100):
        count += 1
    assert len(store.list_records()) == 5
    jobs = store.list_jobs()
    assert sum(j["stage"] == "FETCH" and j["status"] == "completed" for j in jobs) == 5
    assert sum(j["stage"] == "EXTRACT" and j["status"] == "blocked" for j in jobs) == 5
    assert all(j["error"] == "NotConfigured" for j in jobs if j["status"] == "blocked")
    source = next(s for s in store.list_sources() if s["source_id"] == "sociological-studies")
    assert source["cursor"]
    store.enqueue("DISCOVER", source["source_id"], "replay:second", {"cursor": source["cursor"]})
    assert worker.run_once(now=101)
    assert len(store.list_records()) == 5
    assert sum(j["stage"] == "FETCH" for j in store.list_jobs()) == 5


def test_historical_content_restore_creates_new_current_version(seeded):
    original = {**SEED, "records": [deepcopy(SEED["records"][0])]}
    changed = deepcopy(original)
    changed["records"][0]["summary"] = "B: revised input"
    assert seeded.import_seed(changed)["versions"] == 1
    assert seeded.import_seed(original)["versions"] == 1
    current = next(r for r in seeded.list_records() if r["item_id"] == original["records"][0]["id"])
    assert current["version"] == 3
    assert current["summary"] == original["records"][0]["summary"]
    assert current["snapshot_id"] == seeded.get_record(current["item_id"])["snapshot_id"]


def test_withdrawal_persists_across_reimports_and_old_version_links(seeded):
    record_id = SEED["records"][0]["id"]
    changed = {**SEED, "records": [deepcopy(SEED["records"][0])]}
    changed["records"][0]["summary"] = "B"
    seeded.import_seed(changed)
    assert seeded.withdraw(record_id)
    assert not seeded.get_record(record_id + "@v2")["eligibility"]["browse"]
    changed["records"][0]["summary"] = "C"
    seeded.import_seed(changed)
    assert not seeded.get_record(record_id + "@v3")["eligibility"]["browse"]
    assert not seeded.get_record(record_id)["eligibility"]["browse"]
    seeded.import_seed({**SEED, "records": [SEED["records"][0]]})
    assert not seeded.get_record(record_id + "@v4")["eligibility"]["browse"]


def test_collector_body_hash_dedup_does_not_claim_retained_full_text(store):
    record = deepcopy(SEED["records"][0])
    record["body_sha256"] = "a" * 64
    copied = {
        **deepcopy(record),
        "id": "reported-body-reprint",
        "title": "另一个标题",
        "authors": None,
    }
    result = store.import_seed({**SEED, "records": [record, copied]})
    assert result["duplicates"] == 1
    records = store.list_records()
    assert len({r["canonical_study_id"] for r in records}) == 1
    assert all(not r["full_text_retained"] for r in records)
    assert all(r["verification_status"] == "lead_only" for r in records)


def test_coverage_requires_complete_continuous_manifest_not_oldest_record(seeded):
    from qunxue_api.adapters.sqlite.frontier_models import FrontierSourceRow

    service = FrontierService(seeded)
    assert service.baseline_status(date(2026, 10, 1)) == "insufficient_evidence"
    with seeded.database.session() as session:
        for source in session.scalars(select(FrontierSourceRow)):
            source.config = {
                **source.config,
                "coverage_complete": True,
                "coverage_start": "2026-01-01",
                "coverage_end": "2026-10-01",
            }
    assert service.baseline_status(date(2026, 10, 1)) == "available"
    assert service.baseline_status(date(2026, 10, 2)) == "insufficient_evidence"


def test_withdrawal_serializes_with_concurrent_new_version(seeded):
    from threading import Event

    from sqlalchemy import event

    record_id = SEED["records"][0]["id"]
    changed = {**SEED, "records": [deepcopy(SEED["records"][0])]}
    changed["records"][0]["summary"] = "concurrent content update"
    started, completed = Event(), Event()
    futures = []
    pool = ThreadPoolExecutor(max_workers=1)

    def writer():
        started.set()
        try:
            return seeded.import_seed(changed)
        finally:
            completed.set()

    def launch_after_versions_selected(conn, cursor, statement, parameters, context, executemany):
        if "WHERE frontier_records.item_id = ?" in statement and not futures:
            futures.append(pool.submit(writer))
            assert started.wait(1)
            # Import must wait for withdrawal's writer lock; it cannot insert an
            # unobserved version between the version SELECT and the withdrawal commit.
            assert not completed.wait(0.1)

    event.listen(seeded.database.engine, "after_cursor_execute", launch_after_versions_selected)
    try:
        assert seeded.withdraw(record_id)
        assert futures[0].result(timeout=5)["versions"] == 1
    finally:
        event.remove(seeded.database.engine, "after_cursor_execute", launch_after_versions_selected)
        pool.shutdown(wait=True)
    assert not seeded.get_record(record_id + "@v2")["eligibility"]["browse"]
