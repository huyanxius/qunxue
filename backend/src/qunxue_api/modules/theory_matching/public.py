from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from qunxue_api.modules.knowledge_catalog import (
    KnowledgeReleaseRef,
    SourceRecordSnapshot,
    SourceVerificationStatus,
    TheoryProfileSnapshot,
)
from qunxue_api.modules.research_intake import ConfirmedPhenomenonSnapshot


class MatchRunStatus(StrEnum):
    GENERATING = "generating"
    AWAITING_DECISION = "awaiting_decision"
    PARTIAL_FAILURE = "partial_failure"
    NO_RELIABLE_CANDIDATE = "no_reliable_candidate"
    COMPLETED = "completed"
    FAILED = "failed"


class CandidateOrigin(StrEnum):
    REVIEWED_KNOWLEDGE = "reviewed_knowledge"
    MODEL_EXPLORATION = "model_exploration"
    EXTERNAL_UNREVIEWED = "external_unreviewed"
    USER_SUPPLIED = "user_supplied"


class TheoryDecisionAction(StrEnum):
    ADOPT = "adopt"
    EXCLUDE = "exclude"
    RETAIN = "retain"
    COMBINE = "combine"
    DEFER = "defer"
    REQUEST_MORE_EVIDENCE = "request_more_evidence"
    REVISE_APPLICABILITY = "revise_applicability"


class TheoryJudgementVerdict(StrEnum):
    APPLICABLE = "applicable"
    CONDITIONAL = "conditional"
    INSUFFICIENT = "insufficient"
    NOT_APPLICABLE = "not_applicable"


class CandidateJudgementRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    INSUFFICIENT_SOURCES = "insufficient_sources"


class CandidateContentStatus(StrEnum):
    REVIEWED = "reviewed"
    MODEL_GENERATED = "model_generated"
    EXTERNAL_UNREVIEWED = "external_unreviewed"
    USER_SUPPLIED = "user_supplied"


