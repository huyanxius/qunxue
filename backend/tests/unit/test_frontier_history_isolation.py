import unittest
from datetime import date

from qunxue_api.modules.frontier_knowledge.analysis import aggregate_topics
from qunxue_api.modules.frontier_knowledge.domain import content_hash
from qunxue_api.modules.frontier_knowledge.period_report import period_report
from qunxue_api.modules.frontier_knowledge.periods import PublicationInterval
from qunxue_api.modules.frontier_knowledge.service import FrontierService


def row(identifier, day, **extra):
    return dict(
        id=identifier,
        canonical_study_id=identifier,
        source_id="journal",
        source_name="Journal",
        title="组织制度研究",
        topics=["组织社会学"],
        material_type="research_abstract",
        published_at=day,
        published_at_precision="day",
        content_hash=identifier,
        summary=identifier,
        research_question=identifier,
        eligibility={"browse": True},
        url="https://example.org/" + identifier,
        **extra,
    )


class Store:
    def __init__(self, records, briefs=(), coverage=()):
        self.records, self.briefs, self.coverage = records, briefs, coverage

    def list_records(self):
        return self.records

    def get_record(self, identifier):
        return next((r for r in self.records if r["id"] == identifier), None)

    def list_briefs(self):
        return self.briefs

    def list_sources(self):
        return []

    def list_issue_coverage(self):
        return self.coverage

    def get_corpus_overview(self):
        return None


class HistoryTests(unittest.TestCase):
    def test_historical_topic_search_calendar_overview_and_brief_agree(self):
        past, future = row("old", "2024-05-01"), row("future", "2025-05-01")
        brief = dict(
            topic_key="organization",
            stream="research",
            summary="FUTURE SYNTHESIS",
            generated_by="offline_editorial",
            evidence_record_ids=["old", "future"],
            basis_content_hash=content_hash([("future", "future"), ("old", "old")]),
        )
        service = FrontierService(Store([past, future], [brief]))
        cutoff = date(2024, 6, 20)
        topic = service.topics(as_of=cutoff)[0]
        self.assertEqual(topic["id"], "organization-research")
        self.assertEqual(topic["record_ids"], ["old"])
        self.assertEqual([e["record_id"] for e in topic["evidence"]], ["old"])
        self.assertNotIn("future", topic["summary"])
        self.assertIsNone(topic["editorial_brief"])
        self.assertIsNone(topic["research_brief"])
        self.assertEqual(service.search(topic_id=topic["id"], as_of=cutoff)["total"], 1)
        self.assertEqual(service.overview(as_of=cutoff)["statistics"]["research_count"], 1)
        self.assertEqual(service.calendar(year=2025, as_of=cutoff)["future_record_ids"], [])
        self.assertEqual(service.record("old", as_of=cutoff)["id"], "old")
        with self.assertRaises(LookupError):
            service.record("future", as_of=cutoff)

    def test_aggregate_does_not_leak_future_duplicate_text_or_tags(self):
        past = row("old", "2024-05-01")
        future = row("future", "2025-05-01")
        future["canonical_study_id"] = "old"
        future["topics"] = ["数字社会"]
        topics = aggregate_topics([past, future], date(2024, 6, 20))
        self.assertEqual([t["id"] for t in topics], ["organization-research"])
        self.assertEqual(topics[0]["record_ids"], ["old"])
        self.assertNotIn("future", topics[0]["summary"])

    def test_issue_precision_stays_out_of_exact_day_calendar(self):
        issue = row(
            "issue",
            None,
            publication_year=2024,
            issue_id="journal:2024:3",
            discovered_at="2024-06-01",
        )
        issue["published_at_precision"] = "issue"
        service = FrontierService(Store([issue]))
        calendar = service.calendar(year=2024, as_of=date(2024, 6, 20))
        self.assertEqual(calendar["days"], [])
        self.assertEqual(calendar["month_precision"], [])
        self.assertEqual(calendar["issue_precision"][0]["record_ids"], ["issue"])
        self.assertEqual(service.topics(as_of=date(2024, 6, 20))[0]["counts"]["dated"], 0)

    def test_matching_brief_basis_remains_available(self):
        record = row("old", "2024-05-01")
        brief = dict(
            topic_key="organization",
            stream="research",
            summary="VALID",
            generated_by="offline_editorial",
            evidence_record_ids=["old"],
            basis_content_hash=content_hash([("old", "old")]),
        )
        topic = FrontierService(Store([record], [brief])).topics(as_of=date(2024, 6, 20))[0]
        self.assertEqual(topic["summary"], "VALID")
        brief["basis_content_hash"] = "stale"
        self.assertIsNone(
            FrontierService(Store([record], [brief])).topics(as_of=date(2024, 6, 20))[0][
                "editorial_brief"
            ]
        )

    def test_empty_real_coverage_never_claims_normalized_series(self):
        service = FrontierService(Store([row("old", "2024-05-01")]))
        topic = service.topics(as_of=date(2024, 6, 20))[0]
        self.assertTrue(all(m["normalized_share"] is None for m in topic["monthly_series"]))
        self.assertEqual(topic["series_metadata"]["comparison_status"], "sample_distribution_only")


