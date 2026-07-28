from datetime import datetime
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
