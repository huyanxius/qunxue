"""Opt-in single-job frontier orchestration, with no scheduler or network defaults.

Ports finish their own short transactions before returning. Extraction and independent
verification therefore run outside a database transaction; every subsequent write is
guarded again by the original job's lease in the store transaction.
"""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict
from datetime import date, datetime
from time import monotonic, time
from zoneinfo import ZoneInfo

from qunxue_api.modules.frontier_knowledge import (
    RULE_VERSION,
    SCHEMA_VERSION,
    Candidate,
    FrontierExtractorPort,
    FrontierJob,
    FrontierService,
    FrontierSourceAdapter,
    FrontierStore,
    FrontierVerifierPort,
    JobStage,
    content_hash,
    qualify_record,
)

_INVALID_OUTPUT = {
    "InvalidOutput",
    "InvalidJSON",
    "InvalidSchema",
    "InvalidEvidence",
    "InvalidEvidenceReference",
    "UnsupportedNumber",
    "InvalidClaim",
    "InvalidResponse",
}
_MODEL_BLOCKERS = {"NotConfigured", "NetworkDisabled"}


class _LeaseLost(Exception):
    pass


class _Blocked(Exception):
    pass


class _InvalidEvidence(ValueError):
    code = "InvalidEvidence"


class FrontierWorker:
    def __init__(
        self,
        store: FrontierStore,
        extractor: FrontierExtractorPort,
        verifier: FrontierVerifierPort,
        sources: dict[str, FrontierSourceAdapter],
        topic_service: FrontierService,
        vector_index=None,
    ) -> None:
        self.vector_index = vector_index
        self.store = store
        self.extractor = extractor
        self.verifier = verifier
        self.sources = sources
        self.topic_service = topic_service

    def run_once(self, now: float | None = None) -> bool:
        """Process at most one leased job; True means claimed, not published.

        An explicit time is a logical clock origin for deterministic callers. Elapsed
        work still counts against the lease, including slow model or source calls.
        """
        started = monotonic()
        origin = time() if now is None else now
        clock = (lambda: time()) if now is None else (lambda: origin + monotonic() - started)
        job = self.store.claim_job(now=origin)
        if job is None:
            return False
        try:
            self._require_lease(job, clock)
            self._run(job, clock)
        except _LeaseLost:
            # A replacement worker owns completion and publication now.
            return True
        except _Blocked as exc:
            self.store.finish_job(job, now=clock(), status="blocked", reason=str(exc))
        except Exception as exc:
            code = getattr(exc, "code", None)
            code = code if isinstance(code, str) else None
            if code in _MODEL_BLOCKERS:
                self.store.finish_job(job, now=clock(), status="blocked", reason=code)
            elif code in _INVALID_OUTPUT:
                try:
                    self._save_review(
                        job,
                        {},
                        [],
                        "review_queue",
                        clock,
                        error=code,
                    )
                except _LeaseLost:
                    return True
                except Exception:
                    self.store.finish_job(
                        job,
                        now=clock(),
                        status="retry",
                        reason="ReviewPersistenceFailed",
                    )
                else:
                    self.store.finish_job(job, now=clock(), reason=code)
            else:
                # Never persist exception text, provider bodies, URLs, or credentials.
                reason = "RequestFailed" if code == "RequestFailed" else "WorkerFailed"
                self.store.finish_job(job, now=clock(), status="retry", reason=reason)
        else:
            self.store.finish_job(job, now=clock())
        return True

    def _require_lease(self, job: FrontierJob, clock: Callable[[], float]) -> float:
        now = clock()
        if not self.store.owns_lease(job, now=now):
            raise _LeaseLost
        return now

    def _run(self, job: FrontierJob, clock: Callable[[], float]) -> None:
        if job.stage == JobStage.INDEX:
            self.store.reindex(job.object_id, job=job, now=self._require_lease(job, clock))
            if self.vector_index is not None:
                self.vector_index.index_record(
                    job.object_id, job=job, now=self._require_lease(job, clock)
                )
        elif job.stage == JobStage.TREND:
            as_of_value = job.payload.get("as_of")
            as_of = (
                date.fromisoformat(as_of_value)
                if as_of_value
                else datetime.fromtimestamp(clock(), ZoneInfo("Asia/Shanghai")).date()
            )
            topics = self.topic_service.topics(as_of=as_of)
            self.store.save_topics(
                as_of.isoformat(),
                topics,
                job=job,
                now=self._require_lease(job, clock),
            )
        elif job.stage in {JobStage.DISCOVER, JobStage.FETCH}:
            self._collect(job, clock)
        elif job.stage in {JobStage.PARSE, JobStage.EXTRACT, JobStage.VERIFY}:
            snapshot = self.store.get_snapshot(job.object_id)
            if snapshot is None:
                raise _Blocked("SnapshotNotFound")
            blocks = self._blocks(snapshot, job.object_id)
            if job.stage == JobStage.PARSE:
                self._enqueue(job, JobStage.EXTRACT, {}, clock)
            elif job.stage == JobStage.EXTRACT:
                extracted = self.extractor.extract(
                    {"scope": snapshot["scope"], "blocks": deepcopy(list(blocks.values()))},
                )
                self._findings(extracted, blocks)
                self._enqueue(job, JobStage.VERIFY, {"extracted": deepcopy(extracted)}, clock)
            else:
                self._verify(job, snapshot, blocks, clock)
        else:
            raise _Blocked("UnsupportedStage")

    def _collect(self, job: FrontierJob, clock: Callable[[], float]) -> None:
        candidate_data = job.payload.get("candidate", job.payload)
        if not isinstance(candidate_data, dict):
            raise _Blocked("InvalidCandidate")
        source_id = job.payload.get("source_id") or candidate_data.get("source_id")
        if job.stage == JobStage.DISCOVER:
            source_id = source_id or job.object_id
        source = self.sources.get(source_id)
        if source is None:
            raise _Blocked("SourceNotConfigured")
        try:
            if job.stage == JobStage.DISCOVER:
                candidates = source.discover(job.payload.get("cursor"))
                if not hasattr(self.store, "ingest_source_snapshot") or source_id not in {
                    s["source_id"] for s in self.store.list_sources()
                }:
                    raise _Blocked("SourcePersistenceNotConfigured")
                for candidate in candidates:
                    self.store.enqueue(
                        "FETCH",
                        candidate.external_id,
                        f"fetch:{source_id}:{candidate.external_id}:{content_hash(asdict(candidate))}",
                        {"candidate": asdict(candidate)},
                        job=job,
                        now=self._require_lease(job, clock),
                    )
                next_cursor = getattr(source, "next_cursor", None)
                cursor = (next_cursor if isinstance(next_cursor, str) else None) or max(
                    (c.external_id for c in candidates), default=job.payload.get("cursor")
                )
                self.store.update_source_cursor(
                    source_id, cursor, job=job, now=self._require_lease(job, clock)
                )
            else:
                candidate = Candidate(
                    source_id=source_id,
                    external_id=candidate_data.get("external_id", job.object_id),
                    title=candidate_data.get("title", ""),
                    url=candidate_data.get("url", ""),
                    authors=tuple(candidate_data.get("authors") or ()),
                    doi=candidate_data.get("doi"),
                    published_at=candidate_data.get("published_at"),
                    content_hash=candidate_data.get("content_hash"),
                )
                snapshot = source.fetch(candidate)
                if not hasattr(self.store, "ingest_source_snapshot") or not getattr(
                    snapshot, "metadata", None
                ):
                    raise _Blocked("SourcePersistenceNotConfigured")
                snapshot_id = self.store.ingest_source_snapshot(
                    candidate, snapshot, job=job, now=self._require_lease(job, clock)
                )
                self.store.enqueue(
                    "PARSE",
                    snapshot_id,
                    f"parse:{snapshot_id}:{RULE_VERSION}",
                    job=job,
                    now=self._require_lease(job, clock),
                )
        except Exception as exc:
            if getattr(exc, "code", None) == "SourceNotConfigured":
                reason = getattr(source, "reason", None)
                reason = reason if isinstance(reason, str) else "SourceNotConfigured"
                raise _Blocked(reason) from None
            raise

    @staticmethod
    def _blocks(snapshot: dict, snapshot_id: str) -> dict[str, dict]:
        if (
            not isinstance(snapshot, dict)
            or snapshot.get("snapshot_id") != snapshot_id
            or not isinstance(snapshot.get("scope"), str)
            or snapshot.get("scope")
            not in {
                "full_text",
                "abstract_or_notice_only",
                "metadata_and_short_excerpt",
            }
            or not isinstance(snapshot.get("blocks"), list)
            or not snapshot["blocks"]
        ):
            raise _InvalidEvidence
        blocks = {}
        for block in snapshot["blocks"]:
            if (
                not isinstance(block, dict)
                or any(
                    not isinstance(block.get(key), str) or not block[key].strip()
                    for key in ("block_id", "locator")
                )
                or not isinstance(block.get("text"), str)
            ):
                raise _InvalidEvidence
            # Locator-only metadata is preserved in the snapshot but is not model evidence.
            if not block["text"].strip():
                continue
            if block["block_id"] in blocks:
                raise _InvalidEvidence
            blocks[block["block_id"]] = {key: block[key] for key in ("block_id", "text", "locator")}
        if not blocks:
            raise _Blocked("AwaitingSourceText")
        return blocks

    @staticmethod
    def _findings(extracted: dict, blocks: dict[str, dict]) -> list[dict]:
        if not isinstance(extracted, dict) or not isinstance(extracted.get("findings"), list):
            raise _InvalidEvidence
        for finding in extracted["findings"]:
            if not isinstance(finding, dict):
                raise _InvalidEvidence
            claim = finding.get("claim_text")
            ids = finding.get("evidence_block_ids")
            if (
                not isinstance(claim, str)
                or not claim.strip()
                or not isinstance(ids, list)
                or not ids
                or any(not isinstance(block_id, str) or block_id not in blocks for block_id in ids)
                or len(set(ids)) != len(ids)
            ):
                raise _InvalidEvidence
        return extracted["findings"]

    def _verify(
        self,
        job: FrontierJob,
        snapshot: dict,
        blocks: dict[str, dict],
        clock: Callable[[], float],
    ) -> None:
        extracted = deepcopy(job.payload.get("extracted"))
        findings = self._findings(extracted, blocks)
        verdicts = []
        for finding in findings:
            self._require_lease(job, clock)
            cited = [blocks[block_id] for block_id in finding["evidence_block_ids"]]
            evidence = (
                cited[0]
                if len(cited) == 1
                else {
                    "block_id": "evidence-" + content_hash(finding["evidence_block_ids"])[:24],
                    "text": "\n\n".join(block["text"] for block in cited),
                    "locator": "; ".join(block["locator"] for block in cited),
                }
            )
            verdict = self.verifier.verify(finding["claim_text"], deepcopy(evidence))
            if (
                not isinstance(verdict, dict)
                or not isinstance(verdict.get("status"), str)
                or verdict.get("status") not in {"supported", "partially_supported", "unsupported"}
                or not isinstance(verdict.get("reason"), str)
                or not verdict["reason"].strip()
            ):
                raise _InvalidEvidence
            verdicts.append(deepcopy(verdict))
        original = snapshot.get("original_input")
        original = original if isinstance(original, dict) else {}
        status = qualify_record(
            {**snapshot, "blocks": list(blocks.values())},
            findings,
            verdicts,
            source_verified=snapshot.get("source_verified") is True,
            material_type=snapshot.get("material_type") or original.get("material_type", ""),
        )
        self._save_review(
            job,
            extracted,
            verdicts,
            status,
            clock,
            error="EvidenceNotQualified" if status == "review_queue" else None,
        )

    def _enqueue(
        self,
        job: FrontierJob,
        stage: JobStage,
        payload: dict,
        clock: Callable[[], float],
    ) -> None:
        key = content_hash([stage, job.object_id, SCHEMA_VERSION, RULE_VERSION, payload])
        self.store.enqueue(
            stage,
            job.object_id,
            f"frontier:{key}",
            payload,
            job=job,
            now=self._require_lease(job, clock),
        )

    def _save_review(
        self,
        job: FrontierJob,
        extracted: dict,
        verdicts: list[dict],
        status: str,
        clock: Callable[[], float],
        *,
        error: str | None = None,
    ) -> None:
        saved = self.store.save_review_result(
            job.object_id,
            extracted,
            verdicts,
            status,
            error=error,
            job=job,
            now=self._require_lease(job, clock),
        )
        if saved is False:
            raise _LeaseLost
