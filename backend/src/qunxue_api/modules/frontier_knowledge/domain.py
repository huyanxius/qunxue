"""Independent frontier identities, provenance and conservative publication gates."""

import json
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from urllib.parse import urlsplit

SCHEMA_VERSION = "frontier-v1"
RULE_VERSION = "frontier-gates-v1"


class VerificationStatus(StrEnum):
    LEAD_ONLY = "lead_only"
    PRACTICE_SIGNAL = "practice_signal"
    VERIFIED_FRONTIER = "verified_frontier"
    REVIEW_QUEUE = "review_queue"


class JobStage(StrEnum):
    DISCOVER = "DISCOVER"
    FETCH = "FETCH"
    PARSE = "PARSE"
    EXTRACT = "EXTRACT"
    VERIFY = "VERIFY"
    INDEX = "INDEX"
    TREND = "TREND"


@dataclass(frozen=True)
class Candidate:
    source_id: str
    external_id: str
    title: str
    url: str
    authors: tuple[str, ...] = ()
    doi: str | None = None
    published_at: str | None = None
    content_hash: str | None = None


@dataclass(frozen=True)
class SourceBlock:
    block_id: str
    text: str
    locator: str


@dataclass(frozen=True)
class SourceSnapshot:
    snapshot_id: str
    source_id: str
    content_hash: str
    scope: str
    blocks: tuple[SourceBlock, ...]
    metadata: dict | None = None


@dataclass(frozen=True)
class FrontierRecord:
    record_id: str
    snapshot_id: str
    canonical_study_id: str
    verification_status: VerificationStatus
    version: int
    structured: dict


@dataclass(frozen=True)
class FrontierJob:
    job_id: str
    stage: str
    object_id: str
    payload: dict
    attempt: int
    lease_token: str


def content_hash(value: object) -> str:
    return sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def normalize_title_author(title: str, authors: list[str] | tuple[str, ...] | None) -> str:
    # Missing authors are not a safe cross-source identity.
    if not authors:
        return ""

    def normalized(value: str) -> str:
        value = unicodedata.normalize("NFKC", value).casefold()
        return "".join(ch for ch in value if ch.isalnum())

    return content_hash([normalized(title), sorted(normalized(a) for a in authors)])


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(
        r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value.strip(), flags=re.IGNORECASE
    ).lower()
    return cleaned or None


def safe_public_url(url: str, allowed_hosts: list[str]) -> bool:
    parsed = urlsplit(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname in allowed_hosts
        and not parsed.username
        and not parsed.password
        and parsed.port in (None, 443)
    )


def eligibility(status: str) -> dict[str, bool]:
    return {
        "browse": status != "review_queue",
        "rag": status in {"verified_frontier", "practice_signal"},
        "training_candidate": False,
        "match": False,
    }


def validate_import(record: dict, allowed_hosts: list[str]) -> None:
    """Manual seed inputs cannot claim automated verification or missing full text."""
    if not record.get("id") or not record.get("title") or not record.get("url"):
        raise ValueError("record identity, title and URL are required")
    if not safe_public_url(record["url"], allowed_hosts):
        raise ValueError("source URL is outside the approved public-source host list")
    status = record.get("verification_status")
    if status not in {"lead_only", "practice_signal"}:
        raise ValueError("manual metadata/excerpt imports cannot publish verified research")
    if status == "lead_only" and record.get("material_type") != "research_abstract":
        raise ValueError("seed research must retain abstract material type")
    if status == "practice_signal" and record.get("material_type") != "official_practice":
        raise ValueError("practice signal must be an official practice article")
    if not record.get("evidence") or not record.get("verification_note"):
        raise ValueError("manual import must retain evidence and verification provenance")
    for evidence in record["evidence"]:
        if not evidence.get("locator") or not safe_public_url(evidence["url"], allowed_hosts):
            raise ValueError("evidence must have a locator and approved source URL")


