from datetime import date, timedelta

import pytest
from frontier_period_fixtures import fixtures

from qunxue_api.modules.frontier_knowledge.period_report import period_report
from qunxue_api.modules.frontier_knowledge.periods import PublicationInterval


@pytest.mark.parametrize("case", fixtures()["cases"], ids=lambda case: case["case_id"])
def test_independent_period_contract(case):
    value = case["input"]

    def period(key):
        item = value[key]
        return PublicationInterval(
            date.fromisoformat(item["start"]),
            date.fromisoformat(item["end_exclusive"]) - timedelta(days=1),
        )

    actual = period_report(
        value["records"],
        value["coverage"],
        previous=period("previous"),
        current=period("current"),
        topic_key=value["topic_key"],
        as_of=date.fromisoformat(value["as_of"]),
    )
    for key, expected in case["expected"].items():
        if type(expected) in (int, float):
            assert actual[key] == pytest.approx(expected), key
        else:
            assert actual[key] == expected, key


def test_order_and_reprint_invariance():
    from copy import deepcopy
    from random import Random

    value = fixtures()["cases"][0]["input"]
    previous = PublicationInterval(date(2026, 8, 1), date(2026, 8, 31))
    current = PublicationInterval(date(2026, 9, 1), date(2026, 9, 30))

    def run(records):
        return period_report(
            records,
            value["coverage"],
            previous=previous,
            current=current,
            topic_key=value["topic_key"],
            as_of=date(2026, 10, 1),
        )

    expected = run(value["records"])
    shuffled = deepcopy(value["records"])
    Random(42).shuffle(shuffled)
    assert run(shuffled) == expected
    repeated = deepcopy(shuffled[0])
    repeated["id"] += "-copy"
    repeated["discovered_at"] = "2026-10-02"
    actual = run(shuffled + [repeated])
    for key in (
        "previous_count",
        "current_count",
        "previous_share",
        "current_share",
        "hotspot_allowed",
        "decline_allowed",
        "comparability",
    ):
        assert actual[key] == expected[key], key


def test_mixed_day_month_cannot_claim_week_complete():
    from frontier_period_fixtures import cohort

    rows, coverage = cohort("a", "2026-09", 10, 50)
    for i, row in enumerate(rows):
        row["published_at"] = "2026-09-10" if i < 20 else "2026-09-17"
        if i >= 40:
            row["published_at"] = "2026-09"
            row["published_at_precision"] = "month"
    report = period_report(
        rows,
        [coverage],
        previous=PublicationInterval(date(2026, 9, 7), date(2026, 9, 13)),
        current=PublicationInterval(date(2026, 9, 14), date(2026, 9, 20)),
        topic_key="organization",
        as_of=date(2026, 10, 1),
    )
    assert report["comparability"] == "insufficient_coverage"


def test_conflicting_coverage_not_cherry_picked():
    from copy import deepcopy

    value = fixtures()["cases"][0]["input"]
    bad = deepcopy(value["coverage"][-1])
    bad["coverage_complete"] = False
    ledgers = value["coverage"] + [bad]
    report = period_report(
        value["records"],
        ledgers,
        previous=PublicationInterval(date(2026, 8, 1), date(2026, 8, 31)),
        current=PublicationInterval(date(2026, 9, 1), date(2026, 9, 30)),
        topic_key="organization",
        as_of=date(2026, 10, 1),
    )
    assert "b" not in report["cohort_source_ids"]


def test_malformed_evidence_does_not_crash():
    value = fixtures()["cases"][0]["input"]
    for ledger in value["coverage"]:
        ledger["evidence_refs"] = [123]
    report = period_report(
        value["records"],
        value["coverage"],
        previous=PublicationInterval(date(2026, 8, 1), date(2026, 8, 31)),
        current=PublicationInterval(date(2026, 9, 1), date(2026, 9, 30)),
        topic_key="organization",
        as_of=date(2026, 10, 1),
    )
    assert report["comparability"] == "insufficient_coverage"


def test_compatible_canonical_precision_is_resolved():
    from copy import deepcopy

    value = fixtures()["cases"][0]["input"]
    copy = deepcopy(value["records"][0])
    copy["id"] += "-month"
    copy["published_at"] = "2026-08"
    copy["published_at_precision"] = "month"
    report = period_report(
        value["records"] + [copy],
        value["coverage"],
        previous=PublicationInterval(date(2026, 8, 1), date(2026, 8, 31)),
        current=PublicationInterval(date(2026, 9, 1), date(2026, 9, 30)),
        topic_key="organization",
        as_of=date(2026, 10, 1),
    )
    assert report["comparability"] == "complete_common_cohort"
    assert report["previous_count"] == 10


def test_withdrawal_flag_excludes_stale_browse_record():
    value = fixtures()["cases"][0]["input"]
    for row in value["records"]:
        if row["topics"] == ["组织社会学"]:
            row["withdrawn"] = True
    report = period_report(
        value["records"],
        value["coverage"],
        previous=PublicationInterval(date(2026, 8, 1), date(2026, 8, 31)),
        current=PublicationInterval(date(2026, 9, 1), date(2026, 9, 30)),
        topic_key="organization",
        as_of=date(2026, 10, 1),
    )
    assert report["previous_count"] == report["current_count"] == 0
    assert report["hotspot_allowed"] is False


def test_complete_reprint_hosts_do_not_duplicate_global_denominator():
    from copy import deepcopy

    from frontier_period_fixtures import cohort

    records, coverage = [], []
    for month in ("2026-08", "2026-09"):
        rows, ledger = cohort("a", month, 4, 20)
        records += rows
        coverage.append(ledger)
        copies = deepcopy(rows)
        for row in copies:
            row["source_id"] = "b"
            row["id"] += "-copy"
        records += copies
        coverage.append({**ledger, "source_id": "b"})
    report = period_report(
        records,
        coverage,
        previous=PublicationInterval(date(2026, 8, 1), date(2026, 8, 31)),
        current=PublicationInterval(date(2026, 9, 1), date(2026, 9, 30)),
        topic_key="organization",
        as_of=date(2026, 10, 1),
    )
    assert report["current_denominator"] == 20
    assert report["current_source_occurrences"] == 40
    assert report["current_independent_origins"] == 1
