"""Persistence ports for research materials."""

from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from qunxue_api.modules.research_materials.domain import (
    MaterialBlock,
    MaterialKind,
    MaterialParseVersion,
    MaterialReparseRequest,
    ResearchMaterial,
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
