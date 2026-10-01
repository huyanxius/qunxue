"""Evidence-linked corpus distributions; observed samples are not field growth."""

import calendar
from collections import defaultdict
from datetime import date

from .period_report import period_report
from .periods import PublicationInterval, publication_intersection


def _month_start(as_of: date, offset: int) -> date:
    value = as_of.year * 12 + as_of.month - 1 + offset
    return date(value // 12, value % 12 + 1, 1)


def _dated_studies(records: list[dict], as_of: date) -> list[dict]:
    grouped = defaultdict(list)
    for record in records:
        grouped[record["canonical_study_id"]].append(record)
    result = []
    for canonical_id, variants in grouped.items():
        span, conflict = publication_intersection(variants)
        if conflict or span is None or span.start != span.end or span.end > as_of:
            # Coarse intervals refine a day only when all versions are compatible.
            continue
        day = span.start
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
        # Day-dated monthly samples cannot prove completeness from a source flag.
        # Coarse issue records and fixed-cohort shares belong in the period report.
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
            [item for item in coverage if item.get("publication_month") and item.get("issue_id")],
            key=lambda item: (item["publication_month"], item["source_id"], item["issue_id"]),
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
            issue_month = issue["publication_month"]
            month_end = date(
                int(issue_month[:4]),
                int(issue_month[5:7]),
                calendar.monthrange(int(issue_month[:4]), int(issue_month[5:7]))[1],
            )
            complete = (
                month_end < as_of
                and bool(issue.get("issue_url"))
                and issue["coverage_complete"] is True
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
    # Annual fixed issue ledgers have no verified month. Compare them as years,
    # retain provenance, and keep them out of the month and day axes.
    fixed_years = sorted(
        {
            int(c["period"])
            for c in coverage
            if c.get("coverage_scope") == "fixed_issue_sample"
            and c.get("period_precision") == "year"
            and isinstance(c.get("period"), str)
            and len(c["period"]) == 4
            and c["period"].isdigit()
            and 1 <= int(c["period"]) < as_of.year
        }
    )
    fixed_sources = set()
    if stream == "research":
        for old, new in zip(fixed_years, fixed_years[1:], strict=False):
            if new != old + 1:
                continue
            report = period_report(
                records,
                coverage,
                previous=PublicationInterval(date(old, 1, 1), date(old, 12, 31)),
                current=PublicationInterval(date(new, 1, 1), date(new, 12, 31)),
                topic_key=topic.get("topic_key", "uncategorized"),
                as_of=as_of,
            )
            if report["comparability"] == "complete_common_cohort":
                fixed_sources.update(report["cohort_source_ids"])
    comparable_source_ids = sorted(set(comparable_source_ids) | fixed_sources)
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
            "coverage_note": "所列同刊固定期次样本可比；覆盖仅限声明期次。月度曲线描述日精度样本。"
            if comparable_source_ids
            else "月度条数与占比仅描述已读样本；来源或期次覆盖不齐时不推断领域增长。",
        },
    }
