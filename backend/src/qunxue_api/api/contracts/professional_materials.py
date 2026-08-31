"""HTTP contracts for the professional research material archive."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from qunxue_api.modules.research_materials import (
    ConsentScope,
    DeidentificationStatus,
    DoiMetadataCandidate,
    LiteratureEntry,
    LiteratureExchangeFormat,
    MaterialArchiveProfile,
    MaterialBatch,
    MaterialCollection,
    MaterialRelation,
    MaterialRelationType,
    ModelProcessingScope,
    ProfessionalMaterialArchiveView,
    ResearchCase,
    ResearchRole,
    ResearchStage,
    SensitivityLevel,
)


class MaterialArchiveProfileResponse(BaseModel):
    material_id: UUID
    research_role: ResearchRole
    specific_type: str
    stage: ResearchStage
    batch_id: UUID | None
    tags: list[str]
    collection_ids: list[UUID]
    sensitivity: SensitivityLevel
    consent_scope: ConsentScope
    deidentification_status: DeidentificationStatus
    model_processing_scope: ModelProcessingScope
    allows_manual_reading: bool
    allows_external_model_processing: bool
    updated_at: datetime

    @classmethod
    def from_domain(cls, value: MaterialArchiveProfile) -> "MaterialArchiveProfileResponse":
        return cls(
            material_id=value.material_id,
            research_role=value.research_role,
            specific_type=value.specific_type,
            stage=value.stage,
            batch_id=value.batch_id,
            tags=list(value.tags),
            collection_ids=list(value.collection_ids),
            sensitivity=value.sensitivity,
            consent_scope=value.consent_scope,
            deidentification_status=value.deidentification_status,
            model_processing_scope=value.model_processing_scope,
            allows_manual_reading=value.allows_manual_reading,
            allows_external_model_processing=value.allows_external_model_processing,
            updated_at=value.updated_at,
        )


class UpdateMaterialArchiveProfileRequest(BaseModel):
    research_role: ResearchRole
    specific_type: str = Field(min_length=1, max_length=96)
    stage: ResearchStage
    batch_id: UUID | None = None
    tags: list[str] = Field(default_factory=list, max_length=100)
    collection_ids: list[UUID] = Field(default_factory=list, max_length=100)
    sensitivity: SensitivityLevel
    consent_scope: ConsentScope
    deidentification_status: DeidentificationStatus
    model_processing_scope: ModelProcessingScope


class DoiMetadataCandidateResponse(BaseModel):
    doi: str
    item_type: str
    title: str
    csl_data: dict[str, object]
    source: str
    verified_at: datetime

    @classmethod
    def from_domain(cls, value: DoiMetadataCandidate) -> "DoiMetadataCandidateResponse":
        return cls(**{
            "doi": value.doi,
            "item_type": value.item_type,
            "title": value.title,
            "csl_data": value.csl_data,
            "source": value.source,
            "verified_at": value.verified_at,
        })


class CreateMaterialBatchRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class MaterialBatchResponse(BaseModel):
    batch_id: UUID
    name: str
    created_at: datetime

    @classmethod
    def from_domain(cls, value: MaterialBatch) -> "MaterialBatchResponse":
        return cls(batch_id=value.batch_id, name=value.name, created_at=value.created_at)


class CreateMaterialCollectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    parent_collection_id: UUID | None = None


class MaterialCollectionResponse(BaseModel):
    collection_id: UUID
    name: str
    description: str | None
    parent_collection_id: UUID | None
    created_at: datetime

    @classmethod
    def from_domain(cls, value: MaterialCollection) -> "MaterialCollectionResponse":
        return cls(
            collection_id=value.collection_id,
            name=value.name,
            description=value.description,
            parent_collection_id=value.parent_collection_id,
            created_at=value.created_at,
        )


class CreateLiteratureEntryRequest(BaseModel):
    item_type: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=1000)
    doi: str | None = Field(default=None, max_length=300)
    csl_data: dict[str, object] = Field(default_factory=dict)
    attachment_material_ids: list[UUID] = Field(default_factory=list, max_length=100)
    collection_ids: list[UUID] = Field(default_factory=list, max_length=100)


class LiteratureEntryResponse(BaseModel):
    literature_id: UUID
    item_type: str
    title: str
    doi: str | None
    csl_data: dict[str, object]
    attachment_material_ids: list[UUID]
    collection_ids: list[UUID]
    created_at: datetime

    @classmethod
    def from_domain(cls, value: LiteratureEntry) -> "LiteratureEntryResponse":
        return cls(
            literature_id=value.literature_id,
            item_type=value.item_type,
            title=value.title,
            doi=value.doi,
            csl_data=value.csl_data,
            attachment_material_ids=list(value.attachment_material_ids),
            collection_ids=list(value.collection_ids),
            created_at=value.created_at,
        )


class CreateResearchCaseRequest(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=4000)
    attributes: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    material_ids: list[UUID] = Field(default_factory=list, max_length=100)


class ResearchCaseResponse(BaseModel):
    case_id: UUID
    name: str
    description: str | None
    attributes: dict[str, str | int | float | bool | None]
    material_ids: list[UUID]
    created_at: datetime

    @classmethod
    def from_domain(cls, value: ResearchCase) -> "ResearchCaseResponse":
        return cls(
            case_id=value.case_id,
            name=value.name,
            description=value.description,
            attributes=value.attributes,
            material_ids=list(value.material_ids),
            created_at=value.created_at,
        )


class CreateMaterialRelationRequest(BaseModel):
    source_material_id: UUID
    target_material_id: UUID
    relation_type: MaterialRelationType
    note: str | None = Field(default=None, max_length=4000)


class MaterialRelationResponse(BaseModel):
    relation_id: UUID
    source_material_id: UUID
    target_material_id: UUID
    relation_type: MaterialRelationType
    note: str | None
    created_at: datetime

    @classmethod
    def from_domain(cls, value: MaterialRelation) -> "MaterialRelationResponse":
        return cls(
            relation_id=value.relation_id,
            source_material_id=value.source_material_id,
            target_material_id=value.target_material_id,
            relation_type=value.relation_type,
            note=value.note,
            created_at=value.created_at,
        )


class MaterialArchiveInventoryResponse(BaseModel):
    catalog_pending_material_ids: list[UUID]
    parse_failed_material_ids: list[UUID]
    suspected_duplicate_literature_ids: list[UUID]
    pending_deidentification_material_ids: list[UUID]
    restricted_material_ids: list[UUID]


class LiteratureDuplicateHintResponse(BaseModel):
    literature_id: UUID
    candidate_id: UUID
    reasons: list[str]


class ProfessionalMaterialArchiveResponse(BaseModel):
    task_id: UUID
    profiles: list[MaterialArchiveProfileResponse]
    batches: list[MaterialBatchResponse]
    collections: list[MaterialCollectionResponse]
    literature: list[LiteratureEntryResponse]
    cases: list[ResearchCaseResponse]
    relations: list[MaterialRelationResponse]
    inventory: MaterialArchiveInventoryResponse
    duplicate_hints: list[LiteratureDuplicateHintResponse]

    @classmethod
    def from_domain(
        cls, task_id: UUID, value: ProfessionalMaterialArchiveView
    ) -> "ProfessionalMaterialArchiveResponse":
        archive = value.archive
        return cls(
            task_id=task_id,
            profiles=[
                MaterialArchiveProfileResponse.from_domain(item) for item in archive.profiles
            ],
            batches=[MaterialBatchResponse.from_domain(item) for item in archive.batches],
            collections=[
                MaterialCollectionResponse.from_domain(item) for item in archive.collections
            ],
            literature=[LiteratureEntryResponse.from_domain(item) for item in archive.literature],
            cases=[ResearchCaseResponse.from_domain(item) for item in archive.cases],
            relations=[MaterialRelationResponse.from_domain(item) for item in archive.relations],
            inventory=MaterialArchiveInventoryResponse(
                **{
                    key: list(getattr(value.inventory, key))
                    for key in MaterialArchiveInventoryResponse.model_fields
                }
            ),
            duplicate_hints=[
                LiteratureDuplicateHintResponse(
                    literature_id=item.literature_id,
                    candidate_id=item.candidate_id,
                    reasons=list(item.reasons),
                )
                for item in value.duplicate_hints
            ],
        )


class BatchUploadItemResponse(BaseModel):
    filename: str
    status: str
    material_id: UUID | None = None
    error_code: str | None = None
    message: str | None = None


class BatchUploadResponse(BaseModel):
    batch_id: UUID
    items: list[BatchUploadItemResponse]


__all__ = ["LiteratureExchangeFormat"]
