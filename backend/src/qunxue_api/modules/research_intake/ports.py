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
    """研究任务持久化端口；adapter 只能通过模块公共入口实现它。"""

    def get(self, task_id: UUID, user_id: UUID) -> ResearchTask | None: ...

    def list_for_user(self, user_id: UUID, *, limit: int) -> list[ResearchTask]: ...

    def delete(self, task_id: UUID, user_id: UUID) -> ResearchTask | None: ...

    def add_or_get_by_idempotency_key(self, task: ResearchTask) -> ResearchTask: ...

    def save_progress(self, task: ResearchTask) -> ResearchTask | None: ...
