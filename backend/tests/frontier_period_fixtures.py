"""Materialize deterministic adversarial inputs, not a trend implementation."""

import copy
import json
from pathlib import Path

ROOT = Path(__file__).parent
TOPIC = "organization"


def cohort(source, period, numerator, denominator, *, complete=True):
    rows = []
    for i in range(denominator):
        identity = f"{source}-{period}-{i:03d}"
        rows.append(
            {
                "id": identity,
                "canonical_study_id": identity,
                "source_id": source,
                "origin_source_id": source,
                "material_type": "research_abstract",
                "stream": "research",
                "published_at": f"{period}-15",
                "published_at_precision": "day",
                "discovered_at": "2026-10-01",
                "source_published_at": "2026-10-01",
                "topics": ["组织社会学"] if i < numerator else ["数字社会"],
                "title": "组织制度研究" if i < numerator else "数字技术研究",
                "url": f"https://example.org/{identity}",
                "display_ready": True,
                "verification_status": "lead_only",
                "analysis_scope": "abstract",
            }
        )
    coverage = {
        "source_id": source,
        "period": period,
        "coverage_complete": complete,
        "candidate_count": denominator,
        "readable_count": denominator,
        "included_count": denominator,
        "analyzed_count": denominator,
        "excluded_nonresearch_count": 0,
        "evidence_refs": [f"fixture:complete-directory:{source}:{period}"],
    }
    return rows, coverage


def case(identifier, cohorts, expected, description):
    rows, coverage = [], []
    for spec in cohorts:
        batch, ledger = cohort(*spec)
        rows.extend(batch)
        coverage.append(ledger)
    return {
        "case_id": identifier,
        "description": description,
        "input": {
            "as_of": "2026-10-01",
            "timezone": "Asia/Shanghai",
            "period_kind": "month",
            "topic_key": TOPIC,
            "previous": {"start": "2026-08-01", "end_exclusive": "2026-09-01"},
            "current": {"start": "2026-09-01", "end_exclusive": "2026-10-01"},
            "records": rows,
            "coverage": coverage,
        },
        "expected": {"semantic_status": "not_assessed", **expected},
    }


