import unittest
from datetime import date

from qunxue_api.modules.frontier_knowledge.calendar import publication_calendar


class CalendarTests(unittest.TestCase):
    def record(self, identifier="r", canonical="s", day="2026-01-15", precision="day", **extra):
        return dict(
            id=identifier,
            canonical_study_id=canonical,
            published_at=day,
            published_at_precision=precision,
            eligibility={"browse": True},
            **extra,
        )

    def run_calendar(self, *records):
        return publication_calendar(list(records), year=2026, as_of=date(2026, 2, 1))

    def test_reprints_count_once(self):
        result = self.run_calendar(self.record(), self.record(identifier="reprint"))
        self.assertEqual(result["days"][0]["count"], 1)
        self.assertEqual(result["days"][0]["record_ids"], ["r", "reprint"])

    def test_month_stays_out_of_day_heatmap(self):
        result = self.run_calendar(self.record(day="2026-01", precision="month"))
        self.assertEqual(result["days"], [])
        self.assertEqual(result["month_precision"][0]["month"], "2026-01")

    def test_conflicting_dates_do_not_choose_ingestion_order(self):
        result = self.run_calendar(self.record(), self.record(identifier="b", day="2026-01-16"))
        self.assertEqual(result["days"], [])
        self.assertEqual(result["conflicting_record_ids"], ["b", "r"])

    def test_coarse_date_can_agree_with_verified_day(self):
        result = self.run_calendar(
            self.record(), self.record(identifier="b", day="2026-01", precision="month")
        )
        self.assertEqual(result["days"][0]["date"], "2026-01-15")

    def test_future_and_withdrawn_not_in_calendar(self):
        result = self.run_calendar(
            self.record(day="2026-05-01"),
            self.record(identifier="old", canonical="s2", is_current=False),
        )
        self.assertEqual(result["days"], [])
        self.assertEqual(result["future_record_ids"], ["r"])

    def test_issue_precision_kept_without_inventing_month(self):
        record = self.record(
            day=None,
            precision="issue",
            source_id="journal",
            issue_id="journal:2026:4",
            publication_year=2026,
        )
        result = self.run_calendar(record)
        self.assertEqual(result["days"], [])
        self.assertEqual(result["month_precision"], [])
        self.assertEqual(result["issue_precision"][0]["issue_id"], "journal:2026:4")
        self.assertEqual(result["issue_precision"][0]["count"], 1)
        self.assertEqual(result["undated_record_ids"], [])
