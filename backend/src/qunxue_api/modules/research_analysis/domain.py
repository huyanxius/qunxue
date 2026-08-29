"""Pure, approval-gated qualitative analysis records.

Every interpretation starts as a candidate unless a user authored it.  Source
anchors include the immutable parse and segment identity, so a later reparse
cannot silently move a code or memo to different text.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from qunxue_api.modules.research_materials import MaterialLocator


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _required(value: str, name: str, *, limit: int = 20_000) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} is required")
    if len(normalized) > limit:
        raise ValueError(f"{name} is too long")
    return normalized


def _content_hash(value: str, name: str) -> str:
    normalized = _required(value, name, limit=64).lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{name} must be a sha256 hash")
    return normalized


def _require_candidate_decision(
    *,
    status: AnalysisRecordStatus | AnalysisCodeStatus,
    version: int,
    expected_version: int,
    user_confirmed: bool,
) -> None:
    if not user_confirmed:
        raise ValueError("user confirmation is required")
    if version != expected_version:
        raise ValueError("stale analysis record version")
    if status not in {AnalysisRecordStatus.CANDIDATE, AnalysisCodeStatus.CANDIDATE}:
        raise ValueError("analysis record is already decided")


class AnalysisRecordStatus(StrEnum):
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class AnalysisAnnotationKind(StrEnum):
    DESCRIPTIVE = "descriptive"
    RESEARCHER_REFLECTION = "researcher_reflection"


class AnalysisCodeStatus(StrEnum):
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class AnalysisMemoKind(StrEnum):
    DESCRIPTIVE = "descriptive"
    REFLEXIVE = "reflexive"
    ANALYTIC = "analytic"
    METHODOLOGICAL = "methodological"


class ComparisonFindingKind(StrEnum):
    SUPPORT = "support"
    COUNTEREXAMPLE = "counterexample"
    CONTRADICT = "contradict"
    COMPETING_EXPLANATION = "competing_explanation"
    EVIDENCE_GAP = "evidence_gap"


@dataclass(frozen=True, slots=True)
class AnalysisWriteRequest:
    """Durable identity for replaying one API write or one Agent tool call."""

    user_id: UUID
    task_id: UUID
    namespace: str
    idempotency_key: str
    operation: str
    request_hash: str
    result_kind: str
    result_id: UUID
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        task_id: UUID,
        namespace: str,
        idempotency_key: str,
        operation: str,
        request_hash: str,
        result_kind: str,
        result_id: UUID,
        now: datetime,
    ) -> AnalysisWriteRequest:
        return cls(
            user_id=user_id,
            task_id=task_id,
            namespace=_required(namespace, "idempotency namespace", limit=32),
            idempotency_key=_required(idempotency_key, "idempotency key", limit=512),
            operation=_required(operation, "idempotency operation", limit=64),
            request_hash=_content_hash(request_hash, "request_hash"),
            result_kind=_required(result_kind, "result kind", limit=32),
            result_id=result_id,
            created_at=_utc(now),
        )


@dataclass(frozen=True, slots=True)
class AnalysisAnnotation:
    annotation_id: UUID
    user_id: UUID
    task_id: UUID
    material_id: UUID
    parse_id: UUID
    segment_id: str
    segment_content_hash: str
    quote: str
    quote_hash: str
    quote_start: int
    quote_end: int
    locator: MaterialLocator
    annotation_kind: AnalysisAnnotationKind
    case_label: str | None
    observed_at: str | None
    note: str
    reflection: str | None
    created_at: datetime
    source_available: bool = True
    unavailable_reason: str | None = None

    @classmethod
    def create(
        cls,
        *,
        annotation_id: UUID | None = None,
        user_id: UUID,
        task_id: UUID,
        material_id: UUID,
        parse_id: UUID,
        segment_id: str,
        segment_content_hash: str,
        quote: str,
        quote_start: int,
        quote_end: int,
        locator: MaterialLocator,
        annotation_kind: AnalysisAnnotationKind,
        case_label: str | None = None,
        observed_at: str | None = None,
        note: str,
        reflection: str | None = None,
        now: datetime,
    ) -> AnalysisAnnotation:
        import hashlib

        normalized_quote = _required(quote, "quote", limit=100_000)
        if quote_start < 0 or quote_end <= quote_start:
            raise ValueError("quote range must be a non-empty half-open interval")
        if quote_end - quote_start != len(normalized_quote):
            raise ValueError("quote range must match the selected quote length")
        normalized_note = _required(note, "note")
        if annotation_kind is AnalysisAnnotationKind.RESEARCHER_REFLECTION and not (
            reflection and reflection.strip()
        ):
            raise ValueError("researcher reflection is required")
        return cls(
            annotation_id=annotation_id or uuid4(),
            user_id=user_id,
            task_id=task_id,
            material_id=material_id,
            parse_id=parse_id,
            segment_id=_required(segment_id, "segment_id", limit=256),
            segment_content_hash=_content_hash(
                segment_content_hash,
                "segment_content_hash",
            ),
            quote=normalized_quote,
            quote_hash=hashlib.sha256(normalized_quote.encode()).hexdigest(),
            quote_start=quote_start,
            quote_end=quote_end,
            locator=locator,
            annotation_kind=AnalysisAnnotationKind(annotation_kind),
            case_label=case_label.strip() if case_label and case_label.strip() else None,
            observed_at=observed_at.strip() if observed_at and observed_at.strip() else None,
            note=normalized_note,
            reflection=reflection.strip() if reflection and reflection.strip() else None,
            created_at=_utc(now),
        )

    def source_tombstone(self, *, reason: str = "source_deleted") -> AnalysisAnnotation:
        return replace(
            self,
            quote="",
            source_available=False,
            unavailable_reason=_required(reason, "unavailable reason", limit=64),
        )


@dataclass(frozen=True, slots=True)
class AnalysisCode:
    code_id: UUID
    user_id: UUID
    task_id: UUID
    label: str
    definition: str
    annotation_ids: tuple[UUID, ...]
    rationale: str
    source: str
    status: AnalysisCodeStatus
    version: int
    created_at: datetime
    conversation_id: UUID | None = None
    agent_run_id: UUID | None = None
    agent_turn_id: UUID | None = None
    tool_call_id: str | None = None
    decided_at: datetime | None = None
    decision_reason: str | None = None

    @classmethod
    def candidate(
        cls,
        *,
        user_id: UUID,
        task_id: UUID,
        label: str,
        definition: str,
        annotation_ids: tuple[UUID, ...],
        rationale: str,
        now: datetime,
        source: str = "agent",
        conversation_id: UUID | None = None,
        agent_run_id: UUID | None = None,
        agent_turn_id: UUID | None = None,
        tool_call_id: str | None = None,
        code_id: UUID | None = None,
    ) -> AnalysisCode:
        if not annotation_ids:
            raise ValueError("at least one annotation is required")
        return cls(
            code_id=code_id or uuid4(),
            user_id=user_id,
            task_id=task_id,
            label=_required(label, "code label", limit=256),
            definition=_required(definition, "code definition"),
            annotation_ids=tuple(dict.fromkeys(annotation_ids)),
            rationale=_required(rationale, "code rationale"),
            source=_required(source, "code source", limit=32),
            status=AnalysisCodeStatus.CANDIDATE,
            version=1,
            created_at=_utc(now),
            conversation_id=conversation_id,
            agent_run_id=agent_run_id,
            agent_turn_id=agent_turn_id,
            tool_call_id=(
                _required(tool_call_id, "tool_call_id", limit=512)
                if tool_call_id is not None
                else None
            ),
        )

    def confirm(
        self,
        *,
        user_confirmed: bool,
        expected_version: int,
        reason: str,
        now: datetime,
    ) -> AnalysisCode:
        _require_candidate_decision(
            status=self.status,
            version=self.version,
            expected_version=expected_version,
            user_confirmed=user_confirmed,
        )
        return replace(
            self,
            status=AnalysisCodeStatus.CONFIRMED,
            version=self.version + 1,
            decided_at=_utc(now),
            decision_reason=_required(reason, "decision reason"),
        )

    def reject(
        self,
        *,
        user_confirmed: bool,
        expected_version: int,
        reason: str,
        now: datetime,
    ) -> AnalysisCode:
        _require_candidate_decision(
            status=self.status,
            version=self.version,
            expected_version=expected_version,
            user_confirmed=user_confirmed,
        )
        return replace(
            self,
            status=AnalysisCodeStatus.REJECTED,
            version=self.version + 1,
            decided_at=_utc(now),
            decision_reason=_required(reason, "decision reason"),
        )


@dataclass(frozen=True, slots=True)
class AnalysisMemo:
    memo_id: UUID
    user_id: UUID
    task_id: UUID
    title: str
    content: str
    memo_kind: AnalysisMemoKind
    annotation_ids: tuple[UUID, ...]
    code_ids: tuple[UUID, ...]
    source: str
    status: AnalysisRecordStatus
    version: int
    created_at: datetime
    conversation_id: UUID | None = None
    agent_run_id: UUID | None = None
    agent_turn_id: UUID | None = None
    tool_call_id: str | None = None
    decided_at: datetime | None = None
    decision_reason: str | None = None

    @classmethod
    def create_candidate(
        cls,
        *,
        user_id: UUID,
        task_id: UUID,
        title: str,
        content: str,
        memo_kind: AnalysisMemoKind,
        annotation_ids: tuple[UUID, ...] = (),
        code_ids: tuple[UUID, ...] = (),
        source: str = "agent",
        conversation_id: UUID | None = None,
        agent_run_id: UUID | None = None,
        agent_turn_id: UUID | None = None,
        tool_call_id: str | None = None,
        now: datetime,
        memo_id: UUID | None = None,
    ) -> AnalysisMemo:
        return cls(
            memo_id=memo_id or uuid4(),
            user_id=user_id,
            task_id=task_id,
            title=_required(title, "memo title", limit=512),
            content=_required(content, "memo content", limit=100_000),
            memo_kind=AnalysisMemoKind(memo_kind),
            annotation_ids=tuple(dict.fromkeys(annotation_ids)),
            code_ids=tuple(dict.fromkeys(code_ids)),
            source=_required(source, "memo source", limit=32),
            status=AnalysisRecordStatus.CANDIDATE,
            version=1,
            created_at=_utc(now),
            conversation_id=conversation_id,
            agent_run_id=agent_run_id,
            agent_turn_id=agent_turn_id,
            tool_call_id=(
                _required(tool_call_id, "tool_call_id", limit=512)
                if tool_call_id is not None
                else None
            ),
        )

    def confirm(
        self,
        *,
        user_confirmed: bool,
        expected_version: int,
        reason: str,
        now: datetime,
    ) -> AnalysisMemo:
        _require_candidate_decision(
            status=self.status,
            version=self.version,
            expected_version=expected_version,
            user_confirmed=user_confirmed,
        )
        return replace(
            self,
            status=AnalysisRecordStatus.CONFIRMED,
            version=self.version + 1,
            decided_at=_utc(now),
            decision_reason=_required(reason, "decision reason"),
        )

    def reject(
        self,
        *,
        user_confirmed: bool,
        expected_version: int,
        reason: str,
        now: datetime,
    ) -> AnalysisMemo:
        _require_candidate_decision(
            status=self.status,
            version=self.version,
            expected_version=expected_version,
            user_confirmed=user_confirmed,
        )
        return replace(
            self,
            status=AnalysisRecordStatus.REJECTED,
            version=self.version + 1,
            decided_at=_utc(now),
            decision_reason=_required(reason, "decision reason"),
        )


@dataclass(frozen=True, slots=True)
class ComparisonFinding:
    kind: ComparisonFindingKind
    statement: str
    annotation_ids: tuple[UUID, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", ComparisonFindingKind(self.kind))
        object.__setattr__(self, "statement", _required(self.statement, "finding statement"))
        object.__setattr__(self, "annotation_ids", tuple(dict.fromkeys(self.annotation_ids)))


@dataclass(frozen=True, slots=True)
class NextResearchStep:
    kind: str
    action: str
    priority: str = "medium"

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _required(self.kind, "next step kind", limit=32))
        object.__setattr__(self, "action", _required(self.action, "next step action"))
        if self.kind not in {
            "interview",
            "observation",
            "material_collection",
            "research_question",
        }:
            raise ValueError("invalid next step kind")
        if self.priority not in {"high", "medium", "low"}:
            raise ValueError("invalid next step priority")


@dataclass(frozen=True, slots=True)
class CaseComparison:
    comparison_id: UUID
    user_id: UUID
    task_id: UUID
    title: str
    question: str
    case_labels: tuple[str, ...]
    time_labels: tuple[str, ...]
    findings: tuple[ComparisonFinding, ...]
    competing_explanations: tuple[str, ...]
    evidence_gaps: tuple[str, ...]
    next_steps: tuple[NextResearchStep, ...]
    theory_implication: str
    source: str
    status: AnalysisRecordStatus
    version: int
    created_at: datetime
    conversation_id: UUID | None = None
    agent_run_id: UUID | None = None
    agent_turn_id: UUID | None = None
    tool_call_id: str | None = None
    decided_at: datetime | None = None
    decision_reason: str | None = None

    @classmethod
    def create(
        cls,
        *,
        comparison_id: UUID | None = None,
        user_id: UUID,
        task_id: UUID,
        title: str,
        question: str,
        case_labels: tuple[str, ...],
        time_labels: tuple[str, ...] = (),
        findings: tuple[ComparisonFinding, ...],
        competing_explanations: tuple[str, ...] = (),
        evidence_gaps: tuple[str, ...] = (),
        next_steps: tuple[NextResearchStep, ...] = (),
        theory_implication: str,
        now: datetime,
        source: str = "agent",
        conversation_id: UUID | None = None,
        agent_run_id: UUID | None = None,
        agent_turn_id: UUID | None = None,
        tool_call_id: str | None = None,
    ) -> CaseComparison:
        normalized_cases = tuple(_required(item, "case label", limit=256) for item in case_labels)
        if len(set(normalized_cases)) < 2:
            raise ValueError("comparison requires at least two cases")
        normalized_times = tuple(
            _required(item, "time label", limit=256) for item in time_labels
        )
        if normalized_times and len(set(normalized_times)) < 2:
            raise ValueError("comparison requires at least two time labels")
        if not findings:
            raise ValueError("comparison requires findings")
        return cls(
            comparison_id=comparison_id or uuid4(),
            user_id=user_id,
            task_id=task_id,
            title=_required(title, "comparison title", limit=512),
            question=_required(question, "comparison question"),
            case_labels=normalized_cases,
            time_labels=normalized_times,
            findings=findings,
            competing_explanations=tuple(
                _required(item, "competing explanation") for item in competing_explanations
            ),
            evidence_gaps=tuple(_required(item, "evidence gap") for item in evidence_gaps),
            next_steps=next_steps,
            theory_implication=_required(theory_implication, "theory implication"),
            source=_required(source, "comparison source", limit=32),
            status=AnalysisRecordStatus.CANDIDATE,
            version=1,
            created_at=_utc(now),
            conversation_id=conversation_id,
            agent_run_id=agent_run_id,
            agent_turn_id=agent_turn_id,
            tool_call_id=(
                _required(tool_call_id, "tool_call_id", limit=512)
                if tool_call_id is not None
                else None
            ),
        )

    def confirm(
        self,
        *,
        user_confirmed: bool,
        expected_version: int,
        reason: str,
        now: datetime,
    ) -> CaseComparison:
        _require_candidate_decision(
            status=self.status,
            version=self.version,
            expected_version=expected_version,
            user_confirmed=user_confirmed,
        )
        return replace(
            self,
            status=AnalysisRecordStatus.CONFIRMED,
            version=self.version + 1,
            decided_at=_utc(now),
            decision_reason=_required(reason, "decision reason"),
        )

    def reject(
        self,
        *,
        user_confirmed: bool,
        expected_version: int,
        reason: str,
        now: datetime,
    ) -> CaseComparison:
        _require_candidate_decision(
            status=self.status,
            version=self.version,
            expected_version=expected_version,
            user_confirmed=user_confirmed,
        )
        return replace(
            self,
            status=AnalysisRecordStatus.REJECTED,
            version=self.version + 1,
            decided_at=_utc(now),
            decision_reason=_required(reason, "decision reason"),
        )


@dataclass(frozen=True, slots=True)
class ConfirmedComparisonEvidence:
    """One confirmed, source-anchored finding ready for ResearchMap and M4 adapters."""

    evidence_ref_id: str
    comparison_id: UUID
    finding_kind: ComparisonFindingKind
    statement: str
    annotation_id: UUID
    material_id: UUID
    parse_id: UUID
    segment_id: str
    quote: str
    locator: MaterialLocator
    case_label: str | None
    observed_at: str | None


@dataclass(frozen=True, slots=True)
class ConfirmedComparisonProjection:
    """Owner-scoped, confirmed-only boundary for downstream research stages."""

    schema_version: str
    task_id: UUID
    content_hash: str
    comparisons: tuple[CaseComparison, ...]
    evidence_items: tuple[ConfirmedComparisonEvidence, ...]
    research_map_patch: dict[str, list[dict[str, object]]]

    @classmethod
    def create(
        cls,
        *,
        task_id: UUID,
        comparisons: tuple[CaseComparison, ...],
        evidence_items: tuple[ConfirmedComparisonEvidence, ...],
        research_map_patch: dict[str, list[dict[str, object]]],
    ) -> ConfirmedComparisonProjection:
        import hashlib
        import json

        payload = {
            "schema_version": "research-comparison-projection-v1",
            "task_id": str(task_id),
            "comparisons": [asdict(item) for item in comparisons],
            "evidence_items": [asdict(item) for item in evidence_items],
            "research_map_patch": research_map_patch,
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=_handoff_json,
        )
        return cls(
            schema_version="research-comparison-projection-v1",
            task_id=task_id,
            content_hash=hashlib.sha256(canonical.encode()).hexdigest(),
            comparisons=comparisons,
            evidence_items=evidence_items,
            research_map_patch=research_map_patch,
        )


@dataclass(frozen=True, slots=True)
class ResearchAnalysisHandoff:
    """Immutable, confirmed-only input for the research map, M4, and M5."""

    schema_version: str
    task_id: UUID
    content_hash: str
    annotations: tuple[AnalysisAnnotation, ...]
    codes: tuple[AnalysisCode, ...]
    memos: tuple[AnalysisMemo, ...]
    comparisons: tuple[CaseComparison, ...]
    unavailable_annotation_ids: tuple[UUID, ...] = ()

    @classmethod
    def create(
        cls,
        *,
        task_id: UUID,
        annotations: tuple[AnalysisAnnotation, ...],
        codes: tuple[AnalysisCode, ...],
        memos: tuple[AnalysisMemo, ...],
        comparisons: tuple[CaseComparison, ...],
        unavailable_annotation_ids: tuple[UUID, ...] = (),
    ) -> ResearchAnalysisHandoff:
        import hashlib
        import json

        payload = {
            "schema_version": "research-analysis-v1",
            "task_id": str(task_id),
            "annotations": [asdict(item) for item in annotations],
            "codes": [asdict(item) for item in codes],
            "memos": [asdict(item) for item in memos],
            "comparisons": [asdict(item) for item in comparisons],
            "unavailable_annotation_ids": [str(item) for item in unavailable_annotation_ids],
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=_handoff_json,
        )
        return cls(
            schema_version="research-analysis-v1",
            task_id=task_id,
            content_hash=hashlib.sha256(canonical.encode()).hexdigest(),
            annotations=annotations,
            codes=codes,
            memos=memos,
            comparisons=comparisons,
            unavailable_annotation_ids=unavailable_annotation_ids,
        )


def _handoff_json(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return _utc(value).isoformat()
    enum_value = getattr(value, "value", None)
    if enum_value is not None:
        return enum_value
    raise TypeError(f"unsupported analysis handoff value: {type(value).__name__}")