def fixtures():
    cases = []

    def add(*args):
        result = case(*args)
        cases.append(result)
        return result

    add(
        "volume_growth_constant_share",
        [
            ("a", "2026-08", 5, 50),
            ("b", "2026-08", 5, 50),
            ("a", "2026-09", 10, 100),
            ("b", "2026-09", 10, 100),
        ],
        {
            "comparability": "complete_common_cohort",
            "direction": "flat",
            "previous_share": 0.1,
            "current_share": 0.1,
            "delta_pp": 0,
            "previous_count": 10,
            "current_count": 20,
            "hotspot_allowed": False,
        },
        "Topic count doubles only because total journal volume doubles.",
    )
    add(
        "simpson_composition_reversal",
        [
            ("a", "2026-08", 72, 90),
            ("b", "2026-08", 1, 10),
            ("a", "2026-09", 9, 10),
            ("b", "2026-09", 18, 90),
        ],
        {
            "comparability": "complete_common_cohort",
            "direction": "rising",
            "previous_share": 0.45,
            "current_share": 0.55,
            "delta_pp": 10,
            "pooled_previous_share": 0.73,
            "pooled_current_share": 0.27,
        },
        "Each source rises 10 pp while pooled share falls 46 pp.",
    )
    add(
        "new_source_not_a_hotspot",
        [("a", "2026-08", 5, 50), ("a", "2026-09", 5, 50), ("new", "2026-09", 40, 50)],
        {
            "comparability": "complete_common_cohort",
            "cohort_source_ids": ["a"],
            "direction": "flat",
            "previous_share": 0.1,
            "current_share": 0.1,
            "hotspot_allowed": False,
        },
        "Recently added topic-heavy source has no historical comparator.",
    )
    add(
        "lost_source_is_unknown",
        [("a", "2026-08", 20, 50)],
        {
            "comparability": "insufficient_coverage",
            "hotspot_allowed": False,
            "decline_allowed": False,
        },
        "No current source ledger is a collection gap, not scholarly decline.",
    )
    add(
        "zero_topic_source_keeps_denominator",
        [
            ("a", "2026-08", 10, 50),
            ("b", "2026-08", 0, 50),
            ("a", "2026-09", 10, 50),
            ("b", "2026-09", 0, 50),
        ],
        {
            "cohort_source_ids": ["a", "b"],
            "previous_share": 0.1,
            "current_share": 0.1,
            "direction": "flat",
            "previous_denominator": 100,
            "current_denominator": 100,
        },
        "Sources without this topic must remain in the fixed source universe.",
    )
    duplicate = add(
        "reprints_do_not_create_support",
        [("a", "2026-08", 1, 20), ("a", "2026-09", 1, 20)],
        {
            "previous_count": 1,
            "current_count": 1,
            "direction": "flat",
            "hotspot_allowed": False,
            "current_independent_origins": 1,
        },
        "Twenty copies of one paper are still one study from one verified origin.",
    )
    original = duplicate["input"]["records"][20]
    for i in range(20):
        row = copy.deepcopy(original)
        row.update(id=f"reprint-{i}", source_id="reprint-site", origin_source_id="a")
        duplicate["input"]["records"].append(row)
    add(
        "retrospective_ingest_not_current_research",
        [("a", "2026-08", 4, 20), ("a", "2026-09", 0, 20)],
        {"previous_count": 4, "current_count": 0, "hotspot_allowed": False},
        "All discoveries are October; publication periods remain August/September.",
    )
    future = add(
        "future_and_invalid_dates_not_counted",
        [("a", "2026-08", 2, 20), ("a", "2026-09", 2, 20)],
        {"previous_count": 2, "current_count": 0, "hotspot_allowed": False},
        "A publication date in November or February 30 cannot enter September.",
    )
    future["input"]["records"][20]["published_at"] = "2026-11-01"
    future["input"]["records"][21]["published_at"] = "2026-02-30"
    precise = add(
        "month_precision_fits_month",
        [("a", "2026-08", 4, 20), ("a", "2026-09", 4, 20)],
        {"previous_count": 4, "current_count": 4, "direction": "flat"},
        "A verified month is sufficient for its calendar month, without inventing a day.",
    )
    for row in precise["input"]["records"]:
        row["published_at"] = row["published_at"][:7]
        row["published_at_precision"] = "month"
    week = copy.deepcopy(precise)
    week.update(
        case_id="month_precision_cannot_fit_week", description="A month interval straddles weeks."
    )
    week["input"].update(
        period_kind="week",
        previous={"start": "2026-09-07", "end_exclusive": "2026-09-14"},
        current={"start": "2026-09-14", "end_exclusive": "2026-09-21"},
    )
    week["expected"] = {
        "previous_count": 0,
        "current_count": 0,
        "comparability": "insufficient_coverage",
        "semantic_status": "not_assessed",
    }
    cases.append(week)
    year = add(
        "year_precision_cannot_fit_quarter",
        [("a", "2026-09", 4, 20)],
        {"current_count": 0, "comparability": "insufficient_coverage"},
        "A year interval cannot be put in Q3.",
    )
    year["input"].update(
        period_kind="quarter",
        previous={"start": "2026-04-01", "end_exclusive": "2026-07-01"},
        current={"start": "2026-07-01", "end_exclusive": "2026-10-01"},
    )
    for row in year["input"]["records"]:
        row.update(published_at="2026", published_at_precision="year")
    issue = add(
        "issue_number_is_not_a_month",
        [("a", "2026-09", 4, 20)],
        {"current_count": 0, "hotspot_allowed": False},
        "Issue 3 does not mean March; no date mapping is asserted.",
    )
    for row in issue["input"]["records"]:
        row.update(
            published_at=None,
            published_at_precision="issue",
            publication_year=2026,
            publication_issue=3,
        )
    incomplete = add(
        "current_period_not_closed",
        [("a", "2026-08", 10, 20), ("a", "2026-09", 1, 20)],
        {"comparability": "incomplete_period", "decline_allowed": False, "hotspot_allowed": False},
        "On September 2 most of September has not happened.",
    )
    incomplete["input"]["as_of"] = "2026-09-02"
    mismatch = add(
        "false_complete_count_mismatch",
        [("a", "2026-08", 4, 20), ("a", "2026-09", 8, 20)],
        {"comparability": "insufficient_coverage", "hotspot_allowed": False},
        "A ledger saying complete still has three candidates missing.",
    )
    mismatch["input"]["coverage"][1].update(candidate_count=23, readable_count=20)
    no_evidence = add(
        "complete_flag_without_evidence",
        [("a", "2026-08", 4, 20), ("a", "2026-09", 8, 20)],
        {"comparability": "insufficient_coverage", "hotspot_allowed": False},
        "A true flag without directory provenance cannot establish a comparable cohort.",
    )
    for ledger in no_evidence["input"]["coverage"]:
        ledger["evidence_refs"] = []
    add(
        "single_paper_zero_baseline",
        [("a", "2026-08", 0, 20), ("a", "2026-09", 1, 20)],
        {
            "previous_count": 0,
            "current_count": 1,
            "relative_change": None,
            "hotspot_allowed": False,
            "emerging_allowed": False,
        },
        "One new study does not justify a hotspot, infinity, or semantic novelty.",
    )
    add(
        "zero_baseline_short_history",
        [
            ("a", "2026-08", 0, 20),
            ("b", "2026-08", 0, 20),
            ("a", "2026-09", 4, 20),
            ("b", "2026-09", 4, 20),
        ],
        {"relative_change": None, "emerging_allowed": False, "semantic_status": "not_assessed"},
        "Two periods provide too little covered history for first-observed emerging support.",
    )
    add(
        "persistent_flat_is_not_growth",
        [(s, p, 4, 20) for p in ["2026-07", "2026-08", "2026-09"] for s in ["a", "b"]],
        {"direction": "flat", "persistent_allowed": True, "hotspot_allowed": False},
        "The topic is active in three periods without needing an increase.",
    )
    add(
        "frequency_is_not_semantic_shift",
        [
            ("a", "2026-08", 4, 20),
            ("b", "2026-08", 4, 20),
            ("a", "2026-09", 8, 20),
            ("b", "2026-09", 8, 20),
        ],
        {"direction": "rising", "semantic_status": "not_assessed"},
        "An unchanged topic becomes commoner; that does not show changed meaning.",
    )
    practice = add(
        "practice_cannot_inflate_research",
        [("a", "2026-08", 4, 20), ("a", "2026-09", 4, 20)],
        {"current_count": 4, "previous_count": 4, "direction": "flat"},
        "Contradictory explicit stream cannot turn official practice into research.",
    )
    for i in range(15):
        row = copy.deepcopy(practice["input"]["records"][20])
        row.update(
            id=f"practice-{i}",
            canonical_study_id=f"practice-{i}",
            material_type="official_practice",
            stream="research",
        )
        practice["input"]["records"].append(row)
    conflict = add(
        "canonical_date_conflict_fails_closed",
        [("a", "2026-08", 4, 20), ("a", "2026-09", 4, 20)],
        {"comparability": "insufficient_coverage", "hotspot_allowed": False},
        "One canonical study claims both comparison periods; do not cherry-pick recency.",
    )
    row = copy.deepcopy(conflict["input"]["records"][20])
    row.update(id="date-conflict-copy", published_at="2026-08-15")
    conflict["input"]["records"].append(row)
    tags = add(
        "canonical_topic_conflict_is_audited",
        [("a", "2026-08", 4, 20), ("a", "2026-09", 4, 20)],
        {"comparability": "insufficient_coverage", "hotspot_allowed": False},
        "Strict policy invalidates source coverage when canonical topic assignments conflict.",
    )
    row = copy.deepcopy(tags["input"]["records"][20])
    row.update(id="topic-conflict-copy", topics=["数字社会"], title="数字技术研究")
    tags["input"]["records"].append(row)
    add(
        "supported_descriptive_decline",
        [
            ("a", "2026-08", 8, 20),
            ("b", "2026-08", 8, 20),
            ("a", "2026-09", 4, 20),
            ("b", "2026-09", 4, 20),
        ],
        {"direction": "declining", "previous_share": 0.4, "current_share": 0.2, "delta_pp": -20},
        "A complete fixed cohort has a real observed-share decline.",
    )
    quarter = add(
        "quarter_half_open_boundaries",
        [],
        {"previous_count": 1, "current_count": 2},
        "June 30 belongs to Q2; July 1 and September 30 to Q3; October 1 to neither.",
    )
    quarter["input"].update(
        period_kind="quarter",
        previous={"start": "2026-04-01", "end_exclusive": "2026-07-01"},
        current={"start": "2026-07-01", "end_exclusive": "2026-10-01"},
    )
    for i, day in enumerate(["2026-06-30", "2026-07-01", "2026-09-30", "2026-10-01"]):
        batch, _ = cohort("a", day[:7], 1, 1)
        batch[0].update(id=f"quarter-{i}", canonical_study_id=f"quarter-{i}", published_at=day)
        quarter["input"]["records"].extend(batch)
    return {
        "schema_version": "qunxue-temporal-eval-v1",
        "numeric_tolerance": 1e-9,
        "expected_are_contract_assertions_not_model_predictions": True,
        "cases": cases,
    }


if __name__ == "__main__":
    output = ROOT / "fixtures" / "synthetic.json"
    payload = fixtures()
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {len(payload['cases'])} synthetic cases to {output}")
