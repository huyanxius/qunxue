# ruff: noqa: F811
from copy import deepcopy
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_frontier_store import SEED, seeded, store  # noqa: F401

from qunxue_api.api.routes.frontier import router
from qunxue_api.modules.frontier_knowledge import FrontierService, topic_series
from qunxue_api.settings import Settings


def brief_for_topic(seeded):
    topic = next(t for t in FrontierService(seeded).topics() if t["id"] == "care-family-research")
    ids = topic["record_ids"][:2]
    statement = {"text": "测试用证据陈述", "evidence_record_ids": ids}
    return {
        "topic_key": topic["topic_key"],
        "stream": "research",
        "title": "旧标题",
        "summary": "有来源的摘要",
        "why_it_matters": "研究意义",
        "evidence_record_ids": ids,
        "generated_by": "assistant_evidence_synthesis",
        "research_brief": {
            "headline": "照护责任如何在家庭和组织间分配",
            "development": statement,
            "consensus": [statement],
            "differences": [statement],
            "methods": [],
            "research_implication": statement,
            "priority_reads": [{"record_id": ids[0], "reason": "比较起点"}],
            "evidence_record_ids": ids,
        },
    }


def test_rich_brief_round_trip_and_old_contract_fallback(seeded):
    brief = brief_for_topic(seeded)
    assert seeded.import_briefs([brief]) == 1
    topic = next(t for t in FrontierService(seeded).topics() if t["id"] == "care-family-research")
    rich = topic["research_brief"]
    assert rich["headline"] == brief["research_brief"]["headline"]
    assert rich["generated_by"] == "assistant_evidence_synthesis"
    assert len(rich["basis_content_hash"]) == 64
    assert rich["consensus"][0]["evidence_record_ids"] == brief["evidence_record_ids"]
    assert topic["editorial_brief"]["summary"] == brief["summary"]
    older = {key: value for key, value in brief.items() if key != "research_brief"}
    older["generated_by"] = "offline_editorial"
    seeded.import_briefs([older])
    assert (
        next(t for t in FrontierService(seeded).topics() if t["id"] == topic["id"])[
            "research_brief"
        ]
        is None
    )


@pytest.mark.parametrize("path", ["evidence", "consensus", "priority", "single_consensus"])
def test_rich_brief_rejects_unsupported_cross_record_references(seeded, path):
    brief = brief_for_topic(seeded)
    rich = brief["research_brief"]
    if path == "evidence":
        rich["evidence_record_ids"] = ["missing"]
    elif path == "consensus":
        rich["consensus"][0] = {"text": "不合法引用", "evidence_record_ids": ["missing"]}
    elif path == "priority":
        rich["priority_reads"][0]["record_id"] = "missing"
    else:
        rich["consensus"][0] = {
            "text": "单篇不等于共识",
            "evidence_record_ids": rich["evidence_record_ids"][:1],
        }
    with pytest.raises(ValueError):
        seeded.import_briefs([brief])
    assert seeded.list_briefs() == []


def test_rich_brief_references_resolve_current_item_version_and_invalidate(seeded):
    brief = brief_for_topic(seeded)
    target = brief["evidence_record_ids"][0]
    original = next(r for r in SEED["records"] if r["id"] == target)
    changed = deepcopy(original)
    changed["summary"] += "新资料解释"
    seeded.import_seed({**SEED, "records": [changed]})
    seeded.import_briefs([brief])
    persisted = seeded.list_briefs()[0]
    assert f"{target}@v2" in persisted["research_brief"]["evidence_record_ids"]
    assert f"{target}@v2" in persisted["research_brief"]["development"]["evidence_record_ids"]
    seeded.withdraw(f"{target}@v2")
    assert seeded.list_briefs() == []


def test_explicit_assistant_paper_provenance_and_sentence_evidence_are_preserved(store):
    record = deepcopy(SEED["records"][0])
    record.update(
        {
            "algorithm_harvested": True,
            "extraction_method": "assistant_evidence_synthesis",
            "summary_method": "assistant_evidence_synthesis",
            "analysis_scope": "abstract",
            "why_read": "用于比较组织安排",
            "analysis_evidence": [
                {"field": "summary", "statement": record["summary"], "evidence_indexes": [0]}
            ],
        }
    )
    store.import_seed({**SEED, "records": [record]})
    saved = store.list_records()[0]
    assert saved["extraction_method"] == "assistant_evidence_synthesis"
    assert saved["verification_status"] == "lead_only"
    assert not saved["eligibility"]["rag"]
    assert saved["analysis_scope"] == "abstract"
    assert saved["why_read"] == record["why_read"]
    record["analysis_evidence"][0]["evidence_indexes"] = [999]
    with pytest.raises(ValueError, match="indexes"):
        store.import_seed({**SEED, "records": [record]})


