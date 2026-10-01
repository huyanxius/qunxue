import unittest

from qunxue_api.modules.frontier_knowledge.value import (
    WEIGHTS,
    CriterionRating,
    RatingEvidence,
    assess_value,
)


class ValueTests(unittest.TestCase):
    def setUp(self):
        self.evidence = RatingEvidence("paper", 1, "hash", "section3 paragraph2", "reviewer")
        self.full = {
            key: CriterionRating(4, "Located rationale", (self.evidence,)) for key in WEIGHTS
        }

    def test_abstract_does_not_become_full_quality_score(self):
        result = assess_value(self.full, track="empirical", evidence_readiness="abstract")
        self.assertIsNone(result["academic_value"])
        self.assertEqual(result["score_bounds"], {"lower": 0, "upper": 100})

    def test_unknown_not_renormalized(self):
        result = assess_value(
            {"contribution_increment": self.full["contribution_increment"]},
            track="theoretical",
            evidence_readiness="passages_checked",
        )
        self.assertIsNone(result["academic_value"])
        self.assertEqual(result["score_bounds"], {"lower": 30, "upper": 100})

    def test_score_not_publication_authority(self):
        result = assess_value(self.full, track="empirical", evidence_readiness="human_reviewed")
        self.assertEqual(result["academic_value"], 100)
        self.assertFalse(result["authorizes_publication"])

    def test_zero_needs_evidence_too(self):
        result = assess_value(
            {"warrantedness": CriterionRating(0, "No evidence")},
            track="empirical",
            evidence_readiness="passages_checked",
        )
        self.assertIsNone(result["ratings"]["warrantedness"])

    def test_unknown_dimensions_rejected(self):
        with self.assertRaises(ValueError):
            assess_value(
                {"citations": CriterionRating(4, "popular")},
                track="empirical",
                evidence_readiness="human_reviewed",
            )
