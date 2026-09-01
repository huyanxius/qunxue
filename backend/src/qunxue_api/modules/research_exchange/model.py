"""REFI-QDA exchange values without persistence or transport dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID


class QdpxSourceKind(StrEnum):
    TEXT = "text"
    PDF = "pdf"
    PICTURE = "picture"
    AUDIO = "audio"
    VIDEO = "video"


class ExchangeLossSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


@dataclass(frozen=True, slots=True)
class ExchangeLoss:
    object_type: str
    object_id: str
    field: str
    reason: str
    disposition: str
    severity: ExchangeLossSeverity = ExchangeLossSeverity.WARNING


@dataclass(frozen=True, slots=True)
class ExchangeIdentity:
    object_type: str
    native_id: str
    exchange_guid: UUID


@dataclass(frozen=True, slots=True)
class ExchangeReport:
    format: str = "REFI-QDA Project"
    specification_version: str = "1.0"
    validation_scope: str = "official-xsd"
    losses: tuple[ExchangeLoss, ...] = ()
    identities: tuple[ExchangeIdentity, ...] = ()


@dataclass(frozen=True, slots=True)
class QdpxUser:
    user_id: UUID
    name: str
    external_id: str | None = None


@dataclass(frozen=True, slots=True)
class QdpxCode:
    code_id: UUID
    name: str
    description: str | None = None
    parent_code_id: UUID | None = None
    color: str | None = None
    memo_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class QdpxCoding:
    coding_id: UUID
    code_id: UUID
    memo_ids: tuple[UUID, ...] = ()
    user_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class QdpxSelection:
    selection_id: UUID
    start_position: int
    end_position: int
    codings: tuple[QdpxCoding, ...] = ()
    memo_ids: tuple[UUID, ...] = ()
    name: str | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        if self.start_position < 0 or self.end_position <= self.start_position:
            raise ValueError("selection must be a non-empty half-open interval")


@dataclass(frozen=True, slots=True)
class QdpxSource:
    source_id: UUID
    name: str
    kind: QdpxSourceKind
    plain_text: str | None = None
    path: str | None = None
    description: str | None = None
    selections: tuple[QdpxSelection, ...] = ()
    memo_ids: tuple[UUID, ...] = ()
    user_id: UUID | None = None

    def __post_init__(self) -> None:
        kind = QdpxSourceKind(self.kind)
        object.__setattr__(self, "kind", kind)
        if kind is QdpxSourceKind.TEXT and not self.plain_text:
            raise ValueError("text source requires plain text content")
        if kind is not QdpxSourceKind.TEXT and not self.path:
            raise ValueError("binary source requires an archive path")
        if self.plain_text is not None:
            for selection in self.selections:
                if selection.end_position > len(self.plain_text):
                    raise ValueError("selection exceeds source text")


QdpxScalar = str | int | float | bool | None


@dataclass(frozen=True, slots=True)
class QdpxMemo:
    memo_id: UUID
    name: str
    content: str
    target_ids: tuple[UUID, ...] = ()
    user_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class QdpxCase:
    case_id: UUID
    name: str
    description: str | None = None
    attributes: dict[str, QdpxScalar] = field(default_factory=dict)
    source_ids: tuple[UUID, ...] = ()
    selection_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class QdpxSet:
    set_id: UUID
    name: str
    description: str | None = None
    member_code_ids: tuple[UUID, ...] = ()
    member_source_ids: tuple[UUID, ...] = ()
    member_memo_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class QdpxLink:
    link_id: UUID
    name: str
    origin_id: UUID
    target_id: UUID
    direction: str = "Associative"
    memo_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class QdpxProject:
    # REFI-QDA Project 1.0 has no project GUID. Native project identity lives
    # in the recovery manifest and is reported as non-exchangeable.
    project_id: UUID | None
    name: str
    origin: str
    description: str | None = None
    users: tuple[QdpxUser, ...] = ()
    codes: tuple[QdpxCode, ...] = ()
    sources: tuple[QdpxSource, ...] = ()
    memos: tuple[QdpxMemo, ...] = ()
    cases: tuple[QdpxCase, ...] = ()
    sets: tuple[QdpxSet, ...] = ()
    links: tuple[QdpxLink, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.origin.strip():
            raise ValueError("project name and origin are required")
