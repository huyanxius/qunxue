"""Publication-period cohorts independent of collection time and delivery frameworks."""

import calendar
import re
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class PublicationInterval:
    start: date
    end: date

    def contained_by(self, period: "PublicationInterval") -> bool:
        return period.start <= self.start <= self.end <= period.end

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("period end precedes start")


def publication_interval(value: str | None, precision: str) -> PublicationInterval | None:
    """Month/year dates remain intervals; no artificial January or month-first day."""
    if not isinstance(value, str):
        return None
    try:
        if precision == "day" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            day = date.fromisoformat(value)
            return PublicationInterval(day, day)
        if precision == "month" and re.fullmatch(r"\d{4}-\d{2}(?:-\d{2})?", value):
            # Validate the entire value even when only its month is meaningful.
            parsed = date.fromisoformat(value if len(value) == 10 else value + "-01")
            return PublicationInterval(
                date(parsed.year, parsed.month, 1),
                date(parsed.year, parsed.month, calendar.monthrange(parsed.year, parsed.month)[1]),
            )
        if precision == "year" and re.fullmatch(r"\d{4}", value):
            year = int(value)
            return PublicationInterval(date(year, 1, 1), date(year, 12, 31))
    except (ValueError, TypeError):
        return None
    return None


def record_publication_interval(record: dict) -> PublicationInterval | None:
    span = publication_interval(record.get("published_at"), record.get("published_at_precision"))
    if span is not None:
        return span
    # An issue establishes a year at most. It never establishes a month or day.
    year = record.get("publication_year")
    if record.get("published_at_precision") == "issue" and type(year) is int:
        return publication_interval(str(year), "year")
    return None


def publication_intersection(records: list[dict]) -> tuple[PublicationInterval | None, bool]:
    """Resolve compatible coarse/fine versions; return an explicit conflict flag."""
    spans = [
        span for record in records if (span := record_publication_interval(record)) is not None
    ]
    if not spans:
        return None, False
    start, end = max(span.start for span in spans), min(span.end for span in spans)
    if start > end:
        return None, True
    return PublicationInterval(start, end), False


def available_as_of(record: dict, as_of: date) -> bool:
    span = record_publication_interval(record)
    if span is not None:
        if span.end <= as_of:
            return True
        if span.start > as_of or record.get("published_at_precision") != "issue":
            return False
    # For an issue in the open year, discovery proves availability, never publication day.
    year = record.get("publication_year")
    if type(year) is int and year > as_of.year:
        return False
    discovered = publication_interval((record.get("discovered_at") or "")[:10], "day")
    return bool(discovered and discovered.end <= as_of)


def browse_visible(record: dict) -> bool:
    return (
        record.get("eligibility", {}).get("browse") is True
        and record.get("is_current") is not False
        and record.get("withdrawn") is not True
        and not record.get("withdrawn_at")
        and record.get("verification_status") not in {"withdrawn", "retracted", "review_queue"}
    )


@dataclass(frozen=True)
class PeriodStudy:
    canonical_id: str
    source_id: str
    publication: PublicationInterval
    topic_ids: frozenset[str]
    evidence_ids: tuple[str, ...]
    issue_ids: frozenset[str] = frozenset()
    issue_memberships: frozenset[tuple[str, str]] = frozenset()


@dataclass(frozen=True)
class SourceCoverage:
    source_id: str
    period: PublicationInterval
    complete: bool
    evidence_id: str
    canonical_ids: frozenset[str] | None = None
    cohort_key: tuple[str, ...] = ()
    scope: str = "complete_source_period"


@dataclass(frozen=True)
class SourceShare:
    source_id: str
    previous_count: int
    previous_total: int
    current_count: int
    current_total: int

    @property
    def change(self) -> float:
        return self.current_count / self.current_total - self.previous_count / self.previous_total


@dataclass(frozen=True)
class PeriodComparison:
    source_shares: tuple[SourceShare, ...]
    mean_share_change: float | None
    previous_evidence_ids: tuple[str, ...]
    current_evidence_ids: tuple[str, ...]
    excluded_source_ids: tuple[str, ...]
    status: str


def compare_periods(
    studies: tuple[PeriodStudy, ...],
    coverage: tuple[SourceCoverage, ...],
    previous: PublicationInterval,
    current: PublicationInterval,
    topic_id: str,
    *,
    as_of: date,
) -> PeriodComparison:
    """Equal-weight matched sources; report measured change, not semantic trend claims.

    Coverage declarations require evidence. Deduplicate canonical studies within each
    source; conflicting versions are excluded instead of choosing ingestion order.
    An incomplete current period yields no comparison, including no decline signal.
    """
    if previous.end >= current.start:
        raise ValueError("comparison periods overlap or are reversed")
    if current.end >= as_of:
        return PeriodComparison((), None, (), (), (), "open_period")
    source_ids = {study.source_id for study in studies} | {item.source_id for item in coverage}
    rows = []
    excluded = []
    evidence = [set(), set()]
    for source_id in sorted(source_ids):
        candidates = [
            [
                item
                for item in coverage
                if item.source_id == source_id
                and item.complete
                and bool(item.evidence_id.strip())
                and period.contained_by(item.period)
            ]
            for period in (previous, current)
        ]
        pairs = [
            (a, b)
            for a in candidates[0]
            for b in candidates[1]
            if a.scope == b.scope and a.cohort_key == b.cohort_key
        ]
        if len(pairs) != 1:
            excluded.append(source_id)
            continue
        selected_coverage = pairs[0]
        grouped: dict[str, list[PeriodStudy]] = {}
        for study in studies:
            if study.source_id == source_id:
                grouped.setdefault(study.canonical_id, []).append(study)
        unique = []
        conflicted = False
        for variants in grouped.values():
            identities = {(v.publication, v.topic_ids) for v in variants}
            if len(identities) == 1 and all(v.canonical_id and v.evidence_ids for v in variants):
                unique.append(variants)
            else:
                conflicted = True
        if conflicted:
            excluded.append(source_id)
            continue
        totals, counts, selected = [], [], []
        for period, declaration in zip((previous, current), selected_coverage, strict=True):
            members = [
                variants
                for variants in unique
                if variants[0].publication.contained_by(period)
                and (
                    declaration.canonical_ids is None
                    or variants[0].canonical_id in declaration.canonical_ids
                )
            ]
            topic_members = [variants for variants in members if topic_id in variants[0].topic_ids]
            totals.append(len(members))
            counts.append(len(topic_members))
            selected.append(
                {ref for variants in topic_members for v in variants for ref in v.evidence_ids}
            )
        if not all(totals):
            excluded.append(source_id)
            continue
        rows.append(SourceShare(source_id, counts[0], totals[0], counts[1], totals[1]))
        for position in (0, 1):
            evidence[position].update(selected[position])
    return PeriodComparison(
        tuple(rows),
        sum(row.change for row in rows) / len(rows) if rows else None,
        tuple(sorted(evidence[0])),
        tuple(sorted(evidence[1])),
        tuple(excluded),
        "comparable" if rows else "no_comparable_sources",
    )
