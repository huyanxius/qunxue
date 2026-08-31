"""Stable professional archive concepts layered on durable material identities."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

type CaseAttributeValue = str | int | float | bool | None


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _required(value: str, field: str) -> str:
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized:
        raise ValueError(f"{field} is required")
    return normalized


def _unique_uuid(values: tuple[UUID, ...]) -> tuple[UUID, ...]:
    return tuple(dict.fromkeys(values))


def _unique_labels(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            label
            for value in values
            if (label := unicodedata.normalize("NFC", value).strip())
        )
    )


def normalize_doi(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if normalized.startswith(prefix):
            normalized = normalized.removeprefix(prefix).strip()
            break
    if not normalized:
        return None
    if not normalized.startswith("10.") or "/" not in normalized:
        raise ValueError("doi must be a normalized DOI identifier")
    return normalized


class ResearchRole(StrEnum):
    EMPIRICAL_MATERIAL = "empirical_material"
    LITERATURE = "literature"
    RESEARCH_PROCESS = "research_process"
    PRIOR_DRAFT = "prior_draft"
    DATASET = "dataset"
    RESULT = "result"
    OTHER = "other"


class ResearchStage(StrEnum):
    INTAKE = "intake"
    COLLECTION = "collection"
    ANALYSIS = "analysis"
    WRITING = "writing"
    ARCHIVED = "archived"


class SensitivityLevel(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"
    HIGHLY_SENSITIVE = "highly_sensitive"


class ConsentScope(StrEnum):
    PUBLIC_USE = "public_use"
    PROJECT_ONLY = "project_only"
    TEAM_ONLY = "team_only"
    MANUAL_REVIEW_ONLY = "manual_review_only"
    WITHDRAWN = "withdrawn"


class DeidentificationStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    PARTIAL = "partial"
    COMPLETE = "complete"


class ModelProcessingScope(StrEnum):
    NOT_ASSESSED = "not_assessed"
    MANUAL_ONLY = "manual_only"
    LOCAL_ONLY = "local_only"
    EXTERNAL_ALLOWED = "external_allowed"


class MaterialRelationType(StrEnum):
    DERIVED_FROM = "derived_from"
    SUPPLEMENTS = "supplements"
    TRANSLATION_OF = "translation_of"
    VERSION_OF = "version_of"
    DESCRIBES = "describes"
    RELATED = "related"


class LiteratureExchangeFormat(StrEnum):
    BIBTEX = "bibtex"
    RIS = "ris"
    CSL_JSON = "csl_json"


@dataclass(frozen=True, slots=True)
class DoiMetadataCandidate:
    doi: str
    item_type: str
    title: str
    csl_data: dict[str, object]
    source: str
    verified_at: datetime


@dataclass(frozen=True, slots=True)
class MaterialArchiveProfile:
    material_id: UUID
    user_id: UUID
    task_id: UUID
    research_role: ResearchRole
    specific_type: str
    stage: ResearchStage
    batch_id: UUID | None
    tags: tuple[str, ...]
    sensitivity: SensitivityLevel
    consent_scope: ConsentScope
    deidentification_status: DeidentificationStatus
    model_processing_scope: ModelProcessingScope
    created_at: datetime
    updated_at: datetime
    collection_ids: tuple[UUID, ...] = ()

    @classmethod
    def create(
        cls,
        *,
        material_id: UUID,
        user_id: UUID,
        task_id: UUID,
        research_role: ResearchRole = ResearchRole.OTHER,
        specific_type: str = "other",
        stage: ResearchStage = ResearchStage.INTAKE,
        batch_id: UUID | None = None,
        tags: tuple[str, ...] = (),
        sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL,
        consent_scope: ConsentScope = ConsentScope.PROJECT_ONLY,
        deidentification_status: DeidentificationStatus = DeidentificationStatus.PENDING,
        model_processing_scope: ModelProcessingScope = ModelProcessingScope.NOT_ASSESSED,
        collection_ids: tuple[UUID, ...] = (),
        now: datetime,
    ) -> MaterialArchiveProfile:
        timestamp = _utc(now)
        return cls(
            material_id=material_id,
            user_id=user_id,
            task_id=task_id,
            research_role=ResearchRole(research_role),
            specific_type=_required(specific_type, "specific_type"),
            stage=ResearchStage(stage),
            batch_id=batch_id,
            tags=_unique_labels(tags),
            sensitivity=SensitivityLevel(sensitivity),
            consent_scope=ConsentScope(consent_scope),
            deidentification_status=DeidentificationStatus(deidentification_status),
            model_processing_scope=ModelProcessingScope(model_processing_scope),
            created_at=timestamp,
            updated_at=timestamp,
            collection_ids=_unique_uuid(collection_ids),
        )

    @property
    def allows_manual_reading(self) -> bool:
        return self.consent_scope is not ConsentScope.WITHDRAWN

    @property
    def allows_external_model_processing(self) -> bool:
        return (
            self.allows_manual_reading
            and self.model_processing_scope is ModelProcessingScope.EXTERNAL_ALLOWED
            and self.deidentification_status is not DeidentificationStatus.PENDING
        )


@dataclass(frozen=True, slots=True)
class MaterialBatch:
    batch_id: UUID
    user_id: UUID
    task_id: UUID
    name: str
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        task_id: UUID,
        name: str,
        now: datetime,
        batch_id: UUID | None = None,
    ) -> MaterialBatch:
        return cls(batch_id or uuid4(), user_id, task_id, _required(name, "name"), _utc(now))


@dataclass(frozen=True, slots=True)
class MaterialCollection:
    collection_id: UUID
    user_id: UUID
    task_id: UUID
    name: str
    description: str | None
    parent_collection_id: UUID | None
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        task_id: UUID,
        name: str,
        now: datetime,
        collection_id: UUID | None = None,
        description: str | None = None,
        parent_collection_id: UUID | None = None,
    ) -> MaterialCollection:
        return cls(
            collection_id or uuid4(),
            user_id,
            task_id,
            _required(name, "name"),
            description.strip() or None if description is not None else None,
            parent_collection_id,
            _utc(now),
        )


@dataclass(frozen=True, slots=True)
class ImportedLiteratureRecord:
    item_type: str
    title: str
    doi: str | None
    csl_data: dict[str, object]


@dataclass(frozen=True, slots=True)
class LiteratureEntry:
    literature_id: UUID
    user_id: UUID
    task_id: UUID
    item_type: str
    title: str
    doi: str | None
    csl_data: dict[str, object]
    attachment_material_ids: tuple[UUID, ...]
    collection_ids: tuple[UUID, ...]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        task_id: UUID,
        item_type: str,
        title: str,
        csl_data: dict[str, object],
        now: datetime,
        literature_id: UUID | None = None,
        doi: str | None = None,
        attachment_material_ids: tuple[UUID, ...] = (),
        collection_ids: tuple[UUID, ...] = (),
    ) -> LiteratureEntry:
        timestamp = _utc(now)
        normalized_doi = normalize_doi(doi or _optional_text(csl_data.get("DOI")))
        metadata = dict(csl_data)
        metadata.setdefault("type", _required(item_type, "item_type"))
        metadata.setdefault("title", _required(title, "title"))
        if normalized_doi is not None:
            metadata["DOI"] = normalized_doi
        return cls(
            literature_id=literature_id or uuid4(),
            user_id=user_id,
            task_id=task_id,
            item_type=_required(item_type, "item_type"),
            title=_required(title, "title"),
            doi=normalized_doi,
            csl_data=metadata,
            attachment_material_ids=_unique_uuid(attachment_material_ids),
            collection_ids=_unique_uuid(collection_ids),
            created_at=timestamp,
            updated_at=timestamp,
        )

    def duplicate_reasons(self, other: LiteratureEntry) -> tuple[str, ...]:
        reasons: list[str] = []
        if self.doi is not None and self.doi == other.doi:
            reasons.append("same_doi")
        if _title_key(self.title) == _title_key(other.title):
            self_year = _issued_year(self.csl_data)
            other_year = _issued_year(other.csl_data)
            if self_year is None or other_year is None or self_year == other_year:
                reasons.append("same_title_year")
        return tuple(reasons)


@dataclass(frozen=True, slots=True)
class ResearchCase:
    case_id: UUID
    user_id: UUID
    task_id: UUID
    name: str
    description: str | None
    attributes: dict[str, CaseAttributeValue]
    material_ids: tuple[UUID, ...]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        task_id: UUID,
        name: str,
        attributes: dict[str, CaseAttributeValue],
        now: datetime,
        case_id: UUID | None = None,
        description: str | None = None,
        material_ids: tuple[UUID, ...] = (),
    ) -> ResearchCase:
        normalized_attributes: dict[str, CaseAttributeValue] = {}
        for key, value in attributes.items():
            if not isinstance(value, (str, int, float, bool, type(None))):
                raise ValueError("case attributes must be scalar values")
            normalized_attributes[_required(key, "attribute name")] = value
        timestamp = _utc(now)
        return cls(
            case_id or uuid4(),
            user_id,
            task_id,
            _required(name, "name"),
            description.strip() or None if description is not None else None,
            normalized_attributes,
            _unique_uuid(material_ids),
            timestamp,
            timestamp,
        )


@dataclass(frozen=True, slots=True)
class MaterialRelation:
    relation_id: UUID
    user_id: UUID
    task_id: UUID
    source_material_id: UUID
    target_material_id: UUID
    relation_type: MaterialRelationType
    note: str | None
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        task_id: UUID,
        source_material_id: UUID,
        target_material_id: UUID,
        relation_type: MaterialRelationType,
        note: str | None,
        now: datetime,
        relation_id: UUID | None = None,
    ) -> MaterialRelation:
        if source_material_id == target_material_id:
            raise ValueError("relation requires different materials")
        return cls(
            relation_id or uuid4(),
            user_id,
            task_id,
            source_material_id,
            target_material_id,
            MaterialRelationType(relation_type),
            note.strip() or None if note is not None else None,
            _utc(now),
        )


@dataclass(frozen=True, slots=True)
class ProfessionalMaterialArchive:
    profiles: tuple[MaterialArchiveProfile, ...] = ()
    batches: tuple[MaterialBatch, ...] = ()
    collections: tuple[MaterialCollection, ...] = ()
    literature: tuple[LiteratureEntry, ...] = ()
    cases: tuple[ResearchCase, ...] = ()
    relations: tuple[MaterialRelation, ...] = ()


@dataclass(frozen=True, slots=True)
class LiteratureDuplicateHint:
    literature_id: UUID
    candidate_id: UUID
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MaterialArchiveInventory:
    catalog_pending_material_ids: tuple[UUID, ...] = ()
    parse_failed_material_ids: tuple[UUID, ...] = ()
    suspected_duplicate_literature_ids: tuple[UUID, ...] = ()
    pending_deidentification_material_ids: tuple[UUID, ...] = ()
    restricted_material_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class ProfessionalMaterialArchiveView:
    archive: ProfessionalMaterialArchive
    inventory: MaterialArchiveInventory
    duplicate_hints: tuple[LiteratureDuplicateHint, ...] = ()


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _title_key(value: str) -> str:
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", unicodedata.normalize("NFKC", value).lower())


def _issued_year(metadata: dict[str, object]) -> int | None:
    issued = metadata.get("issued")
    if not isinstance(issued, dict):
        return None
    parts = issued.get("date-parts")
    if not isinstance(parts, list) or not parts or not isinstance(parts[0], list) or not parts[0]:
        return None
    year = parts[0][0]
    return int(year) if isinstance(year, (int, str)) and str(year).isdigit() else None
