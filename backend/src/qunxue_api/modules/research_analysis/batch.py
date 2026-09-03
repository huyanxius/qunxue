"""Durable lifecycle records for full-material qualitative coding batches."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4


class BatchCodingStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class BatchCodingRepository(Protocol):
    def add(self, value: "BatchCodingRun") -> "BatchCodingRun": ...
    def get(self, run_id: UUID, *, user_id: UUID, task_id: UUID) -> "BatchCodingRun | None": ...
    def get_by_idempotency(
        self, *, user_id: UUID, task_id: UUID, material_id: UUID, idempotency_key: str
    ) -> "BatchCodingRun | None": ...
    def save(self, value: "BatchCodingRun") -> "BatchCodingRun": ...


@dataclass(frozen=True, slots=True)
class BatchCodingRun:
    run_id: UUID
    user_id: UUID
    task_id: UUID
    material_id: UUID
    parse_id: UUID
    parse_version: int
    idempotency_key: str
    status: BatchCodingStatus
    total_segments: int
    processed_segments: int
    annotation_ids: tuple[UUID, ...]
    code_ids: tuple[UUID, ...]
    low_confidence_segments: tuple[str, ...]
    error_code: str | None
    retry_count: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    @classmethod
    def queued(
        cls,
        *,
        user_id: UUID,
        task_id: UUID,
        material_id: UUID,
        parse_id: UUID,
        parse_version: int,
        idempotency_key: str,
        total_segments: int,
        now: datetime,
        run_id: UUID | None = None,
    ) -> "BatchCodingRun":
        if not idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        if total_segments < 1:
            raise ValueError("material parse has no segments")
        timestamp = now.astimezone(UTC)
        return cls(
            run_id=run_id or uuid4(),
            user_id=user_id,
            task_id=task_id,
            material_id=material_id,
            parse_id=parse_id,
            parse_version=parse_version,
            idempotency_key=idempotency_key,
            status=BatchCodingStatus.QUEUED,
            total_segments=total_segments,
            processed_segments=0,
            annotation_ids=(),
            code_ids=(),
            low_confidence_segments=(),
            error_code=None,
            retry_count=0,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def processing(self, *, now: datetime) -> "BatchCodingRun":
        return replace(
            self,
            status=BatchCodingStatus.PROCESSING,
            updated_at=now.astimezone(UTC),
            error_code=None,
        )

    def progress(
        self,
        *,
        processed_segments: int,
        annotation_id: UUID,
        code_id: UUID,
        low_confidence: bool,
        segment_id: str,
        now: datetime,
    ) -> "BatchCodingRun":
        if self.status is not BatchCodingStatus.PROCESSING:
            raise ValueError("batch is not processing")
        if (
            processed_segments <= self.processed_segments
            or processed_segments > self.total_segments
        ):
            raise ValueError("invalid batch progress")
        return replace(
            self,
            processed_segments=processed_segments,
            annotation_ids=self.annotation_ids + (annotation_id,),
            code_ids=self.code_ids + (code_id,),
            low_confidence_segments=self.low_confidence_segments
            + ((segment_id,) if low_confidence else ()),
            updated_at=now.astimezone(UTC),
        )

    def complete(self, *, now: datetime) -> "BatchCodingRun":
        if self.processed_segments != self.total_segments:
            raise ValueError("cannot complete before every segment is processed")
        timestamp = now.astimezone(UTC)
        return replace(
            self, status=BatchCodingStatus.COMPLETED, updated_at=timestamp, completed_at=timestamp
        )

    def fail(self, *, error_code: str, now: datetime) -> "BatchCodingRun":
        if not error_code.strip():
            raise ValueError("error_code is required")
        return replace(
            self,
            status=BatchCodingStatus.FAILED,
            error_code=error_code,
            updated_at=now.astimezone(UTC),
        )

    def retry(self, *, now: datetime) -> "BatchCodingRun":
        if self.status is not BatchCodingStatus.FAILED:
            raise ValueError("only failed batches can be retried")
        return replace(
            self,
            status=BatchCodingStatus.QUEUED,
            retry_count=self.retry_count + 1,
            error_code=None,
            updated_at=now.astimezone(UTC),
        )
