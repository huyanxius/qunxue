"""Immutable transcript shapes independent from ASR and transport libraries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class TranscriptSource(StrEnum):
    AUTOMATIC = "automatic"
    IMPORTED = "imported"
    MANUAL_CORRECTION = "manual_correction"


class TranscriptionStatus(StrEnum):
    NOT_STARTED = "not_started"
    UNAVAILABLE = "unavailable"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class ProcessingLocation(StrEnum):
    LOCAL = "local"
    EXTERNAL = "external"


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    ordinal: int
    text: str
    start_ms: int | None = None
    end_ms: int | None = None
    speaker: str | None = None
    segment_id: str | None = None

    def __post_init__(self) -> None:
        if self.ordinal < 0:
            raise ValueError("transcript segment ordinal must be non-negative")
        if not self.text.strip():
            raise ValueError("transcript segment text is required")
        if (self.start_ms is None) != (self.end_ms is None):
            raise ValueError("transcript timecodes must provide both start and end")
        if self.start_ms is not None and self.start_ms < 0:
            raise ValueError("transcript start must be non-negative")
        if (
            self.start_ms is not None
            and self.end_ms is not None
            and self.end_ms <= self.start_ms
        ):
            raise ValueError("transcript end must follow start")
        if self.speaker is not None and not self.speaker.strip():
            raise ValueError("transcript speaker must not be blank")
        if self.segment_id is not None and not self.segment_id.strip():
            raise ValueError("transcript segment ID must not be blank")


@dataclass(frozen=True, slots=True)
class ParsedTranscript:
    source_format: str
    segments: tuple[TranscriptSegment, ...]

    def __post_init__(self) -> None:
        if not self.source_format.strip():
            raise ValueError("transcript source format is required")
        if not self.segments:
            raise ValueError("transcript requires at least one segment")
        if [item.ordinal for item in self.segments] != list(range(len(self.segments))):
            raise ValueError("transcript ordinals must be contiguous and zero-based")


@dataclass(frozen=True, slots=True)
class TranscriptVersion:
    version_id: UUID
    material_id: UUID
    version: int
    source: TranscriptSource
    provider: str | None
    created_from_version_id: UUID | None
    segments: tuple[TranscriptSegment, ...]
    created_at: datetime
    is_current: bool


@dataclass(frozen=True, slots=True)
class TranscriptionWorkspace:
    material_id: UUID
    status: TranscriptionStatus
    automatic_available: bool
    automatic_provider: str | None
    current_version: TranscriptVersion | None
    versions: tuple[TranscriptVersion, ...]
    error_code: str | None = None
