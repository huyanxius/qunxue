"""Evidence-led period comparison over normalized frontier records."""

from collections import defaultdict
from datetime import date, timedelta

from .analysis import record_topic_keys
from .measurement import MEASUREMENT_METHOD, MEASUREMENT_VERSION, publisher_keywords
from .periods import (
    PeriodStudy,
    PublicationInterval,
    SourceCoverage,
    compare_periods,
    publication_intersection,
    publication_interval,
    record_publication_interval,
)


def _research(record):
    return (
        record.get("stream") != "practice"
        and record.get("material_type") != "official_practice"
        and record.get("is_current") is not False
        and record.get("withdrawn") is not True
        and not record.get("withdrawn_at")
        and record.get("verification_status") not in {"withdrawn", "retracted", "review_queue"}
        and record.get("eligibility", {}).get("browse", True) is True
    )


def _members(studies, period):
    return [s for s in studies if s.publication.contained_by(period)]


def _coverage(studies, ledgers, period):
    result = []
    ledger_groups = defaultdict(list)
    for ledger in ledgers:
        ledger_groups[
            (ledger.get("source_id"), ledger.get("period"), ledger.get("period_precision", "month"))
        ].append(ledger)
    conflicts = set()
    for key, versions in ledger_groups.items():
        signatures = {
            tuple(
                str(v.get(field))
                for field in (
                    "coverage_complete",
                    "candidate_count",
                    "readable_count",
                    "included_count",
                    "analyzed_count",
                    "excluded_nonresearch_count",
                    "coverage_scope",
                    "issue_ids",
                    "comparison_issue_keys",
                )
            )
            for v in versions
        }
        if len(signatures) > 1:
            conflicts.add(key)
    for source_id in sorted({s.source_id for s in studies}):
        valid = []
        if any(
            s.source_id == source_id
            and s.publication.start <= period.end
            and s.publication.end >= period.start
            and not s.publication.contained_by(period)
            for s in studies
        ):
            continue
        for ledger in ledgers:
            if ledger.get("source_id") != source_id or ledger.get("coverage_complete") is not True:
                continue
            if (
                source_id,
                ledger.get("period"),
                ledger.get("period_precision", "month"),
            ) in conflicts:
                continue
            scope = ledger.get("coverage_scope")
            precision = ledger.get("period_precision", "month")
            if (scope is not None and not isinstance(scope, str)) or not isinstance(precision, str):
                continue
            if not (
                (scope in {None, "complete_source_period"} and precision == "month")
                or (scope == "fixed_issue_sample" and precision == "year")
            ):
                continue
            span = publication_interval(
                ledger.get("period"), ledger.get("period_precision", "month")
            )
            refs = ledger.get("evidence_refs")
            if (
                not span
                or not isinstance(refs, list)
                or not refs
                or not all(isinstance(ref, str) and ref.strip() for ref in refs)
            ):
                continue
            fixed = ledger.get("coverage_scope") == "fixed_issue_sample"
            issue_ids, keys = ledger.get("issue_ids"), ledger.get("comparison_issue_keys")
            if fixed and (
                span != period
                or not isinstance(issue_ids, list)
                or not issue_ids
                or not all(isinstance(i, str) and i.strip() for i in issue_ids)
                or not isinstance(keys, list)
                or not keys
                or not all(isinstance(k, str) and k.strip() for k in keys)
                or len(set(issue_ids)) != len(issue_ids)
                or len(set(keys)) != len(keys)
                or len(keys) != len(issue_ids)
            ):
                continue
            members = [
                item
                for item in _members(studies, span)
                if item.source_id == source_id and (not fixed or item.issue_ids & set(issue_ids))
            ]
            if fixed:
                memberships = {
                    pair
                    for item in members
                    for pair in item.issue_memberships
                    if pair[0] in issue_ids
                }
                if (
                    {i for i, _ in memberships} != set(issue_ids)
                    or {key for _, key in memberships} != set(keys)
                    or any(
                        sum(i == expected for i, _ in memberships) != 1 for expected in issue_ids
                    )
                ):
                    continue
            canonical_ids = frozenset(item.canonical_id for item in members)
            count = len(canonical_ids)
            excluded = ledger.get("excluded_nonresearch_count", 0)
            fields = [
                ledger.get(k)
                for k in ("candidate_count", "readable_count", "included_count", "analyzed_count")
            ]
            if (
                not all(type(v) is int and v >= 0 for v in [excluded, *fields])
                or fields[0] - excluded != count
                or fields[1] - excluded != count
                or fields[2] != count
                or fields[3] != count
            ):
                continue
            if fixed:
                result.append(
                    SourceCoverage(
                        source_id,
                        period,
                        True,
                        "|".join(sorted(set(refs))),
                        canonical_ids,
                        tuple(sorted(keys)),
                        "fixed_issue_sample",
                    )
                )
            else:
                valid.append((span, refs))
        cursor = period.start
        refs = []
        for span, evidence in sorted(valid, key=lambda x: x[0].start):
            if span.end < cursor or span.start > cursor:
                continue
            refs.extend(evidence)
            if span.end >= period.end:
                result.append(SourceCoverage(source_id, period, True, "|".join(sorted(set(refs)))))
                break
            cursor = span.end + timedelta(days=1)
    return result


