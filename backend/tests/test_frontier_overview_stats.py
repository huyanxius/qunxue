from copy import deepcopy
from datetime import date

import pytest

from qunxue_api.modules.frontier_knowledge.analysis import aggregate_topics
from qunxue_api.modules.frontier_knowledge.overview_stats import (
    corpus_statistics,
    visible_corpus_records,
)


def _record(record_id: str, **overrides) -> dict:
    return {
        "id": record_id,
        "canonical_study_id": record_id,
        "source_id": "journal-a",
        "source_name": "期刊甲",
        "publication_year": 2026,
        "material_type": "research_abstract",
        "verification_status": "lead_only",
        "eligibility": {"browse": True},
        "topics": ["社会理论"],
        "methods": None,
        "data": None,
        **overrides,
    }


def _stats(records: list[dict]) -> dict:
    return corpus_statistics(records, aggregate_topics(records, as_of=date(2026, 10, 1)))


def _bins(stats: dict, name: str) -> dict:
    return {row["key"]: row for row in stats[f"{name}_distribution"]}


def test_browse_dedup_uses_latest_page_date_then_descending_id_without_mutation() -> None:
    records = [
        _record("old", canonical_study_id="same", source_published_at="2025-01-01"),
        _record("new-a", canonical_study_id="same", source_published_at="2026-01-01"),
        _record("new-z", canonical_study_id="same", source_published_at="2026-01-01"),
        _record("no-date"),
    ]
    before = deepcopy(records)
    assert [row["id"] for row in visible_corpus_records(records)] == ["new-z", "no-date"]
    assert records == before
    assert _stats(records) == _stats(list(reversed(records)))
    stats = _stats(records)
    assert stats["research_count"] == 2
    assert _bins(stats, "source")["journal-a"]["record_ids"] == ["new-z", "no-date"]


def test_research_and_official_practice_never_share_counts_or_distribution_members() -> None:
    records = [
        _record("research", canonical_study_id="same", methods="访谈"),
        _record(
            "practice",
            canonical_study_id="same",
            material_type="official_practice",
            stream="research",
            methods="回归",
            source_id="practice-only",
        ),
    ]
    stats = _stats(records)
    assert stats["research_count"] == stats["practice_count"] == 1
    assert _bins(stats, "method").keys() == {"interview_observation"}
    for name in ("source", "year", "topic", "method", "data"):
        assert all(row["record_ids"] == ["research"] for row in stats[f"{name}_distribution"])


@pytest.mark.parametrize(
    "flags",
    [
        {"verification_status": "review_queue"},
        {"verification_status": "withdrawn"},
        {"withdrawn": True},
        {"withdrawn_at": "2026-10-01"},
        {"eligibility": {"browse": False}},
        {"eligibility": {"browse": None}},
        {"eligibility": {}},
        {"is_current": False},
    ],
)
def test_ineligible_records_are_excluded_before_representative_selection(flags: dict) -> None:
    records = [
        _record("visible", canonical_study_id="same"),
        _record("hidden", canonical_study_id="same", source_published_at="2026-10-01", **flags),
        _record("other-hidden", **flags),
    ]
    stats = _stats(records)
    assert stats["research_count"] == 1
    assert _bins(stats, "source")["journal-a"]["record_ids"] == ["visible"]


def test_missing_metadata_is_explicit_and_never_inferred_from_other_fields() -> None:
    records = [
        _record(
            "missing",
            source_id=None,
            source_name=None,
            publication_year=None,
            source_published_at="2026-01-01",
            discovered_at="2026-01-02",
            title="2026年期刊研究：访谈、人口普查与回归",
            summary="田野与CFPS分析",
            findings=["使用CGSS数据"],
            sample="问卷",
            data_source="CFPS",
        ),
    ]
    stats = _stats(records)
    for name in ("source", "year", "method", "data"):
        assert _bins(stats, name).keys() == {"unknown"}
    assert stats["classification_method"] == "explicit_field_dictionary_v1"
    assert stats["overlapping_categories"] is True


def test_methods_and_data_have_independent_overlapping_dictionaries() -> None:
    records = [
        _record(
            "overlap",
            methods=["半结构式访谈", "参与式观察与民族志", "比较案例研究"],
            data="中国家庭追踪调查面板数据与第七次人口普查，另有访谈和政策文本",
        ),
        _record("single", methods="访谈与访谈", data="CGSS2021调查数据"),
    ]
    stats = _stats(records)
    methods, data = _bins(stats, "method"), _bins(stats, "data")
    assert methods.keys() == {
        "interview_observation",
        "fieldwork_ethnography",
        "case_study",
        "comparative_analysis",
    }
    assert methods["interview_observation"]["count"] == 2
    assert data.keys() == {"survey", "panel", "census", "interview_fieldwork", "policy_documents"}
    assert data["survey"]["count"] == 2
    assert sum(row["count"] for row in data.values()) > stats["research_count"]
    assert all(row["count"] == len(set(row["record_ids"])) for row in methods.values())


