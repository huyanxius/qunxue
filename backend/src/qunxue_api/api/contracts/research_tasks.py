from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from qunxue_api.modules.research_intake import (
    EntryType,
    ResearchTask,
    ResearchTaskAction,
    ResearchTaskStatus,
)


class CreateResearchTaskRequest(BaseModel):
    entry_type: EntryType = EntryType.DIRECT_INPUT


class ResearchTraceActor(StrEnum):
    USER = "user"
    SYSTEM = "system"
    MODEL = "model"
    MOCK = "mock"


class ResearchTaskResponse(BaseModel):
    task_id: UUID
    entry_type: EntryType
    status: ResearchTaskStatus
    version: int
    allowed_actions: list[ResearchTaskAction]
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
            created_at=task.created_at,
            updated_at=task.updated_at,
        )


class ResearchTaskPageResponse(BaseModel):
    items: list[ResearchTaskResponse]
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
