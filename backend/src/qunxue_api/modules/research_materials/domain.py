"""Pure domain objects for user-owned research materials.

The material is a durable source identity.  Parsed versions are append-only;
the material's current pointer changes only after a complete successful parse.
No parser, web framework, ORM, or model SDK is imported here.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from qunxue_api.modules.research_materials.errors import (
    MaterialDeleted,
    MaterialParseError,
    MaterialVersionConflict,
    UnsupportedMaterialFormat,
)


class MaterialStatus(StrEnum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"


class MaterialIngestionStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ParsedMaterial:
    """Stable parser output consumed by the application boundary.

    Concrete parsers live in adapters; this immutable shape keeps the
    application independent from any parser implementation or library.
    """

    full_text: str
    structured_document: dict[str, Any]
    blocks: tuple[MaterialBlock, ...]
    content_hash: str
    parser_name: str
    parser_version: str
    schema_version: str


class MaterialKind(StrEnum):
    PAPER = "paper"
    INTERVIEW_TRANSCRIPT = "interview_transcript"
    OBSERVATION_RECORD = "observation_record"
    FIELD_NOTE = "field_note"
    OTHER = "other"

    @classmethod
    def _missing_(cls, value: object) -> MaterialKind | None:
        """Read the pre-canonical ``observation`` value without persisting it.

        Older clients used ``observation`` for observation records.  Keeping
        this alias at the domain boundary lets those requests continue to
        work while every response and row uses the canonical value.
        """

        if isinstance(value, str) and value.strip().lower() == "observation":
            return cls.OBSERVATION_RECORD
        return None


class MaterialFormat(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    MARKDOWN = "markdown"
    MP3 = "mp3"
    M4A = "m4a"
    WAV = "wav"
    MP4 = "mp4"
    WEBM = "webm"

    @property
    def canonical_media_type(self) -> str:
        """Return the MIME sent to downstream parsers for this format."""

        return {
            MaterialFormat.PDF: "application/pdf",
            MaterialFormat.DOCX: (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            MaterialFormat.TXT: "text/plain",
            MaterialFormat.MARKDOWN: "text/markdown",
            MaterialFormat.MP3: "audio/mpeg",
            MaterialFormat.M4A: "audio/mp4",
            MaterialFormat.WAV: "audio/wav",
            MaterialFormat.MP4: "video/mp4",
            MaterialFormat.WEBM: "video/webm",
        }[self]

    @property
    def is_media(self) -> bool:
        return self in {
            MaterialFormat.MP3,
            MaterialFormat.M4A,
            MaterialFormat.WAV,
            MaterialFormat.MP4,
            MaterialFormat.WEBM,
        }

    @classmethod
    def from_media_type(cls, media_type: str | None) -> MaterialFormat:
        normalized = (media_type or "").split(";", 1)[0].strip().lower()
        mapping = {
            "application/pdf": cls.PDF,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": cls.DOCX,
            "text/plain": cls.TXT,
            "text/markdown": cls.MARKDOWN,
            "text/x-markdown": cls.MARKDOWN,
            "application/markdown": cls.MARKDOWN,
            "audio/mpeg": cls.MP3,
            "audio/mp3": cls.MP3,
            "audio/mp4": cls.M4A,
            "audio/x-m4a": cls.M4A,
            "audio/wav": cls.WAV,
            "audio/x-wav": cls.WAV,
            "video/mp4": cls.MP4,
            "video/webm": cls.WEBM,
        }
        try:
            return mapping[normalized]
        except KeyError as error:
            raise UnsupportedMaterialFormat(media_type) from error

    @classmethod
    def from_filename(cls, filename: str) -> MaterialFormat:
        suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        mapping = {
            "pdf": cls.PDF,
            "docx": cls.DOCX,
            "txt": cls.TXT,
            "md": cls.MARKDOWN,
            "markdown": cls.MARKDOWN,
            "mp3": cls.MP3,
            "m4a": cls.M4A,
            "wav": cls.WAV,
            "mp4": cls.MP4,
            "webm": cls.WEBM,
        }
        try:
            return mapping[suffix]
        except KeyError as error:
            raise UnsupportedMaterialFormat(filename) from error

    @classmethod
    def resolve(cls, *, filename: str, media_type: str | None) -> MaterialFormat:
        """Resolve a format while rejecting extension/MIME disagreements.

        A generic ``text/plain`` MIME is accepted for a Markdown filename
        because browsers commonly send that type; binary document MIME types
        must agree with the extension when one is available.
        """

        by_name = cls.from_filename(filename)
        normalized = (media_type or "").split(";", 1)[0].strip().lower()
        if normalized in {"", "application/octet-stream"}:
            return by_name
        by_media = cls.from_media_type(normalized)
        if by_name is MaterialFormat.MARKDOWN and by_media is MaterialFormat.TXT:
            return by_name
        if by_name is not by_media:
            raise UnsupportedMaterialFormat(f"{filename} ({media_type})")
        return by_name


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class MaterialLocator:
    """A parser-provided, stable location inside one parse version.

    A parser only fills coordinates it can prove.  For example, DOCX has no
    reliable page number without a rendered layout, so its locator uses a
    heading path and paragraph/character offsets instead of inventing pages.
    """

    page: int | None = None
    section_path: tuple[str, ...] = ()
    paragraph: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    block_index: int | None = None
    time_start_ms: int | None = None
    time_end_ms: int | None = None
    speaker: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "page",
            "paragraph",
            "line_start",
            "line_end",
            "char_start",
            "char_end",
            "block_index",
            "time_start_ms",
            "time_end_ms",
        ):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.page == 0:
            raise ValueError("page numbers are one-based")
        if (
            self.line_start is not None
            and self.line_end is not None
            and self.line_end < self.line_start
        ):
            raise ValueError("line_end must not precede line_start")
        if (
            self.char_start is not None
            and self.char_end is not None
            and self.char_end < self.char_start
        ):
            raise ValueError("char_end must not precede char_start")
        if (
            self.time_start_ms is not None
            and self.time_end_ms is not None
            and self.time_end_ms <= self.time_start_ms
        ):
            raise ValueError("time_end_ms must follow time_start_ms")
        if self.speaker is not None and not self.speaker.strip():
            raise ValueError("speaker must not be blank")

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "page": self.page,
            "section_path": list(self.section_path),
            "paragraph": self.paragraph,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "block_index": self.block_index,
        }
        # Omit absent media fields so existing document locators keep their
        # serialized shape and stable keys across the schema extension.
        if self.time_start_ms is not None:
            payload["time_start_ms"] = self.time_start_ms
        if self.time_end_ms is not None:
            payload["time_end_ms"] = self.time_end_ms
        if self.speaker is not None:
            payload["speaker"] = self.speaker
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> MaterialLocator:
        value = payload or {}
        return cls(
            page=_optional_int(value.get("page")),
            section_path=tuple(str(item) for item in value.get("section_path", ())),
            paragraph=_optional_int(value.get("paragraph")),
            line_start=_optional_int(value.get("line_start")),
            line_end=_optional_int(value.get("line_end")),
            char_start=_optional_int(value.get("char_start")),
            char_end=_optional_int(value.get("char_end")),
            block_index=_optional_int(value.get("block_index")),
            time_start_ms=_optional_int(value.get("time_start_ms")),
            time_end_ms=_optional_int(value.get("time_end_ms")),
            speaker=(str(value["speaker"]) if value.get("speaker") is not None else None),
        )

    def stable_key(self) -> str:
        return _canonical_json(self.as_dict())

    def display(self) -> str:
        pieces: list[str] = []
        if self.page is not None:
            pieces.append(f"第{self.page}页")
        if self.section_path:
            pieces.append(" / ".join(self.section_path))
        if self.paragraph is not None:
            pieces.append(f"第{self.paragraph}段")
        if self.line_start is not None:
            end = self.line_end if self.line_end is not None else self.line_start
            pieces.append(f"第{self.line_start}-{end}行")
        if self.char_start is not None:
            end = self.char_end if self.char_end is not None else self.char_start
            pieces.append(f"字符{self.char_start}-{end}")
        if self.time_start_ms is not None:
            end = self.time_end_ms if self.time_end_ms is not None else self.time_start_ms
            pieces.append(f"{_display_timecode(self.time_start_ms)}-{_display_timecode(end)}")
        if self.speaker is not None:
            pieces.append(self.speaker)
        return "，".join(pieces) or "原文位置未提供"


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _display_timecode(milliseconds: int) -> str:
    minutes, remainder = divmod(milliseconds, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"
    return f"{minutes:02d}:{seconds:02d}.{millis:03d}"


@dataclass(frozen=True, slots=True)
class MaterialBlock:
    segment_id: str
    parse_id: UUID
    material_id: UUID
    ordinal: int
    kind: str
    text: str
    content_hash: str
    locator: MaterialLocator

    @property
    def block_id(self) -> str:
        """Compatibility name for callers that call a segment a block."""

        return self.segment_id

    @classmethod
    def create(
        cls,
        *,
        parse_id: UUID,
        material_id: UUID,
        ordinal: int,
        kind: str,
        text: str,
        locator: MaterialLocator,
        segment_id: str | None = None,
    ) -> MaterialBlock:
        if ordinal < 0:
            raise ValueError("block ordinal must be non-negative")
        if not kind.strip():
            raise ValueError("block kind is required")
        if not text:
            raise ValueError("block text is required")
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        stable_input = f"{parse_id}:{ordinal}:{kind}:{content_hash}:{locator.stable_key()}"
        stable_id = segment_id or hashlib.sha256(stable_input.encode("utf-8")).hexdigest()
        return cls(
            segment_id=stable_id,
            parse_id=parse_id,
            material_id=material_id,
            ordinal=ordinal,
            kind=kind,
            text=text,
            content_hash=content_hash,
            locator=locator,
        )


@dataclass(frozen=True, slots=True)
class MaterialParseVersion:
    parse_id: UUID
    material_id: UUID
    version: int
    parser_name: str
    parser_version: str
    schema_version: str
    status: MaterialStatus
    full_text: str
    structured_document: dict[str, object]
    blocks: tuple[MaterialBlock, ...]
    content_hash: str
    created_at: datetime
    completed_at: datetime | None = None
    error_code: str | None = None

    @classmethod
    def create(
        cls,
        *,
        parse_id: UUID,
        material_id: UUID,
        version: int,
        parser_name: str,
        parser_version: str,
        schema_version: str,
        full_text: str,
        structured_document: Mapping[str, object] | None,
        blocks: tuple[MaterialBlock, ...],
        content_hash: str | None = None,
        now: datetime,
    ) -> MaterialParseVersion:
        if version < 1:
            raise ValueError("parse version starts at one")
        if not parser_name.strip() or not parser_version.strip() or not schema_version.strip():
            raise ValueError("parser identity is required")
        if not full_text.strip():
            raise MaterialParseError("parsed material contains no extractable text")
        _validate_blocks(blocks, parse_id=parse_id, material_id=material_id)
        digest = content_hash or hashlib.sha256(full_text.encode("utf-8")).hexdigest()
        return cls(
            parse_id=parse_id,
            material_id=material_id,
            version=version,
            parser_name=parser_name,
            parser_version=parser_version,
            schema_version=schema_version,
            status=MaterialStatus.READY,
            full_text=full_text,
            structured_document=dict(structured_document or {}),
            blocks=tuple(blocks),
            content_hash=digest,
            created_at=_utc(now),
            completed_at=_utc(now),
        )

    @classmethod
    def failed(
        cls,
        *,
        parse_id: UUID,
        material_id: UUID,
        version: int,
        parser_name: str,
        parser_version: str,
        schema_version: str,
        error_code: str,
        now: datetime,
    ) -> MaterialParseVersion:
        if not error_code.strip():
            raise ValueError("error_code is required")
        return cls(
            parse_id=parse_id,
            material_id=material_id,
            version=version,
            parser_name=parser_name,
            parser_version=parser_version,
            schema_version=schema_version,
            status=MaterialStatus.FAILED,
            full_text="",
            structured_document={},
            blocks=(),
            content_hash="",
            created_at=_utc(now),
            completed_at=_utc(now),
            error_code=error_code,
        )


@dataclass(frozen=True, slots=True)
class MaterialReparseRequest:
    """A durable request claim that binds one retry key to one parse."""

    material_id: UUID
    parse_id: UUID
    idempotency_key: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class MaterialIngestionJob:
    """Durable parse/index work claim for one immutable parse ID."""

    job_id: UUID
    material_id: UUID
    user_id: UUID
    task_id: UUID
    parse_id: UUID
    ingestion_status: MaterialIngestionStatus
    attempt_count: int
    max_attempts: int
    available_at: datetime
    lease_expires_at: datetime | None
    error_code: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


def _validate_blocks(
    blocks: tuple[MaterialBlock, ...], *, parse_id: UUID, material_id: UUID
) -> None:
    if not blocks:
        raise ValueError("successful parse requires at least one source block")
    ordinals = [block.ordinal for block in blocks]
    if ordinals != list(range(len(blocks))):
        raise ValueError("material block ordinals must be contiguous and zero-based")
    seen_ids: set[str] = set()
    for block in blocks:
        if block.parse_id != parse_id or block.material_id != material_id:
            raise ValueError("material block belongs to a different parse or material")
        if block.segment_id in seen_ids:
            raise ValueError("material block IDs must be unique")
        seen_ids.add(block.segment_id)


@dataclass(frozen=True, slots=True)
class ResearchMaterial:
    material_id: UUID
    user_id: UUID
    task_id: UUID
    idempotency_key: str
    original_filename: str
    display_name: str
    media_type: str
    material_format: MaterialFormat
    material_kind: MaterialKind
    size_bytes: int
    content_hash: str
    status: MaterialStatus
    current_parse_id: UUID | None
    current_parse_version: int | None
    processing_policy_version: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    last_error_code: str | None = None

    @classmethod
    def create(
        cls,
        *,
        material_id: UUID | None = None,
        user_id: UUID,
        task_id: UUID,
        idempotency_key: str,
        original_filename: str,
        media_type: str | None,
        content: bytes,
        material_kind: MaterialKind = MaterialKind.OTHER,
        display_name: str | None = None,
        processing_policy_version: str = "1",
        now: datetime,
    ) -> ResearchMaterial:
        if not idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        if not original_filename.strip():
            raise ValueError("original filename is required")
        if not content:
            raise ValueError("research material is empty")
        material_format = MaterialFormat.resolve(
            filename=original_filename,
            media_type=media_type,
        )
        # Browsers frequently omit a type for text files, send the generic
        # octet-stream type, or label Markdown as text/plain.  Store the
        # canonical MIME for the resolved extension so the parser and clients
        # observe one stable value regardless of those transport quirks.
        normalized_media_type = material_format.canonical_media_type
        timestamp = _utc(now)
        return cls(
            material_id=material_id or uuid4(),
            user_id=user_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
            original_filename=original_filename,
            display_name=display_name or original_filename,
            media_type=normalized_media_type,
            material_format=material_format,
            material_kind=MaterialKind(material_kind),
            size_bytes=len(content),
            content_hash=hashlib.sha256(content).hexdigest(),
            status=MaterialStatus.UPLOADED,
            current_parse_id=None,
            current_parse_version=None,
            processing_policy_version=processing_policy_version,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def begin_reparse(self, *, parse_id: UUID, now: datetime) -> ResearchMaterial:
        if self.status is MaterialStatus.DELETED:
            raise MaterialDeleted("deleted material cannot be reparsed")
        if self.status is MaterialStatus.PARSING:
            raise MaterialVersionConflict("another parse attempt is already active")
        if self.current_parse_id == parse_id:
            raise MaterialVersionConflict("parse ID is already current")
        return self._replace(
            status=MaterialStatus.PARSING,
            updated_at=_utc(now),
            last_error_code=None,
        )

    def record_parse_success(self, parsed: MaterialParseVersion) -> ResearchMaterial:
        if self.status is MaterialStatus.DELETED:
            raise MaterialDeleted("deleted material cannot accept a parse")
        if parsed.material_id != self.material_id:
            raise MaterialVersionConflict("parse belongs to a different material")
        current_version = self.current_parse_version or 0
        if parsed.version <= current_version:
            raise MaterialVersionConflict(
                f"parse version must exceed current version {current_version}, "
                f"got {parsed.version}"
            )
        if parsed.status is not MaterialStatus.READY:
            raise MaterialParseError("only a successful parse can become current")
        return self._replace(
            status=MaterialStatus.READY,
            current_parse_id=parsed.parse_id,
            current_parse_version=parsed.version,
            updated_at=parsed.completed_at or parsed.created_at,
            last_error_code=None,
        )

    def fail_parse(self, *, parse_id: UUID, error_code: str, now: datetime) -> ResearchMaterial:
        if self.status is MaterialStatus.DELETED:
            raise MaterialDeleted("deleted material cannot fail a parse")
        if not error_code.strip():
            raise ValueError("error_code is required")
        # A failed attempt does not erase a previously successful pointer.
        return self._replace(
            status=MaterialStatus.FAILED,
            updated_at=_utc(now),
            last_error_code=error_code,
        )

    def delete(self, *, now: datetime) -> ResearchMaterial:
        if self.status is MaterialStatus.DELETED:
            return self
        return self._replace(
            status=MaterialStatus.DELETED,
            current_parse_id=None,
            current_parse_version=None,
            deleted_at=_utc(now),
            updated_at=_utc(now),
            last_error_code=None,
        )

    def _replace(self, **changes: object) -> ResearchMaterial:
        values = {
            "material_id": self.material_id,
            "user_id": self.user_id,
            "task_id": self.task_id,
            "idempotency_key": self.idempotency_key,
            "original_filename": self.original_filename,
            "display_name": self.display_name,
            "media_type": self.media_type,
            "material_format": self.material_format,
            "material_kind": self.material_kind,
            "size_bytes": self.size_bytes,
            "content_hash": self.content_hash,
            "status": self.status,
            "current_parse_id": self.current_parse_id,
            "current_parse_version": self.current_parse_version,
            "processing_policy_version": self.processing_policy_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deleted_at": self.deleted_at,
            "last_error_code": self.last_error_code,
        }
        values.update(changes)
        return ResearchMaterial(**values)


@dataclass(frozen=True, slots=True)
class ResearchMaterialSearchHit:
    material_id: UUID
    parse_id: UUID
    segment_id: str
    title: str
    material_kind: MaterialKind
    material_format: MaterialFormat
    excerpt: str
    locator: MaterialLocator
    score: float


@dataclass(frozen=True, slots=True)
class ResearchMaterialSearchResult:
    query: str
    total: int
    items: tuple[ResearchMaterialSearchHit, ...]
