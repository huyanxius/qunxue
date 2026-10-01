"""Evidence-linked editorial summaries, separate from full-text verification."""

SYNTHESIS_METHODS = {"offline_editorial", "assistant_evidence_synthesis"}


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 12000:
        raise ValueError(f"{field} requires non-empty text of at most 12000 characters")
    return value.strip()


def _references(value: object, allowed: set[str], field: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(record_id, str) or record_id not in allowed for record_id in value)
    ):
        raise ValueError(f"{field} must reference current evidence in this topic and stream")
    return list(dict.fromkeys(value))


def validate_research_brief(value: dict, allowed_ids: set[str], records: dict[str, dict]) -> dict:
    if not isinstance(value, dict):
        raise ValueError("research_brief must be an object")
    ids = _references(value.get("evidence_record_ids"), allowed_ids, "research_brief evidence")
    allowed = set(ids)

    def statement(item: object, field: str, *, multiple: bool = False) -> dict:
        if not isinstance(item, dict):
            raise ValueError(f"{field} must be an evidence-linked statement")
        references = _references(item.get("evidence_record_ids"), allowed, field)
        if multiple and len({records[i]["canonical_study_id"] for i in references}) < 2:
            raise ValueError(f"{field} must compare at least two independent records")
        return {"text": _text(item.get("text"), field), "evidence_record_ids": references}

    result = {"headline": _text(value.get("headline"), "headline"), "evidence_record_ids": ids}
    for field in ("development", "research_implication"):
        result[field] = None if value.get(field) is None else statement(value[field], field)
    for field in ("consensus", "differences", "methods"):
        items = value.get(field, [])
        if not isinstance(items, list) or len(items) > 12:
            raise ValueError(f"{field} must be a list with at most 12 statements")
        result[field] = [
            statement(item, field, multiple=field in {"consensus", "differences"}) for item in items
        ]
    reads = value.get("priority_reads", [])
    if not isinstance(reads, list) or len(reads) > 12:
        raise ValueError("priority_reads must be a list with at most 12 records")
    result["priority_reads"] = []
    seen = set()
    for item in reads:
        if not isinstance(item, dict) or item.get("record_id") not in allowed:
            raise ValueError("priority_reads must reference the brief's own evidence")
        if item["record_id"] in seen:
            raise ValueError("priority_reads cannot repeat a record")
        seen.add(item["record_id"])
        result["priority_reads"].append(
            {"record_id": item["record_id"], "reason": _text(item.get("reason"), "reading reason")}
        )
    return result


def validate_paper_analysis(record: dict) -> None:
    """Validate traceability only; this gate never upgrades publication eligibility."""
    scope = record.get("analysis_scope")
    if scope is not None and scope not in {"abstract", "full_text", "practice_body", "metadata"}:
        raise ValueError("unrecognized paper analysis scope")
    if record.get("verification_status") == "lead_only" and scope == "full_text":
        raise ValueError("abstract leads cannot claim full-text synthesis")
    if record.get("why_read") is not None:
        _text(record["why_read"], "why_read")
    entries = record.get("analysis_evidence") or []
    if not isinstance(entries, list):
        raise ValueError("analysis_evidence must be a list")
    evidence = record.get("evidence") or []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("analysis_evidence entry must be an object")
        _text(entry.get("field"), "analysis field")
        _text(entry.get("statement"), "analysis statement")
        indices = entry.get("evidence_indexes")
        if (
            not isinstance(indices, list)
            or not indices
            or any(type(i) is not int or i < 0 or i >= len(evidence) for i in indices)
        ):
            raise ValueError("paper analysis evidence indexes must locate actual source evidence")


def validate_media(record: dict, public_hosts: list[str], media_hosts: list[str]) -> list[dict]:
    from .domain import safe_public_url

    media = record.get("media") or []
    if not isinstance(media, list) or len(media) > 8:
        raise ValueError("media must contain at most 8 verified content images")
    result = []
    seen = set()
    for entry in media:
        if not isinstance(entry, dict):
            raise ValueError("media entries must be objects")
        if entry.get("kind") not in {"figure", "chart", "article_photo", "illustration"}:
            raise ValueError("media must be substantive figures, not logos or default covers")
        url, source_url = entry.get("url"), entry.get("source_url")
        if not isinstance(url, str) or not safe_public_url(url, media_hosts):
            raise ValueError("media URL must use an approved publisher HTTPS host")
        if not isinstance(source_url, str) or not safe_public_url(source_url, public_hosts):
            raise ValueError("media source_url must identify an approved public source article")
        if url in seen:
            continue
        seen.add(url)
        item = {
            "url": url,
            "source_url": source_url,
            "kind": entry["kind"],
            "caption": _text(entry.get("caption"), "media caption"),
        }
        if entry.get("alt") is not None:
            item["alt"] = _text(entry["alt"], "media alt")
        result.append(item)
    return result
