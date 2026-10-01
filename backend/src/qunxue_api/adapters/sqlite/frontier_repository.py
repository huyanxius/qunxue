"""Transactional frontier storage; networking is never done inside a transaction."""

import re
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.dialects.sqlite import insert

from qunxue_api.adapters.frontier_sources import SOURCE_DEFINITIONS
from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.adapters.sqlite.frontier_models import (
    FrontierClaimRow,
    FrontierEditorialBriefRow,
    FrontierIndexRow,
    FrontierItemRow,
    FrontierJobRow,
    FrontierRecordRow,
    FrontierReviewRow,
    FrontierSnapshotRow,
    FrontierSourceRow,
    FrontierTopicRunRow,
)
from qunxue_api.modules.frontier_knowledge import (
    RULE_VERSION,
    SCHEMA_VERSION,
    SYNTHESIS_METHODS,
    FrontierJob,
    aggregate_topics,
    content_hash,
    eligibility,
    frontier_today,
    normalize_doi,
    normalize_title_author,
    safe_public_url,
    validate_corpus_overview,
    validate_import,
    validate_media,
    validate_paper_analysis,
    validate_research_brief,
    visible_corpus_records,
)


class SqliteFrontierStore:
    def __init__(self, database: Database):
        self.database = database

    def configure_sources(self) -> None:
        with self.database.session() as session:
            for source_id, name, adapter, base_url, hours, hosts, reason in SOURCE_DEFINITIONS:
                session.execute(
                    insert(FrontierSourceRow)
                    .values(
                        source_id=source_id,
                        name=name,
                        adapter_type=adapter,
                        base_url=base_url,
                        schedule_hours=hours,
                        enabled=False,
                        status="not_configured",
                        cursor=None,
                        last_success_at=None,
                        last_error=None,
                        config={
                            "approved_public_hosts": hosts,
                            "reason": reason,
                            "automatic_collection": False,
                            "coverage_start": None,
                            "coverage_complete": False,
                            "sampling_strategy": "manual_curated_seed",
                        },
                    )
                    .on_conflict_do_nothing(index_elements=["source_id"])
                )

    def import_seed(
        self, payload: dict, *, job: FrontierJob | None = None, now: float | None = None
    ) -> dict:
        self.configure_sources()
        result = {"created": 0, "unchanged": 0, "versions": 0, "duplicates": 0}
        # One writer transaction protects identity resolution and prevents duplicate versions.
        with self.database.session() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            if job is not None and not self._lease_owned(session, job, now):
                raise ValueError("stale_worker_lease")
            sources = {s.name: s for s in session.scalars(select(FrontierSourceRow))}
            for original in payload["records"]:
                record = deepcopy(original)
                source = sources.get(record["source_name"])
                if source is None:
                    raise ValueError("unregistered frontier source")
                validate_import(record, source.config["approved_public_hosts"])
                validate_paper_analysis(record)
                record["media"] = validate_media(
                    record,
                    source.config["approved_public_hosts"],
                    source.config["approved_public_hosts"]
                    + source.config.get("approved_media_hosts", []),
                )
                record["analysis_evidence"] = record.get("analysis_evidence") or []
                if (
                    not record.get("issue_id")
                    and record.get("publication_year")
                    and record.get("publication_issue")
                ):
                    record["issue_id"] = (
                        f"{source.source_id}:{record['publication_year']}:"
                        f"{record['publication_issue']}"
                    )
                sampling = payload.get("sampling_strategy", "manual_curated_seed")
                if isinstance(sampling, dict):
                    sampling_key = {
                        "society-journal": "society",
                        "social-construction": "social_construction",
                        "social-work-news": "practice",
                    }.get(source.source_id, "manual_seed")
                    sampling = sampling.get(sampling_key, "unknown_non_exhaustive_sample")
                source.config = {
                    **source.config,
                    "sampling_strategy": sampling,
                    "coverage_complete": False,
                    "coverage_start": None,
                }
                record["sampling_strategy"] = sampling
                record["coverage_complete"] = False
                semantic_content = deepcopy(record)
                for volatile in ("discovered_at", "verified_at", "fetched_at", "source_file"):
                    semantic_content.pop(volatile, None)
                snapshot_meta = semantic_content.get("source_snapshot")
                if isinstance(snapshot_meta, dict):
                    for volatile in ("captured_at", "fetched_at", "local_audit_reference"):
                        snapshot_meta.pop(volatile, None)
                digest = content_hash(semantic_content)
                external_id = record.get("external_id") or record["id"]
                item = session.scalar(
                    select(FrontierItemRow).where(
                        FrontierItemRow.source_id == source.source_id,
                        FrontierItemRow.external_id == external_id,
                    )
                )
                doi = normalize_doi(record.get("doi"))
                title_key = normalize_title_author(record["title"], record.get("authors"))
                # This batch stores excerpts, so it MUST NOT masquerade as a full-body hash.
                full_text = (record.get("source_snapshot") or {}).get("full_text")
                body_hash = content_hash(" ".join(full_text.split())) if full_text else None
                reported_body_hash = record.get("body_sha256")
                if (
                    body_hash is None
                    and isinstance(reported_body_hash, str)
                    and re.fullmatch(r"[a-f0-9]{64}", reported_body_hash)
                ):
                    # Trusted local crawler reports the parsed body hash. This does not
                    # imply the product retains or model-verifies the original body.
                    body_hash = reported_body_hash
                if item is None:
                    duplicate = None
                    level = "new"
                    for field, value, candidate_level in (
                        (FrontierItemRow.doi, doi, "doi"),
                        (FrontierItemRow.title_author_key, title_key, "title_author"),
                        (FrontierItemRow.body_hash, body_hash, "body_hash"),
                    ):
                        if value:
                            duplicate = session.scalar(
                                select(FrontierItemRow)
                                .where(field == value)
                                .order_by(FrontierItemRow.item_id)
                            )
                            if duplicate:
                                level = candidate_level
                                break
                    item_id = record["id"]
                    if session.get(FrontierItemRow, item_id):
                        item_id = f"{item_id}-{content_hash([source.source_id, external_id])[:10]}"
                    item = FrontierItemRow(
                        item_id=item_id,
                        source_id=source.source_id,
                        external_id=external_id,
                        title=record["title"],
                        doi=doi,
                        title_author_key=title_key,
                        body_hash=body_hash,
                        canonical_study_id=(duplicate.canonical_study_id if duplicate else item_id),
                        dedupe_level=level,
                        original_item_id=duplicate.item_id if duplicate else None,
                    )
                    session.add(item)
                    session.flush()
                    if duplicate:
                        result["duplicates"] += 1
                existing = session.scalar(
                    select(FrontierSnapshotRow).where(
                        FrontierSnapshotRow.item_id == item.item_id,
                        FrontierSnapshotRow.content_hash == digest,
                    )
                )
                current = session.scalar(
                    select(FrontierRecordRow).where(
                        FrontierRecordRow.item_id == item.item_id,
                        FrontierRecordRow.is_current.is_(True),
                    )
                )
                if existing and current and current.snapshot_id == existing.snapshot_id:
                    result["unchanged"] += 1
                    continue
                # Withdrawn items stay withdrawn across new content and historical restores.
                withdrawn = (
                    current is not None and not current.structured_json["eligibility"]["browse"]
                )
                item.title, item.doi, item.title_author_key, item.body_hash = (
                    record["title"],
                    doi,
                    title_key,
                    body_hash,
                )
                version = current.version + 1 if current else 1
                if current:
                    current.is_current = False
                    result["versions"] += 1
                snapshot_id = f"snapshot-{content_hash([item.item_id, digest])[:32]}"
                blocks = [
                    {
                        "block_id": f"{snapshot_id}:block:{i}",
                        "text": e.get("snippet") or "",
                        "locator": e["locator"],
                        "url": e["url"],
                        "supports": e.get("supports", []),
                    }
                    for i, e in enumerate(record["evidence"])
                ]
                if full_text:
                    blocks.extend(
                        {
                            "block_id": f"{snapshot_id}:body:{i}",
                            "text": paragraph,
                            "locator": f"source body paragraph {i + 1}",
                            "url": record["url"],
                            "supports": [],
                        }
                        for i, paragraph in enumerate(full_text.split("\n\n"))
                        if paragraph.strip()
                    )
                snapshot = {
                    "snapshot_id": snapshot_id,
                    "source_id": source.source_id,
                    "content_hash": digest,
                    "scope": "full_text" if full_text else "metadata_and_short_excerpt",
                    "blocks": blocks,
                    "original_input": deepcopy(record),
                    "source_verified": True,
                    "material_type": record["material_type"],
                    "full_text_retained": bool(full_text),
                }
                if existing is None:
                    session.add(
                        FrontierSnapshotRow(
                            snapshot_id=snapshot_id,
                            item_id=item.item_id,
                            source_id=source.source_id,
                            content_hash=digest,
                            scope=snapshot["scope"],
                            payload=snapshot,
                            fetched_at=record.get("discovered_at", payload["generated_at"]),
                        )
                    )
                session.flush()
                record_id = item.item_id if version == 1 else f"{item.item_id}@v{version}"
                if withdrawn:
                    record["verification_status"] = "review_queue"
                record.update(
                    {
                        "id": record_id,
                        "source_id": source.source_id,
                        "item_id": item.item_id,
                        "snapshot_id": snapshot_id,
                        "canonical_study_id": item.canonical_study_id,
                        "content_hash": digest,
                        "version": version,
                        "schema_version": SCHEMA_VERSION,
                        "rule_version": RULE_VERSION,
                        "extraction_method": (
                            record["extraction_method"]
                            if record.get("extraction_method") in SYNTHESIS_METHODS
                            else (
                                "assistant_evidence_synthesis"
                                if record.get("summary_method") == "assistant_evidence_synthesis"
                                else "deterministic_source_import"
                                if record.get("algorithm_harvested") or record.get("summary_method")
                                else "manual_structured_seed"
                            )
                        ),
                        "eligibility": eligibility(record["verification_status"]),
                        "dedupe_level": item.dedupe_level,
                        "reprint_of": item.original_item_id,
                        "snapshot_scope": snapshot["scope"],
                        "full_text_retained": bool(full_text),
                        "evidence": [
                            {**e, "block_id": blocks[i]["block_id"]}
                            for i, e in enumerate(record["evidence"])
                        ],
                    }
                )
                session.add(
                    FrontierRecordRow(
                        record_id=record_id,
                        item_id=item.item_id,
                        snapshot_id=snapshot_id,
                        source_id=source.source_id,
                        canonical_study_id=item.canonical_study_id,
                        version=version,
                        verification_status=record["verification_status"],
                        rag_eligible=record["eligibility"]["rag"],
                        is_current=True,
                        structured_json=record,
                    )
                )
                session.flush()
                for index, claim in enumerate(record.get("findings") or []):
                    supporting = [
                        b["block_id"] for b in blocks if b["text"] and "findings" in b["supports"]
                    ]
                    session.add(
                        FrontierClaimRow(
                            claim_id=f"claim-{content_hash([record_id, index])[:32]}",
                            record_id=record_id,
                            claim_text=claim,
                            evidence_block_ids=supporting,
                            verifier_status="not_run_manual_seed",
                            reason="人工结构化线索；独立模型未运行，不是全文核验结果",
                        )
                    )
                session.add(
                    FrontierIndexRow(
                        record_id=record_id,
                        content_hash=digest,
                        schema_version=SCHEMA_VERSION,
                        lexical_text=self.lexical_text(record),
                        embedding_status="not_configured",
                    )
                )
                result["created"] += 1
            self._import_issue_coverage(session, payload.get("issue_coverage", []), sources)
        return result

    @staticmethod
    def lexical_text(record: dict) -> str:
        return " ".join(
            [
                record["title"],
                record.get("summary") or "",
                record.get("research_question") or "",
                record["source_name"],
                *(record.get("authors") or []),
                *record.get("topics", []),
            ]
        ).casefold()

    def list_records(self) -> list[dict]:
        with self.database.session() as session:
            return [
                deepcopy(row.structured_json)
                for row in session.scalars(
                    select(FrontierRecordRow).where(FrontierRecordRow.is_current.is_(True))
                )
            ]

    def get_record(self, record_id: str) -> dict | None:
        with self.database.session() as session:
            row = session.get(FrontierRecordRow, record_id)
            if row is None:
                return None
            result = deepcopy(row.structured_json)
            result["is_current"] = row.is_current
            result["claims"] = [
                {
                    "claim_id": c.claim_id,
                    "claim_text": c.claim_text,
                    "evidence_block_ids": c.evidence_block_ids,
                    "verifier_status": c.verifier_status,
                    "reason": c.reason,
                }
                for c in session.scalars(
                    select(FrontierClaimRow).where(FrontierClaimRow.record_id == record_id)
                )
            ]
            return result

    def get_snapshot(self, snapshot_id: str) -> dict | None:
        with self.database.session() as session:
            row = session.get(FrontierSnapshotRow, snapshot_id)
            return deepcopy(row.payload) if row else None

    def list_sources(self) -> list[dict]:
        with self.database.session() as session:
            counts = dict(
                session.execute(
                    select(FrontierRecordRow.source_id, func.count())
                    .where(FrontierRecordRow.is_current.is_(True))
                    .group_by(FrontierRecordRow.source_id)
                ).all()
            )
            return [
                {
                    "source_id": row.source_id,
                    "name": row.name,
                    "adapter_type": row.adapter_type,
                    "base_url": row.base_url,
                    "schedule_hours": row.schedule_hours,
                    "enabled": row.enabled,
                    "status": row.status,
                    "cursor": row.cursor,
                    "last_success_at": row.last_success_at,
                    "last_error": row.last_error,
                    "record_count": counts.get(row.source_id, 0),
                    "reason": row.config["reason"],
                    "coverage_start": row.config.get("coverage_start"),
                    "coverage_end": row.config.get("coverage_end"),
                    "automatic_collection": False,
                    "coverage_complete": row.config.get("coverage_complete", False),
                    "sampling_strategy": row.config.get("sampling_strategy", "unknown"),
                }
                for row in session.scalars(
                    select(FrontierSourceRow).order_by(FrontierSourceRow.source_id)
                )
            ]

    def enqueue(
        self,
        stage: str,
        object_id: str,
        idempotency_key: str,
        payload: dict | None = None,
        *,
        job: FrontierJob | None = None,
        now: float | None = None,
    ) -> str:
        from qunxue_api.modules.frontier_knowledge import JobStage

        JobStage(stage)
        with self.database.session() as session:
            self._fence(session, job, now)
            job_id = f"job-{uuid4().hex}"
            session.execute(
                insert(FrontierJobRow)
                .values(
                    job_id=job_id,
                    stage=stage,
                    object_id=object_id,
                    payload=payload or {},
                    idempotency_key=idempotency_key,
                    status="pending",
                    attempt=0,
                    next_run_at=0,
                    lease_until=None,
                    lease_token=None,
                    error=None,
                )
                .on_conflict_do_nothing(index_elements=["idempotency_key"])
            )
            return session.scalar(
                select(FrontierJobRow.job_id).where(
                    FrontierJobRow.idempotency_key == idempotency_key
                )
            )

    def claim_job(self, *, now: float, lease_seconds: int = 120) -> FrontierJob | None:
        with self.database.session() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            row = session.scalar(
                select(FrontierJobRow)
                .where(
                    FrontierJobRow.attempt < 4,
                    or_(
                        (FrontierJobRow.status.in_(["pending", "retry"]))
                        & (FrontierJobRow.next_run_at <= now),
                        (FrontierJobRow.status == "running") & (FrontierJobRow.lease_until <= now),
                    ),
                )
                .order_by(FrontierJobRow.next_run_at, FrontierJobRow.job_id)
                .limit(1)
            )
            if row is None:
                # Crashed final attempts must become terminal instead of remaining running forever.
                session.execute(
                    update(FrontierJobRow)
                    .where(
                        FrontierJobRow.status == "running",
                        FrontierJobRow.lease_until <= now,
                        FrontierJobRow.attempt >= 4,
                    )
                    .values(
                        status="failed",
                        lease_token=None,
                        lease_until=None,
                        error="lease_expired_after_final_attempt",
                    )
                )
                return None
            row.status = "running"
            row.attempt += 1
            row.lease_token = uuid4().hex
            row.lease_until = now + lease_seconds
            return FrontierJob(
                row.job_id,
                row.stage,
                row.object_id,
                deepcopy(row.payload),
                row.attempt,
                row.lease_token,
            )

    def finish_job(
        self, job: FrontierJob, *, now: float, status: str = "completed", reason: str | None = None
    ) -> bool:
        if status not in {"completed", "blocked", "retry", "failed"}:
            raise ValueError("invalid job result")
        if status == "retry" and job.attempt >= 4:
            status = "failed"
        with self.database.session() as session:
            result = session.execute(
                update(FrontierJobRow)
                .where(
                    FrontierJobRow.job_id == job.job_id,
                    FrontierJobRow.status == "running",
                    FrontierJobRow.lease_token == job.lease_token,
                    FrontierJobRow.lease_until > now,
                )
                .values(
                    status=status,
                    error=reason,
                    lease_until=None,
                    lease_token=None,
                    next_run_at=now + (30, 120, 600, 600)[min(job.attempt - 1, 3)],
                )
            )
            return result.rowcount == 1

    def resume_blocked(self) -> int:
        with self.database.session() as session:
            result = session.execute(
                update(FrontierJobRow)
                .where(FrontierJobRow.status == "blocked")
                .values(status="pending", attempt=0, next_run_at=0, error=None)
            )
            return result.rowcount

    def list_jobs(self) -> list[dict]:
        with self.database.session() as session:
            return [
                {
                    "job_id": j.job_id,
                    "stage": j.stage,
                    "object_id": j.object_id,
                    "status": j.status,
                    "attempt": j.attempt,
                    "next_run_at": j.next_run_at,
                    "lease_until": j.lease_until,
                    "error": j.error,
                }
                for j in session.scalars(select(FrontierJobRow))
            ]

    def reindex(
        self, record_id: str, *, job: FrontierJob | None = None, now: float | None = None
    ) -> None:
        record = self.get_record(record_id)
        if not record:
            raise LookupError("record not found")
        with self.database.session() as session:
            self._fence(session, job, now)
            values = {
                "record_id": record_id,
                "content_hash": record["content_hash"],
                "schema_version": SCHEMA_VERSION,
                "lexical_text": self.lexical_text(record),
                "embedding_status": "not_configured",
            }
            session.execute(
                insert(FrontierIndexRow)
                .values(**values)
                .on_conflict_do_update(index_elements=["record_id"], set_=values)
            )

    def save_topics(
        self,
        as_of: str,
        topics: list[dict],
        *,
        job: FrontierJob | None = None,
        now: float | None = None,
    ) -> None:
        digest = content_hash(topics)
        with self.database.session() as session:
            self._fence(session, job, now)
            session.execute(
                insert(FrontierTopicRunRow)
                .values(
                    run_id=f"topics-{content_hash([as_of, digest])[:32]}",
                    as_of=as_of,
                    input_hash=digest,
                    method="curated_topic_dictionary_v1",
                    payload=topics,
                )
                .on_conflict_do_nothing(index_elements=["run_id"])
            )

    def owns_lease(self, job: FrontierJob, now: float) -> bool:
        with self.database.session() as session:
            return (
                session.scalar(
                    select(FrontierJobRow.job_id).where(
                        FrontierJobRow.job_id == job.job_id,
                        FrontierJobRow.status == "running",
                        FrontierJobRow.lease_token == job.lease_token,
                        FrontierJobRow.lease_until > now,
                    )
                )
                is not None
            )

    def save_review_result(
        self,
        snapshot_id: str,
        extracted: dict,
        verdicts: list[dict],
        verification_status: str,
        *,
        job: FrontierJob,
        now: float,
        error: str | None = None,
    ) -> bool:
        # Publication is deliberately a separate explicit operation: an unreviewed model
        # result cannot replace the manual provenance or mutate the current browse record.
        with self.database.session() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            owned = session.scalar(
                select(FrontierJobRow.job_id).where(
                    FrontierJobRow.job_id == job.job_id,
                    FrontierJobRow.status == "running",
                    FrontierJobRow.lease_token == job.lease_token,
                    FrontierJobRow.lease_until > now,
                )
            )
            if not owned:
                return False
            session.execute(
                insert(FrontierReviewRow)
                .values(
                    review_id=f"review-{content_hash(job.job_id)[:32]}",
                    snapshot_id=snapshot_id,
                    job_id=job.job_id,
                    status=verification_status,
                    extracted=extracted,
                    verdicts=verdicts,
                    error=error,
                )
                .on_conflict_do_nothing(index_elements=["job_id"])
            )
            return True

    def list_reviews(self) -> list[dict]:
        with self.database.session() as session:
            return [
                {
                    "review_id": row.review_id,
                    "snapshot_id": row.snapshot_id,
                    "job_id": row.job_id,
                    "verification_status": row.status,
                    "extracted": row.extracted,
                    "verdicts": row.verdicts,
                    "error": row.error,
                }
                for row in session.scalars(select(FrontierReviewRow))
            ]

    def import_briefs(self, briefs: list[dict]) -> int:
        records = {r["id"]: r for r in self.list_records() if r["eligibility"]["browse"]}
        topics = {t["id"]: t for t in aggregate_topics(list(records.values()), frontier_today())}
        aliases = {record["item_id"]: record["id"] for record in records.values()}

        def resolve(record_id):
            return record_id if record_id in records else aliases.get(record_id, record_id)

        with self.database.session() as session:
            for original_brief in briefs:
                brief = deepcopy(original_brief)
                if isinstance(brief.get("evidence_record_ids"), list):
                    brief["evidence_record_ids"] = [
                        resolve(i) for i in brief["evidence_record_ids"]
                    ]
                rich = brief.get("research_brief")
                if isinstance(rich, dict):
                    if isinstance(rich.get("evidence_record_ids"), list):
                        rich["evidence_record_ids"] = [
                            resolve(i) for i in rich["evidence_record_ids"]
                        ]
                    statements = [rich.get("development"), rich.get("research_implication")]
                    for field in ("consensus", "differences", "methods"):
                        if isinstance(rich.get(field), list):
                            statements.extend(rich[field])
                    for statement in statements:
                        if isinstance(statement, dict) and isinstance(
                            statement.get("evidence_record_ids"), list
                        ):
                            statement["evidence_record_ids"] = [
                                resolve(i) for i in statement["evidence_record_ids"]
                            ]
                    if isinstance(rich.get("priority_reads"), list):
                        for read in rich["priority_reads"]:
                            if isinstance(read, dict):
                                read["record_id"] = resolve(read.get("record_id"))
                if brief.get("generated_by") not in SYNTHESIS_METHODS:
                    raise ValueError("briefs require an explicit supported editorial provenance")
                key = f"{brief['topic_key']}-{brief['stream']}"
                topic = topics.get(key)
                ids = brief.get("evidence_record_ids", [])
                if not topic or not ids or any(i not in topic["record_ids"] for i in ids):
                    raise ValueError(
                        "brief evidence must be current records in this topic and stream"
                    )
                if any(not brief.get(field) for field in ("title", "summary", "why_it_matters")):
                    raise ValueError("brief title, summary and value explanation are required")
                research_brief = None
                if brief.get("research_brief") is not None:
                    research_brief = validate_research_brief(
                        brief["research_brief"], set(ids), records
                    )
                digest = content_hash(sorted((i, records[i]["content_hash"]) for i in set(ids)))
                updated = datetime.now(UTC).isoformat()
                metadata = {
                    "generated_by": brief["generated_by"],
                    "basis_content_hash": digest,
                    "updated_at": updated,
                }
                payload = {**brief, **metadata}
                if research_brief is not None:
                    payload["research_brief"] = {**research_brief, **metadata}
                values = {
                    "brief_id": key,
                    "topic_key": brief["topic_key"],
                    "stream": brief["stream"],
                    "basis_content_hash": digest,
                    "updated_at": updated,
                    "payload": payload,
                }
                session.execute(
                    insert(FrontierEditorialBriefRow)
                    .values(**values)
                    .on_conflict_do_update(index_elements=["brief_id"], set_=values)
                )
        return len(briefs)

    def list_briefs(self) -> list[dict]:
        records = {r["id"]: r for r in self.list_records() if r["eligibility"]["browse"]}
        with self.database.session() as session:
            result = []
            for row in session.scalars(select(FrontierEditorialBriefRow)):
                if row.brief_id == "corpus-overview:research":
                    continue
                ids = row.payload["evidence_record_ids"]
                if any(i not in records for i in ids):
                    continue
                digest = content_hash(sorted((i, records[i]["content_hash"]) for i in set(ids)))
                if digest == row.basis_content_hash:
                    result.append(deepcopy(row.payload))
            return result

    def import_corpus_overview(self, value: dict) -> dict:
        research = [
            r
            for r in visible_corpus_records(self.list_records())
            if r["material_type"] != "official_practice"
        ]
        payload = validate_corpus_overview(value, research)
        payload["updated_at"] = datetime.now(UTC).isoformat()
        values = {
            "brief_id": "corpus-overview:research",
            "topic_key": "corpus-overview",
            "stream": "research",
            "basis_content_hash": payload["basis_content_hash"],
            "updated_at": payload["updated_at"],
            "payload": payload,
        }
        with self.database.session() as session:
            session.execute(
                insert(FrontierEditorialBriefRow)
                .values(**values)
                .on_conflict_do_update(index_elements=["brief_id"], set_=values)
            )
        return {"saved": True, "analyzed_record_count": len(research)}

    def get_corpus_overview(self) -> dict | None:
        with self.database.session() as session:
            row = session.get(FrontierEditorialBriefRow, "corpus-overview:research")
            return deepcopy(row.payload) if row else None

    @staticmethod
    def _fence(session, job: FrontierJob | None, now: float | None) -> None:
        if job is None:
            return
        if now is None:
            raise ValueError("lease fence requires current time")
        session.execute(text("BEGIN IMMEDIATE"))
        owned = session.scalar(
            select(FrontierJobRow.job_id).where(
                FrontierJobRow.job_id == job.job_id,
                FrontierJobRow.status == "running",
                FrontierJobRow.lease_token == job.lease_token,
                FrontierJobRow.lease_until > now,
            )
        )
        if not owned:
            raise ValueError("stale_worker_lease")

    @staticmethod
    def _lease_owned(session, job, now):
        return (
            now is not None
            and session.scalar(
                select(FrontierJobRow.job_id).where(
                    FrontierJobRow.job_id == job.job_id,
                    FrontierJobRow.status == "running",
                    FrontierJobRow.lease_token == job.lease_token,
                    FrontierJobRow.lease_until > now,
                )
            )
            is not None
        )

    def ingest_source_snapshot(self, candidate, snapshot, *, job, now) -> str:
        if snapshot.source_id != candidate.source_id or not snapshot.metadata:
            raise ValueError("source snapshot mismatch")
        self.import_seed(
            {
                "generated_at": frontier_today().isoformat(),
                "sampling_strategy": "explicit_local_corpus_replay_non_exhaustive",
                "records": [snapshot.metadata],
            },
            job=job,
            now=now,
        )
        with self.database.session() as session:
            row = session.scalar(
                select(FrontierRecordRow)
                .join(FrontierItemRow, FrontierRecordRow.item_id == FrontierItemRow.item_id)
                .where(
                    FrontierItemRow.source_id == candidate.source_id,
                    FrontierItemRow.external_id == candidate.external_id,
                    FrontierRecordRow.is_current.is_(True),
                )
            )
            return row.snapshot_id

    def update_source_cursor(self, source_id: str, cursor: str | None, *, job, now) -> None:
        with self.database.session() as session:
            self._fence(session, job, now)
            source = session.get(FrontierSourceRow, source_id)
            if not source:
                raise LookupError("source not configured")
            source.cursor = cursor
            source.last_success_at = datetime.fromtimestamp(now, UTC).isoformat()
            source.status = "local_replay_completed"
            source.last_error = None

    def schedule_sources(self, *, now: float) -> list[str]:
        """Explicit opt-in scheduler; default disabled sources never produce jobs."""
        ids = []
        for source in self.list_sources():
            if source["enabled"]:
                bucket = int(now // (source["schedule_hours"] * 3600))
                ids.append(
                    self.enqueue(
                        "DISCOVER",
                        source["source_id"],
                        f"discover:{source['source_id']}:{bucket}",
                        {"cursor": source["cursor"]},
                    )
                )
        return ids

    def withdraw(self, record_id: str) -> bool:
        """Recoverable local administrative withdrawal, inherited by future versions."""
        from sqlalchemy import delete

        from qunxue_api.adapters.sqlite.frontier_models import FrontierVectorRow

        with self.database.session() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            row = session.get(FrontierRecordRow, record_id)
            if row is None:
                return False
            versions = list(
                session.scalars(
                    select(FrontierRecordRow).where(FrontierRecordRow.item_id == row.item_id)
                )
            )
            ids = [version.record_id for version in versions]
            for version in versions:
                version.verification_status = "review_queue"
                version.rag_eligible = False
                version.structured_json = {
                    **version.structured_json,
                    "verification_status": "review_queue",
                    "eligibility": eligibility("review_queue"),
                }
            session.execute(delete(FrontierIndexRow).where(FrontierIndexRow.record_id.in_(ids)))
            session.execute(delete(FrontierVectorRow).where(FrontierVectorRow.record_id.in_(ids)))
            return True

    @staticmethod
    def _import_issue_coverage(session, coverage: list[dict], sources: dict) -> None:
        if not isinstance(coverage, list):
            raise ValueError("issue_coverage must be a list")
        by_id = {source.source_id: source for source in sources.values()}
        for item in coverage:
            if not isinstance(item, dict):
                raise ValueError("issue coverage must be an object")
            source = sources.get(item.get("source_name")) or by_id.get(item.get("source_id"))
            if source is None:
                raise ValueError("issue coverage source is not registered")
            month = item.get("publication_month")
            if month is None:
                if item.get("coverage_complete") is True:
                    raise ValueError(
                        "complete issue coverage requires a verified publication month"
                    )
            else:
                try:
                    parsed_month = datetime.strptime(month, "%Y-%m").strftime("%Y-%m")
                except (ValueError, TypeError):
                    raise ValueError(
                        "issue coverage requires a verified publication month"
                    ) from None
                if month != parsed_month:
                    raise ValueError("issue publication month must use YYYY-MM")
            issue_id = item.get("issue_id")
            if not issue_id and item.get("publication_year") and item.get("publication_issue"):
                issue_id = (
                    f"{source.source_id}:{item['publication_year']}:{item['publication_issue']}"
                )
            if not isinstance(issue_id, str) or not issue_id.strip() or len(issue_id) > 250:
                raise ValueError("issue coverage requires a stable issue_id")
            counts = [
                item.get(key) for key in ("candidate_count", "readable_count", "included_count")
            ]
            if (
                any(type(value) is not int or value < 0 for value in counts)
                or not counts[0] >= counts[1] >= counts[2]
            ):
                raise ValueError("invalid issue candidate/readable/included counts")
            url = item.get("issue_url", "")
            if not safe_public_url(url, source.config["approved_public_hosts"]):
                raise ValueError("issue coverage URL is outside the approved source")
            value = {
                "issue_id": issue_id,
                "source_id": source.source_id,
                "label": item.get("label")
                or (
                    f"{source.name} {item['publication_year']}年第{item['publication_issue']}期"
                    if item.get("publication_year") and item.get("publication_issue")
                    else f"{source.name} {issue_id}"
                ),
                "publication_year": item.get("publication_year"),
                "publication_issue": item.get("publication_issue"),
                "publication_month": month,
                "candidate_count": counts[0],
                "readable_count": counts[1],
                "included_count": counts[2],
                "coverage_complete": item.get("coverage_complete") is True,
                "issue_url": url,
            }
            current = {
                entry["issue_id"]: entry for entry in source.config.get("issue_coverage", [])
            }
            current[issue_id] = value
            source.config = {**source.config, "issue_coverage": list(current.values())}
        session.flush()

    def list_issue_coverage(self) -> list[dict]:
        with self.database.session() as session:
            return [
                deepcopy(item)
                for source in session.scalars(select(FrontierSourceRow))
                for item in source.config.get("issue_coverage", [])
            ]
