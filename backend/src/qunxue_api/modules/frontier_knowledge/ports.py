"""Ports do not import network, ORM, Web or model libraries."""

from typing import Protocol

from .domain import Candidate, FrontierJob, SourceBlock, SourceSnapshot


class FrontierStore(Protocol):
    def list_records(self) -> list[dict]: ...
    def get_record(self, record_id: str) -> dict | None: ...
    def get_snapshot(self, snapshot_id: str) -> dict | None: ...
    def list_sources(self) -> list[dict]: ...
    def list_briefs(self) -> list[dict]: ...
    def list_issue_coverage(self) -> list[dict]: ...
    def get_corpus_overview(self) -> dict | None: ...
    def enqueue(
        self,
        stage: str,
        object_id: str,
        idempotency_key: str,
        payload: dict | None = None,
        *,
        job: FrontierJob | None = None,
        now: float | None = None,
    ) -> str: ...
    def claim_job(self, *, now: float, lease_seconds: int = 120) -> FrontierJob | None: ...
    def finish_job(
        self, job: FrontierJob, *, now: float, status: str = "completed", reason: str | None = None
    ) -> bool: ...
    def owns_lease(self, job: FrontierJob, now: float) -> bool: ...
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
    ) -> bool: ...
    def reindex(
        self, record_id: str, *, job: FrontierJob | None = None, now: float | None = None
    ) -> None: ...
    def save_topics(
        self,
        as_of: str,
        topics: list[dict],
        *,
        job: FrontierJob | None = None,
        now: float | None = None,
    ) -> None: ...


class FrontierSourceAdapter(Protocol):
    def discover(self, cursor: str | None) -> tuple[Candidate, ...]: ...
    def fetch(self, candidate: Candidate) -> SourceSnapshot: ...
    def parse(self, snapshot: SourceSnapshot) -> tuple[SourceBlock, ...]: ...


class FrontierExtractorPort(Protocol):
    def extract(self, snapshot: dict) -> dict: ...


class FrontierVerifierPort(Protocol):
    def verify(self, claim: str, block: dict) -> dict: ...
