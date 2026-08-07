from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from qunxue_api.modules.research_intake.domain import (
    ConfirmedPhenomenonSnapshot,
    DirectPhenomenonInput,
    PhenomenonCandidate,
    PhenomenonCandidateDraft,
    PhenomenonEvidenceRefSnapshot,
    PhenomenonExample,
    PhenomenonModelSnapshot,
    PhenomenonProgress,
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


@runtime_checkable
class PhenomenonRepository(Protocol):
    def list_examples(self) -> list[PhenomenonExample]: ...

    def submit_direct(
        self,
        *,
        task_id: UUID,
        phenomenon: str,
        research_intent: str | None,
        context: str | None,
        now: datetime,
        input_id: UUID,
    ) -> DirectPhenomenonInput: ...

    def input_for_task(self, task_id: UUID) -> DirectPhenomenonInput | None: ...

    def save_candidate(
        self,
        *,
        task_id: UUID,
        candidate_id: UUID,
        draft: PhenomenonCandidateDraft,
        evidence_refs: tuple[PhenomenonEvidenceRefSnapshot, ...],
        model: PhenomenonModelSnapshot,
        now: datetime,
    ) -> PhenomenonCandidate: ...

    def get_candidate(
        self, task_id: UUID, candidate_id: UUID, version: int | None = None
    ) -> PhenomenonCandidate | None: ...

    def update_candidate(
        self,
        *,
        task_id: UUID,
        candidate_id: UUID,
        expected_version: int,
        phenomenon: str,
        research_intent: str | None,
        context: str | None,
        now: datetime,
    ) -> PhenomenonCandidate | None: ...

    def confirm_candidate(
        self,
        *,
        task_id: UUID,
        candidate_id: UUID,
        expected_version: int,
        query_id: UUID,
        now: datetime,
    ) -> tuple[ConfirmedPhenomenonSnapshot, datetime] | None: ...

    def progress(self, task_id: UUID) -> PhenomenonProgress: ...
