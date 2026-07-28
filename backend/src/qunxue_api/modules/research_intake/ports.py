from typing import Protocol
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


class ResearchTaskRepository(Protocol):
    def get(self, task_id: UUID) -> ResearchTask | None: ...

    def get_by_idempotency_key(self, idempotency_key: str) -> ResearchTask | None: ...

    def add(self, task: ResearchTask) -> None: ...
