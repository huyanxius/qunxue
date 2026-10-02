"""Small deterministic browse projection, shared by imports and migration backfill."""

from datetime import date

from .analysis import _TOPIC_DICTIONARY, _label, _stream, _tags
from .periods import browse_visible, publication_interval, record_publication_interval

SUMMARY_FIELDS = (
    "id",
    "title",
    "authors",
    "source_id",
    "source_name",
    "source_publisher",
    "source_published_at",
    "published_at",
    "published_at_display",
    "publication_year",
    "publication_issue",
    "url",
    "topics",
    "material_type",
    "verification_status",
    "within_preferred_window",
)


def record_summary(record: dict) -> dict:
    return {
        **{key: record.get(key) for key in SUMMARY_FIELDS},
        "summary": (record.get("summary") or "")[:280],
        "has_media": bool(record.get("media")),
        "research_question": (record.get("research_question") or "")[:280] or None,
        "findings": [text[:280] for text in (record.get("findings") or []) if text.strip()][:1],
    }


def build_read_projection(record: dict) -> dict:
    span = record_publication_interval(record)
    available = span.end if span else None
    discovered = publication_interval((record.get("discovered_at") or "")[:10], "day")
    year = record.get("publication_year")
    if discovered and (span is None or record.get("published_at_precision") == "issue"):
        fallback = max(discovered.end, date(year, 1, 1)) if type(year) is int else discovered.end
        available = min(available, fallback) if available else fallback
    # Topic aggregation has an additional declared-year/discovery cutoff. Keep
    # that historic rule distinct from browse availability (notably old issues).
    topic_available = available
    if topic_available and type(year) is int and 1 <= year <= 9999:
        topic_available = max(topic_available, date(year, 1, 1))
    if topic_available and discovered and record.get("published_at") is None:
        topic_available = max(topic_available, discovered.end)
    tags = _tags(record)
    topic_keys = [
        key for key, _, aliases in _TOPIC_DICTIONARY if tags & {_label(alias) for alias in aliases}
    ]
    return {
        "read_browse": browse_visible(record),
        "read_available_on": available.isoformat() if available else None,
        "read_topic_available_on": topic_available.isoformat() if topic_available else None,
        "read_display_date": record.get("published_at") or record.get("source_published_at") or "",
        "read_sort_date": record.get("source_published_at") or "",
        "read_publication_day": span.start.isoformat()
        if span and record.get("published_at_precision") == "day"
        else None,
        "read_stream": _stream(record),
        "read_topic_keys": topic_keys,
        "read_lexical_text": " ".join(
            [
                record["title"],
                record.get("summary") or "",
                record.get("research_question") or "",
                record["source_name"],
                *(record.get("authors") or []),
                *record.get("topics", []),
            ]
        ).casefold(),
        "read_summary": record_summary(record),
    }
