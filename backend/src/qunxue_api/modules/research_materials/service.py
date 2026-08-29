"""Use-case facade for the material repository."""

from datetime import datetime
from uuid import UUID, uuid4

from qunxue_api.modules.research_materials.domain import (
    MaterialKind,
    MaterialParseVersion,
    ResearchMaterial,
)
from qunxue_api.modules.research_materials.ports import ResearchMaterialRepository


class ResearchMaterialService:
    def __init__(self, repository: ResearchMaterialRepository) -> None:
        self._repository = repository

    def upload(
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
    ) -> ResearchMaterial:
        return self._repository.create(
            user_id=user_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
            filename=filename,
            media_type=media_type,
            content=content,
            material_kind=material_kind,
            display_name=display_name,
            processing_policy_version=processing_policy_version,
            now=now,
        )

    def list(self, *, user_id: UUID, task_id: UUID, limit: int = 100, offset: int = 0):
        return self._repository.list(user_id=user_id, task_id=task_id, limit=limit, offset=offset)

    def get(self, material_id: UUID, *, user_id: UUID, task_id: UUID) -> ResearchMaterial | None:
        return self._repository.get(material_id, user_id=user_id, task_id=task_id)

    def begin_reparse(
        self,
        material_id: UUID,
        *,
        user_id: UUID,
        task_id: UUID,
        now: datetime,
        expected_current_version: int | None = None,
    ) -> ResearchMaterial | None:
        return self._repository.begin_reparse(
            material_id,
            user_id=user_id,
            task_id=task_id,
            parse_id=uuid4(),
            now=now,
            expected_current_version=expected_current_version,
        )

    def save_parse(self, parsed: MaterialParseVersion) -> MaterialParseVersion:
        return self._repository.save_parse(parsed)

    def delete(
        self,
        material_id: UUID,
        *,
        user_id: UUID,
        task_id: UUID,
        idempotency_key: str,
        now: datetime,
    ) -> ResearchMaterial | None:
        return self._repository.delete(
            material_id,
            user_id=user_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
            now=now,
        )
