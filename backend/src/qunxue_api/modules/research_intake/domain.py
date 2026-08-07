from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID


class EntryType(StrEnum):
    DIRECT_INPUT = "direct_input"


class EntryInputType(StrEnum):
    DIRECT_INPUT = "direct_input"
    MATERIAL_INPUT = "material_input"


class ResearchTaskStatus(StrEnum):
    DRAFT = "draft"


class ResearchTaskAction(StrEnum):
    SUBMIT_PHENOMENON = "submit_phenomenon"


class PhenomenonEvidenceVerificationStatus(StrEnum):
    VERIFIED = "verified"
    USER_ATTESTED = "user_attested"
    PENDING = "pending"


@dataclass(frozen=True, slots=True)
class PhenomenonEvidenceRefSnapshot:
    """Displayable evidence retained with a phenomenon, not an orphaned ID."""

    evidence_ref_id: str
    excerpt: str
    source_ref_id: str
    source_description: str | None
    locator: str | None
    verification_status: PhenomenonEvidenceVerificationStatus
    use_boundary: str


@dataclass(frozen=True, slots=True)
class ConfirmedPhenomenonSnapshot:
    """研究入口交给理论匹配的不可变交接物，不暴露入口模块的存储对象。"""

    task_id: UUID
    phenomenon_query_id: UUID
    version: int
    phenomenon: str
    research_intent: str | None
    context: str | None
    evidence_refs: tuple[PhenomenonEvidenceRefSnapshot, ...] = ()


@dataclass(frozen=True, slots=True)
class PhenomenonCandidateDraft:
    """通用生成能力只能提出候选，不能产生用户确认状态。"""

    phenomenon: str
    research_intent: str | None
    context: str | None
    source_ref_ids: tuple[str, ...]
    evidence_refs: tuple[PhenomenonEvidenceRefSnapshot, ...] = ()


@dataclass(frozen=True, slots=True)
class ResearchTask:
    task_id: UUID
    entry_type: EntryType
    status: ResearchTaskStatus
    version: int
    idempotency_key: str
    created_at: datetime
    updated_at: datetime

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
        entry_type: EntryType,
        idempotency_key: str,
        now: datetime,
    ) -> "ResearchTask":
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        return cls(
            task_id=task_id,
            entry_type=entry_type,
            status=ResearchTaskStatus.DRAFT,
            version=1,
            idempotency_key=idempotency_key,
            created_at=now,
            updated_at=now,
        )
