"""Method-neutral qualitative workspace records built on confirmed analysis.

The records in this module extend the existing annotation, code, memo and
comparison aggregate. They deliberately carry only opaque case references and
stable analysis IDs; material identity and case identity remain owned by their
upstream modules.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from qunxue_api.modules.research_analysis.domain import (
    AnalysisRecordStatus,
    ComparisonFindingKind,
)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _required(value: str, name: str, *, limit: int = 20_000) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} is required")
    if len(normalized) > limit:
        raise ValueError(f"{name} is too long")
    return normalized


def _distinct_text(values: tuple[str, ...], name: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_required(item, name) for item in values))


def _distinct_ids(values: tuple[UUID, ...]) -> tuple[UUID, ...]:
    return tuple(dict.fromkeys(values))


def _require_candidate_decision(
    *,
    status: AnalysisRecordStatus,
    version: int,
    expected_version: int,
    user_confirmed: bool,
) -> None:
    if not user_confirmed:
        raise ValueError("user confirmation is required")
    if version != expected_version:
        raise ValueError("stale theme version")
    if status is not AnalysisRecordStatus.CANDIDATE:
        raise ValueError("theme is already decided")


class CodebookLifecycle(StrEnum):
    ACTIVE = "active"
    MERGED = "merged"
    SPLIT = "split"
    RETIRED = "retired"


class MemoTargetKind(StrEnum):
    PROJECT = "project"
    MATERIAL = "material"
    SOURCE = "source"
    CODE = "code"
    CASE = "case"
    COMPARISON = "comparison"
    DRAFT = "draft"


class MatrixSubjectKind(StrEnum):
    CODE = "code"
    THEME = "theme"


class QualitativeMethod(StrEnum):
    THEMATIC_ANALYSIS = "thematic_analysis"
    GROUNDED_THEORY = "grounded_theory"
    ETHNOGRAPHY = "ethnography"
    CASE_STUDY = "case_study"
    NARRATIVE_RESEARCH = "narrative_research"
    DISCOURSE_CONVERSATION_ANALYSIS = "discourse_conversation_analysis"
    LITERATURE_REVIEW = "literature_review"


@dataclass(frozen=True, slots=True)
class QualitativeMethodPreset:
    method: QualitativeMethod
    label: str
    primary_view: str
    matrix_axes: tuple[str, str]
    prompts: str
    guardrails: str


def qualitative_method_presets() -> dict[QualitativeMethod, QualitativeMethodPreset]:
    """Return view defaults, never a method decision or a second analysis engine."""

    values = (
        QualitativeMethodPreset(
            method=QualitativeMethod.THEMATIC_ANALYSIS,
            label="主题分析",
            primary_view="themes",
            matrix_axes=("个案", "主题"),
            prompts="从跨材料的共享意义模式发展候选主题，并回看全部相关原文。",
            guardrails="代码不等于主题；频次不自动构成主题，主题须有中心组织概念。",
        ),
        QualitativeMethodPreset(
            method=QualitativeMethod.GROUNDED_THEORY,
            label="扎根理论",
            primary_view="constant_comparison",
            matrix_axes=("比较单元", "概念或范畴"),
            prompts="持续比较事件、个案与范畴，用备忘记录概念发展，并明确理论抽样问题。",
            guardrails="不把预设代码直接当理论，也不替研究者宣布理论饱和。",
        ),
        QualitativeMethodPreset(
            method=QualitativeMethod.ETHNOGRAPHY,
            label="民族志",
            primary_view="field_context",
            matrix_axes=("场域", "时点"),
            prompts="并置观察、参与位置、场域关系与研究者反思，保留情境厚度。",
            guardrails="描述性记录与研究者反思必须分开，片段不能脱离场域和时点。",
        ),
        QualitativeMethodPreset(
            method=QualitativeMethod.CASE_STUDY,
            label="个案研究",
            primary_view="case_matrix",
            matrix_axes=("个案", "分析命题"),
            prompts="先保持个案整体性，再做个案内解释与跨个案比较。",
            guardrails="属性用于筛选与比较，不把个案压缩为变量行。",
        ),
        QualitativeMethodPreset(
            method=QualitativeMethod.NARRATIVE_RESEARCH,
            label="叙事研究",
            primary_view="narrative_sequence",
            matrix_axes=("个案", "叙事时序"),
            prompts="关注情节、转折、叙述位置与时间组织，比较叙事如何建构经验。",
            guardrails="不把叙事拆成失去顺序与讲述位置的主题碎片。",
        ),
        QualitativeMethodPreset(
            method=QualitativeMethod.DISCOURSE_CONVERSATION_ANALYSIS,
            label="话语/会话分析",
            primary_view="sequential_excerpt",
            matrix_axes=("互动场景", "话语实践"),
            prompts="保留相邻话轮、措辞、停顿与回应位置，检查话语如何完成社会行动。",
            guardrails="引用必须保留轮次与语境；词频和脱离顺序的摘句不能代替分析。",
        ),
        QualitativeMethodPreset(
            method=QualitativeMethod.LITERATURE_REVIEW,
            label="文献综述",
            primary_view="source_concept_matrix",
            matrix_axes=("文献", "概念"),
            prompts="并列研究问题、概念、证据与方法限制，标出共识、争论和知识缺口。",
            guardrails="文献代码不自动成为综述结论，来源质量与适用边界须显式保留。",
        ),
    )
    return {item.method: item for item in values}


@dataclass(frozen=True, slots=True)
class CodebookEntry:
    user_id: UUID
    task_id: UUID
    code_id: UUID
    inclusion_rules: tuple[str, ...]
    exclusion_rules: tuple[str, ...]
    parent_code_id: UUID | None
    positive_example_annotation_ids: tuple[UUID, ...]
    negative_example_annotation_ids: tuple[UUID, ...]
    lifecycle: CodebookLifecycle
    related_code_ids: tuple[UUID, ...]
    version: int
    updated_at: datetime
    revision_reason: str

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        task_id: UUID,
        code_id: UUID,
        inclusion_rules: tuple[str, ...],
        exclusion_rules: tuple[str, ...],
        parent_code_id: UUID | None,
        positive_example_annotation_ids: tuple[UUID, ...],
        negative_example_annotation_ids: tuple[UUID, ...],
        now: datetime,
    ) -> CodebookEntry:
        included = _distinct_text(inclusion_rules, "inclusion rule")
        excluded = _distinct_text(exclusion_rules, "exclusion rule")
        positive = _distinct_ids(positive_example_annotation_ids)
        negative = _distinct_ids(negative_example_annotation_ids)
        if not included or not excluded:
            raise ValueError("codebook entry requires inclusion and exclusion rules")
        if not positive or not negative:
            raise ValueError("codebook entry requires positive and negative source examples")
        if set(positive) & set(negative):
            raise ValueError("one source annotation cannot be both a positive and negative example")
        if parent_code_id == code_id:
            raise ValueError("code cannot be its own parent")
        return cls(
            user_id=user_id,
            task_id=task_id,
            code_id=code_id,
            inclusion_rules=included,
            exclusion_rules=excluded,
            parent_code_id=parent_code_id,
            positive_example_annotation_ids=positive,
            negative_example_annotation_ids=negative,
            lifecycle=CodebookLifecycle.ACTIVE,
            related_code_ids=(),
            version=1,
            updated_at=_utc(now),
            revision_reason="建立代码本边界",
        )

    def revise(
        self,
        *,
        inclusion_rules: tuple[str, ...],
        exclusion_rules: tuple[str, ...],
        parent_code_id: UUID | None,
        positive_example_annotation_ids: tuple[UUID, ...],
        negative_example_annotation_ids: tuple[UUID, ...],
        expected_version: int,
        now: datetime,
    ) -> CodebookEntry:
        if self.version != expected_version:
            raise ValueError("stale codebook entry version")
        revised = CodebookEntry.create(
            user_id=self.user_id,
            task_id=self.task_id,
            code_id=self.code_id,
            inclusion_rules=inclusion_rules,
            exclusion_rules=exclusion_rules,
            parent_code_id=parent_code_id,
            positive_example_annotation_ids=positive_example_annotation_ids,
            negative_example_annotation_ids=negative_example_annotation_ids,
            now=now,
        )
        return replace(
            revised,
            lifecycle=self.lifecycle,
            related_code_ids=self.related_code_ids,
            version=self.version + 1,
            revision_reason="修订代码本边界",
        )

    def transition(
        self,
        *,
        lifecycle: CodebookLifecycle,
        related_code_ids: tuple[UUID, ...],
        expected_version: int,
        reason: str,
        now: datetime,
    ) -> CodebookEntry:
        if self.version != expected_version:
            raise ValueError("stale codebook entry version")
        normalized_related = _distinct_ids(related_code_ids)
        if (
            lifecycle in {CodebookLifecycle.MERGED, CodebookLifecycle.SPLIT}
            and not normalized_related
        ):
            raise ValueError("merged or split code requires related codes")
        if self.code_id in normalized_related:
            raise ValueError("codebook relation cannot point to itself")
        return replace(
            self,
            lifecycle=CodebookLifecycle(lifecycle),
            related_code_ids=normalized_related,
            version=self.version + 1,
            updated_at=_utc(now),
            revision_reason=_required(reason, "revision reason"),
        )


@dataclass(frozen=True, slots=True)
class AnalysisTheme:
    theme_id: UUID
    user_id: UUID
    task_id: UUID
    label: str
    central_concept: str
    code_ids: tuple[UUID, ...]
    annotation_ids: tuple[UUID, ...]
    source: str
    status: AnalysisRecordStatus
    version: int
    created_at: datetime
    decided_at: datetime | None = None
    decision_reason: str | None = None

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        task_id: UUID,
        label: str,
        central_concept: str,
        code_ids: tuple[UUID, ...],
        annotation_ids: tuple[UUID, ...],
        source: str,
        now: datetime,
        theme_id: UUID | None = None,
    ) -> AnalysisTheme:
        if not code_ids or not annotation_ids:
            raise ValueError("theme requires codes and source annotations")
        value = cls(
            theme_id=theme_id or uuid4(),
            user_id=user_id,
            task_id=task_id,
            label=_required(label, "theme label", limit=512),
            central_concept=_required(central_concept, "theme central concept"),
            code_ids=_distinct_ids(code_ids),
            annotation_ids=_distinct_ids(annotation_ids),
            source=_required(source, "theme source", limit=32),
            status=AnalysisRecordStatus.CANDIDATE,
            version=1,
            created_at=_utc(now),
        )
        if source == "user":
            return value.confirm(
                user_confirmed=True,
                expected_version=1,
                reason="研究者建立并确认",
                now=now,
            )
        return value

    def confirm(
        self,
        *,
        user_confirmed: bool,
        expected_version: int,
        reason: str,
        now: datetime,
    ) -> AnalysisTheme:
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


@dataclass(frozen=True, slots=True)
class AnalysisMemoLink:
    link_id: UUID
    user_id: UUID
    task_id: UUID
    memo_id: UUID
    target_kind: MemoTargetKind
    target_ref: str
    annotation_ids: tuple[UUID, ...]
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        task_id: UUID,
        memo_id: UUID,
        target_kind: MemoTargetKind,
        target_ref: str,
        annotation_ids: tuple[UUID, ...],
        now: datetime,
    ) -> AnalysisMemoLink:
        anchors = _distinct_ids(annotation_ids)
        if not anchors:
            raise ValueError("memo link requires a source annotation")
        return cls(
            link_id=uuid4(),
            user_id=user_id,
            task_id=task_id,
            memo_id=memo_id,
            target_kind=MemoTargetKind(target_kind),
            target_ref=_required(target_ref, "memo target reference", limit=512),
            annotation_ids=anchors,
            created_at=_utc(now),
        )


@dataclass(frozen=True, slots=True)
class AnalysisCaseProfile:
    profile_id: UUID
    user_id: UUID
    task_id: UUID
    case_ref: str
    display_label: str
    attributes: tuple[tuple[str, str], ...]
    summary: str
    annotation_ids: tuple[UUID, ...]
    memo_ids: tuple[UUID, ...]
    version: int
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        task_id: UUID,
        case_ref: str,
        display_label: str,
        attributes: tuple[tuple[str, str], ...],
        summary: str,
        annotation_ids: tuple[UUID, ...],
        memo_ids: tuple[UUID, ...],
        now: datetime,
        profile_id: UUID | None = None,
        version: int = 1,
    ) -> AnalysisCaseProfile:
        anchors = _distinct_ids(annotation_ids)
        if not anchors:
            raise ValueError("case profile requires a source annotation")
        normalized_attributes = tuple(
            dict.fromkeys(
                (
                    _required(name, "case attribute name", limit=128),
                    _required(value, "case attribute value", limit=512),
                )
                for name, value in attributes
            )
        )
        return cls(
            profile_id=profile_id or uuid4(),
            user_id=user_id,
            task_id=task_id,
            case_ref=_required(case_ref, "opaque case reference", limit=512),
            display_label=_required(display_label, "case display label", limit=512),
            attributes=normalized_attributes,
            summary=_required(summary, "case summary", limit=100_000),
            annotation_ids=anchors,
            memo_ids=_distinct_ids(memo_ids),
            version=version,
            updated_at=_utc(now),
        )


@dataclass(frozen=True, slots=True)
class CaseThemeMatrixCell:
    cell_id: UUID
    user_id: UUID
    task_id: UUID
    case_profile_id: UUID
    subject_kind: MatrixSubjectKind
    subject_id: UUID
    summary: str
    annotation_ids: tuple[UUID, ...]
    memo_ids: tuple[UUID, ...]
    finding_kinds: tuple[ComparisonFindingKind, ...]
    version: int
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        user_id: UUID,
        task_id: UUID,
        case_profile_id: UUID,
        subject_kind: MatrixSubjectKind,
        subject_id: UUID,
        summary: str,
        annotation_ids: tuple[UUID, ...],
        memo_ids: tuple[UUID, ...],
        finding_kinds: tuple[ComparisonFindingKind, ...],
        now: datetime,
        cell_id: UUID | None = None,
        version: int = 1,
    ) -> CaseThemeMatrixCell:
        anchors = _distinct_ids(annotation_ids)
        if not anchors:
            raise ValueError("matrix cell requires a source annotation")
        return cls(
            cell_id=cell_id or uuid4(),
            user_id=user_id,
            task_id=task_id,
            case_profile_id=case_profile_id,
            subject_kind=MatrixSubjectKind(subject_kind),
            subject_id=subject_id,
            summary=_required(summary, "matrix summary", limit=100_000),
            annotation_ids=anchors,
            memo_ids=_distinct_ids(memo_ids),
            finding_kinds=tuple(
                dict.fromkeys(ComparisonFindingKind(item) for item in finding_kinds)
            ),
            version=version,
            updated_at=_utc(now),
        )


@dataclass(frozen=True, slots=True)
class MethodPresetSelection:
    user_id: UUID
    task_id: UUID
    method: QualitativeMethod
    version: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CaseThemeMatrix:
    row_profile_ids: tuple[UUID, ...]
    column_subjects: tuple[tuple[MatrixSubjectKind, UUID], ...]
    cells: tuple[CaseThemeMatrixCell, ...]
    attribute_filters: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class QualitativeWorkspaceSnapshot:
    schema_version: str
    task_id: UUID
    content_hash: str
    method_preset: MethodPresetSelection
    codebook_entries: tuple[CodebookEntry, ...]
    memo_links: tuple[AnalysisMemoLink, ...]
    case_profiles: tuple[AnalysisCaseProfile, ...]
    formal_themes: tuple[AnalysisTheme, ...]
    candidate_themes: tuple[AnalysisTheme, ...]
    matrix_cells: tuple[CaseThemeMatrixCell, ...]

    @classmethod
    def create(
        cls,
        *,
        task_id: UUID,
        method_preset: MethodPresetSelection,
        codebook_entries: tuple[CodebookEntry, ...],
        memo_links: tuple[AnalysisMemoLink, ...],
        case_profiles: tuple[AnalysisCaseProfile, ...],
        formal_themes: tuple[AnalysisTheme, ...],
        candidate_themes: tuple[AnalysisTheme, ...],
        matrix_cells: tuple[CaseThemeMatrixCell, ...],
    ) -> QualitativeWorkspaceSnapshot:
        import hashlib
        import json

        payload = {
            "schema_version": "qualitative-workspace-v1",
            "task_id": str(task_id),
            "method_preset": asdict(method_preset),
            "codebook_entries": [asdict(item) for item in codebook_entries],
            "memo_links": [asdict(item) for item in memo_links],
            "case_profiles": [asdict(item) for item in case_profiles],
            "formal_themes": [asdict(item) for item in formal_themes],
            "candidate_themes": [asdict(item) for item in candidate_themes],
            "matrix_cells": [asdict(item) for item in matrix_cells],
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=_snapshot_json,
        )
        return cls(
            schema_version="qualitative-workspace-v1",
            task_id=task_id,
            content_hash=hashlib.sha256(canonical.encode()).hexdigest(),
            method_preset=method_preset,
            codebook_entries=codebook_entries,
            memo_links=memo_links,
            case_profiles=case_profiles,
            formal_themes=formal_themes,
            candidate_themes=candidate_themes,
            matrix_cells=matrix_cells,
        )


def _snapshot_json(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return _utc(value).isoformat()
    enum_value = getattr(value, "value", None)
    if enum_value is not None:
        return enum_value
    raise TypeError(f"unsupported qualitative snapshot value: {type(value).__name__}")
