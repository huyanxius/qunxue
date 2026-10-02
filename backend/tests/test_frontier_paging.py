"""Fast list invariants: SQL parity, bounded projection, cache invalidation."""

import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from qunxue_api.adapters.sqlite.base import Base
from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.adapters.sqlite.frontier_models import FrontierRecordRow
from qunxue_api.adapters.sqlite.frontier_repository import SqliteFrontierStore
from qunxue_api.api.routes.frontier import router
from qunxue_api.modules.frontier_knowledge import FrontierService, build_read_projection
from qunxue_api.modules.frontier_knowledge.periods import available_as_of

SEED = json.loads((Path(__file__).parents[1] / "data/frontier-seed.json").read_text())


@pytest.fixture
def store(tmp_path):
    database = Database(f"sqlite:///{tmp_path}/paging.db")
    Base.metadata.create_all(
        database.engine,
        tables=[
            table for table in Base.metadata.tables.values() if table.name.startswith("frontier_")
        ],
    )
    value = SqliteFrontierStore(database)
    value.import_seed(SEED)
    yield value
    database.engine.dispose()


def test_sql_filters_dedup_and_pagination_match_reference(store):
    # Cover canonical variants with tags unioned before source/text filtering.
    with store.database.session() as session:
        rows = list(session.scalars(select(FrontierRecordRow)))
        rows[1].canonical_study_id = rows[0].canonical_study_id
        rows[1].structured_json = {
            **rows[1].structured_json,
            "canonical_study_id": rows[0].canonical_study_id,
            "published_at": "2026-09-28",
            "published_at_precision": "day",
        }
    records = store.list_records()
    legacy = FrontierService(SimpleNamespace(list_records=lambda: records))
    sql = FrontierService(store)
    filters = [
        {},
        {"source_id": "", "material_type": ""},
        {"q": "社会"},
        {"stream": "research"},
        {"stream": "practice"},
        {"source_id": records[0]["source_id"]},
        {"since_days": 30},
        {"topic_id": "uncategorized-research"},
    ]
    filters += [{"topic_id": topic["id"]} for topic in sql.topics(detail=False)]
    for cutoff in (date(2026, 1, 1), date(2026, 9, 28), date(2026, 10, 2)):
        for query in filters:
            for offset in (0, 2, 100):
                for summaries in (False, True):
                    actual = sql.search(
                        **query, as_of=cutoff, limit=2, offset=offset, summaries=summaries
                    )
                    expected = legacy.search(
                        **query, as_of=cutoff, limit=2, offset=offset, summaries=summaries
                    )
                    assert actual == expected, (cutoff, query, offset, summaries)
    assert sql.search(summaries=True, focus=True) == legacy.search(summaries=True, focus=True)


@pytest.mark.parametrize(
    "precision,value,year",
    [
        ("day", "2026-09-28", 2026),
        ("day", "2026-02-30", None),
        ("month", "2026-09", 2026),
        ("year", "2026", 2026),
        ("issue", None, 2026),
        ("unknown", None, None),
        ("unknown", None, 2027),
    ],
)
def test_projection_preserves_historical_availability(precision, value, year):
    record = {
        **SEED["records"][0],
        "published_at_precision": precision,
        "published_at": value,
        "publication_year": year,
        "discovered_at": "2026-09-20",
    }
    projection = build_read_projection(record)
    for cutoff in (
        date(2025, 12, 31),
        date(2026, 9, 19),
        date(2026, 9, 20),
        date(2026, 9, 28),
        date(2026, 9, 30),
        date(2026, 12, 31),
        date(2027, 1, 1),
    ):
        actual = bool(
            projection["read_available_on"]
            and projection["read_available_on"] <= cutoff.isoformat()
        )
        assert actual == available_as_of(record, cutoff)


def test_summary_projection_does_not_read_full_records(store):
    with patch.object(store, "list_records", side_effect=AssertionError("unbounded read")):
        result = FrontierService(store).search(summaries=True, limit=2, as_of=date(2026, 10, 2))
    assert len(result["items"]) == 2
    assert result["total"] > 2
    assert result["next_offset"] == 2
    for row in result["items"]:
        assert len(row["summary"]) <= 280
        assert not {"evidence", "media", "analysis_evidence", "source_snapshot"} & row.keys()
    with store.database.session() as session:
        indexes = session.execute(text("PRAGMA index_list(frontier_records)")).all()
        assert "ix_frontier_browse_date_id" in {row[1] for row in indexes}


def test_public_cache_etag_and_cross_store_invalidation(store):
    app = FastAPI()
    app.state.frontier_store = store
    app.state.frontier_service = FrontierService(store)
    app.include_router(router)
    client = TestClient(app)
    url = "/api/frontier/summaries?as_of=2026-10-02&limit=2"
    first = client.get(url)
    assert first.status_code == 200
    assert first.headers["cache-control"] == "public, max-age=0, must-revalidate"
    etag = first.headers["etag"]
    with patch.object(store, "search_records", side_effect=AssertionError("cache missed")):
        assert client.get(url).json() == first.json()
        assert client.get(url, headers={"If-None-Match": etag}).status_code == 304
    # A separate writer instance invalidates the process-local response cache.
    writer = SqliteFrontierStore(store.database)
    assert writer.withdraw(first.json()["items"][0]["id"])
    second = client.get(url, headers={"If-None-Match": etag})
    assert second.status_code == 200
    assert second.headers["etag"] != etag
    assert second.json()["total"] == first.json()["total"] - 1
    changed = deepcopy(SEED)
    changed["records"] = [changed["records"][-1]]
    changed["records"][0]["title"] += " 新版本"
    revision = writer.read_revision()
    writer.import_seed(changed)
    assert writer.read_revision() > revision
    # Detail and personalized knowledge links are deliberately not public-cached.
    detail = client.get("/api/frontier/records/" + second.json()["items"][0]["id"])
    assert "cache-control" not in detail.headers


def test_light_topics_retain_sparklines_without_large_evidence(store):
    service = FrontierService(store)
    topics = service.topics(detail=False, as_of=date(2026, 10, 2))
    assert topics
    assert all(not topic["record_ids"] and not topic["evidence"] for topic in topics)
    assert all(
        not point["dated_record_ids"]
        for topic in topics
        for point in topic.get("monthly_series", [])
    )
    detail = service.topics(topic_id=topics[0]["id"], as_of=date(2026, 10, 2))
    assert len(detail) == 1
    assert detail[0]["record_ids"]


def test_summary_id_lookup_is_bounded_and_uses_same_visibility(store):
    service = FrontierService(store)
    page = service.search(summaries=True, as_of=date(2026, 10, 2))
    ids = [row["id"] for row in page["items"][:3]]
    result = service.search(summaries=True, record_ids=ids, as_of=date(2026, 10, 2))
    assert [row["id"] for row in result["items"]] == ids
    assert store.withdraw(ids[0])
    result = service.search(summaries=True, record_ids=ids, as_of=date(2026, 10, 2))
    assert [row["id"] for row in result["items"]] == ids[1:]
    app = FastAPI()
    app.state.frontier_store = store
    app.state.frontier_service = service
    app.include_router(router)
    client = TestClient(app)
    assert (
        client.get(
            "/api/frontier/summaries", params=[("record_ids", str(i)) for i in range(101)]
        ).status_code
        == 422
    )