def issue_fixture():
    records, ledgers = [], []
    for year, topical in [(2023, 1), (2024, 2)]:
        for issue in (1, 2, 3):
            for index in range(2):
                r = row(
                    f"{year}-{issue}-{index}",
                    None,
                    publication_year=year,
                    publication_issue=issue,
                    issue_id=f"journal:{year}:{issue}",
                )
                r["published_at_precision"] = "issue"
                if index >= topical:
                    r["topics"] = ["数字社会"]
                    r["title"] = "数字技术研究"
                records.append(r)
        ledgers.append(
            dict(
                source_id="journal",
                period=str(year),
                period_precision="year",
                coverage_scope="fixed_issue_sample",
                issue_ids=[f"journal:{year}:{n}" for n in (1, 2)],
                comparison_issue_keys=["1", "2"],
                coverage_complete=True,
                candidate_count=4,
                readable_count=4,
                included_count=4,
                analyzed_count=4,
                excluded_nonresearch_count=0,
                evidence_refs=[f"directory:{year}:1,2"],
            )
        )
    return records, ledgers


def report(records, ledgers, as_of=date(2025, 1, 2), topic_key="organization-research"):
    return period_report(
        records,
        ledgers,
        previous=PublicationInterval(date(2023, 1, 1), date(2023, 12, 31)),
        current=PublicationInterval(date(2024, 1, 1), date(2024, 12, 31)),
        topic_key=topic_key,
        as_of=as_of,
    )


class FixedIssueTests(unittest.TestCase):
    def test_real_topic_id_fixed_issue_denominator_is_comparable(self):
        records, ledgers = issue_fixture()
        actual = report(records, ledgers)
        self.assertEqual(actual["comparability"], "complete_common_cohort")
        self.assertEqual(actual["previous_count"], 3)  # all observed, including issue 3
        self.assertEqual(actual["current_count"], 6)
        self.assertEqual(actual["previous_denominator"], 4)  # only issues 1 and 2
        self.assertEqual(actual["current_denominator"], 4)
        self.assertEqual(actual["previous_share"], 0.5)
        self.assertEqual(actual["current_share"], 1)
        self.assertEqual(actual["delta_pp"], 50)
        self.assertEqual(actual["share_basis"], "fixed_issue_sample_common_sources")
        self.assertFalse(actual["hotspot_allowed"])  # keep existing evidence gates

    def test_missing_issue_open_year_or_changed_issue_universe_abstains(self):
        records, ledgers = issue_fixture()
        self.assertEqual(report(records[:-4], ledgers)["comparability"], "insufficient_coverage")
        self.assertEqual(
            report(records, ledgers, date(2024, 9, 1))["comparability"], "incomplete_period"
        )
        ledgers[-1]["comparison_issue_keys"] = ["1", "3"]
        self.assertEqual(report(records, ledgers)["comparability"], "insufficient_coverage")

    def test_future_year_evidence_is_absent_and_period_sample_not_fabricated(self):
        records, ledgers = issue_fixture()
        actual = report(records, ledgers, date(2024, 9, 1))
        self.assertEqual(actual["current_count"], 0)
        self.assertTrue(all(not key.startswith("2024-") for key in actual["evidence_record_ids"]))


class SeriesTests(unittest.TestCase):
    def test_source_blanket_complete_does_not_substitute_for_real_coverage(self):
        from qunxue_api.modules.frontier_knowledge.series import topic_series

        r = row("old", "2024-05-01")
        source = dict(
            source_id="journal",
            coverage_complete=True,
            coverage_start="2020-01-01",
            coverage_end="2026-12-31",
        )
        actual = topic_series(
            {"stream": "research", "record_ids": ["old"]}, [r], [source], [], date(2024, 6, 20)
        )
        self.assertTrue(all(m["normalized_share"] is None for m in actual["monthly_series"]))
        self.assertTrue(all(not m["coverage_complete"] for m in actual["monthly_series"]))

    def test_fixed_issue_ledgers_can_enter_topics_without_fabricated_months(self):
        records, ledgers = issue_fixture()
        for r in records:
            r["discovered_at"] = "2025-01-01"
        topic = FrontierService(Store(records, coverage=ledgers)).topics(as_of=date(2025, 1, 2))[0]
        self.assertEqual(topic["series_metadata"]["comparison_status"], "complete_issue_cohort")
        self.assertEqual(topic["issue_series"], [])
        self.assertTrue(all(m["record_count"] == 0 for m in topic["monthly_series"]))