def qualify_record(
    snapshot: dict,
    findings: list[dict],
    verdicts: list[dict],
    *,
    source_verified: bool,
    material_type: str,
) -> str:
    """Fail closed: metadata/abstracts never become full-text verified frontier."""
    from decimal import Decimal, DecimalException

    if not source_verified:
        return "review_queue"
    if snapshot.get("scope") != "full_text":
        return "lead_only" if material_type == "research_abstract" else "review_queue"
    source_blocks = snapshot.get("blocks", [])
    if not isinstance(source_blocks, (list, tuple)) or not source_blocks:
        return "review_queue"
    blocks = {}
    for block in source_blocks:
        if not isinstance(block, dict) or any(
            not isinstance(block.get(key), str) or not block[key].strip()
            for key in ("block_id", "text")
        ):
            return "review_queue"
        if block["block_id"] in blocks:
            return "review_queue"
        blocks[block["block_id"]] = block["text"]
    body = unicodedata.normalize("NFKC", "\n".join(blocks.values())).casefold()
    # A long login/paywall/challenge response is not usable full text. This is
    # intentionally conservative: ambiguous pages belong in the review queue.
    access_barriers = (
        r"captcha|recaptcha|hcaptcha|cf-chl",
        r"(?:verify|confirm|prove)\s+(?:that\s+)?you\s+are\s+(?:a\s+)?human",
        r"(?:checking|verify)\s+(?:your\s+)?browser",
        r"(?:enable|allow)\s+javascript\s+and\s+cookies",
        r"access denied|authentication required|login required",
        r"(?:sign\s+in|log\s*in|subscribe)\s+to\s+(?:continue|read|access)",
        r"please\s+(?:sign\s+in|log\s*in)",
        r"(?:purchase|buy)\s+(?:this\s+article|access|full\s+text)",
        r"access\s+through\s+your\s+institution",
        r"验证码|人机验证|请先登录|登录后(?:阅读|查看|继续)|付费阅读|购买全文|订阅后阅读",
        r"<input\b[^>]*\btype\s*=\s*[\"']?password\b",
    )
    if len(body.strip()) < 200 or any(re.search(pattern, body) for pattern in access_barriers):
        return "review_queue"
    if not findings or len(findings) != len(verdicts):
        return "review_queue"

    number_pattern = re.compile(
        r"(?P<prefix>百分之)?(?<![\d.])"
        r"(?P<number>[+-]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)"
        r"(?:[eE][+-]?\d+)?)"
        r"\s*(?P<scale>thousand\b|million\b|billion\b|万|亿)?"
        r"\s*(?P<unit>percentage\s+points?\b|percent(?:age)?\b|per\s+cent\b|个百分点|%)?",
        re.IGNORECASE,
    )

    def quantities(text: str) -> set[tuple[Decimal, str]]:
        result = set()
        normalized = unicodedata.normalize("NFKC", text).replace("−", "-")
        for match in number_pattern.finditer(normalized):
            unit = (match["unit"] or "").lower()
            if unit == "个百分点" or "point" in unit:
                unit = "percentage_points"
            elif unit or match["prefix"]:
                unit = "percent"
            quantity = Decimal(match["number"].replace(",", ""))
            scale = (match["scale"] or "").lower()
            if scale:
                parts = quantity.as_tuple()
                exponent = {"thousand": 3, "million": 6, "billion": 9, "万": 4, "亿": 8}[scale]
                quantity = Decimal((parts.sign, parts.digits, parts.exponent + exponent))
            result.add((quantity, unit))
        return result

    for finding, verdict in zip(findings, verdicts, strict=True):
        if not isinstance(finding, dict) or not isinstance(verdict, dict):
            return "review_queue"
        claim = finding.get("claim_text")
        ids = finding.get("evidence_block_ids", [])
        if not isinstance(claim, str) or not claim.strip() or not isinstance(ids, list):
            return "review_queue"
        if not ids or any(not isinstance(i, str) or i not in blocks for i in ids):
            return "review_queue"
        if len(set(ids)) != len(ids):
            return "review_queue"
        evidence = " ".join(blocks[i] for i in ids)
        try:
            if not quantities(claim).issubset(quantities(evidence)):
                return "review_queue"
        except (DecimalException, ValueError, OverflowError):
            return "review_queue"
        if verdict.get("status") != "supported":
            return "review_queue"
    return "practice_signal" if material_type == "official_practice" else "verified_frontier"


def frontier_today():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Asia/Shanghai")).date()
