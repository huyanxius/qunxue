"""Reviewable additions bound to immutable knowledge and evidence versions."""

from dataclasses import dataclass, replace
from enum import StrEnum

from .domain import content_hash


class UpdateKind(StrEnum):
    SUPPLEMENT = "supplement"
    NEW_TOPIC = "new_topic"
    DISAGREEMENT = "disagreement"
    REVISION = "revision"


class UpdateState(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    STALE = "stale"


@dataclass(frozen=True)
class EvidenceVersion:
    record_id: str
    version: int
    content_hash: str

    def __post_init__(self):
        if not self.record_id.strip() or self.version < 1 or not self.content_hash.strip():
            raise ValueError("evidence requires identity, version and hash")


@dataclass(frozen=True)
class KnowledgeTarget:
    release_id: str
    entry_id: str
    content_version: int

    def __post_init__(self):
        if not self.release_id.strip() or not self.entry_id.strip() or self.content_version < 1:
            raise ValueError("target requires release, entry and version")


@dataclass(frozen=True)
class KnowledgeUpdateProposal:
    proposal_id: str
    target: KnowledgeTarget
    kind: UpdateKind
    proposed_content: str
    rationale: str
    evidence: tuple[EvidenceVersion, ...]
    state: UpdateState = UpdateState.PROPOSED
    reviewer_id: str | None = None
    review_note: str | None = None


def propose_update(
    target: KnowledgeTarget,
    kind: UpdateKind,
    proposed_content: str,
    rationale: str,
    evidence: tuple[EvidenceVersion, ...],
) -> KnowledgeUpdateProposal:
    """Retry-stable identity. New topics anchor to an existing parent-context entry."""
    text, reason = proposed_content.strip(), rationale.strip()
    if not text or not reason or not evidence:
        raise ValueError("proposal requires content, rationale and evidence")
    by_id = {}
    for item in evidence:
        if item.record_id in by_id and by_id[item.record_id] != item:
            raise ValueError("conflicting evidence versions")
        by_id[item.record_id] = item
    refs = tuple(by_id[key] for key in sorted(by_id))
    proposal_id = content_hash(
        {
            "target": [target.release_id, target.entry_id, target.content_version],
            "kind": kind.value,
            "content": text,
            "rationale": reason,
            "evidence": [[r.record_id, r.version, r.content_hash] for r in refs],
        }
    )
    return KnowledgeUpdateProposal(proposal_id, target, kind, text, reason, refs)


def review_update(
    proposal: KnowledgeUpdateProposal,
    *,
    current_target: KnowledgeTarget,
    available_evidence: tuple[EvidenceVersion, ...],
    approve: bool,
    reviewer_id: str,
    note: str,
) -> KnowledgeUpdateProposal:
    """Caller checks reviewer access; persistence must check/update atomically.

    Available evidence includes only currently knowledge-eligible records.
    Approval does not publish or modify an existing knowledge release.
    """
    if proposal.state != UpdateState.PROPOSED:
        raise ValueError("proposal already left review queue")
    if not reviewer_id.strip() or not note.strip():
        raise ValueError("review requires identity and note")
    if approve and (
        proposal.target != current_target
        or not set(proposal.evidence).issubset(set(available_evidence))
    ):
        return replace(proposal, state=UpdateState.STALE)
    return replace(
        proposal,
        state=UpdateState.APPROVED if approve else UpdateState.REJECTED,
        reviewer_id=reviewer_id.strip(),
        review_note=note.strip(),
    )
