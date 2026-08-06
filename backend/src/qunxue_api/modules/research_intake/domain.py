from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID


class EntryType(StrEnum):
    DIRECT_INPUT = "direct_input"


class ResearchTaskStatus(StrEnum):
    DRAFT = "draft"


class ResearchTaskAction(StrEnum):
    SUBMIT_PHENOMENON = "submit_phenomenon"


class PhenomenonSource(StrEnum):
    USER_INPUT = "user_input"


@dataclass(frozen=True, slots=True)
class PhenomenonQuery:
    phenomenon: str
    research_intent: str | None
    context: str | None
    source: PhenomenonSource = PhenomenonSource.USER_INPUT


@dataclass(frozen=True, slots=True)
class ConfirmedPhenomenonSnapshot:
    """Immutable handoff from intake into theory matching."""

    task_id: UUID
    phenomenon_query_id: UUID
    version: int
    phenomenon: str
    research_intent: str | None
    context: str | None
    source: PhenomenonSource = PhenomenonSource.USER_INPUT


@dataclass(frozen=True, slots=True)
class PhenomenonCandidateDraft:
    """Generated capabilities may propose candidates, never user confirmation."""

    phenomenon: str
    research_intent: str | None
    context: str | None
    source_ref_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResearchTask:
    task_id: UUID
    phenomenon_query: PhenomenonQuery
    created_at: datetime
    updated_at: datetime
    entry_type: EntryType = EntryType.DIRECT_INPUT
    status: ResearchTaskStatus = ResearchTaskStatus.DRAFT
    version: int = 1

    @property
    def phenomenon(self) -> str:
        return self.phenomenon_query.phenomenon

    @property
    def research_intent(self) -> str | None:
        return self.phenomenon_query.research_intent

    @property
    def context(self) -> str | None:
        return self.phenomenon_query.context

    @property
    def source(self) -> PhenomenonSource:
        return self.phenomenon_query.source

    @property
    def allowed_actions(self) -> tuple[ResearchTaskAction, ...]:
        if self.status is ResearchTaskStatus.DRAFT:
            return (ResearchTaskAction.SUBMIT_PHENOMENON,)
        return ()

    @classmethod
    def create(
        cls,
        *,
        task_id: UUID,
        phenomenon_query: PhenomenonQuery,
        now: datetime,
    ) -> "ResearchTask":
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        return cls(
            task_id=task_id,
            phenomenon_query=phenomenon_query,
            created_at=now,
            updated_at=now,
            entry_type=EntryType.DIRECT_INPUT,
            status=ResearchTaskStatus.DRAFT,
            version=1,
        )