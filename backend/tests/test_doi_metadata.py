from datetime import UTC, datetime
from urllib.error import URLError

import pytest

from qunxue_api.adapters.research_materials.doi import CrossrefDoiMetadataResolver
from qunxue_api.modules.research_materials import DoiMetadataUnavailable


def test_crossref_doi_candidate_preserves_contributors_dates_and_identifiers() -> None:
    requested: list[str] = []

    def fetch_json(url: str) -> dict[str, object]:
        requested.append(url)
        return {
            "status": "ok",
            "message": {
                "DOI": "10.1234/ABC.1",
                "type": "journal-article",
                "title": ["Care after Migration"],
                "author": [{"family": "Li", "given": "Ming", "ORCID": "https://orcid.org/0000-0001"}],
                "published": {"date-parts": [[2025, 4, 3]]},
                "container-title": ["Journal of Migration"],
                "publisher": "Example Press",
                "URL": "https://doi.org/10.1234/abc.1",
            },
        }

    candidate = CrossrefDoiMetadataResolver(
        fetch_json=fetch_json,
        clock=lambda: datetime(2026, 8, 31, 12, tzinfo=UTC),
    ).resolve("https://doi.org/10.1234/ABC.1")

    assert requested[0].endswith("/works/10.1234%2Fabc.1")
    assert candidate.doi == "10.1234/abc.1"
    assert candidate.title == "Care after Migration"
    assert candidate.item_type == "article-journal"
    assert candidate.csl_data["issued"] == {"date-parts": [[2025, 4, 3]]}
    assert candidate.csl_data["author"][0]["ORCID"] == "https://orcid.org/0000-0001"
    assert candidate.source == "crossref"


def test_crossref_network_failure_uses_stable_unavailable_error() -> None:
    def fetch_json(_url: str) -> dict[str, object]:
        raise URLError("temporary DNS failure")

    with pytest.raises(DoiMetadataUnavailable, match="unavailable"):
        CrossrefDoiMetadataResolver(fetch_json=fetch_json).resolve("10.1234/abc.1")
