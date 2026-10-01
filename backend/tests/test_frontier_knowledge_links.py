from types import SimpleNamespace

import pytest

from qunxue_api.application.frontier_knowledge_links import FrontierKnowledgeLinks
from qunxue_api.modules.knowledge_catalog import KnowledgeReleaseLevel, KnowledgeReleaseRef


class Store:
    def __init__(self, record):
        self.record = record

    def get_snapshot(self, snapshot_id):
        return None

    def get_record(self, record_id):
        return self.record


class Catalog:
    def __init__(self):
        self.calls = []

    def existing_release(self, *, purpose):
        return KnowledgeReleaseRef("release-1", KnowledgeReleaseLevel.PREVIEW, "sha256:release")

    def browse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            release=self.existing_release(purpose=None),
            entries=(
                SimpleNamespace(
                    knowledge_id="entry",
                    title="劳动社会学",
                    content_version=2,
                    eligibility=SimpleNamespace(browse_eligible=True),
                ),
                SimpleNamespace(
                    knowledge_id="hidden",
                    title="hidden",
                    content_version=1,
                    eligibility=SimpleNamespace(browse_eligible=False),
                ),
            ),
        )


def test_links_pin_release_and_combine_topic_matches():
    catalog = Catalog()
    service = FrontierKnowledgeLinks(
        Store(
            {
                "id": "record",
                "title": "record",
                "version": 1,
                "content_hash": "sha256:record",
                "snapshot_id": "snapshot",
                "published_at": "2026-01-01",
                "published_at_precision": "day",
                "is_current": True,
                "eligibility": {"browse": True},
                "topics": ["平台劳动", "劳动", "劳动"],
            }
        ),
        catalog,
    )
    result = service.for_record("record")
    assert result["knowledge_release_id"] == "release-1"
    assert len(result["matches"]) == 1
    assert result["matches"][0]["content_version"] == 2
    assert len(result["matches"][0]["matched_topics"]) == 2
    assert result["relationship"] == "reading_lead"
    assert all(c["release_id"] == "release-1" for c in catalog.calls)


@pytest.mark.parametrize(
    "record",
    [
        None,
        {"eligibility": {"browse": False}},
        {"is_current": False, "eligibility": {"browse": True}},
    ],
)
def test_unavailable_records_do_not_query_catalog(record):
    catalog = Catalog()
    with pytest.raises(LookupError):
        FrontierKnowledgeLinks(Store(record), catalog).for_record("record")
    assert not catalog.calls


def test_public_links_route_bootstrap(plain_client):
    assert plain_client.get("/api/frontier/records/not-found/knowledge-links").status_code == 404
