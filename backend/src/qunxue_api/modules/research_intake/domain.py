from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID


class EntryType(StrEnum):
    DIRECT_INPUT = "direct_input"
    MATERIAL_INPUT = "material_input"


class EntryInputType(StrEnum):
    DIRECT_INPUT = "direct_input"
    MATERIAL_INPUT = "material_input"


class ResearchTaskStatus(StrEnum):
    DRAFT = "draft"
    PHENOMENON_CONFIRMED = "phenomenon_confirmed"
    MATCH_GENERATING = "match_generating"
    DECISIONS_RECORDED = "decisions_recorded"
    THEORY_PLAN_CONFIRMED = "theory_plan_confirmed"
    FRAMEWORK_DRAFT = "framework_draft"
    FRAMEWORK_CONFIRMED = "framework_confirmed"


class ResearchTaskAction(StrEnum):
    SUBMIT_PHENOMENON = "submit_phenomenon"


class ResearchStartProposalStatus(StrEnum):
    PENDING_CONFIRMATION = "pending_confirmation"
    CONFIRMED = "confirmed"


class PhenomenonEvidenceVerificationStatus(StrEnum):
    VERIFIED = "verified"
    USER_ATTESTED = "user_attested"
    PENDING = "pending"


class PhenomenonCandidateStatus(StrEnum):
    PROPOSED = "proposed"
    EDITED = "edited"
    CONFIRMED = "confirmed"


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
    content_hash: str = ""
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
class PhenomenonModelSnapshot:
    provider: str
    model_version: str
    capability: str
    degraded: bool
    knowledge_release_id: str | None
    trace_id: UUID
    request_id: UUID
    contract_version: str


@dataclass(frozen=True, slots=True)
class DirectPhenomenonInput:
    input_id: UUID
    task_id: UUID
    version: int
    phenomenon: str
    research_intent: str | None
    context: str | None
    source_ref_ids: tuple[str, ...]
    accepted_at: datetime


@dataclass(frozen=True, slots=True)
class PhenomenonCandidate:
    candidate_id: UUID
    task_id: UUID
    version: int
    status: PhenomenonCandidateStatus
    phenomenon: str
    research_intent: str | None
    context: str | None
    source_ref_ids: tuple[str, ...]
    evidence_refs: tuple[PhenomenonEvidenceRefSnapshot, ...]
    model: PhenomenonModelSnapshot
    missing_information: tuple[str, ...] = ()
    source_traceability: str = "traceable"
    content_origin: str = "system_generated"


@dataclass(frozen=True, slots=True)
class MaterialIntakeRun:
    run_id: UUID
    task_id: UUID
    status: str
    filename: str
    media_type: str
    processing_policy_version: str
    candidates: tuple[PhenomenonCandidate, ...]
    accepted_at: datetime


@dataclass(frozen=True, slots=True)
class PreparedPhenomenonCandidate:
    candidate_id: UUID
    draft: PhenomenonCandidateDraft
    evidence_refs: tuple[PhenomenonEvidenceRefSnapshot, ...]
    missing_information: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PhenomenonProgress:
    candidate: PhenomenonCandidate | None
    confirmed: ConfirmedPhenomenonSnapshot | None
    confirmed_at: datetime | None


@dataclass(frozen=True, slots=True)
class PhenomenonExample:
    example_id: str
    title: str
    phenomenon: str
    research_intent: str | None
    context: str | None


@dataclass(frozen=True, slots=True)
class ResearchTask:
    task_id: UUID
    user_id: UUID
    entry_type: EntryType
    status: ResearchTaskStatus
    version: int
    idempotency_key: str
    created_at: datetime
    updated_at: datetime
    seed_theory_id: str | None = None
    seed_theory_name: str | None = None
    phenomenon_query_id: UUID | None = None
    phenomenon_version: int | None = None
    phenomenon_summary: str | None = None
    phenomenon_research_intent: str | None = None
    adopted_theory_count: int = 0
    current_phenomenon_candidate_id: UUID | None = None
    current_material_intake_run_id: UUID | None = None
    current_match_run_id: UUID | None = None
    current_theory_plan_id: UUID | None = None
    current_framework_id: UUID | None = None
    knowledge_release_id: str | None = None
    conversation_id: UUID | None = None
    source_turn_id: UUID | None = None
    source_agent_run_id: UUID | None = None

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
        user_id: UUID,
        entry_type: EntryType,
        idempotency_key: str,
        seed_theory_id: str | None,
        seed_theory_name: str | None,
        now: datetime,
        knowledge_release_id: str | None = None,
        conversation_id: UUID | None = None,
        source_turn_id: UUID | None = None,
        source_agent_run_id: UUID | None = None,
    ) -> "ResearchTask":
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        return cls(
            task_id=task_id,
            user_id=user_id,
            entry_type=entry_type,
            status=ResearchTaskStatus.DRAFT,
            version=1,
            idempotency_key=idempotency_key,
            seed_theory_id=seed_theory_id,
            seed_theory_name=seed_theory_name,
            created_at=now,
            updated_at=now,
            knowledge_release_id=knowledge_release_id,
            conversation_id=conversation_id,
            source_turn_id=source_turn_id,
            source_agent_run_id=source_agent_run_id,
        )


@dataclass(frozen=True, slots=True)
class ResearchStartProposal:
    proposal_id: UUID
    user_id: UUID
    conversation_id: UUID
    source_run_id: UUID
    source_turn_id: UUID
    knowledge_release_id: str
    phenomenon: str
    research_intent: str | None
    context: str | None
    version: int
    status: ResearchStartProposalStatus
    created_at: datetime
    confirmed_task_id: UUID | None = None
    confirmed_request_hash: str | None = None
    confirmed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ResearchStartConfirmation:
    user_id: UUID
    idempotency_key: str
    proposal_id: UUID
    request_hash: str
    task_id: UUID
    created_at: datetime
