"""Evidence-linked corpus distributions; observed samples are not field growth."""

import calendar
from collections import defaultdict
from contextlib import suppress
from datetime import date


def _month_start(as_of: date, offset: int) -> date:
    value = as_of.year * 12 + as_of.month - 1 + offset
    return date(value // 12, value % 12 + 1, 1)


def _dated_studies(records: list[dict], as_of: date) -> list[dict]:
    grouped = defaultdict(list)
    for record in records:
        grouped[record["canonical_study_id"]].append(record)
    result = []
    for canonical_id, variants in grouped.items():
        days = set()
        for record in variants:
            if record.get("published_at_precision") != "day":
                continue
            with suppress(ValueError):
                days.add(date.fromisoformat(record.get("published_at") or ""))
        if len(days) != 1:
            continue
        day = next(iter(days))
        if day > as_of:
            continue
        result.append({"canonical_id": canonical_id, "day": day, "variants": variants})
    return result


def topic_series(
    topic: dict, records: list[dict], sources: list[dict], coverage: list[dict], as_of: date
) -> dict:
    stream = topic["stream"]
    members = set(topic["record_ids"])
    stream_records = [
        r
        for r in records
        if ("practice" if r["material_type"] == "official_practice" else "research") == stream
    ]
    studies = _dated_studies(stream_records, as_of)
    # Shares always use the same material stream and the same observation period.
    monthly = []
    source_by_id = {source["source_id"]: source for source in sources}
    for offset in range(-11, 1):
        start = _month_start(as_of, offset)
        end = date(start.year, start.month, calendar.monthrange(start.year, start.month)[1])
        observed_end = min(end, as_of)
        denominator_studies = [study for study in studies if start <= study["day"] <= observed_end]
        selected = [
            study
            for study in denominator_studies
            if any(r["id"] in members for r in study["variants"])
        ]
        ids = sorted(
            {r["id"] for study in selected for r in study["variants"] if r["id"] in members}
        )
        observed_sources = sorted(
            {r["source_id"] for study in denominator_studies for r in study["variants"]}
        )
        denominator_ids = sorted(
            {r["id"] for study in denominator_studies for r in study["variants"]}
        )
        complete = bool(observed_sources) and end <= as_of
        for source_id in {r["source_id"] for r in stream_records}:
            source = source_by_id.get(source_id, {})
            try:
                complete = (
                    complete
                    and source.get("coverage_complete") is True
                    and date.fromisoformat(source["coverage_start"]) <= start
                    and date.fromisoformat(source["coverage_end"]) >= end
                )
            except (KeyError, TypeError, ValueError):
                complete = False
        count, denominator = len(selected), len(denominator_studies)
        share = count / denominator if denominator else None
        monthly.append(
            {
                "month": start.strftime("%Y-%m"),
                "record_count": count,
                "dated_record_ids": ids,
                "denominator_record_ids": denominator_ids,
                "source_ids": sorted(
                    {r["source_id"] for study in selected for r in study["variants"]}
                ),
                "denominator_source_ids": observed_sources,
                "denominator": denominator,
                "sample_share": share,
                "normalized_share": share if complete else None,
                "coverage_complete": bool(complete),
                "is_partial_month": end > as_of,
                "observation_basis": "complete_source_coverage"
                if complete
                else "sampled_publications",
            }
        )

    issue_series = []
    if stream == "research":
        for issue in sorted(
            coverage,
            key=lambda item: (item["publication_month"] or "", item["source_id"], item["issue_id"]),
        ):
            if not issue["publication_month"] or issue["publication_month"] > as_of.strftime(
                "%Y-%m"
            ):
                continue
            issue_records = [
                r
                for r in stream_records
                if r.get("issue_id") == issue["issue_id"] and r["source_id"] == issue["source_id"]
            ]
            if not issue_records:
                continue
            denominator = len({r["canonical_study_id"] for r in issue_records})
            analyzed_count = len(
                {
                    r["canonical_study_id"]
                    for r in issue_records
                    if r.get("extraction_method") == "assistant_evidence_synthesis"
                    and r.get("analysis_scope") == "abstract"
                    and r.get("summary")
                    and r.get("why_read")
                    and r.get("analysis_evidence")
                }
            )
            selected = [r for r in issue_records if r["id"] in members]
            numerator = len({r["canonical_study_id"] for r in selected})
            complete = (
                issue["coverage_complete"] is True
                and issue["candidate_count"]
                == issue["readable_count"]
                == issue["included_count"]
                == denominator
                == analyzed_count
                and denominator > 0
            )
            issue_series.append(
                {
                    **issue,
                    "denominator": denominator,
                    "analyzed_count": analyzed_count,
                    "topic_record_count": numerator,
                    "share": numerator / denominator if complete else None,
                    "coverage_complete": complete,
                    "evidence_record_ids": sorted(r["id"] for r in selected),
                    "denominator_record_ids": sorted(r["id"] for r in issue_records),
                    "comparison_group": (
                        f"{issue['source_id']}:issue:{issue['publication_issue']}"
                        if issue.get("publication_issue")
                        else issue["source_id"]
                    ),
                }
            )
    comparable = defaultdict(int)
    for issue in issue_series:
        if issue["coverage_complete"]:
            comparable[(issue["source_id"], issue["comparison_group"])] += 1
    comparable_source_ids = sorted(
        {source_id for (source_id, _group), count in comparable.items() if count >= 2}
    )
    return {
        "monthly_series": monthly,
        "issue_series": issue_series,
        "series_metadata": {
            "date_basis": "exact_publication_date",
            "unit": "deduplicated_records",
            "comparison_status": "complete_issue_cohort"
            if comparable_source_ids
            else "sample_distribution_only",
            "comparable_source_ids": comparable_source_ids,
            "topic_membership_overlaps": True,
            "coverage_note": "同刊完整期次可比议题占比；月度曲线仅描述收录样本，不推断全学科增长。"
            if comparable_source_ids
            else "月度条数与占比仅描述已读样本；来源或期次覆盖不齐时不推断领域增长。",
        },
    }
