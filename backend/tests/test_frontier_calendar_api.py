from fastapi import FastAPI
from fastapi.testclient import TestClient

from qunxue_api.api.routes.frontier import router
from qunxue_api.modules.frontier_knowledge import FrontierService


class CalendarStore:
    def list_records(self):
        return [
            {
                "id": "day",
                "canonical_study_id": "a",
                "published_at": "2026-01-15",
                "published_at_precision": "day",
                "eligibility": {"browse": True},
            },
            {
                "id": "month",
                "canonical_study_id": "b",
                "published_at": "2026-01",
                "published_at_precision": "month",
                "eligibility": {"browse": True},
            },
        ]


def test_calendar_contract_and_date_precision():
    app = FastAPI()
    app.state.frontier_service = FrontierService(CalendarStore())
    app.include_router(router)
    client = TestClient(app)
    response = client.get("/api/frontier/calendar?year=2026&as_of=2026-02-01")
    assert response.status_code == 200
    value = response.json()
    assert value["days"] == [{"date": "2026-01-15", "count": 1, "record_ids": ["day"]}]
    assert value["month_precision"] == [{"month": "2026-01", "count": 1, "record_ids": ["month"]}]
    assert value["timezone"] == "Asia/Shanghai"
    assert client.get("/api/frontier/calendar?year=0").status_code == 422
    assert client.get("/api/frontier/calendar").status_code == 422


def test_calendar_with_real_corpus_and_withdrawal(tmp_path):
    from datetime import date
    from pathlib import Path

    from qunxue_api.adapters.sqlite.base import Base
    from qunxue_api.adapters.sqlite.database import Database
    from qunxue_api.adapters.sqlite.frontier_repository import SqliteFrontierStore
    from qunxue_api.json_shards import load_json

    database = Database(f"sqlite:///{tmp_path}/calendar.db")
    tables = [
        table for table in Base.metadata.tables.values() if table.name.startswith("frontier_")
    ]
    Base.metadata.create_all(database.engine, tables=tables)
    store = SqliteFrontierStore(database)
    corpus = load_json(Path(__file__).parents[1] / "data/frontier-corpus.json")
    try:
        store.import_seed(corpus)
        service = FrontierService(store)
        result = service.calendar(year=2026, as_of=date(2026, 10, 2))
        assert result["days"]
        assert result["issue_precision"]
        target = result["days"][0]["record_ids"][0]
        assert store.withdraw(target)
        changed = service.calendar(year=2026, as_of=date(2026, 10, 2))
        assert target not in {ref for item in changed["days"] for ref in item["record_ids"]}
    finally:
        database.engine.dispose()
