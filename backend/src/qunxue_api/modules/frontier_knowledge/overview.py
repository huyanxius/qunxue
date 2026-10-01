"""Corpus-wide synthesis validated against a complete, current reading index."""

from hashlib import sha256

from .briefs import _references, _text
from .domain import content_hash

OVERVIEW_SECTIONS = {"shared_focus", "change", "methods", "differences", "research_opportunities"}


def overview_basis(records: list[dict]) -> str:
    return content_hash(sorted((r["id"], r["content_hash"]) for r in records))


def validate_corpus_overview(value: dict, research: list[dict]) -> dict:
    if not isinstance(value, dict) or value.get("generated_by") != "assistant_evidence_synthesis":
        raise ValueError(
            "corpus overview requires explicit assistant evidence synthesis provenance"
        )
    records = {record["id"]: record for record in research}
    if not records:
        raise ValueError("corpus overview requires a non-empty research corpus")
    scope = value.get("scope")
    if not isinstance(scope, dict) or scope.get("stream") != "research":
        raise ValueError("corpus overview must keep research and practice separate")
    allowed = set(records)
    for label, ids in (
        ("coverage_record_ids", scope.get("coverage_record_ids")),
        ("reviewed_record_ids", value.get("reviewed_record_ids")),
    ):
        if not isinstance(ids, list) or len(ids) != len(allowed) or set(ids) != allowed:
            raise ValueError(
                f"{label} must cover every current deduplicated research record exactly once"
            )
    index = value.get("review_index")
    if not isinstance(index, list) or len(index) != len(allowed):
        raise ValueError("review_index must cover all current research summaries")
    seen = set()
    for row in index:
        if not isinstance(row, dict) or row.get("record_id") not in allowed:
            raise ValueError("review_index references missing research")
        key = row["record_id"]
        if key in seen:
            raise ValueError("review_index cannot repeat a research record")
        seen.add(key)
        record = records[key]
        if (
            record.get("summary_method") != "assistant_evidence_synthesis"
            or not record.get("summary")
            or not record.get("analysis_evidence")
        ):
            raise ValueError("all corpus research must have evidence-linked assistant summaries")
        if row.get("summary_sha256") != sha256(record["summary"].encode("utf-8")).hexdigest():
            raise ValueError("review_index summary hash is stale or incorrect")
    sections = value.get("sections")
    if not isinstance(sections, list) or len(sections) != len(OVERVIEW_SECTIONS):
        raise ValueError("corpus overview requires all five evidence-linked sections")
    section_ids, evidence_ids, cleaned = set(), set(), []
    for section in sections:
        if not isinstance(section, dict) or section.get("id") not in OVERVIEW_SECTIONS:
            raise ValueError("unrecognized corpus overview section")
        key = section["id"]
        if key in section_ids:
            raise ValueError("corpus overview sections cannot repeat")
        section_ids.add(key)
        statements = section.get("statements")
        if not isinstance(statements, list) or not 1 <= len(statements) <= 20:
            raise ValueError("each overview section requires evidence-linked statements")
        entries = []
        for statement in statements:
            if not isinstance(statement, dict):
                raise ValueError("overview statement must be an object")
            ids = _references(statement.get("evidence_record_ids"), allowed, "overview statement")
            if key in {"shared_focus", "change", "differences"} and len(ids) < 2:
                raise ValueError("cross-paper overview statements need at least two studies")
            entries.append(
                {
                    "text": _text(statement.get("text"), "overview statement"),
                    "evidence_record_ids": ids,
                }
            )
            evidence_ids.update(ids)
        cleaned.append(
            {
                "id": key,
                "title": _text(section.get("title"), "section title"),
                "statements": entries,
            }
        )
    return {
        "headline": _text(value.get("headline"), "overview headline"),
        "summary": _text(value.get("summary"), "overview summary"),
        "sections": cleaned,
        "scope": {
            "stream": "research",
            "coverage_record_ids": sorted(allowed),
            "analyzed_record_count": len(allowed),
            "source_count": len({r["source_id"] for r in research}),
            "systematic_review_method": _text(
                scope.get("systematic_review_method"), "review method"
            ),
        },
        "reviewed_record_ids": sorted(allowed),
        "review_index": sorted(index, key=lambda row: row["record_id"]),
        "evidence_record_ids": sorted(evidence_ids),
        "generated_by": "assistant_evidence_synthesis",
        "basis_content_hash": overview_basis(research),
        "source_hashes": [
            {"record_id": key, "content_hash": records[key]["content_hash"]}
            for key in sorted(allowed)
        ],
    }
