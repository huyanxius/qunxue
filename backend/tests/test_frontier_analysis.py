import json
from copy import deepcopy
from datetime import date, timedelta

import pytest

from qunxue_api.modules.frontier_knowledge.analysis import aggregate_topics

AS_OF = date(2026, 10, 1)


def _record(record_id: str, age: int | None = 1, **overrides) -> dict:
    record = {
        "id": record_id,
        "canonical_study_id": record_id,
        "source_id": "source-a",
        "source_name": "来源甲",
        "topics": ["组织社会学"],
        "published_at": (AS_OF - timedelta(days=age)).isoformat() if age is not None else None,
        "published_at_precision": "day" if age is not None else "issue",
        "material_type": "research_abstract",
        "url": f"https://example.com/{record_id}",
    }
    record.update(overrides)
    return record


def _topic(records: list[dict], coverage_days: int | None = None) -> dict:
    coverage = AS_OF - timedelta(days=coverage_days) if coverage_days is not None else None
    return aggregate_topics(records, as_of=AS_OF, coverage_start=coverage)[0]


def _growth_records(prior_count: int = 6) -> list[dict]:
    return [
        _record(f"recent-{i}", age, source_id=f"source-{i % 2}")
        for i, age in enumerate((0, 1, 8, 15))
    ] + [_record(f"prior-{i}", 40 + i) for i in range(prior_count)]


def _persistence_records(prior_count: int = 3) -> list[dict]:
    return [
        _record(f"recent-{i}", age, source_id=f"source-{i % 2}")
        for i, age in enumerate((2, 9, 16, 30))
    ] + [_record(f"prior-{i}", 100 + i) for i in range(prior_count)]


@pytest.mark.parametrize(
    ("age", "days_30", "days_90", "days_180", "growth_prior", "previous_90"),
    [
        (-1, 0, 0, 0, 0, 0),
        (0, 1, 1, 1, 0, 0),
        (29, 1, 1, 1, 0, 0),
        (30, 0, 1, 1, 1, 0),
        (89, 0, 1, 1, 1, 0),
        (90, 0, 0, 1, 1, 1),
        (119, 0, 0, 1, 1, 1),
        (120, 0, 0, 1, 0, 1),
        (179, 0, 0, 1, 0, 1),
        (180, 0, 0, 0, 0, 0),
    ],
)
def test_window_boundaries(
    age: int,
    days_30: int,
    days_90: int,
    days_180: int,
    growth_prior: int,
    previous_90: int,
) -> None:
    result = _topic([_record("boundary", age)], coverage_days=200)
    counts = result["counts"]
    assert counts["total"] == 1
    assert counts["days_30"] == days_30
    assert counts["days_90"] == days_90
    assert counts["days_180"] == days_180
    assert counts["prior_90_for_growth"] == growth_prior
    assert counts["previous_90"] == counts["prior_90_for_persistence"] == previous_90
    assert counts["dated"] == int(age >= 0)
    assert counts["future_dated"] == int(age < 0)
    assert counts["undated"] == 0


def test_windows_expose_exact_inclusive_dates() -> None:
    windows = _topic([_record("one")])["time_windows"]
    assert windows["days_30"] == {"start": "2026-09-02", "end": "2026-10-01"}
    assert windows["days_90"] == {"start": "2026-07-04", "end": "2026-10-01"}
    assert windows["days_180"] == {"start": "2026-04-05", "end": "2026-10-01"}
    assert windows["prior_90_for_growth"] == {"start": "2026-06-04", "end": "2026-09-01"}
    assert windows["prior_90_for_persistence"] == {
        "start": "2026-04-05",
        "end": "2026-07-03",
    }


@pytest.mark.parametrize("precision", [None, "issue", "month", "year", "unknown"])
def test_non_day_precision_never_uses_source_page_or_discovery_date(precision: str | None) -> None:
    row = _record(
        "imprecise",
        published_at_precision=precision,
        source_published_at=AS_OF.isoformat(),
        discovered_at=AS_OF.isoformat(),
    )
    result = _topic([row])
    assert result["counts"]["undated"] == 1
    assert result["counts"]["days_180"] == 0
    assert result["evidence"][0]["counted_published_at"] is None


@pytest.mark.parametrize("published_at", [None, "2026-09", "2026-02-30", "2026-09-01T00:00:00Z"])
def test_invalid_or_non_calendar_dates_are_not_treated_as_day_precision(published_at) -> None:
    result = _topic([_record("invalid", published_at=published_at)])
    assert result["counts"]["undated"] == 1
    assert result["counts"]["dated"] == 0


