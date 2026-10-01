"""Offline source normalization. Does not read configuration or connect to production."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path

SOURCE_IDS = {
    "社会": "society-journal",
    "社会建设": "social-construction",
    "社会学研究": "sociological-studies",
    "社会发展研究": "social-development",
    "青年研究": "youth-studies",
    "中国青年研究": "china-youth",
    "中国社会工作报": "social-work-news",
    "社会学视野": "sociology-perspective",
}
GENERATED_AT = "2026-10-01T20:00:00+00:00"


def canonical_json(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def rows(value):
    return value if isinstance(value, list) else value["records"]


def clean_author(value):
    return re.sub(
        r"\[[\d,，\s]+\]|[¹²³⁴⁵⁶⁷⁸⁹⁰]+", "", unicodedata.normalize("NFKC", value)
    ).strip()


def title_author(record):
    if not record.get("authors"):
        return None
    norm = lambda s: "".join(
        c for c in unicodedata.normalize("NFKC", s).casefold() if c.isalnum()
    )
    return (
        norm(record["title"]),
        tuple(sorted(norm(a) for a in record["authors"])),
        record.get("publication_year"),
        record.get("publication_issue"),
    )


def normalized_journal(original):
    r = deepcopy(original)
    name = r.get("source_name") or r["journal"]
    sid = SOURCE_IDS[name]
    abstract = r.get("abstract")
    excerpt = r.get("abstract_excerpt")
    evidence = deepcopy(
        r.get("evidence")
        or [
            {
                "url": v["url"],
                "locator": v.get("locator") or "public displayed metadata",
                "supports": v.get("fields", []),
            }
            for v in r.get("provenance", [])
            if v.get("url")
        ]
    )
    authors = [clean_author(a) for a in (r.get("authors") or [])]
    year = int(r["publication_year"])
    issue = int(r["publication_issue"])
    scope = (
        "public_abstract_excerpt"
        if excerpt
        else "public_complete_abstract"
        if abstract
        else "directory_metadata"
    )
    return {
        **r,
        "source_id": sid,
        "source_name": name,
        "source_publisher": name,
        "authors_raw": r.get("authors"),
        "authors": authors or None,
        "publication_year": year,
        "publication_issue": issue,
        "issue_id": f"{sid}:{year}:{issue}",
        "external_id": r.get("external_id") or r["id"],
        "published_at_precision": r.get("published_at_precision") or "issue",
        "published_at_display": r.get("published_at") or f"{year}年第{issue}期",
        "source_published_at": r.get("source_published_at"),
        "material_type": "research_abstract",
        "stream": "research",
        "summary": "",
        "summary_method": None,
        "findings": [],
        "research_question": None,
        "methods": None,
        "data": None,
        "topics": r.get("keywords") or [],
        "topics_source": "publisher_keywords",
        "verification_status": "lead_only",
        "verification_note": "公开来源的题名、作者、刊期与摘要状态已核；未读取或审读全文。",
        "editorial_caveat": "仅展示元数据和原始来源链接；摘要内容保留作内部分析，不是我们的研究总结。",
        "source_scope": scope,
        "analysis_scope": "metadata",
        "display_ready": True,
        "evidence": evidence,
        "full_text_verified": False,
        "human_full_text_reviewed": False,
        "readable_abstract": bool(abstract or excerpt),
        "internal_source_content": {
            "abstract": abstract,
            "abstract_excerpt": excerpt,
            "abstract_status": r.get("abstract_status") or scope,
            "permission_scope": "internal_analysis_only",
            "full_text": None,
        },
        "discovered_at": r.get("discovered_at") or GENERATED_AT,
        "origin_source_id": sid,
        "source_aliases": [r.get("source_id")] if r.get("source_id") != sid else [],
        "original_source_record": r,
    }


def normalized_news(original):
    r = deepcopy(original)
    url = r["url"]
    sid = "social-work-news"
    return {
        **r,
        "id": "news-metadata-" + sha(url.encode())[:24],
        "external_id": url,
        "source_id": sid,
        "source_name": "中国社会工作报",
        "source_publisher": "中国社会工作报",
        "material_type": "official_practice",
        "stream": "practice",
        "published_at_precision": r.get("date_precision") or "unknown",
        "published_at_display": r.get("published_at") or "出版日期待核",
        "publication_year": int(r["published_at"][:4])
        if r.get("published_at")
        else None,
        "publication_issue": None,
        "source_published_at": r.get("web_published_at"),
        "summary": "",
        "summary_method": None,
        "topics": [],
        "findings": [],
        "research_question": None,
        "methods": None,
        "data": None,
        "verification_status": "practice_signal",
        "verification_note": "已核官方文章元数据；新闻或实践线索，不是同行评审研究，也未审读全文。",
        "editorial_caveat": "仅事实元数据与来源链接，未授权转载正文。",
        "analysis_scope": "metadata",
        "source_scope": "newspaper_metadata_only",
        "display_ready": True,
        "evidence": [
            {
                "url": url,
                "locator": "official reader article title/byline/publication metadata",
                "snippet": None,
                "supports": ["metadata"],
            }
        ],
        "source_snapshot": {
            "response_sha256": r.get("reader_response_sha256"),
            "hash_scope": r.get("hash_scope"),
            "full_text": None,
        },
        "full_text_verified": False,
        "human_full_text_reviewed": False,
        "abstract": None,
        "full_text": None,
        "discovered_at": r.get("collection_completed_at") or GENERATED_AT,
        "origin_source_id": sid,
        "original_source_record": r,
    }


def write_shards(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    parts = path.with_suffix(".parts")
    parts.mkdir(exist_ok=True)
    manifest = []
    for i, start in enumerate(range(0, len(payload["records"]), 48), 1):
        part = parts / f"{i:03}.json"
        content = json.dumps(
            payload["records"][start : start + 48], ensure_ascii=False, indent=2
        ).encode()
        part.write_bytes(content)
        manifest.append(
            {
                "path": str(part.relative_to(path.parent)),
                "sha256": sha(content),
                "count": len(payload["records"][start : start + 48]),
            }
        )
    data = {
        "$format": "qunxue-json-shards-v1",
        "kind": "records",
        "count": len(payload["records"]),
        "canonical_sha256": sha(canonical_json(payload)),
        "parts": manifest,
        "metadata": {k: v for k, v in payload.items() if k != "records"},
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def generate(manifest_path, output):
    manifest = read(manifest_path)
    records = []
    excluded = []
    pending = []
    provenance = []
    indexed = []
    # Original frozen seed is loaded directly, never reconstructed from prior provisional title-only merges.
    original = Path(manifest["original_corpus"])
    header = read(original)
    old = [row for part in header["parts"] for row in read(original.parent / part["path"])]
    for original_record in old:
        r = deepcopy(original_record)
        r["source_id"] = SOURCE_IDS[r["source_name"]]
        r["origin_source_id"] = r["source_id"]
        r["source_aliases"] = (
            [original_record.get("source_id")]
            if original_record.get("source_id") != r["source_id"]
            else []
        )
        records.append(r)
    for entry in manifest["journal_inputs"]:
        path = Path(entry["records"])
        raw = rows(read(path))
        provenance.append(
            {
                "path": str(path),
                "sha256": sha(path.read_bytes()),
                "input_count": len(raw),
            }
        )
        groups = defaultdict(list)
        for r in raw:
            groups[(r.get("publication_year"), r.get("publication_issue"))].append(r)
            if (
                r.get("is_research_article") is False
                or "总目录" in r["title"]
                or r.get("record_type")
                in {"annual_contents", "english_toc_and_abstracts", "conference_report"}
            ):
                excluded.append(
                    {
                        "id": r["id"],
                        "source_id": r["source_id"],
                        "year": r.get("publication_year"),
                        "issue": r.get("publication_issue"),
                        "title": r["title"],
                        "reason": r.get("record_type") or "annual_contents",
                        "original_source_record": r,
                    }
                )
                continue
            records.append(normalized_journal(r))
        if entry["source_id"] == "mixed":
            for sid in sorted({r["source_id"] for r in raw}):
                subgroups = {
                    key: [r for r in group if r["source_id"] == sid]
                    for key, group in groups.items()
                }
                indexed.append(
                    (
                        {**entry, "source_id": sid},
                        {k: v for k, v in subgroups.items() if v},
                    )
                )
        else:
            indexed.append((entry, groups))
    applied_notes = []
    if manifest.get("reviewed_notes"):
        byid = {r["id"]: r for r in records}
        for note in read(manifest["reviewed_notes"])["notes"]:
            record = byid[note["record_id"]]
            abstract = record.get("internal_source_content", {}).get("abstract")
            if (
                not abstract
                or sha(abstract.encode()) != note["basis_sha256"]
                or record["url"] != note["source_url"]
            ):
                raise ValueError(
                    "Reviewed note source/hash mismatch: " + note["record_id"]
                )
            if (
                note.get("full_text_reviewed") is not False
                or note.get("academic_quality_score") is not None
            ):
                raise ValueError(
                    "Abstract notes cannot become full-text quality scores"
                )
            for field in (
                "summary",
                "research_question",
                "methods",
                "findings",
                "why_read",
            ):
                record[field] = deepcopy(note[field])
            record.update(
                summary_method="assistant_evidence_synthesis",
                extraction_method="assistant_evidence_synthesis",
                analysis_scope="abstract",
                reading_note_basis_sha256=note["basis_sha256"],
                reading_note_review_type=note["review_type"],
            )
            index = next(
                (
                    i
                    for i, e in enumerate(record["evidence"])
                    if "abstract" in e.get("supports", [])
                ),
                0,
            )
            record["analysis_evidence"] = [
                {"field": field, "statement": value, "evidence_indexes": [index]}
                for field in (
                    "summary",
                    "research_question",
                    "methods",
                    "findings",
                    "why_read",
                )
                for value in (
                    record[field]
                    if isinstance(record[field], list)
                    else [record[field]]
                )
            ]
            applied_notes.append(
                {
                    "record_id": record["id"],
                    "basis_sha256": note["basis_sha256"],
                    "scope": "assistant_abstract_reading",
                }
            )
    # Canonical identities preserve original IDs. Publication issue participates in the fallback key.
    identities = {}
    aliases = []
    for r in records:
        doi = (r.get("doi") or "").strip().lower()
        keys = []
        if doi:
            keys.append(("doi", doi))
        if title_author(r):
            keys.append(("title_author", title_author(r)))
        keys.append(("source_url", r["source_id"], r["url"]))
        matched = next((k for k in keys if k in identities), None)
        canonical = (
            identities[matched] if matched else r.get("canonical_study_id") or r["id"]
        )
        for key in keys:
            identities.setdefault(key, canonical)
        r["canonical_study_id"] = canonical
        if canonical != r["id"]:
            aliases.append(
                {
                    "record_id": r["id"],
                    "canonical_study_id": canonical,
                    "basis": matched[0],
                }
            )
    # Separate news denominator: only parsed official article URLs are browse eligible.
    urls = set()
    for entry in manifest["news_inputs"]:
        path = Path(entry)
        raw = rows(read(path))
        provenance.append(
            {
                "path": str(path),
                "sha256": sha(path.read_bytes()),
                "input_count": len(raw),
            }
        )
        for r in raw:
            if r["url"] in urls:
                continue
            urls.add(r["url"])
            if r.get("parsed") is not True:
                pending.append(
                    {
                        "reason": "article_metadata_unparsed",
                        "source_id": "social-work-news",
                        "verification_status": "review_queue",
                        "eligibility": {"browse": False, "rag": False},
                        "original_source_record": r,
                    }
                )
                continue
            n = normalized_news(r)
            n["canonical_study_id"] = n["id"]
            records.append(n)
    for entry in manifest.get("pending_inputs", []):
        for r in rows(read(entry)):
            pending.append(
                {
                    "reason": "abstract_unavailable",
                    "source_id": r.get("source_id", "china-youth"),
                    "verification_status": "review_queue",
                    "eligibility": {"browse": False, "rag": False},
                    "original_source_record": r,
                }
            )
    ledgers = []
    # Evidence-based closed index directory samples, not journal-wide completeness.
    for entry, groups in indexed:
        sid = entry["source_id"]
        byyear = defaultdict(list)
        for (year, issue), raw in groups.items():
            if year and issue:
                byyear[int(year)].append((int(issue), raw))
        for year, issues in sorted(byyear.items()):
            issue_numbers = sorted(i for i, _ in issues)
            issue_ids = [f"{sid}:{year}:{i}" for i in issue_numbers]
            members = [
                r
                for r in records
                if r["source_id"] == sid
                and r.get("issue_id") in issue_ids
                and r["material_type"] != "official_practice"
            ]
            unique = {r["canonical_study_id"] for r in members}
            removed = [
                r
                for r in excluded
                if r["source_id"] == sid
                and r["year"] == year
                and r["issue"] in issue_numbers
            ]
            observed = sum(len(raw) for _, raw in issues)
            included = len(unique)
            # This must account for every observed directory row; never force counts to match.
            reconciled = observed - len(removed) == included
            evidence = [
                f"sha256:{sha(Path(entry['records']).read_bytes())}:records:{year}:issues:{','.join(map(str, issue_numbers))}",
                f"manifest:exclusions:{sid}:{year}",
            ]
            issue_url = next(
                (
                    e["url"]
                    for r in members
                    for e in r["evidence"]
                    if "journal/details" in e["url"] or "/Magazine/" in e["url"]
                ),
                members[0]["url"] if members else "",
            )
            ledgers.append(
                {
                    "issue_id": f"fixed:{sid}:{year}:{','.join(map(str, issue_numbers))}",
                    "source_id": sid,
                    "publication_year": year,
                    "period": str(year),
                    "period_precision": "year",
                    "publication_month": None,
                    "coverage_scope": "fixed_issue_sample",
                    "issue_ids": issue_ids,
                    "comparison_issue_keys": list(map(str, issue_numbers)),
                    "coverage_complete": reconciled,
                    "candidate_count": observed,
                    "readable_count": observed,
                    "included_count": included,
                    "analyzed_count": included,
                    "excluded_nonresearch_count": len(removed),
                    "missing_abstract_count": sum(
                        not r.get("readable_abstract") for r in members
                    ),
                    "historical_complete": False,
                    "evidence_refs": evidence,
                    "issue_url": issue_url,
                    "research_record_ids": sorted(r["id"] for r in members),
                    "excluded_record_ids": sorted(r["id"] for r in removed),
                    "scope_note": "All observed rows of the explicitly listed index issue directories only; full journal/global completeness remains unknown.",
                }
            )
    payload = {
        "generated_at": GENERATED_AT,
        "sampling_strategy": "explicit_offline_indexed_issue_and_newspaper_metadata_import",
        "records": records,
        "issue_coverage": ledgers,
    }
    output = Path(output)
    write_shards(output / "frontier-closeout.json", payload)
    research = [r for r in records if r["material_type"] != "official_practice"]
    canonical = {r["canonical_study_id"]: r for r in research}
    practice = [r for r in records if r["material_type"] == "official_practice"]
    audit = {
        "research_record_variants": len(research),
        "research_unique": len(canonical),
        "research_by_year": dict(
            sorted(
                Counter(r.get("publication_year") for r in canonical.values()).items()
            )
        ),
        "practice_count": len(practice),
        "news_parsed_urls": len(urls)
        - sum(p["reason"] == "article_metadata_unparsed" for p in pending),
        "news_observed_urls": len(urls),
        "pending_count": len(pending),
        "source_zero_status": {
            "sociology-perspective": {
                "included_count": 0,
                "status": "not_configured",
                "reason": "No verified collected entries; absence is not complete publication coverage.",
            }
        },
        "aliases": aliases,
        "excluded": excluded,
        "pending": pending,
        "source_inputs": provenance,
        "reviewed_reading_notes": applied_notes,
        "coverage": ledgers,
        "canonical_sha256": sha(canonical_json(payload)),
    }
    (output / "frontier-closeout-audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        {
            k: v
            for k, v in audit.items()
            if k
            in [
                "research_record_variants",
                "research_unique",
                "research_by_year",
                "practice_count",
                "news_parsed_urls",
                "news_observed_urls",
                "pending_count",
                "canonical_sha256",
            ]
        }
    )
    return payload, audit


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("output")
    a = parser.parse_args()
    generate(a.manifest, a.output)