def test_lead_cannot_claim_full_text_synthesis(store):
    record = {**deepcopy(SEED["records"][0]), "analysis_scope": "full_text"}
    with pytest.raises(ValueError, match="cannot claim"):
        store.import_seed({**SEED, "records": [record]})


@pytest.mark.parametrize("tag", ["乡村建设", "社区参与"])
def test_rural_participation_source_keywords_map_without_fixed_record_ids(store, tag):
    record = {**deepcopy(SEED["records"][0]), "topics": [tag]}
    store.import_seed({**SEED, "records": [record]})
    topic = next(t for t in FrontierService(store).topics() if t["id"] == "urban-rural-research")
    assert topic["record_ids"] == [record["id"]]


def test_monthly_series_has_true_denominator_dedup_and_unknown_date_exclusion(seeded):
    records = seeded.list_records()
    one = {**records[0], "published_at": "2026-09-15", "published_at_precision": "day"}
    duplicate = {**one, "id": "reprint"}
    unrelated = {**records[1], "published_at": "2026-09-20", "published_at_precision": "day"}
    future = {**records[2], "published_at": "2026-10-20", "published_at_precision": "day"}
    topic = {"stream": "research", "record_ids": [one["id"], "reprint", future["id"]]}
    result = topic_series(
        topic, [one, duplicate, unrelated, future, records[3]], [], [], date(2026, 10, 1)
    )
    september = next(point for point in result["monthly_series"] if point["month"] == "2026-09")
    assert september["record_count"] == 1
    assert september["denominator"] == 2
    assert september["sample_share"] == 0.5
    assert september["normalized_share"] is None
    assert set(september["dated_record_ids"]) == {one["id"], "reprint"}
    assert len(result["monthly_series"]) == 12
    assert result["monthly_series"][-1]["is_partial_month"]
    assert result["monthly_series"][-1]["record_count"] == 0


def test_conflicting_dates_do_not_pick_a_favorable_month(seeded):
    record = {
        **seeded.list_records()[0],
        "published_at": "2026-09-01",
        "published_at_precision": "day",
    }
    duplicate = {**record, "id": "other-date", "published_at": "2026-08-01"}
    result = topic_series(
        {"stream": "research", "record_ids": [record["id"], duplicate["id"]]},
        [record, duplicate],
        [],
        [],
        date(2026, 10, 1),
    )
    assert all(point["record_count"] == 0 for point in result["monthly_series"])


@pytest.mark.parametrize(
    ("second_issue", "expected_status"),
    [(1, "complete_issue_cohort"), (2, "sample_distribution_only")],
)
def test_issue_coverage_needs_actual_complete_denominator_and_same_source(
    store, second_issue, expected_status
):
    records = []
    manifests = []
    for year in (2025, 2026):
        issue = second_issue if year == 2026 else 1
        for index in range(2):
            record = deepcopy(SEED["records"][0])
            record.update(
                {
                    "id": f"issue-{year}-paper-{index}",
                    "title": f"测试{year}-{index}",
                    "publication_year": year,
                    "publication_issue": issue,
                    "published_at": f"{year}-0{issue}-20",
                    "published_at_precision": "day",
                }
            )
            record.update(
                {
                    "extraction_method": "assistant_evidence_synthesis",
                    "analysis_scope": "abstract",
                    "why_read": "测试用释义阅读理由",
                    "analysis_evidence": [
                        {
                            "field": "summary",
                            "statement": record["summary"],
                            "evidence_indexes": [0],
                        }
                    ],
                }
            )
            records.append(record)
        manifests.append(
            {
                "source_name": "社会学研究",
                "publication_year": year,
                "publication_issue": issue,
                "publication_month": f"{year}-0{issue}",
                "candidate_count": 2,
                "readable_count": 2,
                "included_count": 2,
                "coverage_complete": True,
                "issue_url": "https://sociology.nju.edu.cn/issue",
            }
        )
    store.import_seed({**SEED, "records": records, "issue_coverage": manifests})
    topic = next(t for t in FrontierService(store).topics() if t["id"] == "organization-research")
    assert len(topic["issue_series"]) == 2
    assert all(point["share"] == 1 for point in topic["issue_series"])
    assert topic["series_metadata"]["comparison_status"] == expected_status
    store.withdraw(records[0]["id"])
    topic = next(t for t in FrontierService(store).topics() if t["id"] == "organization-research")
    first = topic["issue_series"][0]
    assert first["coverage_complete"] is False
    assert first["share"] is None
    assert topic["series_metadata"]["comparison_status"] == "sample_distribution_only"


