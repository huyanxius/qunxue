from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from qunxue_api.api.routes.frontier import router
from qunxue_api.modules.frontier_knowledge.service import FrontierService


class Store:
    def list_records(self):
        return []

    def list_issue_coverage(self):
        return []


def test_period_report_api_reads_real_service_and_abstains():
    app = FastAPI()
    app.include_router(router)
    app.state.frontier_service = FrontierService(Store())
    client = TestClient(app)
    q = dict(
        previous_start="2025-01-01",
        previous_end="2025-12-31",
        current_start="2026-01-01",
        current_end="2026-12-31",
        topic_key="youth",
        as_of="2026-10-02",
    )
    response = client.get("/api/frontier/period-report", params=q)
    assert response.status_code == 200
    report = response.json()
    assert report["current_count"] == 0
    assert report["current_share"] is None
    assert report["semantic_status"] == "not_assessed"
    assert report["hotspot_allowed"] is False
    q["previous_end"] = "2024-12-31"
    assert client.get("/api/frontier/period-report", params=q).status_code == 422


def test_cutoff_applies_without_since_days_and_to_overview():
    from qunxue_api.modules.frontier_knowledge.service import available_as_of

    before = {"published_at": "2026-01-20", "published_at_precision": "day"}
    future = {"published_at": "2026-05-20", "published_at_precision": "day"}
    assert available_as_of(before, date(2026, 1, 20))
    assert not available_as_of(future, date(2026, 1, 20))

    class FutureStore:
        def list_records(self):
            return [{**future, "id": "future", "eligibility": {"browse": True}}]

        def get_corpus_overview(self):
            return None

    service = FrontierService(FutureStore())
    assert service.search(as_of=date(2026, 1, 20))["items"] == []
    assert service.overview(as_of=date(2026, 1, 20))["statistics"]["research_count"] == 0
