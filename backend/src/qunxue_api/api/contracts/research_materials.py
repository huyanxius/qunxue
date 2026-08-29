from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, BeforeValidator

from qunxue_api.modules.research_materials import (
    MaterialBlock,
    MaterialKind,
    MaterialLocator,
    ResearchMaterial,
)


def _normalize_material_kind_input(value: object) -> object:
    """Accept the pre-release ``observation`` spelling at the HTTP edge.

    ``observation_record`` is the persisted/public value.  Keeping the alias
    in the request validator lets an already-released client continue to
    upload while ensuring every domain object and response uses one canonical
    value.
    """

    if isinstance(value, str) and value.strip().lower() == "observation":
        return MaterialKind.OBSERVATION_RECORD.value
    return value


ResearchMaterialKindInput = Annotated[
    MaterialKind,
    BeforeValidator(_normalize_material_kind_input),
]


class ResearchMaterialLocatorResponse(BaseModel):
    page: int | None
    section_path: list[str]
    paragraph: int | None
    line_start: int | None
    line_end: int | None
    char_start: int | None
    char_end: int | None
    block_index: int | None

    @classmethod
    def from_domain(cls, locator: MaterialLocator) -> "ResearchMaterialLocatorResponse":
        return cls(**locator.as_dict())


class ResearchMaterialSegmentResponse(BaseModel):
    segment_id: str
    material_id: UUID
    parse_id: UUID
    ordinal: int
    kind: str
    text: str
    locator: ResearchMaterialLocatorResponse

    @classmethod
    def from_domain(cls, block: MaterialBlock) -> "ResearchMaterialSegmentResponse":
        return cls(
            segment_id=block.segment_id,
            material_id=block.material_id,
            parse_id=block.parse_id,
            ordinal=block.ordinal,
            kind=block.kind,
            text=block.text,
            locator=ResearchMaterialLocatorResponse.from_domain(block.locator),
        )


class ResearchMaterialResponse(BaseModel):
    material_id: UUID
    task_id: UUID
    filename: str
    display_name: str
    media_type: str
    material_format: str
    material_kind: MaterialKind
    size_bytes: int
    status: str
    version: int
    parse_id: UUID | None
    parse_version: int | None
    is_current_parse: bool
    segment_count: int
    updated_at: datetime
    error_code: str | None
    segments: list[ResearchMaterialSegmentResponse] | None = None

    @classmethod
    def from_domain(
        cls,
        material: ResearchMaterial,
        *,
        segments: tuple[MaterialBlock, ...] | None = None,
        parse_id: UUID | None = None,
        parse_version: int | None = None,
    ) -> "ResearchMaterialResponse":
        return cls(
            material_id=material.material_id,
            task_id=material.task_id,
            filename=material.original_filename,
            display_name=material.display_name,
            media_type=material.media_type,
            material_format=material.material_format.value,
            material_kind=material.material_kind,
            size_bytes=material.size_bytes,
            status=(
                "processing"
                if material.status.value in {"uploaded", "parsing"}
                else material.status.value
            ),
            version=material.current_parse_version or 1,
            parse_id=parse_id,
            parse_version=parse_version,
            is_current_parse=(
                parse_id is not None and parse_id == material.current_parse_id
            ),
            segment_count=len(segments or ()),
            updated_at=material.updated_at,
            error_code=material.last_error_code,
            segments=(
                [ResearchMaterialSegmentResponse.from_domain(item) for item in segments]
                if segments is not None
                else None
            ),
        )


class ResearchMaterialListResponse(BaseModel):
    task_id: UUID
    items: list[ResearchMaterialResponse]
