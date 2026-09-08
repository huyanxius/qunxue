from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from qunxue_api.api.contracts.research_materials import ResearchMaterialLocatorResponse

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


class CreateSharedKnowledgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name
    description: Description = ""


class UpdateSharedKnowledgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name | None = None
    description: Description | None = None
    sharing_enabled: bool | None = None


class JoinSharedKnowledgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    share_token: str = Field(min_length=20, max_length=128)


class CourseProfileResponse(BaseModel):
    role: Literal["teacher", "student"] | None = None
    guide_dismissed: bool = False


class UpdateCourseProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["teacher", "student"]
    guide_dismissed: bool = False


class CourseTopicResponse(BaseModel):
    title: str
    summary: str
    segment_ids: list[str]


class CourseRelationResponse(BaseModel):
    source: str
    target: str
    label: str
    segment_ids: list[str]


class CourseKnowledgeResponse(BaseModel):
    summary: str
    topics: list[CourseTopicResponse]
    relations: list[CourseRelationResponse] = Field(default_factory=list)


class SharedDocumentResponse(BaseModel):
    id: UUID
    filename: str
    media_type: str
    size_bytes: int
    parse_id: UUID
    status: Literal["processing", "ready", "failed"]
    knowledge_status: Literal["queued", "running", "ready", "failed"] = "queued"
    knowledge: CourseKnowledgeResponse | None = None
    knowledge_error: str | None = None
    index_status: Literal["queued", "running", "ready", "failed"] = "queued"
    index_error: str | None = None
    error_message: str | None = None
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime


class SharedKnowledgeResponse(BaseModel):
    id: UUID
    name: str | None = None
    description: str | None = None
    viewer_access: Literal["owner", "reader", "unavailable"]
    sharing_enabled: bool = False
    share_token: str | None = Field(default=None, exclude_if=lambda value: value is None)
    ready_document_count: int = 0
    documents: list[SharedDocumentResponse] = Field(default_factory=list)


class SharedKnowledgeListResponse(BaseModel):
    items: list[SharedKnowledgeResponse]


class SharedKnowledgeJoinResponse(BaseModel):
    knowledge_base_id: UUID
    name: str
    added: bool


class SharedSourceSegmentResponse(BaseModel):
    segment_id: str
    parse_id: str
    ordinal: int
    kind: str
    text: str
    locator: ResearchMaterialLocatorResponse


class SharedDocumentSourceResponse(BaseModel):
    document: SharedDocumentResponse
    knowledge_base_id: UUID
    knowledge_base_name: str
    segments: list[SharedSourceSegmentResponse]