def test_method_dataset_names_never_supply_data_classification() -> None:
    stats = _stats([_record("method-only", methods="CGSS调查数据的回归分析", data=None)])
    assert _bins(stats, "method").keys() == {"quantitative_analysis"}
    assert _bins(stats, "data").keys() == {"unknown"}


@pytest.mark.parametrize(
    "negative",
    [
        "公开摘要未提及访谈或回归方法",
        "未报告具体方法",
        "无访谈数据",
        "数据未知",
        "未说明是否采用问卷调查",
        "未采用人口普查数据",
        "摘要无访谈数据",
        "未发现回归分析说明",
        "not reported",
        "N/A",
    ],
)
def test_negated_or_unreported_fields_do_not_create_positive_matches(negative: str) -> None:
    stats = _stats([_record("negated", methods=negative, data=negative)])
    assert _bins(stats, "method").keys() == {"unknown"}
    assert _bins(stats, "data").keys() == {"unknown"}


def test_negation_is_clause_local_and_nonparticipant_observation_is_positive() -> None:
    stats = _stats(
        [
            _record(
                "mixed",
                methods="非参与式观察；未报告回归分析，采用访谈",
                data="未提供CGSS调查数据；采用政策文本",
            )
        ]
    )
    assert _bins(stats, "method").keys() == {"interview_observation"}
    assert _bins(stats, "data").keys() == {"policy_documents"}


def test_positive_unmatched_text_is_distinct_from_missing_or_unsupported_values() -> None:
    stats = _stats(
        [
            _record("uncategorized", methods="机制探讨", data="城市女性孕产期经历"),
            _record("absent", methods=[], data={"name": "CGSS"}),
        ]
    )
    for name in ("method", "data"):
        assert _bins(stats, name)["unclassified"]["record_ids"] == ["uncategorized"]
        assert _bins(stats, name)["unknown"]["record_ids"] == ["absent"]


def test_topics_use_passed_membership_and_count_duplicate_aliases_once() -> None:
    records = [
        _record("a-alias", canonical_study_id="same", topics=[]),
        _record("z-representative", canonical_study_id="same", topics=[]),
        _record("independent", topics=["社会理论"]),
        _record("practice", material_type="official_practice"),
        _record("hidden", verification_status="review_queue"),
    ]
    topics = [
        {
            "topic_key": "custom",
            "title": "传入主题",
            "stream": "research",
            "record_ids": ["a-alias", "z-representative", "practice", "hidden", "missing"],
        },
        {
            "topic_key": "second",
            "title": "第二主题",
            "stream": "research",
            "record_ids": ["a-alias"],
        },
        {"topic_key": "practice-only", "stream": "practice", "record_ids": ["independent"]},
    ]
    bins = _bins(corpus_statistics(records, topics), "topic")
    assert bins["custom"]["count"] == bins["second"]["count"] == 1
    assert bins["custom"]["record_ids"] == ["z-representative"]
    assert bins["unknown"]["record_ids"] == ["independent"]
    assert bins.keys() == {"custom", "second", "unknown"}


def test_years_and_sources_are_explicit_metadata_and_support_unknowns() -> None:
    stats = _stats(
        [
            _record("year", publication_year="2025", source_id=None, source_name="仅刊名"),
            _record("calendar", publication_year=None, published_at="2024-02-29"),
            _record(
                "invalid",
                publication_year=True,
                published_at="2025-02-29",
                source_id=None,
                source_name=None,
            ),
        ]
    )
    assert _bins(stats, "year").keys() == {"2025", "2024", "unknown"}
    assert _bins(stats, "source").keys() == {"仅刊名", "journal-a", "unknown"}


def test_empty_corpus_returns_empty_distributions_and_zero_counts() -> None:
    stats = corpus_statistics([], [])
    assert stats["research_count"] == stats["practice_count"] == 0
    assert all(
        stats[f"{name}_distribution"] == []
        for name in (
            "source",
            "year",
            "topic",
            "method",
            "data",
        )
    )


def test_raw_corpus_without_runtime_eligibility_remains_supported() -> None:
    record = _record("raw")
    del record["eligibility"]
    assert corpus_statistics([record], [])["research_count"] == 1


def test_ascii_dictionary_tokens_do_not_match_inside_unrelated_words() -> None:
    stats = _stats([_record("words", methods="logistic思路探讨", data="classification说明")])
    assert _bins(stats, "method").keys() == {"unclassified"}
    assert _bins(stats, "data").keys() == {"unclassified"}


def test_visible_missing_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty string id"):
        visible_corpus_records([{"methods": "访谈"}])