class MatchCompletionBasis(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    PARTIAL_WITH_USER_ACK = "partial_with_user_ack"


@dataclass(frozen=True, slots=True)
class MatchRunModelSnapshot:
    """Configured judge identity plus the trace attached to one matching run."""

    provider: str
    model_version: str
    capability: str
    degraded: bool
    knowledge_release_id: str
    trace_id: UUID
    request_id: UUID
    contract_version: str


@dataclass(frozen=True, slots=True)
class EvidenceItemSnapshot:
    """一次匹配运行实际看到的证据；无需再跨模块按 ID 回查正文。"""

    evidence_ref_id: str
    claim: str
    excerpt: str | None
    locator: str | None
    source: SourceRecordSnapshot | None
    verification_status: SourceVerificationStatus
    use_boundary: str


@dataclass(frozen=True, slots=True)
class EvidenceBundleSnapshot:
    evidence_bundle_id: str
    version: int
    content_hash: str
    release: KnowledgeReleaseRef
    theory_profiles: tuple[TheoryProfileSnapshot, ...]
    evidence_items: tuple[EvidenceItemSnapshot, ...]


@dataclass(frozen=True, slots=True)
class TheoryCandidateContentSnapshot:
    """已审核理论和库外探索理论进入比较界面后的统一内容快照。"""

    theory_id: str | None
    title: str
    origin: CandidateOrigin
    problem_focus: str
    core_claims: tuple[str, ...]
    analysis_levels: tuple[str, ...]
    source_ids: tuple[str, ...]
    reviewed_profile: TheoryProfileSnapshot | None
    formal_adoption_eligible: bool
    adoption_blockers: tuple[str, ...]
    knowledge_id: str | None = None
    seed_theory_id: str | None = None
    content_status: CandidateContentStatus = CandidateContentStatus.MODEL_GENERATED


@dataclass(frozen=True, slots=True)
class TheoryJudgementInput:
    """模型能力的完整不可变输入，禁止实现自行读取其他模块的数据库。"""

    knowledge_release: KnowledgeReleaseRef
    phenomenon: ConfirmedPhenomenonSnapshot
    candidate: TheoryCandidateContentSnapshot
    comparison_candidates: tuple[TheoryCandidateContentSnapshot, ...]
    evidence_items: tuple[EvidenceItemSnapshot, ...]


@dataclass(frozen=True, slots=True)
class TheoryJudgementDraft:
    """模型输出尚未取得业务 ID，也没有替用户作采用决定。"""

    verdict: TheoryJudgementVerdict
    match_rationale: str
    applicable_conditions: tuple[str, ...]
    limitations: tuple[str, ...]
    material_requirements: tuple[str, ...]
    evidence_gaps: tuple[str, ...]
    alternative_explanations: tuple[str, ...]
    evidence_ref_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TheoryJudgementBatchItem:
    candidate_id: UUID
    candidate_version: int
    judgement_input: TheoryJudgementInput


@dataclass(frozen=True, slots=True)
class TheoryJudgementBatchInput:
    """One ordered candidate set; target IDs narrow a retry without losing context."""

    items: tuple[TheoryJudgementBatchItem, ...]
    target_candidate_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class TheoryJudgementBatchItemResult:
    candidate_id: UUID
    candidate_version: int
    status: CandidateJudgementRunStatus
    judgement: TheoryJudgementDraft | None
    failure_code: str | None
    trace_id: UUID
    request_id: UUID
    contract_version: str


@dataclass(frozen=True, slots=True)
class TheoryJudgementBatchResult:
    """Stable rerank output with per-candidate failure and retry information."""

    results: tuple[TheoryJudgementBatchItemResult, ...]
    input_candidate_order: tuple[UUID, ...]
    ranked_candidate_order: tuple[UUID, ...]
    completion_basis: MatchCompletionBasis
    retryable_candidate_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class TheoryCandidateSnapshot:
    candidate_id: UUID
    candidate_version: int
    content: TheoryCandidateContentSnapshot
    judgement: TheoryJudgementDraft
    trace_id: UUID
    request_id: UUID
    contract_version: str
    judgement_run_status: CandidateJudgementRunStatus = CandidateJudgementRunStatus.SUCCEEDED


@dataclass(frozen=True, slots=True)
class MatchRunSnapshot:
    match_run_id: UUID
    task_id: UUID
    version: int
    status: MatchRunStatus
    phenomenon: ConfirmedPhenomenonSnapshot
    knowledge_release: KnowledgeReleaseRef
    evidence_bundle: EvidenceBundleSnapshot
    candidates: tuple[TheoryCandidateSnapshot, ...]
    completion_basis: MatchCompletionBasis = MatchCompletionBasis.COMPLETE
    partial_completion_acknowledged: bool = False
    failed_candidate_ids: tuple[UUID, ...] = ()
    partial_completion_acknowledgement_reason: str | None = None
    partial_completion_acknowledged_at: datetime | None = None
    partial_completion_idempotency_key: str | None = None
    partial_completion_request_hash: str | None = None
    stable_candidate_order: tuple[UUID, ...] = ()
    next_cursor: str | None = None
    model: MatchRunModelSnapshot | None = None


@dataclass(frozen=True, slots=True)
class TheoryDecisionCommand:
    candidate_id: UUID
    candidate_version: int
    action: TheoryDecisionAction
    reason: str
    related_source_ids: tuple[str, ...] = ()
    revised_applicability: str | None = None
    related_candidate_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class TheoryDecisionRecord:
    decision_id: UUID
    candidate_id: UUID
    candidate_version: int
    action: TheoryDecisionAction
    reason: str
    related_source_ids: tuple[str, ...]
    revised_applicability: str | None
    recorded_at: datetime
    related_candidate_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class TheoryUseAssignment:
    """角色代码允许项目后续扩充；说明文字记录该理论具体解释什么。"""

    candidate_id: UUID
    role_code: str
    responsibility: str


@dataclass(frozen=True, slots=True)
class TheoryRelationCommand:
    candidate_ids: tuple[UUID, ...]
    relation_kind: str
    explanation: str
    premise_compatibility: str
    supporting_evidence: tuple[str, ...]
    excluding_evidence: tuple[str, ...]
    distinguishing_evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TheoryRelationSnapshot:
    relation_id: UUID
    candidate_ids: tuple[UUID, ...]
    relation_kind: str
    explanation: str
    premise_compatibility: str
    supporting_evidence: tuple[str, ...]
    excluding_evidence: tuple[str, ...]
    distinguishing_evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TheoryDecisionSetSnapshot:
    """用户决定先被记录；记录本身不会自动升级成已确认理论方案。"""

    decision_set_id: UUID
    match_run_id: UUID
    version: int
    decisions: tuple[TheoryDecisionRecord, ...]
    use_assignments: tuple[TheoryUseAssignment, ...]
    relations: tuple[TheoryRelationSnapshot, ...]
    recorded_at: datetime
    idempotency_key: str | None = None
    request_hash: str | None = None


@dataclass(frozen=True, slots=True)
class DeferredTheoryPlanSnapshot:
    task_id: UUID
    match_run_id: UUID
    version: int
    reason: str
    deferred_at: datetime


@dataclass(frozen=True, slots=True)
class ConfirmedTheoryPlanSnapshot:
    """交给研究框架模块的完整快照，不要求下游跨模块回查。"""

    theory_plan_id: UUID
    task_id: UUID
    match_run_id: UUID
    decision_set_id: UUID
    version: int
    phenomenon: ConfirmedPhenomenonSnapshot
    knowledge_release: KnowledgeReleaseRef
    evidence_bundle: EvidenceBundleSnapshot
    candidates: tuple[TheoryCandidateSnapshot, ...]
    decisions: tuple[TheoryDecisionRecord, ...]
    use_assignments: tuple[TheoryUseAssignment, ...]
    relations: tuple[TheoryRelationSnapshot, ...]
    confirmed_at: datetime
    idempotency_key: str | None = None
    request_hash: str | None = None


class TheoryPlanGateViolation(ValueError):
    """至少一项采用、多理论关系与解释分工必须由服务端共同校验。"""

    def __init__(self, violations: tuple[str, ...]) -> None:
        self.violations = violations
        super().__init__("; ".join(violations))


class TheoryEvidenceSource(Protocol):
    """消费方拥有的检索端口；相似度不能替代适用性判断。"""

    def retrieve(
        self,
        *,
        phenomenon: ConfirmedPhenomenonSnapshot,
        release: KnowledgeReleaseRef,
    ) -> EvidenceBundleSnapshot: ...


class MatchRunRepository(Protocol):
    def add(self, snapshot: MatchRunSnapshot) -> MatchRunSnapshot: ...

    def get(self, match_run_id: UUID) -> MatchRunSnapshot | None: ...

    def delete(self, match_run_id: UUID) -> None: ...

    def save(self, snapshot: MatchRunSnapshot) -> MatchRunSnapshot: ...

    def add_decision_set(
        self, snapshot: TheoryDecisionSetSnapshot
    ) -> TheoryDecisionSetSnapshot: ...

    def get_decision_set(self, decision_set_id: UUID) -> TheoryDecisionSetSnapshot | None: ...

    def get_decision_set_for_match_run(
        self, match_run_id: UUID
    ) -> TheoryDecisionSetSnapshot | None: ...

    def list_decision_sets(
        self, match_run_id: UUID
    ) -> tuple[TheoryDecisionSetSnapshot, ...]: ...

    def add_confirmed_plan(
        self, snapshot: ConfirmedTheoryPlanSnapshot
    ) -> ConfirmedTheoryPlanSnapshot: ...

    def get_confirmed_plan(self, theory_plan_id: UUID) -> ConfirmedTheoryPlanSnapshot | None: ...

    def get_confirmed_plan_for_decision_set(
        self, decision_set_id: UUID
    ) -> ConfirmedTheoryPlanSnapshot | None: ...


class TheoryCandidateJudge(Protocol):
    """批量判断并稳定重排；提供方路由留在 adapter。"""

    def judge_and_rerank(
        self,
        *,
        input: TheoryJudgementBatchInput,
    ) -> TheoryJudgementBatchResult: ...


class TheoryMatching(Protocol):
    def start(
        self,
        *,
        phenomenon: ConfirmedPhenomenonSnapshot,
        release: KnowledgeReleaseRef,
    ) -> MatchRunSnapshot: ...

    def get(self, match_run_id: UUID) -> MatchRunSnapshot: ...

    def discard(self, match_run_id: UUID) -> None: ...

    def retry_candidate(
        self,
        *,
        match_run_id: UUID,
        candidate_id: UUID,
        expected_version: int,
    ) -> MatchRunSnapshot: ...

    def acknowledge_partial_completion(
        self,
        *,
        match_run_id: UUID,
        expected_version: int,
        acknowledged_candidate_ids: tuple[UUID, ...],
        failed_candidate_ids: tuple[UUID, ...],
        reason: str,
    ) -> MatchRunSnapshot: ...

    def record_decisions(
        self,
        *,
        match_run_id: UUID,
        expected_version: int,
        decisions: tuple[TheoryDecisionCommand, ...],
        use_assignments: tuple[TheoryUseAssignment, ...],
        relations: tuple[TheoryRelationCommand, ...],
        completion_basis: MatchCompletionBasis | None = None,
        idempotency_key: str | None = None,
        request_hash: str | None = None,
    ) -> TheoryDecisionSetSnapshot: ...

    def get_decision_set(self, decision_set_id: UUID) -> TheoryDecisionSetSnapshot: ...

    def get_decision_set_for_match_run(
        self, match_run_id: UUID
    ) -> TheoryDecisionSetSnapshot | None: ...

    def get_confirmed_plan(self, theory_plan_id: UUID) -> ConfirmedTheoryPlanSnapshot: ...

    def confirm_plan(
        self,
        *,
        decision_set_id: UUID,
        expected_version: int,
        idempotency_key: str | None = None,
        request_hash: str | None = None,
    ) -> ConfirmedTheoryPlanSnapshot: ...

    def defer_plan(
        self,
        *,
        match_run_id: UUID,
        expected_version: int,
        reason: str,
    ) -> DeferredTheoryPlanSnapshot: ...
