from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from qunxue_api.modules.research_intake import PhenomenonSource, ResearchTask


class CreateResearchTaskRequest(BaseModel):
    phenomenon: str
    research_intent: str | None = None
    context: str | None = None


class ResearchTaskResponse(BaseModel):
    task_id: UUID
    phenomenon: str
    research_intent: str | None
    context: str | None
    source: PhenomenonSource
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, task: ResearchTask) -> "ResearchTaskResponse":
        return cls(
            task_id=task.task_id,
            phenomenon=task.phenomenon,
            research_intent=task.research_intent,
            context=task.context,
            source=task.source,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )
