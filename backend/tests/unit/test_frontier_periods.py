import unittest
from datetime import date

from qunxue_api.modules.frontier_knowledge.periods import (
    PeriodStudy,
    PublicationInterval,
    SourceCoverage,
    compare_periods,
    publication_interval,
)


class PeriodTests(unittest.TestCase):
    def setUp(self):
        self.old = PublicationInterval(date(2025, 1, 1), date(2025, 1, 31))
        self.new = PublicationInterval(date(2026, 1, 1), date(2026, 1, 31))
        self.coverage = (
            SourceCoverage("a", self.old, True, "archive-2025"),
            SourceCoverage("a", self.new, True, "archive-2026"),
        )
        self.studies = (
            PeriodStudy("old", "a", self.old, frozenset(), ("old-ref",)),
            PeriodStudy("new", "a", self.new, frozenset({"care"}), ("new-ref",)),
        )

    def compare(self, studies=None, **kwargs):
        return compare_periods(
            studies or self.studies,
            self.coverage,
            self.old,
            self.new,
            "care",
            as_of=kwargs.get("as_of", date(2026, 2, 1)),
        )

    def test_month_is_not_day(self):
        result = publication_interval("2026-02", "month")
        self.assertEqual(result.end, date(2026, 2, 28))
        self.assertIsNone(publication_interval("2026-02-31", "month"))
        self.assertIsNone(publication_interval("2026-02", "day"))

    def test_duplicate_does_not_change_share(self):
        original = self.compare()
        repeated = self.compare(self.studies + (self.studies[1],) * 50)
        self.assertEqual(original, repeated)
        self.assertEqual(original.mean_share_change, 1.0)

    def test_new_source_does_not_change_share(self):
        added = PeriodStudy("new2", "b", self.new, frozenset({"care"}), ("b-ref",))
        result = self.compare(self.studies + (added,))
        self.assertEqual(result.mean_share_change, self.compare().mean_share_change)
        self.assertEqual(result.excluded_source_ids, ("b",))

    def test_last_day_is_still_open(self):
        self.assertEqual(self.compare(as_of=date(2026, 1, 31)).status, "open_period")

    def test_open_period_cannot_decline(self):
        result = self.compare(as_of=date(2026, 1, 15))
        self.assertEqual(result.status, "open_period")
        self.assertIsNone(result.mean_share_change)

    def test_conflict_invalidates_source_not_denominator_only(self):
        conflicting = PeriodStudy("new", "a", self.new, frozenset(), ("new-ref2",))
        result = self.compare(self.studies + (conflicting,))
        self.assertEqual(result.status, "no_comparable_sources")

    def test_month_does_not_fit_partial_month(self):
        self.assertFalse(
            self.new.contained_by(PublicationInterval(date(2026, 1, 1), date(2026, 1, 15)))
        )

    def test_coverage_requires_evidence(self):
        coverage = tuple(SourceCoverage(c.source_id, c.period, True, "") for c in self.coverage)
        result = compare_periods(
            self.studies, coverage, self.old, self.new, "care", as_of=date(2026, 2, 1)
        )
        self.assertEqual(result.status, "no_comparable_sources")

    def test_iso_week_date_not_accepted_as_calendar_day(self):
        self.assertIsNone(publication_interval("2026-W01-1", "day"))


if __name__ == "__main__":
    unittest.main()
