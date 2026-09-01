from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from qunxue_api.modules.transcription import (
    TranscriptionWorkspace,
    TranscriptSegment,
    TranscriptVersion,
)


class TranscriptSegmentInput(BaseModel):
    segment_id: str | None = None
    ordinal: int = Field(ge=0)
    speaker: str | None = None
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    text: str = Field(min_length=1)

    def to_domain(self) -> TranscriptSegment:
        return TranscriptSegment(
            segment_id=self.segment_id,
            ordinal=self.ordinal,
            speaker=self.speaker,
            start_ms=self.start_ms,
            end_ms=self.end_ms,
            text=self.text,
        )


class CreateTranscriptVersionRequest(BaseModel):
    base_version_id: UUID
    segments: list[TranscriptSegmentInput] = Field(min_length=1)


class TranscriptSegmentResponse(BaseModel):
    segment_id: str
    ordinal: int
    speaker: str | None
    start_ms: int | None
    end_ms: int | None
    text: str

    @classmethod
    def from_domain(cls, value: TranscriptSegment) -> "TranscriptSegmentResponse":
        if value.segment_id is None:
            raise ValueError("persisted transcript segment requires an ID")
        return cls(
            segment_id=value.segment_id,
            ordinal=value.ordinal,
            speaker=value.speaker,
            start_ms=value.start_ms,
            end_ms=value.end_ms,
            text=value.text,
        )


class TranscriptVersionResponse(BaseModel):
    version_id: UUID
    material_id: UUID
    version: int
    source: str
    provider: str | None
    created_from_version_id: UUID | None
    created_at: datetime
    is_current: bool
    segments: list[TranscriptSegmentResponse]

    @classmethod
    def from_domain(cls, value: TranscriptVersion) -> "TranscriptVersionResponse":
        return cls(
            version_id=value.version_id,
            material_id=value.material_id,
            version=value.version,
            source=value.source.value,
            provider=value.provider,
            created_from_version_id=value.created_from_version_id,
            created_at=value.created_at,
            is_current=value.is_current,
            segments=[TranscriptSegmentResponse.from_domain(item) for item in value.segments],
        )


class TranscriptionWorkspaceResponse(BaseModel):
    material_id: UUID
    status: str
    automatic_available: bool
    automatic_provider: str | None
    error_code: str | None
    current_version: TranscriptVersionResponse | None
    versions: list[TranscriptVersionResponse]

    @classmethod
    def from_domain(cls, value: TranscriptionWorkspace) -> "TranscriptionWorkspaceResponse":
        return cls(
            material_id=value.material_id,
            status=value.status.value,
            automatic_available=value.automatic_available,
            automatic_provider=value.automatic_provider,
            error_code=value.error_code,
            current_version=(
                TranscriptVersionResponse.from_domain(value.current_version)
                if value.current_version
                else None
            ),
            versions=[TranscriptVersionResponse.from_domain(item) for item in value.versions],
        )