def test_undated_and_future_records_remain_auditable_without_inflating_windows() -> None:
    result = _topic([_record("past", 5), _record("undated", None), _record("future", -5)])
    assert result["counts"]["total"] == 3
    assert result["counts"]["dated"] == 1
    assert result["counts"]["undated"] == 1
    assert result["counts"]["future_dated"] == 1
    assert result["counts"]["days_30"] == 1
    assert result["record_ids"] == ["future", "past", "undated"]
    assert {row["date_status"] for row in result["evidence"]} == {"dated", "undated", "future"}


def test_canonical_studies_are_deduplicated_but_all_record_references_remain() -> None:
    records = [
        _record("original", canonical_study_id="study-1"),
        _record("copy", canonical_study_id="study-1"),
        _record("independent", canonical_study_id="study-2"),
    ]
    result = _topic(records)
    assert result["counts"]["total"] == result["counts"]["days_30"] == 2
    assert result["source_distribution"] == {"source-a": 2}
    assert result["record_ids"] == ["copy", "independent", "original"]
    assert len(result["evidence"]) == 3


def test_duplicate_dates_in_conflict_are_excluded_instead_of_cherry_picked() -> None:
    result = _topic(
        [
            _record("a", 1, canonical_study_id="same"),
            _record("b", 40, canonical_study_id="same"),
        ]
    )
    assert result["counts"]["total"] == result["counts"]["undated"] == 1
    assert result["counts"]["days_180"] == 0
    assert any("日期存在冲突" in reason for reason in result["reasons"])


def test_precise_duplicate_can_supply_publication_date_missing_from_another_copy() -> None:
    result = _topic(
        [
            _record("a", None, canonical_study_id="same"),
            _record("b", 20, canonical_study_id="same"),
        ]
    )
    assert result["counts"]["dated"] == 1
    assert result["counts"]["undated"] == 0
    assert result["counts"]["days_30"] == 1


def test_practice_and_research_remain_separate_even_for_same_canonical_id() -> None:
    results = aggregate_topics(
        [
            _record("research", canonical_study_id="same"),
            _record("practice", canonical_study_id="same", material_type="official_practice"),
        ],
        as_of=AS_OF,
    )
    assert {row["id"] for row in results} == {"organization-research", "organization-practice"}
    assert {row["stream"] for row in results} == {"research", "practice"}
    assert all(row["counts"]["total"] == 1 for row in results)
    assert all(len(row["record_ids"]) == 1 for row in results)


def test_dictionary_is_explicit_allows_multiple_topics_and_ignores_title_keywords() -> None:
    results = aggregate_topics(
        [
            _record("two-topics", topics=["家庭社会学", "青年成长"]),
            _record("unknown", topics=["尚未归类标签"], title="组织社会学"),
        ],
        as_of=AS_OF,
    )
    assert {row["topic_key"] for row in results} == {"care-family", "youth", "uncategorized"}
    assert all(
        row["record_ids"] == ["two-topics"]
        for row in results
        if row["topic_key"] != "uncategorized"
    )
    assert all(row["counts"]["total"] == 1 for row in results)


def test_duplicate_topic_annotations_are_unioned_before_assignment() -> None:
    results = aggregate_topics(
        [
            _record("family", topics=["家庭社会学"], canonical_study_id="same"),
            _record("young", topics=["青年成长"], canonical_study_id="same"),
        ],
        as_of=AS_OF,
    )
    assert {row["topic_key"] for row in results} == {"care-family", "youth"}
    assert all(row["counts"]["total"] == 1 for row in results)
    assert all(row["record_ids"] == ["family", "young"] for row in results)


def test_growth_requires_coverage_and_does_not_infer_it_from_old_records() -> None:
    records = _growth_records() + [_record("old", 400)]
    result = _topic(records)
    assert result["growth_baseline"] is None
    assert result["trend_status"] == "insufficient_evidence"
    assert result["trend_signals"] == []


@pytest.mark.parametrize(("coverage_days", "supported"), [(118, False), (119, True)])
def test_growth_coverage_boundary_and_exact_twofold_threshold(coverage_days: int, supported: bool):
    result = _topic(_growth_records(), coverage_days)
    assert ("rapid_growth" in result["trend_signals"]) is supported
    assert result["growth_baseline"] == (2.0 if supported else None)
    assert "sustained_activity" not in result["trend_signals"]


def test_growth_below_twofold_threshold_is_not_supported() -> None:
    result = _topic(_growth_records(prior_count=7), coverage_days=119)
    assert result["growth_baseline"] == pytest.approx(7 / 3)
    assert result["trend_status"] == "insufficient_evidence"
    assert "rapid_growth" not in result["trend_signals"]


