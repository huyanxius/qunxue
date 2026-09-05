"""Persistence ports for research materials."""

from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from qunxue_api.modules.research_materials.domain import (
    MaterialBlock,
    MaterialIngestionJob,
    MaterialKind,
    MaterialParseVersion,
    MaterialReparseRequest,
    ResearchMaterial,
    ResearchMaterialSearchResult,
)


@runtime_checkable
class ResearchMaterialRepository(Protocol):
    def create(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        idempotency_key: str,
        filename: str,
        media_type: str | None,
        content: bytes,
        material_kind: MaterialKind = MaterialKind.OTHER,
        display_name: str | None = None,
        processing_policy_version: str = "1",
        now: datetime,
    ) -> ResearchMaterial: ...

    def get(
        self, material_id: UUID, *, user_id: UUID, task_id: UUID, include_deleted: bool = False
    ) -> ResearchMaterial | None: ...

    def get_owned(self, material_id: UUID, *, user_id: UUID) -> ResearchMaterial | None: ...

    def list_owned(
        self, *, user_id: UUID, limit: int = 100, offset: int = 0
    ) -> tuple[ResearchMaterial, ...]: ...

    def list(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        include_deleted: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[ResearchMaterial, ...]: ...

    def get_original(
        self, material_id: UUID, *, user_id: UUID, task_id: UUID
    ) -> bytes | None: ...

    def get_parse(
        self,
        material_id: UUID,
        parse_id: UUID,
        *,
        user_id: UUID,
        task_id: UUID,
    ) -> MaterialParseVersion | None: ...

    def list_parses(
        self, material_id: UUID, *, user_id: UUID, task_id: UUID
    ) -> tuple[MaterialParseVersion, ...]: ...

    def get_segment(
        self,
        material_id: UUID,
        parse_id: UUID,
        segment_id: str,
        *,
        user_id: UUID,
        task_id: UUID,
    ) -> MaterialBlock | None: ...

    def begin_reparse(
        self,
        material_id: UUID,
        *,
        user_id: UUID,
        task_id: UUID,
        parse_id: UUID,
        now: datetime,
        expected_current_version: int | None = None,
    ) -> ResearchMaterial | None: ...

    def reserve_reparse(
        self,
        material_id: UUID,
        *,
        user_id: UUID,
        task_id: UUID,
        idempotency_key: str,
        parse_id: UUID,
        now: datetime,
    ) -> MaterialReparseRequest: ...

    def save_parse(self, parsed: MaterialParseVersion) -> MaterialParseVersion: ...

    def delete(
        self,
        material_id: UUID,
        *,
        user_id: UUID,
        task_id: UUID,
        idempotency_key: str,
        now: datetime,
    ) -> ResearchMaterial | None: ...

    def enqueue_ingestion(
        self,
        *,
        material: ResearchMaterial,
        parse_id: UUID,
        now: datetime,
        max_attempts: int = 3,
    ) -> MaterialIngestionJob: ...

    def get_ingestion(self, job_id: UUID) -> MaterialIngestionJob | None: ...

    def get_material_ingestion(
        self, material_id: UUID, *, user_id: UUID, task_id: UUID
    ) -> MaterialIngestionJob | None: ...

    def claim_ingestion(
        self, job_id: UUID, *, now: datetime, lease_expires_at: datetime
    ) -> MaterialIngestionJob | None: ...

    def complete_ingestion(
        self,
        job_id: UUID,
        *,
        expected_attempt_count: int,
        expected_parse_id: UUID,
        now: datetime,
    ) -> MaterialIngestionJob | None: ...

    def fail_ingestion(
        self,
        job_id: UUID,
        *,
        expected_attempt_count: int,
        expected_parse_id: UUID,
        error_code: str,
        retry_at: datetime | None,
        now: datetime,
    ) -> MaterialIngestionJob | None: ...

    def recoverable_ingestion_ids(self, *, now: datetime) -> tuple[UUID, ...]: ...


@runtime_checkable
class ResearchMaterialSearchRepository(Protocol):
    def search(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        query: str,
        material_ids: tuple[UUID, ...] = (),
        material_parse_ids: tuple[tuple[UUID, UUID], ...] = (),
        material_kind: MaterialKind | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> ResearchMaterialSearchResult: ...
