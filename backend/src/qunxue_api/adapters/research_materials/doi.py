"""Crossref DOI metadata adapter returning the module's CSL-shaped contract."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from urllib.parse import quote
from urllib.request import Request, urlopen

from qunxue_api.modules.research_materials import (
    DoiMetadataCandidate,
    DoiMetadataUnavailable,
    normalize_doi,
)


class CrossrefDoiMetadataResolver:
    def __init__(self, *, fetch_json=None, clock=None) -> None:
        self._fetch_json = fetch_json or self._default_fetch_json
        self._clock = clock or (lambda: datetime.now(UTC))

    def resolve(self, doi: str) -> DoiMetadataCandidate:
        normalized = normalize_doi(doi)
        if normalized is None:
            raise ValueError("doi is required")
        try:
            payload = self._fetch_json(
                f"https://api.crossref.org/works/{quote(normalized, safe='')}"
            )
        except (OSError, json.JSONDecodeError) as error:
            raise DoiMetadataUnavailable("Crossref metadata service is unavailable") from error
        message = payload.get("message") if isinstance(payload, dict) else None
        if not isinstance(message, dict):
            raise ValueError("Crossref returned no DOI metadata")
        title = _first_text(message.get("title"))
        if title is None:
            raise ValueError("Crossref metadata has no title")
        item_type = _crossref_type(str(message.get("type") or ""))
        csl_data: dict[str, object] = {
            "type": item_type,
            "title": title,
            "DOI": normalized,
        }
        authors = message.get("author")
        if isinstance(authors, list):
            csl_data["author"] = [
                {
                    key: value
                    for key in ("family", "given", "ORCID", "suffix")
                    if isinstance((value := author.get(key)), str) and value
                }
                for author in authors
                if isinstance(author, dict)
            ]
        published = (
            message.get("published")
            or message.get("published-print")
            or message.get("published-online")
        )
        if isinstance(published, dict) and isinstance(published.get("date-parts"), list):
            csl_data["issued"] = {"date-parts": published["date-parts"]}
        container = _first_text(message.get("container-title"))
        if container:
            csl_data["container-title"] = container
        for source, target in (("publisher", "publisher"), ("URL", "URL"), ("ISSN", "ISSN")):
            value = message.get(source)
            if isinstance(value, (str, list)) and value:
                csl_data[target] = value
        return DoiMetadataCandidate(
            doi=normalized,
            item_type=item_type,
            title=title,
            csl_data=csl_data,
            source="crossref",
            verified_at=self._clock(),
        )

    @staticmethod
    def _default_fetch_json(url: str) -> dict[str, object]:
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "qunxue/0.1 (DOI metadata verification)",
            },
        )
        with urlopen(request, timeout=8) as response:  # noqa: S310 - fixed HTTPS endpoint
            payload = json.load(response)
        if not isinstance(payload, dict):
            raise ValueError("Crossref returned an invalid response")
        return payload


def _first_text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, list):
        return next((str(item).strip() for item in value if str(item).strip()), None)
    return None


def _crossref_type(value: str) -> str:
    return {
        "journal-article": "article-journal",
        "book-chapter": "chapter",
        "proceedings-article": "paper-conference",
        "posted-content": "article",
        "dissertation": "thesis",
    }.get(value, value or "document")
