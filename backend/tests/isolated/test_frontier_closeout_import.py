from qunxue_api.adapters.sqlite.base import Base
from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.adapters.sqlite.frontier_repository import SqliteFrontierStore


def store():
    db = Database("sqlite:///:memory:")
    Base.metadata.create_all(db.engine)
    return SqliteFrontierStore(db)


def record(item, year=2023, issue=1):
    return dict(
        id=item,
        external_id=item,
        title="编后语",
        authors=["编辑部"],
        source_name="青年研究",
        source_publisher="青年研究",
        url=f"https://m.ncpssd.org/Literature/articleinfo?id={item}",
        publication_year=year,
        publication_issue=issue,
        published_at=None,
        published_at_precision="issue",
        published_at_display=f"{year}年第{issue}期",
        material_type="research_abstract",
        verification_status="lead_only",
        verification_note="公开元数据已核，全文未读",
        evidence=[
            {
                "url": f"https://m.ncpssd.org/Literature/articleinfo?id={item}",
                "locator": "public metadata",
            }
        ],
        summary="",
        topics=[],
        findings=[],
        display_ready=True,
        source_scope="public_abstract_metadata",
    )


def test_same_title_author_different_issue_is_not_same_study():
    s = store()
    s.import_seed(
        {
            "generated_at": "2026-10-01T20:00:00Z",
            "records": [record("one", 2023, 1), record("two", 2023, 2), record("copy", 2023, 1)],
        }
    )
    rows = s.list_records()
    ids = {r["item_id"]: r["canonical_study_id"] for r in rows}
    assert ids["one"] != ids["two"]
    assert ids["one"] == ids["copy"]


def test_fixed_issue_coverage_retains_year_precision_and_provenance():
    s = store()
    ledger = dict(
        source_id="youth-studies",
        issue_id="fixed:youth-studies:2023:1",
        period="2023",
        period_precision="year",
        publication_year=2023,
        coverage_scope="fixed_issue_sample",
        issue_ids=["youth-studies:2023:1"],
        comparison_issue_keys=["1"],
        coverage_complete=True,
        candidate_count=1,
        readable_count=1,
        included_count=1,
        analyzed_count=1,
        excluded_nonresearch_count=0,
        evidence_refs=["snapshot:sha256:abc"],
        issue_url="https://m.ncpssd.org/journal/details?gch=80985X&years=2023&num=1",
    )
    s.import_seed(
        {
            "generated_at": "2026-10-01T20:00:00Z",
            "records": [record("one")],
            "issue_coverage": [ledger],
        }
    )
    actual = s.list_issue_coverage()[0]
    assert actual["period"] == "2023"
    assert actual["coverage_scope"] == "fixed_issue_sample"
    assert actual["comparison_issue_keys"] == ["1"]
    assert actual["publication_month"] is None
    assert actual["evidence_refs"] == ledger["evidence_refs"]
    assert all(not source["coverage_complete"] for source in s.list_sources())


def test_newspaper_metadata_is_browsable_but_not_body_rag():
    s = store()
    r = record("news")
    r.update(
        source_name="中国社会工作报",
        authors=None,
        url="https://www.zyshgzb.gov.cn/n1/2025/0101/c459911-40393584.html",
        material_type="official_practice",
        verification_status="practice_signal",
        source_scope="newspaper_metadata_only",
        evidence=[
            {
                "url": "https://www.zyshgzb.gov.cn/n1/2025/0101/c459911-40393584.html",
                "locator": "official article metadata",
            }
        ],
    )
    s.import_seed({"generated_at": "2026-10-01T20:00:00Z", "records": [r]})
    row = s.list_records()[0]
    assert row["eligibility"]["browse"]
    assert not row["eligibility"]["rag"]


def test_public_record_response_removes_internal_source_content():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from qunxue_api.api.routes.frontier import router

    s = store()
    r = record("protected")
    r.update(
        internal_source_content={"abstract": "protected-source-abstract"},
        original_source_record={"abstract": "protected-source-abstract"},
        abstract="protected-source-abstract",
        abstract_en="protected-english-abstract",
        future_private_payload={"raw_response": "unknown-private-content"},
    )
    s.import_seed({"generated_at": "2026-10-01T20:00:00Z", "records": [r]})
    actual = s.list_records()[0]
    app = FastAPI()
    app.include_router(router)
    from types import SimpleNamespace

    app.state.frontier_service = SimpleNamespace(record=lambda _, as_of=None: actual)
    response = TestClient(app).get("/api/frontier/records/" + actual["id"])
    assert response.status_code == 200
    assert "protected-source-abstract" not in response.text
    assert "internal_source_content" not in response.json()
    assert "protected-english-abstract" not in response.text
    assert "unknown-private-content" not in response.text
    assert "future_private_payload" not in response.json()


def test_manual_review_never_enters_worker_queue():
    s = store()
    first = s.queue_manual_review(
        "pending-source", "review:one", {"reason": "missing public abstract"}
    )
    assert s.queue_manual_review("pending-source", "review:one", {}) == first
    assert s.list_jobs()[0]["status"] == "blocked"
    assert s.resume_blocked() == 0
    assert s.claim_job(now=1) is None
