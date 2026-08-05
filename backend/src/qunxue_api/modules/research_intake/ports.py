from typing import Protocol, runtime_checkable
from uuid import UUID

from qunxue_api.modules.research_intake.domain import (
    PhenomenonCandidateDraft,
    ResearchTask,
)


class PhenomenonCandidateBuilder(Protocol):
    """Consumer-owned model port; its output always remains a candidate."""

    def build(
        self,
        *,
        task_id: UUID,
        raw_input: str,
        research_intent: str | None,
        context: str | None,
    ) -> PhenomenonCandidateDraft: ...


@runtime_checkable
class ResearchTaskRepository(Protocol):
    """Persistence port for research intake tasks."""

    def get(self, task_id: UUID) -> ResearchTask | None: ...

    def add(self, task: ResearchTask) -> ResearchTask: ...
