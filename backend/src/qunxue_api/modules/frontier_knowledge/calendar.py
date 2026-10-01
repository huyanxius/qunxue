"""Publication activity with exact-day and coarse-date records kept distinct."""

from collections import defaultdict
from datetime import date

from .periods import publication_intersection


def publication_calendar(records: list[dict], *, year: int, as_of: date) -> dict:
    """Current browse-eligible versions only; canonical duplicates count once."""
    if not 1 <= year <= 9999:
        raise ValueError("year out of range")
    grouped = defaultdict(list)
    for record in records:
        if record.get("eligibility", {}).get("browse") is not True:
            continue
        if record.get("is_current") is False:
            continue
        canonical = record.get("canonical_study_id")
        if canonical and record.get("id"):
            grouped[canonical].append(record)
    days = defaultdict(lambda: {"canonical_ids": set(), "record_ids": set()})
    months = defaultdict(lambda: {"canonical_ids": set(), "record_ids": set()})
    issues = {}
    unknown, conflicts, future = [], [], []
    for canonical, variants in sorted(grouped.items()):
        span, conflict = publication_intersection(variants)
        refs = sorted({v["id"] for v in variants})
        if conflict:
            conflicts.extend(refs)
            continue
        if span is None or all(v.get("published_at_precision") == "issue" for v in variants):
            issue_keys = {
                (v.get("source_id"), v.get("issue_id"), v.get("publication_year"))
                for v in variants
                if v.get("published_at_precision") == "issue"
                and v.get("source_id")
                and v.get("issue_id")
                and isinstance(v.get("publication_year"), int)
            }
            if len(issue_keys) == 1:
                source_id, issue_id, publication_year = next(iter(issue_keys))
                if publication_year == year and publication_year <= as_of.year:
                    bucket = issues.setdefault(
                        (source_id, issue_id),
                        {
                            "source_id": source_id,
                            "issue_id": issue_id,
                            "publication_year": publication_year,
                            "canonical_ids": set(),
                            "record_ids": set(),
                        },
                    )
                    bucket["canonical_ids"].add(canonical)
                    bucket["record_ids"].update(refs)
                elif publication_year > as_of.year:
                    future.extend(refs)
            else:
                unknown.extend(refs)
            continue
        start, end = span.start, span.end
        if start.year != year:
            continue
        if end > as_of:
            future.extend(refs)
            continue
        if start == end:
            bucket = days[start.isoformat()]
        elif start.year == end.year and start.month == end.month:
            # Only completed verified month intervals enter historical buckets.
            bucket = months[start.strftime("%Y-%m")]
        else:
            unknown.extend(refs)
            continue
        bucket["canonical_ids"].add(canonical)
        bucket["record_ids"].update(refs)

    def serialize(buckets, key):
        return [
            {
                key: label,
                "count": len(value["canonical_ids"]),
                "record_ids": sorted(value["record_ids"]),
            }
            for label, value in sorted(buckets.items())
        ]

    return {
        "year": year,
        "as_of": as_of.isoformat(),
        "timezone": "Asia/Shanghai",
        "days": serialize(days, "date"),
        "month_precision": serialize(months, "month"),
        "issue_precision": [
            {
                "source_id": item["source_id"],
                "issue_id": item["issue_id"],
                "publication_year": item["publication_year"],
                "count": len(item["canonical_ids"]),
                "record_ids": sorted(item["record_ids"]),
            }
            for _, item in sorted(issues.items())
        ],
        "undated_record_ids": sorted(unknown),
        "conflicting_record_ids": sorted(conflicts),
        "future_record_ids": sorted(future),
    }