def test_old_api_corpus_adds_series_without_paid_network_or_brief_requirement(seeded):
    app = FastAPI()
    app.state.frontier_store = seeded
    app.state.frontier_service = FrontierService(seeded)
    app.state.settings = Settings(_env_file=None)
    app.include_router(router)
    response = TestClient(app).get("/api/frontier/topics?as_of=2026-10-01")
    assert response.status_code == 200
    topic = response.json()["items"][0]
    assert topic["research_brief"] is None
    assert topic["issue_series"] == []
    assert len(topic["monthly_series"]) == 12
    assert topic["series_metadata"]["comparison_status"] == "sample_distribution_only"


def test_article_media_is_attributed_and_preserved_without_fetching(store):
    record = deepcopy(SEED["records"][0])
    record["media"] = [
        {
            "url": "https://sociology.nju.edu.cn/images/article-figure.png",
            "caption": "来源正文图",
            "source_url": record["url"],
            "kind": "figure",
            "alt": "组织关系图",
        }
    ]
    store.import_seed({**SEED, "records": [record]})
    assert store.list_records()[0]["media"] == record["media"]
    assert store.list_records()[0]["verification_status"] == "lead_only"


@pytest.mark.parametrize(
    "change",
    [
        {"url": "https://unapproved.example/figure.png"},
        {"url": "http://sociology.nju.edu.cn/figure.png"},
        {"kind": "logo"},
        {"url": "https://user:secret@sociology.nju.edu.cn/figure.png"},
        {"source_url": "https://unapproved.example/article"},
    ],
)
def test_media_rejects_arbitrary_hosts_credentials_and_non_content_images(store, change):
    record = deepcopy(SEED["records"][0])
    record["media"] = [
        {
            "url": "https://sociology.nju.edu.cn/figure.png",
            "caption": "图",
            "source_url": record["url"],
            "kind": "figure",
            **change,
        }
    ]
    with pytest.raises(ValueError, match="media"):
        store.import_seed({**SEED, "records": [record]})
    assert store.list_records() == []


def test_unknown_issue_month_is_retained_but_never_invented_on_time_axis(store):
    record = deepcopy(SEED["records"][0])
    coverage = {
        "source_name": record["source_name"],
        "publication_year": 2026,
        "publication_issue": record["publication_issue"],
        "publication_month": None,
        "candidate_count": 1,
        "readable_count": 1,
        "included_count": 1,
        "coverage_complete": False,
        "issue_url": record["url"],
    }
    store.import_seed({**SEED, "records": [record], "issue_coverage": [coverage]})
    assert store.list_issue_coverage()[0]["publication_month"] is None
    assert all(not topic["issue_series"] for topic in FrontierService(store).topics())


def test_claimed_complete_metadata_pool_cannot_supply_comparable_synthesis_shares(store):
    record = deepcopy(SEED["records"][0])
    coverage = {
        "source_name": record["source_name"],
        "publication_year": 2026,
        "publication_issue": record["publication_issue"],
        "publication_month": "2026-07",
        "candidate_count": 1,
        "readable_count": 1,
        "included_count": 1,
        "coverage_complete": True,
        "issue_url": record["url"],
    }
    store.import_seed({**SEED, "records": [record], "issue_coverage": [coverage]})
    point = FrontierService(store).topics()[0]["issue_series"][0]
    assert point["analyzed_count"] == 0
    assert not point["coverage_complete"]
    assert point["share"] is None