class GuardTests(unittest.TestCase):
    def test_ledger_issue_keys_must_match_actual_publication_issue(self):
        records, ledgers = issue_fixture()
        for ledger in ledgers:
            ledger["comparison_issue_keys"] = ["8", "9"]
        self.assertEqual(report(records, ledgers)["comparability"], "insufficient_coverage")

    def test_nested_brief_cannot_reference_future_evidence(self):
        r = row("old", "2024-05-01")
        brief = dict(
            topic_key="organization",
            stream="research",
            summary="VALID",
            generated_by="offline_editorial",
            evidence_record_ids=["old"],
            basis_content_hash=content_hash([("old", "old")]),
            research_brief={
                "evidence_record_ids": ["old"],
                "development": {"text": "future", "evidence_record_ids": ["future"]},
            },
        )
        topic = FrontierService(Store([r], [brief])).topics(as_of=date(2024, 6, 20))[0]
        self.assertIsNone(topic["research_brief"])

    def test_future_duplicate_does_not_conflict_with_historical_period_study(self):
        records, ledgers = issue_fixture()
        r = dict(
            records[0],
            id="future-variant",
            publication_year=2026,
            published_at="2026-01-01",
            published_at_precision="day",
            topics=["数字社会"],
        )
        actual = report(records + [r], ledgers)
        self.assertEqual(actual["previous_count"], 3)
        self.assertNotIn("future-variant", actual["evidence_record_ids"])


if __name__ == "__main__":
    unittest.main()


class ReviewGuardTests(unittest.TestCase):
    def test_unknown_or_misspelled_annual_scope_cannot_claim_complete_source(self):
        records, ledgers = issue_fixture()
        records = [r for r in records if r["publication_issue"] in (1, 2)]
        for scope in ("fixed_issue_sampel", "unknown", "complete_source_period", None):
            broken = [dict(ledger, coverage_scope=scope) for ledger in ledgers]
            for ledger in broken:
                ledger.pop("issue_ids")
                ledger.pop("comparison_issue_keys")
            self.assertEqual(report(records, broken)["comparability"], "insufficient_coverage")

    def test_damaged_nested_references_discard_brief_without_crashing_topics(self):
        r = row("old", "2024-05-01")
        for bad in ({}, []):
            for field in ("evidence_record_ids", "record_id"):
                item = {field: [bad] if field == "evidence_record_ids" else bad}
                brief = dict(
                    topic_key="organization",
                    stream="research",
                    summary="BAD",
                    generated_by="offline_editorial",
                    evidence_record_ids=["old"],
                    basis_content_hash=content_hash([("old", "old")]),
                    research_brief=item,
                )
                topic = FrontierService(Store([r], [brief])).topics(as_of=date(2024, 6, 20))[0]
                self.assertIsNone(topic["editorial_brief"])
                self.assertEqual(topic["record_ids"], ["old"])

    def test_monthly_series_excludes_incompatible_coarse_fine_versions(self):
        from qunxue_api.modules.frontier_knowledge.series import topic_series

        day = row("day", "2024-01-15")
        month = dict(day, id="month", published_at="2024-02", published_at_precision="month")
        result = topic_series(
            {"stream": "research", "record_ids": ["day", "month"]},
            [day, month],
            [],
            [],
            date(2024, 3, 1),
        )
        self.assertTrue(all(p["record_count"] == 0 for p in result["monthly_series"]))

    def test_monthly_series_keeps_compatible_coarse_fine_publication(self):
        from qunxue_api.modules.frontier_knowledge.series import topic_series

        day = row("day", "2024-01-15")
        month = dict(day, id="month", published_at="2024-01", published_at_precision="month")
        result = topic_series(
            {"stream": "research", "record_ids": ["day", "month"]},
            [day, month],
            [],
            [],
            date(2024, 3, 1),
        )
        january = next(p for p in result["monthly_series"] if p["month"] == "2024-01")
        self.assertEqual(january["record_count"], 1)
        self.assertEqual(january["dated_record_ids"], ["day", "month"])
