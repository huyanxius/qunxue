import unittest

from qunxue_api.modules.frontier_knowledge.updates import (
    EvidenceVersion,
    KnowledgeTarget,
    UpdateKind,
    UpdateState,
    propose_update,
    review_update,
)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.target = KnowledgeTarget("release", "entry", 1)
        self.ref = EvidenceVersion("paper", 1, "hash")
        self.proposal = propose_update(
            self.target,
            UpdateKind.SUPPLEMENT,
            "New evidence",
            "Explains new observation",
            (self.ref,),
        )

    def review(self, **kwargs):
        return review_update(
            self.proposal,
            current_target=kwargs.get("target", self.target),
            available_evidence=kwargs.get("evidence", (self.ref,)),
            approve=kwargs.get("approve", True),
            reviewer_id="teacher",
            note="Reviewed",
        )

    def test_idempotent_suggestion(self):
        duplicate = propose_update(
            self.target,
            UpdateKind.SUPPLEMENT,
            "New evidence",
            "Explains new observation",
            (self.ref, self.ref),
        )
        self.assertEqual(self.proposal, duplicate)

    def test_concurrent_knowledge_change_invalidates_acceptance(self):
        self.assertEqual(
            self.review(target=KnowledgeTarget("release", "entry", 2)).state, UpdateState.STALE
        )
        self.assertEqual(self.proposal.state, UpdateState.PROPOSED)

    def test_withdrawal_invalidates_acceptance(self):
        self.assertEqual(self.review(evidence=()).state, UpdateState.STALE)

    def test_evidence_revision_invalidates_acceptance(self):
        self.assertEqual(
            self.review(evidence=(EvidenceVersion("paper", 2, "new"),)).state, UpdateState.STALE
        )

    def test_approval_does_not_change_knowledge_target(self):
        accepted = self.review()
        self.assertEqual(accepted.state, UpdateState.APPROVED)
        self.assertEqual(accepted.target, self.target)
        self.assertEqual(accepted.reviewer_id, "teacher")

    def test_conflicting_evidence_rejected(self):
        with self.assertRaises(ValueError):
            propose_update(
                self.target,
                UpdateKind.REVISION,
                "text",
                "reason",
                (self.ref, EvidenceVersion("paper", 2, "changed")),
            )

    def test_can_reject_obsolete_proposal(self):
        self.assertEqual(self.review(evidence=(), approve=False).state, UpdateState.REJECTED)
