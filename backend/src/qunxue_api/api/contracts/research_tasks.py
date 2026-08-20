from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from qunxue_api.modules.research_intake import (
    EntryType,
    ResearchTask,
    ResearchTaskAction,
    ResearchTaskStatus,
)


class CreateResearchTaskRequest(BaseModel):
    entry_type: EntryType = EntryType.DIRECT_INPUT
    seed_theory_id: str | None = Field(default=None, min_length=1, max_length=128)


class ResearchTraceActor(StrEnum):
    USER = "user"
    SYSTEM = "system"
    MODEL = "model"
    MOCK = "mock"


class ResearchTaskLifecycleStatus(StrEnum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class ResearchTaskStage(StrEnum):
    PHENOMENON_INPUT = "phenomenon_input"
    PHENOMENON_CONFIRMATION = "phenomenon_confirmation"
    THEORY_MATCHING = "theory_matching"
    THEORY_DECISION = "theory_decision"
    FRAMEWORK_DRAFTING = "framework_drafting"
    FRAMEWORK_REVIEW = "framework_review"
    COMPLETED = "completed"


class ResearchTaskNavigationAction(StrEnum):
    SUBMIT_PHENOMENON = "submit_phenomenon"
    CONFIRM_PHENOMENON = "confirm_phenomenon"
    START_MATCHING = "start_matching"
    REVIEW_THEORY_CANDIDATES = "review_theory_candidates"
    CONFIRM_THEORY_PLAN = "confirm_theory_plan"
    CREATE_FRAMEWORK = "create_framework"
    REVIEW_FRAMEWORK = "review_framework"
    CONFIRM_FRAMEWORK = "confirm_framework"
    EXPORT = "export"


class ResearchTaskResponse(BaseModel):
    task_id: UUID
    entry_type: EntryType
    status: ResearchTaskStatus
    version: int
    allowed_actions: list[ResearchTaskAction]
    seed_theory_id: str | None
    seed_theory_name: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, task: ResearchTask) -> "ResearchTaskResponse":
        return cls(
            task_id=task.task_id,
            entry_type=task.entry_type,
            status=task.status,
            version=task.version,
            allowed_actions=list(task.allowed_actions),
            seed_theory_id=task.seed_theory_id,
            seed_theory_name=task.seed_theory_name,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )


class ResearchTaskPhenomenonSummaryResponse(BaseModel):
    phenomenon_query_id: UUID
    version: int
    phenomenon: str
    research_intent: str | None


class ResearchTaskNavigationResponse(BaseModel):
    """Task-scoped aggregate used by `/my` and task-only deep links."""

    task_id: UUID
    entry_type: EntryType
    status: ResearchTaskLifecycleStatus
    current_stage: ResearchTaskStage
    version: int
    allowed_actions: list[ResearchTaskNavigationAction]
    seed_theory_id: str | None
    seed_theory_name: str | None
    phenomenon_summary: ResearchTaskPhenomenonSummaryResponse | None
    adopted_theory_count: int
    current_phenomenon_candidate_id: UUID | None
    current_material_intake_run_id: UUID | None
    current_match_run_id: UUID | None
    current_theory_plan_id: UUID | None
    current_framework_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ResearchTaskPageResponse(BaseModel):
    items: list[ResearchTaskNavigationResponse]
    next_cursor: str | None


class DeleteResearchTaskResponse(BaseModel):
    task_id: UUID
    version: int
    allowed_actions: list[ResearchTaskAction]
    deleted: Literal[True]


class ResearchTraceEventResponse(BaseModel):
    event_id: UUID
    sequence: int
    event_type: str
    actor: ResearchTraceActor
    object_version: int
    occurred_at: datetime
    trace_id: UUID


class ResearchTraceResponse(BaseModel):
    task_id: UUID
    version: int
    allowed_actions: list[ResearchTaskAction]
    events: list[ResearchTraceEventResponse]
    next_cursor: str | None
    contract_version: str


class MarkdownExportResponse(BaseModel):
    task_id: UUID
    version: int
    allowed_actions: list[ResearchTaskAction]
    filename: str
    media_type: Literal["text/markdown"]
    markdown: str
    contract_version: str
