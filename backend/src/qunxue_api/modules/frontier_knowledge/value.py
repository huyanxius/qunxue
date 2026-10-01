"""Transparent assessment arithmetic; ratings require reviewed passage evidence.

Weights are project policy, not a claim of scholarly consensus. Popularity and
publication venue are deliberately not inputs to academic contribution scoring.
"""

import hashlib
from dataclasses import dataclass

WEIGHTS = {
    "question_significance": 15,
    "contribution_increment": 30,
    "warrantedness": 25,
    "scope_and_limits": 15,
    "scholarly_dialogue": 15,
}
RULE_VERSION = "academic-value-draft-2026-10-02"


@dataclass(frozen=True)
class RatingEvidence:
    record_id: str
    version: int
    snapshot_hash: str
    locator: str
    reviewed_by: str

    def valid(self) -> bool:
        return self.version > 0 and all(
            value.strip()
            for value in (self.record_id, self.snapshot_hash, self.locator, self.reviewed_by)
        )


@dataclass(frozen=True)
class CriterionRating:
    score: int | None
    rationale: str
    evidence: tuple[RatingEvidence, ...] = ()


def assess_value(
    ratings: dict[str, CriterionRating], *, track: str, evidence_readiness: str
) -> dict:
    """Unknown is not zero; partial weights are never renormalized."""
    if track not in {"theoretical", "empirical", "policy_practice"}:
        raise ValueError("unknown research track")
    if evidence_readiness not in {
        "metadata",
        "abstract",
        "full_text_available",
        "passages_checked",
        "human_reviewed",
    }:
        raise ValueError("unknown evidence readiness")
    if set(ratings) - set(WEIGHTS):
        raise ValueError("unknown criterion")
    assessed, missing = {}, {}
    lower, unknown_weight = 0.0, 0
    for criterion, weight in WEIGHTS.items():
        rating = ratings.get(criterion)
        if (
            rating is not None
            and rating.score is not None
            and (type(rating.score) is not int or not 0 <= rating.score <= 4)
        ):
            raise ValueError("rating must be an integer from zero through four")
        reason = None
        if rating is None or rating.score is None:
            reason = "unassessed"
        elif evidence_readiness not in {"passages_checked", "human_reviewed"}:
            reason = "passage_review_required"
        elif (
            not rating.rationale.strip()
            or not rating.evidence
            or not all(e.valid() for e in rating.evidence)
        ):
            reason = "located_evidence_required"
        if reason:
            missing[criterion] = reason
            assessed[criterion] = None
            unknown_weight += weight
        else:
            assessed[criterion] = rating.score
            lower += weight * rating.score / 4
    total = lower if not missing else None
    return {
        "rule_version": RULE_VERSION,
        "track": track,
        "ratings": assessed,
        "academic_value": total,
        "score_bounds": {"lower": lower, "upper": lower + unknown_weight},
        "missing_reasons": missing,
        "evidence_readiness": evidence_readiness,
        "priority": None
        if total is None
        else "priority_review"
        if total >= 75
        else "candidate"
        if total >= 50
        else "not_yet_for_update",
        "authorizes_publication": False,
    }


READING_FIELDS = ("research_question", "methods", "data", "sample", "findings", "limitations")
READING_RULE_VERSION = "reading-evidence-readiness-v1"


def reading_basis(record: dict, snapshot: dict | None) -> list[dict]:
    """Only a located excerpt in the bound source snapshot supports a field."""
    if not snapshot or not (
        snapshot.get("snapshot_id") == record.get("snapshot_id")
        and snapshot.get("content_hash") == record.get("content_hash")
        and snapshot.get("source_verified") is True
    ):
        return []
    blocks = {b.get("block_id"): b for b in snapshot.get("blocks", []) if isinstance(b, dict)}
    basis = []
    for evidence in record.get("evidence", []):
        block = blocks.get(evidence.get("block_id"))
        snippet = evidence.get("snippet")
        if not block or not isinstance(snippet, str) or not snippet.strip():
            continue
        if (
            evidence.get("locator") != block.get("locator")
            or not block.get("locator")
            or evidence.get("url") != block.get("url")
            or snippet not in (block.get("text") or "")
        ):
            continue
        fields = [f for f in READING_FIELDS if f in evidence.get("supports", []) and record.get(f)]
        if fields:
            basis.append(
                {
                    "block_id": evidence["block_id"],
                    "locator": evidence["locator"],
                    "url": evidence["url"],
                    "snippet": snippet,
                    "fields": fields,
                    "basis_type": "located_source_excerpt",
                    "source_content_hash": snapshot["content_hash"],
                }
            )
    basis.extend(_assistant_reading_basis(record, snapshot, blocks))
    return basis