def period_report(
    records: list[dict],
    ledgers: list[dict],
    *,
    previous: PublicationInterval,
    current: PublicationInterval,
    topic_key: str,
    as_of: date,
) -> dict:
    """Observed unique counts and normalized common-cohort shares are separate.

    Support flags are conservative policy candidates awaiting real-corpus calibration.
    No statistical direction constitutes a semantic-change assessment.
    """
    if topic_key.endswith("-practice"):
        raise ValueError("publication period reports require a research topic")
    if topic_key.endswith("-research"):
        topic_key = topic_key.removesuffix("-research")
    groups = defaultdict(list)
    for record in records:
        interval = record_publication_interval(record)
        if interval is not None and interval.end > as_of:
            continue
        if _research(record) and record.get("canonical_study_id") and record.get("id"):
            groups[record["canonical_study_id"]].append(record)
    studies, origins, conflict_sources = [], {}, set()
    for canonical_id, variants in groups.items():
        topic_sets = {record_topic_keys(v) for v in variants}
        span, date_conflict = publication_intersection(variants)
        if len(topic_sets) != 1 or date_conflict:
            conflict_sources.update(v["source_id"] for v in variants if v.get("source_id"))
            continue
        if span is None:
            continue
        topics = next(iter(topic_sets))
        if span.end > as_of:
            continue
        origin_set = {v.get("origin_source_id") for v in variants if v.get("origin_source_id")}
        origins[canonical_id] = next(iter(origin_set)) if len(origin_set) == 1 else None
        for source_id in sorted({v.get("source_id") for v in variants if v.get("source_id")}):
            studies.append(
                PeriodStudy(
                    canonical_id,
                    source_id,
                    span,
                    topics,
                    tuple(sorted(v["id"] for v in variants if v.get("source_id") == source_id)),
                    frozenset(
                        v["issue_id"]
                        for v in variants
                        if v.get("source_id") == source_id and v.get("issue_id")
                    ),
                    frozenset(
                        (v["issue_id"], str(v["publication_issue"]))
                        for v in variants
                        if v.get("source_id") == source_id
                        and v.get("issue_id")
                        and type(v.get("publication_issue")) is int
                        and v["publication_issue"] > 0
                    ),
                )
            )
    cover = _coverage(studies, ledgers, previous) + _coverage(studies, ledgers, current)
    cover = [c for c in cover if c.source_id not in conflict_sources]
    comparison = compare_periods(
        tuple(studies), tuple(cover), previous, current, topic_key, as_of=as_of
    )
    common = {row.source_id for row in comparison.source_shares}
    observed = [_members(studies, period) for period in (previous, current)]
    topic_groups = [
        {s.canonical_id for s in group if topic_key in s.topic_ids} for group in observed
    ]
    counts = [len(group) for group in topic_groups]
    rows = comparison.source_shares
    shares = [
        sum(getattr(r, f"{side}_count") / getattr(r, f"{side}_total") for r in rows) / len(rows)
        if rows
        else None
        for side in ("previous", "current")
    ]
    denominators = [
        sum(getattr(r, f"{side}_total") for r in rows) for side in ("previous", "current")
    ]
    occurrence_denominators = denominators

    def cohort_members(group, period):
        return [
            s
            for s in group
            if s.source_id in common
            and any(
                c.source_id == s.source_id
                and c.period == period
                and (c.canonical_ids is None or s.canonical_id in c.canonical_ids)
                for c in cover
            )
        ]

    cohort_observed = [
        cohort_members(group, period)
        for group, period in zip(observed, (previous, current), strict=True)
    ]
    unique_groups = [{s.canonical_id for s in group} for group in cohort_observed]
    unique_topics = [
        {s.canonical_id for s in group if topic_key in s.topic_ids} for group in cohort_observed
    ]
    denominators = [len(group) for group in unique_groups]
    pooled = [
        len(topic) / len(group) if group else None
        for topic, group in zip(unique_topics, unique_groups, strict=True)
    ]
    delta = comparison.mean_share_change
    direction = (
        None
        if delta is None
        else "rising"
        if delta > 1e-12
        else "declining"
        if delta < -1e-12
        else "flat"
    )
    relative = shares[1] / shares[0] - 1 if shares[0] else None
    independent_origins = [
        len({origins.get(key) for key in group} - {None}) for group in topic_groups
    ]
    comparable = bool(rows)
    cohort_groups = unique_groups
    cohort_topics = [
        {s.canonical_id for s in group if topic_key in s.topic_ids} for group in cohort_observed
    ]
    cohort_origins = [{origins.get(key) for key in group} & common for group in cohort_topics]
    enough = comparable and min(len(group) for group in cohort_groups) >= 20
    # Leave-one-source-out stability uses the same fixed weighting rule.
    stable = len(rows) > 1 and all(
        sum(r.change for r in rows if r.source_id != omitted.source_id) * (delta or 0) > 0
        for omitted in rows
    )
    hotspot = bool(
        enough
        and stable
        and len(cohort_topics[1]) >= 4
        and len(cohort_origins[1]) >= 2
        and delta is not None
        and delta >= 0.05
        and relative is not None
        and relative >= 0.5
    )
    decline = bool(
        enough
        and stable
        and len(cohort_topics[0]) >= 4
        and len(cohort_origins[0]) >= 2
        and delta is not None
        and delta <= -0.05
        and relative is not None
        and relative <= -1 / 3
    )
    persistent = False
    # Persistence is sustained presence across three completed, fixed-cohort months.
    month_index = current.start.year * 12 + current.start.month - 1
    if comparable and current.start.day == 1 and 14 <= month_index < 119987:
        histories = []
        for offset in (-2, -1, 0):
            index = month_index + offset
            start = date(index // 12, index % 12 + 1, 1)
            following = date((index + 1) // 12, (index + 1) % 12 + 1, 1)
            histories.append(PublicationInterval(start, following - timedelta(days=1)))
        if histories[-1] == current and histories[-2] == previous:
            persistent = True
            for period in histories:
                valid_sources = {c.source_id for c in _coverage(studies, ledgers, period)}
                period_members = [s for s in _members(studies, period) if s.source_id in common]
                topic_ids = {s.canonical_id for s in period_members if topic_key in s.topic_ids}
                origin_ids = {origins.get(key) for key in topic_ids} & common
                if (
                    not common.issubset(valid_sources)
                    or period.end >= as_of
                    or len(topic_ids) < 4
                    or len(origin_ids) < 2
                    or len({s.canonical_id for s in period_members}) < 20
                ):
                    persistent = False
                    break

    def classification_counts(cohort):
        ids = {item.canonical_id for item in cohort}
        categorized = {
            item.canonical_id for item in cohort if item.topic_ids != frozenset({"uncategorized"})
        }
        return {
            "denominator": len(ids),
            "classified": len(categorized),
            "uncategorized": len(ids - categorized),
            "title_available": sum(
                any(isinstance(v.get("title"), str) and v["title"].strip() for v in groups[key])
                for key in ids
            ),
            "publisher_keywords_available": sum(
                any(publisher_keywords(v) for v in groups[key]) for key in ids
            ),
        }

    scopes = {c.scope for c in cover if c.source_id in common}
    coverage_scope = next(iter(scopes)) if len(scopes) == 1 else "unproven"
    if coverage_scope == "fixed_issue_sample":
        # Three month persistence does not apply to annual fixed-issue samples.
        persistent = False
    if topic_key == "uncategorized":
        hotspot = decline = persistent = False
    return {
        "as_of": as_of.isoformat(),
        "timezone": "Asia/Shanghai",
        "date_basis": "research_publication",
        "semantic_status": "not_assessed",
        "method_version": "publication_periods_v2",
        "measurement_method": MEASUREMENT_METHOD,
        "measurement_version": MEASUREMENT_VERSION,
        "classification_coverage": {
            "previous": classification_counts(cohort_observed[0]),
            "current": classification_counts(cohort_observed[1]),
        },
        "comparability": "incomplete_period"
        if comparison.status == "open_period"
        else "complete_common_cohort"
        if comparable
        else "insufficient_coverage",
        "direction": direction,
        "previous_share": shares[0],
        "current_share": shares[1],
        "pooled_previous_share": pooled[0],
        "pooled_current_share": pooled[1],
        "delta_pp": delta * 100 if delta is not None else None,
        "relative_change": relative,
        "counts_basis": "all_observed_sources",
        "share_basis": "fixed_issue_sample_common_sources"
        if coverage_scope == "fixed_issue_sample"
        else "complete_common_source_cohort",
        "coverage_scope": coverage_scope,
        "previous_window": {"start": previous.start.isoformat(), "end": previous.end.isoformat()},
        "current_window": {"start": current.start.isoformat(), "end": current.end.isoformat()},
        "comparison_issue_keys": sorted(
            {key for c in cover if c.source_id in common for key in c.cohort_key}
        ),
        "cohort_previous_count": len(cohort_topics[0]),
        "cohort_current_count": len(cohort_topics[1]),
        "previous_count": counts[0],
        "current_count": counts[1],
        "previous_denominator": denominators[0],
        "previous_source_occurrences": occurrence_denominators[0],
        "current_source_occurrences": occurrence_denominators[1],
        "normalization_method": "equal_weight_source_occurrence_shares",
        "current_denominator": denominators[1],
        "current_independent_origins": independent_origins[1],
        "cohort_source_ids": sorted(common),
        "hotspot_allowed": hotspot,
        "decline_allowed": decline,
        "emerging_allowed": False,
        "persistent_allowed": persistent,
        "evidence_record_ids": sorted(
            {
                ref
                for group in observed
                for s in group
                if topic_key in s.topic_ids
                for ref in s.evidence_ids
            }
        ),
        "coverage_evidence_refs": sorted({c.evidence_id for c in cover if c.source_id in common}),
        "excluded_source_ids": sorted(set(comparison.excluded_source_ids) | conflict_sources),
    }
