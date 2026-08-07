from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from qunxue_api.api.contracts.common import ModelMetadata
from qunxue_api.modules.research_intake import (
    EntryInputType,
    PhenomenonEvidenceVerificationStatus,
)


class EntryInputAction(StrEnum):
    EXTRACT_PHENOMENON_CANDIDATES = "extract_phenomenon_candidates"


class PhenomenonCandidateStatus(StrEnum):
    PROPOSED = "proposed"
    EDITED = "edited"
    CONFIRMED = "confirmed"
    SUPERSEDED = "superseded"


class PhenomenonCandidateAction(StrEnum):
    UPDATE = "update"
    CONFIRM = "confirm"


class PhenomenonSnapshotAction(StrEnum):
    START_MATCHING = "start_matching"


class DirectInputRequest(BaseModel):
    phenomenon: str = Field(min_length=1, max_length=10_000)
    research_intent: str | None = Field(default=None, max_length=4_000)
    context: str | None = Field(default=None, max_length=10_000)


class DeidentifiedMaterialInput(BaseModel):
    material_ref_id: str = Field(min_length=1, max_length=128)
    media_type: Literal["text/plain", "text/markdown"]
    deidentified_text: str = Field(min_length=1, max_length=100_000)
    source_description: str | None = Field(default=None, max_length=1_000)


class MaterialInputRequest(BaseModel):
    materials: list[DeidentifiedMaterialInput] = Field(min_length=1, max_length=20)
    research_intent: str | None = Field(default=None, max_length=4_000)
    context: str | None = Field(default=None, max_length=10_000)
    deidentification_acknowledged: Literal[True]
    processing_authority_acknowledged: Literal[True]
    retention_policy_acknowledged: Literal["no_raw_material_persistence"]


class EntryInputResponse(BaseModel):
    input_id: UUID
    task_id: UUID
    entry_type: EntryInputType
    version: int
    allowed_actions: list[EntryInputAction]
    source_ref_ids: list[str]
    accepted_at: datetime


class ExtractPhenomenonCandidatesRequest(BaseModel):
    expected_task_version: int = Field(ge=1)
    requested_count: int = Field(default=4, ge=1, le=8)


class PhenomenonEvidenceReferenceResponse(BaseModel):
    evidence_ref_id: str
    excerpt: str
    source_ref_id: str
    source_description: str | None
    locator: str | None
    verification_status: PhenomenonEvidenceVerificationStatus
    use_boundary: str


class PhenomenonCandidateResponse(BaseModel):
    candidate_id: UUID
    task_id: UUID
    version: int
    status: PhenomenonCandidateStatus
    allowed_actions: list[PhenomenonCandidateAction]
    phenomenon: str
    research_intent: str | None
    context: str | None
    source_ref_ids: list[str]
    evidence_refs: list[PhenomenonEvidenceReferenceResponse]
    model: ModelMetadata


class PhenomenonCandidatePageResponse(BaseModel):
    task_id: UUID
    version: int
    allowed_actions: list[PhenomenonCandidateAction]
    candidates: list[PhenomenonCandidateResponse]
    stable_order: list[UUID]
    next_cursor: str | None
    model: ModelMetadata


class UpdatePhenomenonCandidateRequest(BaseModel):
    expected_version: int = Field(ge=1)
    phenomenon: str = Field(min_length=1, max_length=10_000)
    research_intent: str | None = Field(default=None, max_length=4_000)
    context: str | None = Field(default=None, max_length=10_000)


class ConfirmPhenomenonCandidateRequest(BaseModel):
    expected_version: int = Field(ge=1)


class PhenomenonSnapshotResponse(BaseModel):
    phenomenon_query_id: UUID
    task_id: UUID
    version: int
    status: Literal["confirmed"]
    allowed_actions: list[PhenomenonSnapshotAction]
    phenomenon: str
    research_intent: str | None
    context: str | None
    content_hash: str = Field(min_length=64, max_length=64)
    source_ref_ids: list[str]
    evidence_refs: list[PhenomenonEvidenceReferenceResponse]
    confirmed_at: datetime


class PhenomenonSnapshotPageResponse(BaseModel):
    task_id: UUID
    version: int
    allowed_actions: list[PhenomenonSnapshotAction]
    snapshots: list[PhenomenonSnapshotResponse]
    next_cursor: str | None


class PhenomenonExampleResponse(BaseModel):
    example_id: str
    title: str
    phenomenon: str
    research_intent: str | None
    context: str | None
    source_type: Literal["built_in_example"] = "built_in_example"


class PhenomenonExamplePageResponse(BaseModel):
    items: list[PhenomenonExampleResponse]