def _assistant_reading_basis(record: dict, snapshot: dict, blocks: dict) -> list[dict]:
    """Verify approved self-written abstract notes without exposing source abstracts."""
    if (
        record.get("reading_note_review_type") != "assistant_abstract_reading"
        or record.get("analysis_scope") != "abstract"
    ):
        return []
    internal = record.get("internal_source_content") or {}
    original = snapshot.get("original_input", {}).get("internal_source_content") or {}
    source = internal.get("abstract")
    if not isinstance(source, str) or not source or source != original.get("abstract"):
        return []
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if record.get("reading_note_basis_sha256") != digest:
        return []
    basis = []
    source_evidence = record.get("evidence", [])
    for claim in record.get("analysis_evidence", []):
        field, statement = claim.get("field"), claim.get("statement")
        if field not in READING_FIELDS or not statement:
            continue
        displayed = record.get(field)
        if not (displayed == statement or isinstance(displayed, list) and statement in displayed):
            continue
        indexes = claim.get("evidence_indexes", [])
        if not indexes or any(
            type(i) is not int or not 0 <= i < len(source_evidence) for i in indexes
        ):
            continue
        for index in indexes:
            evidence = source_evidence[index]
            block = blocks.get(evidence.get("block_id"))
            if (
                not block
                or "abstract" not in evidence.get("supports", [])
                or not evidence.get("locator")
                or not evidence.get("url")
                or evidence.get("locator") != block.get("locator")
                or evidence.get("url") != block.get("url")
            ):
                continue
            basis.append(
                {
                    "block_id": evidence["block_id"],
                    "locator": evidence["locator"],
                    "url": evidence["url"],
                    "snippet": statement,
                    "fields": [field],
                    "basis_type": "assistant_abstract_reading",
                    "source_content_hash": digest,
                }
            )
    return basis


def assess_record_value(record: dict, snapshot: dict | None) -> dict:
    """Read existing reviewed facts; never manufacture ratings from an abstract.

    value_assessment is an optional trusted-import fact, not a new review system.
    Every rating is bound to this record version and a retained source passage.
    """
    basis = reading_basis(record, snapshot)
    supported = [f for f in READING_FIELDS if any(f in b["fields"] for b in basis)]
    full_passages = bool(
        basis
        and snapshot
        and snapshot.get("scope") == "full_text"
        and record.get("analysis_scope") == "full_text"
    )
    readiness = "passages_checked" if full_passages else "abstract" if basis else "metadata"
    raw = record.get("value_assessment")
    raw = raw if isinstance(raw, dict) else {}
    track = raw.get("track")
    valid_track = track in {"empirical", "theoretical", "policy_practice"}
    stored_readiness = raw.get("evidence_readiness")
    if full_passages and stored_readiness in {"passages_checked", "human_reviewed"}:
        readiness = stored_readiness
    ratings, rejected = {}, {}
    raw_ratings = raw.get("ratings")
    raw_ratings = raw_ratings if isinstance(raw_ratings, dict) else {}
    for key in WEIGHTS:
        item = raw_ratings.get(key)
        if not isinstance(item, dict):
            continue
        try:
            evidence = tuple(RatingEvidence(**e) for e in item.get("evidence", []))
            score = item.get("score")
            if score is not None and (type(score) is not int or not 0 <= score <= 4):
                raise ValueError("invalid score")
            rationale = item.get("rationale", "")
            if not isinstance(rationale, str):
                raise ValueError("invalid rationale")
            blocks = snapshot.get("blocks", []) if snapshot else []
            bound = (
                snapshot
                and snapshot.get("source_verified") is True
                and snapshot.get("snapshot_id") == record.get("snapshot_id")
                and snapshot.get("content_hash") == record.get("content_hash")
            )
            if evidence and not (
                bound
                and all(
                    e.valid()
                    and e.record_id == record.get("id")
                    and e.version == record.get("version")
                    and e.snapshot_hash == snapshot.get("content_hash")
                    and any(b.get("locator") == e.locator and b.get("text") for b in blocks)
                    for e in evidence
                )
            ):
                rejected[key] = "record_snapshot_binding_required"
                continue
            if valid_track:
                ratings[key] = CriterionRating(score, rationale, evidence)
        except (TypeError, ValueError, AttributeError):
            rejected[key] = "invalid_stored_rating"
    assessment = assess_value(
        ratings, track=track if valid_track else "empirical", evidence_readiness=readiness
    )
    assessment["track"] = track if valid_track else None
    assessment["missing_reasons"].update(rejected)
    if not valid_track:
        assessment["missing_reasons"] = dict.fromkeys(WEIGHTS, "research_track_required")
    assessed_count = sum(v is not None for v in assessment["ratings"].values())
    assessment["status"] = (
        "assessed"
        if assessed_count == len(WEIGHTS)
        else "partial"
        if assessed_count
        else "unassessed"
    )
    assessment["criteria"] = {
        key: {
            "weight": weight,
            "score": assessment["ratings"][key],
            "rationale": ratings[key].rationale if key in ratings else None,
            "evidence": [vars(e) for e in ratings[key].evidence] if key in ratings else [],
            "missing_reason": assessment["missing_reasons"].get(key),
        }
        for key, weight in WEIGHTS.items()
    }
    missing = {
        f: record.get("missing_reasons", {}).get(f)
        or ("located_source_evidence_required" if record.get(f) else "field_not_available")
        for f in READING_FIELDS
        if f not in supported
    }
    priority = (
        "passage_supported" if full_passages else "abstract_supported" if basis else "metadata_only"
    )
    return {
        "record_id": record["id"],
        "title": record["title"],
        "version": record["version"],
        "content_hash": record["content_hash"],
        "reading_rule_version": READING_RULE_VERSION,
        "reading_priority": priority,
        "evidence_readiness": readiness,
        "supported_fields": supported,
        "missing_fields": missing,
        # Source evidence stays internal. Public reading support only needs
        # stable references; even a valid snippet can contain a full raw abstract.
        "basis": [{**item, "snippet": ""} for item in basis],
        "assessment": assessment,
        "limitations": [
            "阅读顺序按可定位证据的准备度组织，不代表学术质量或模型理解。",
            "rubric 权重是项目草案；未评估不是零分，部分评分不重算权重。",
        ],
    }