def test_zero_baseline_does_not_turn_into_infinite_growth_or_new_topic_claim() -> None:
    result = _topic(_growth_records(prior_count=0), coverage_days=119)
    assert result["growth_baseline"] == 0.0
    assert result["trend_status"] == "insufficient_evidence"
    assert result["novelty_status"] == "not_assessed"
    assert any("零基线" in reason for reason in result["reasons"])


def test_four_repeated_records_do_not_meet_minimum_independent_study_count() -> None:
    records = [
        _record(f"duplicate-{i}", 1, canonical_study_id="same", source_id=f"source-{i % 2}")
        for i in range(4)
    ] + [_record("prior", 40)]
    result = _topic(records, coverage_days=119)
    assert result["counts"]["days_30"] == 1
    assert result["trend_status"] == "insufficient_evidence"


def test_single_source_cannot_support_growth() -> None:
    records = _growth_records()
    for record in records:
        record["source_id"] = "one-source"
    result = _topic(records, coverage_days=119)
    assert result["trend_status"] == "insufficient_evidence"
    assert result["source_distribution"] == {"one-source": 10}


def test_secondary_source_on_duplicate_does_not_manufacture_cross_source_support() -> None:
    records = _growth_records()
    for record in records:
        record["source_id"] = "one-source"
    records.append(_record("copy", 0, canonical_study_id="recent-0", source_id="repost"))
    result = _topic(records, coverage_days=119)
    assert result["counts"]["days_30"] == 4
    assert result["source_distribution"] == {"one-source": 10, "repost": 1}
    assert result["trend_status"] == "insufficient_evidence"


@pytest.mark.parametrize(("coverage_days", "supported"), [(178, False), (179, True)])
def test_persistence_requires_full_180_day_coverage(coverage_days: int, supported: bool) -> None:
    result = _topic(_persistence_records(), coverage_days)
    assert ("sustained_activity" in result["trend_signals"]) is supported
    assert result["counts"]["previous_90"] == 3


def test_persistence_must_exceed_previous_period_not_only_equal_it() -> None:
    result = _topic(_persistence_records(prior_count=4), coverage_days=179)
    assert result["counts"]["days_90"] == result["counts"]["previous_90"] == 4
    assert "sustained_activity" not in result["trend_signals"]


def test_persistence_needs_three_distinct_calendar_weeks() -> None:
    records = [_record(f"recent-{i}", i, source_id=f"source-{i % 2}") for i in range(4)]
    result = _topic(records, coverage_days=179)
    assert "sustained_activity" not in result["trend_signals"]
    assert any("3个日历周" in reason for reason in result["reasons"])


def test_missing_sources_do_not_count_as_real_source_diversity() -> None:
    records = _growth_records()
    for record in records:
        record["source_id"] = None
        record["source_name"] = None
    result = _topic(records, coverage_days=119)
    assert result["source_ids"] == []
    assert result["source_distribution"] == {}
    assert result["trend_status"] == "insufficient_evidence"


def test_source_name_fallback_and_label_whitespace_normalization() -> None:
    result = _topic([_record("one", source_id=None, topics=["　组织社会学  "])])
    assert result["source_ids"] == ["来源甲"]
    assert result["counts"]["total"] == 1


def test_results_are_deterministic_json_ready_and_do_not_mutate_inputs() -> None:
    records = _growth_records()
    original = deepcopy(records)
    forward = _topic(records, coverage_days=179)
    reverse = _topic(list(reversed(records)), coverage_days=179)
    assert forward == reverse
    assert json.loads(json.dumps(forward, ensure_ascii=False)) == forward
    assert records == original
    assert forward["method"] == "curated_topic_dictionary_v1"
    assert forward["summary_method"] == "editorial_synthesis"
    assert "编辑归纳" in forward["summary"]
    assert forward["novelty_status"] == "not_assessed"


def test_summary_uses_record_questions_and_preserves_evidence_links() -> None:
    result = _topic([_record("one", research_question="医院怎样组织专业协作？")])
    assert "医院怎样组织专业协作？" in result["summary"]
    assert "不代表一致结论" in result["summary"]
    assert result["evidence"][0]["url"] == "https://example.com/one"


def test_empty_and_unrecognized_corpus_have_no_invented_topic() -> None:
    assert aggregate_topics([], as_of=AS_OF) == []
    result = aggregate_topics([_record("unknown", topics=[])], as_of=AS_OF)
    assert result[0]["topic_key"] == "uncategorized"
    assert result[0]["record_ids"] == ["unknown"]
    assert result[0]["trend_status"] == "insufficient_evidence"


def test_missing_record_id_fails_instead_of_inventing_provenance() -> None:
    with pytest.raises(ValueError, match="non-empty string id"):
        aggregate_topics([{"topics": ["组织社会学"]}], as_of=AS_OF)
