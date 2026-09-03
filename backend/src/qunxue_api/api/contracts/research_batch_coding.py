from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from qunxue_api.modules.research_analysis import BatchCodingRun


class BatchCodingRunResponse(BaseModel):
    run_id: UUID
    task_id: UUID
    material_id: UUID
    parse_id: UUID
    parse_version: int
    status: str
    total_segments: int
    processed_segments: int
    annotation_ids: list[UUID]
    code_ids: list[UUID]
    low_confidence_segments: list[str]
    error_code: str | None
    retry_count: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    @classmethod
    def from_domain(cls, value: BatchCodingRun) -> "BatchCodingRunResponse":
        return cls(
            run_id=value.run_id,
            task_id=value.task_id,
            material_id=value.material_id,
            parse_id=value.parse_id,
            parse_version=value.parse_version,
            status=value.status.value,
            total_segments=value.total_segments,
            processed_segments=value.processed_segments,
            annotation_ids=list(value.annotation_ids),
            code_ids=list(value.code_ids),
            low_confidence_segments=list(value.low_confidence_segments),
            error_code=value.error_code,
            retry_count=value.retry_count,
            created_at=value.created_at,
            updated_at=value.updated_at,
            completed_at=value.completed_at,
        )
