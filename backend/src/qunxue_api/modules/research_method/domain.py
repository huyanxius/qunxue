"""Approval-gated, versioned research method plans."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4


class MethodKind(StrEnum):
    QUALITATIVE = "qualitative"
    QUANTITATIVE = "quantitative"
    MIXED = "mixed"
    UNDECIDED = "undecided"


class MethodPlanStatus(StrEnum):
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    CONFIRMED = "confirmed"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class MethodPlanSection:
    key: str
    title: str
    content: str
    source: str = "system"

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.title.strip() or not self.content.strip():
            raise ValueError("method plan section requires key, title, and content")
        if self.source not in {"system", "user"}:
            raise ValueError("method plan section source must be system or user")


@dataclass(frozen=True, slots=True)
class MethodPlanConstraints:
    material_constraints: tuple[str, ...]
    ethical_constraints: tuple[str, ...]
    theory_concepts: tuple[str, ...] = ()
    evidence_ref_ids: tuple[str, ...] = ()
    knowledge_release_id: str | None = None


@dataclass(frozen=True, slots=True)
class MethodPlanEvidenceRef:
    """Framework/theory evidence copied into the plan as immutable provenance."""

    evidence_ref_id: str
    source_id: str
    source_kind: str
    knowledge_release_id: str | None = None
    annotation_id: str | None = None
    material_id: str | None = None
    parse_id: str | None = None
    segment_id: str | None = None
    locator: str | None = None

    def __post_init__(self) -> None:
        if not self.evidence_ref_id.strip() or not self.source_id.strip():
            raise ValueError("method plan evidence requires an id and source")
        if not self.source_kind.strip():
            raise ValueError("method plan evidence requires a source kind")


@dataclass(frozen=True, slots=True)
class MethodPlanContextItem:
    """One exact framework/theory section retained for downstream method design."""

    key: str
    title: str
    content: str
    evidence_refs: tuple[MethodPlanEvidenceRef, ...] = ()

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.title.strip() or not self.content.strip():
            raise ValueError("method plan context requires key, title, and content")


@dataclass(frozen=True, slots=True)
class MethodPlanReview:
    review_id: UUID
    note: str
    blocking: bool
    created_at: datetime
    resolved_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class MethodPlanSnapshot:
    plan_id: UUID
    task_id: UUID
    framework_id: UUID
    framework_version: int
    theory_plan_id: UUID
    theory_plan_version: int
    method_kind: MethodKind
    decision_source: str
    rationale: str
    research_question: str
    theory_summary: str
    shared_constraints: MethodPlanConstraints
    sections: tuple[MethodPlanSection, ...]
    reviews: tuple[MethodPlanReview, ...]
    status: MethodPlanStatus
    version: int
    revision_id: UUID
    change_summary: str
    actor: str
    created_at: datetime
    restored_from_version: int | None = None
    stale_reason: str | None = None
    confirmed_at: datetime | None = None
    shared_context: tuple[MethodPlanContextItem, ...] = ()

    @property
    def unresolved_blocking_reviews(self) -> tuple[MethodPlanReview, ...]:
        return tuple(item for item in self.reviews if item.blocking and item.resolved_at is None)


class MethodPlanRepository(Protocol):
    def add(self, snapshot: MethodPlanSnapshot) -> MethodPlanSnapshot: ...
    def latest_for_task(self, task_id: UUID) -> MethodPlanSnapshot | None: ...
    def latest(self, plan_id: UUID) -> MethodPlanSnapshot | None: ...
    def get_version(self, plan_id: UUID, version: int) -> MethodPlanSnapshot | None: ...
    def list_versions(self, plan_id: UUID) -> tuple[MethodPlanSnapshot, ...]: ...
    def mark_stale(self, plan_id: UUID, reason: str) -> MethodPlanSnapshot | None: ...


class MethodPlanService:
    def __init__(self, repository: MethodPlanRepository) -> None:
        self._repository = repository

    @classmethod
    def in_memory(cls) -> MethodPlanService:
        return cls(_MemoryMethodPlanRepository())

    def create(
        self,
        *,
        task_id: UUID,
        framework_id: UUID,
        framework_version: int,
        theory_plan_id: UUID,
        theory_plan_version: int,
        research_question: str,
        theory_summary: str,
        material_constraints: tuple[str, ...],
        ethical_constraints: tuple[str, ...],
        theory_concepts: tuple[str, ...] = (),
        evidence_ref_ids: tuple[str, ...] = (),
        knowledge_release_id: str | None = None,
        shared_context: tuple[MethodPlanContextItem, ...] = (),
        method_kind: MethodKind,
        framework_confirmed: bool = True,
        now: datetime | None = None,
    ) -> MethodPlanSnapshot:
        if not framework_confirmed:
            raise ValueError("confirmed research framework is required")
        existing = self._repository.latest_for_task(task_id)
        if (
            existing is not None
            and existing.status is not MethodPlanStatus.STALE
            and existing.framework_id == framework_id
            and existing.framework_version == framework_version
            and existing.theory_plan_id == theory_plan_id
            and existing.theory_plan_version == theory_plan_version
        ):
            return existing
        stamp = _utc(now or datetime.now(UTC))
        kind = MethodKind(method_kind)
        plan_id = existing.plan_id if existing is not None else uuid4()
        version = existing.version + 1 if existing is not None else 1
        return self._repository.add(
            MethodPlanSnapshot(
                plan_id=plan_id,
                task_id=task_id,
                framework_id=framework_id,
                framework_version=framework_version,
                theory_plan_id=theory_plan_id,
                theory_plan_version=theory_plan_version,
                method_kind=kind,
                decision_source="system_recommendation",
                rationale="系统根据已确认研究框架生成方法路径草案，等待用户选择或暂缓。",
                research_question=_required(research_question, "research question"),
                theory_summary=_required(theory_summary, "theory summary"),
                shared_constraints=MethodPlanConstraints(
                    tuple(_clean_list(material_constraints)),
                    tuple(_clean_list(ethical_constraints)),
                    tuple(_clean_list(theory_concepts)),
                    tuple(_clean_list(evidence_ref_ids)),
                    knowledge_release_id.strip() if knowledge_release_id else None,
                ),
                sections=_default_sections(kind, shared_context=shared_context),
                reviews=(),
                status=MethodPlanStatus.DRAFT,
                version=version,
                revision_id=uuid4(),
                change_summary=(
                    "基于更新后的研究框架重建方法计划"
                    if existing is not None
                    else "创建方法计划草案"
                ),
                actor="system",
                created_at=stamp,
                shared_context=tuple(shared_context),
            )
        )

    def get(self, plan_id: UUID) -> MethodPlanSnapshot:
        value = self._repository.latest(plan_id)
        if value is None:
            raise LookupError(plan_id)
        return value

    def get_version(self, plan_id: UUID, version: int) -> MethodPlanSnapshot:
        value = self._repository.get_version(plan_id, version)
        if value is None:
            raise LookupError((plan_id, version))
        return value

    def latest_for_task(self, task_id: UUID) -> MethodPlanSnapshot | None:
        return self._repository.latest_for_task(task_id)

    def list_versions(self, plan_id: UUID) -> tuple[MethodPlanSnapshot, ...]:
        values = self._repository.list_versions(plan_id)
        if not values:
            raise LookupError(plan_id)
        return values

    def revise(
        self,
        *,
        plan_id: UUID,
        expected_version: int,
        method_kind: MethodKind,
        sections: tuple[MethodPlanSection, ...],
        rationale: str,
        change_summary: str,
        actor: str,
    ) -> MethodPlanSnapshot:
        current = self.get(plan_id)
        _assert_version(current, expected_version)
        if current.status is MethodPlanStatus.CONFIRMED:
            raise ValueError("confirmed method plan must be restored before revision")
        if current.status is MethodPlanStatus.STALE:
            raise ValueError("stale method plan must be recreated from the current framework")
        kind = MethodKind(method_kind)
        normalized_sections = _normalize_sections(
            kind, sections, shared_context=current.shared_context
        )
        updated = replace(
            current,
            method_kind=kind,
            decision_source="user_decision",
            rationale=_required(rationale, "rationale"),
            sections=normalized_sections,
            reviews=current.reviews,
            status=(
                MethodPlanStatus.UNDER_REVIEW
                if any(item.resolved_at is None for item in current.reviews)
                else MethodPlanStatus.DRAFT
            ),
            version=current.version + 1,
            revision_id=uuid4(),
            change_summary=_required(change_summary, "change summary"),
            actor=actor.strip() or "user",
            created_at=datetime.now(UTC),
            restored_from_version=None,
            stale_reason=None,
            confirmed_at=None,
            shared_context=current.shared_context,
        )
        return self._repository.add(updated)

    def submit_review(
        self, *, plan_id: UUID, expected_version: int, note: str, blocking: bool
    ) -> MethodPlanSnapshot:
        current = self.get(plan_id)
        _assert_version(current, expected_version)
        if current.status in {MethodPlanStatus.CONFIRMED, MethodPlanStatus.STALE}:
            raise ValueError("method plan cannot be reviewed in its current state")
        review = MethodPlanReview(
            uuid4(), _required(note, "review note"), blocking, datetime.now(UTC)
        )
        return self._repository.add(
            replace(
                current,
                reviews=(*current.reviews, review),
                status=MethodPlanStatus.UNDER_REVIEW,
                version=current.version + 1,
                revision_id=uuid4(),
                change_summary="提交方法计划审校意见",
                actor="reviewer",
                created_at=datetime.now(UTC),
            )
        )

    def resolve_review(
        self, *, plan_id: UUID, expected_version: int, review_id: UUID, reason: str
    ) -> MethodPlanSnapshot:
        current = self.get(plan_id)
        _assert_version(current, expected_version)
        if current.status in {MethodPlanStatus.CONFIRMED, MethodPlanStatus.STALE}:
            raise ValueError("method plan review cannot be resolved in its current state")
        if not any(item.review_id == review_id for item in current.reviews):
            raise LookupError(review_id)
        stamp = datetime.now(UTC)
        reviews = tuple(
            replace(item, resolved_at=stamp) if item.review_id == review_id else item
            for item in current.reviews
        )
        return self._repository.add(
            replace(
                current,
                reviews=reviews,
                status=MethodPlanStatus.DRAFT,
                version=current.version + 1,
                revision_id=uuid4(),
                change_summary=_required(reason, "resolution reason"),
                actor="reviewer",
                created_at=stamp,
            )
        )

    def confirm(self, *, plan_id: UUID, expected_version: int, reason: str) -> MethodPlanSnapshot:
        current = self.get(plan_id)
        _assert_version(current, expected_version)
        if current.status is MethodPlanStatus.STALE:
            raise ValueError("stale method plan cannot be confirmed")
        if current.unresolved_blocking_reviews:
            raise ValueError("blocking method plan review must be resolved before confirmation")
        if current.status is MethodPlanStatus.CONFIRMED:
            raise ValueError("method plan is already confirmed")
        missing = _missing_user_sections(current)
        if missing:
            raise ValueError(
                "method plan requires user decisions for: " + ", ".join(missing)
            )
        stamp = datetime.now(UTC)
        return self._repository.add(
            replace(
                current,
                status=MethodPlanStatus.CONFIRMED,
                version=current.version + 1,
                revision_id=uuid4(),
                change_summary=_required(reason, "confirmation reason"),
                actor="user",
                created_at=stamp,
                confirmed_at=stamp,
            )
        )

    def restore(
        self, *, plan_id: UUID, source_version: int, expected_version: int, reason: str
    ) -> MethodPlanSnapshot:
        current = self.get(plan_id)
        _assert_version(current, expected_version)
        if current.status is MethodPlanStatus.STALE:
            raise ValueError("stale method plan must be recreated from the current framework")
        source = self._repository.get_version(plan_id, source_version)
        if source is None:
            raise LookupError(source_version)
        if (
            source.framework_id != current.framework_id
            or source.framework_version != current.framework_version
            or source.theory_plan_id != current.theory_plan_id
            or source.theory_plan_version != current.theory_plan_version
        ):
            raise ValueError("method plan version is based on outdated research evidence")
        return self._repository.add(
            replace(
                source,
                status=MethodPlanStatus.DRAFT,
                version=current.version + 1,
                revision_id=uuid4(),
                change_summary=_required(reason, "restore reason"),
                actor="user",
                created_at=datetime.now(UTC),
                restored_from_version=source_version,
                confirmed_at=None,
                # Reviews belong to the plan lifecycle, not to a discarded
                # section payload.  Keeping them prevents restore from
                # silently bypassing an unresolved blocking concern.
                reviews=current.reviews,
                stale_reason=None,
            )
        )

    def mark_stale(self, *, plan_id: UUID, reason: str) -> MethodPlanSnapshot:
        current = self.get(plan_id)
        if current.status is MethodPlanStatus.STALE:
            return current
        return self._repository.mark_stale(plan_id, _required(reason, "stale reason")) or current

    def mark_stale_for_task(self, *, task_id: UUID, reason: str) -> MethodPlanSnapshot | None:
        current = self._repository.latest_for_task(task_id)
        if current is None:
            return None
        return self.mark_stale(plan_id=current.plan_id, reason=reason)


class _MemoryMethodPlanRepository:
    def __init__(self) -> None:
        self._versions: dict[UUID, list[MethodPlanSnapshot]] = {}

    def add(self, snapshot: MethodPlanSnapshot) -> MethodPlanSnapshot:
        versions = self._versions.setdefault(snapshot.plan_id, [])
        if versions and snapshot.version <= versions[-1].version:
            return versions[-1]
        versions.append(snapshot)
        return snapshot

    def latest_for_task(self, task_id: UUID) -> MethodPlanSnapshot | None:
        values = [
            item
            for versions in self._versions.values()
            for item in versions[-1:]
            if item.task_id == task_id
        ]
        return max(values, key=lambda item: item.created_at, default=None)

    def latest(self, plan_id: UUID) -> MethodPlanSnapshot | None:
        return self._versions.get(plan_id, [])[-1] if self._versions.get(plan_id) else None

    def get_version(self, plan_id: UUID, version: int) -> MethodPlanSnapshot | None:
        return next(
            (item for item in self._versions.get(plan_id, []) if item.version == version), None
        )

    def list_versions(self, plan_id: UUID) -> tuple[MethodPlanSnapshot, ...]:
        return tuple(reversed(self._versions.get(plan_id, [])))

    def mark_stale(self, plan_id: UUID, reason: str) -> MethodPlanSnapshot | None:
        current = self.latest(plan_id)
        if current is None:
            return None
        stale = replace(
            current,
            status=MethodPlanStatus.STALE,
            version=current.version + 1,
            revision_id=uuid4(),
            change_summary="方法计划因依据版本变化而失效",
            actor="system",
            created_at=datetime.now(UTC),
            stale_reason=reason,
            confirmed_at=None,
        )
        self._versions[plan_id].append(stale)
        return stale


def _required(value: str, name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} is required")
    return normalized


def _clean_list(values: tuple[str, ...]) -> list[str]:
    return [_required(value, "constraint") for value in values if value.strip()]


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _assert_version(current: MethodPlanSnapshot, expected: int) -> None:
    if current.version != expected:
        raise ValueError("stale method plan version")


def _default_sections(
    kind: MethodKind,
    *,
    shared_context: tuple[MethodPlanContextItem, ...] = (),
) -> tuple[MethodPlanSection, ...]:
    common = [
        MethodPlanSection(
            "design", "研究设计", "请说明研究设计、时间范围、案例边界与研究对象的关系。"
        ),
        MethodPlanSection(
            "ethics", "伦理与风险", "请说明去标识化、最小必要使用、撤回和敏感内容处理。"
        ),
    ]
    if kind is MethodKind.QUALITATIVE:
        common.extend(
            [
                MethodPlanSection(
                    "research_object",
                    "研究对象",
                    "请界定研究对象、场域与纳入/排除边界。",
                ),
                MethodPlanSection(
                    "sampling",
                    "取样策略",
                    "请说明案例/参与者取样逻辑、数量或停止条件。",
                ),
                MethodPlanSection(
                    "material_acquisition",
                    "材料获取",
                    "请说明材料来源、获取步骤、授权范围与缺失材料的处理。",
                ),
                MethodPlanSection(
                    "analysis", "质性分析路径", "说明编码、分析备忘、跨案例比较和理论检验路径。"
                ),
                MethodPlanSection(
                    "credibility", "可信度策略", "说明三角互证、反例检视、审校与审计轨迹。"
                ),
                MethodPlanSection("reflexivity", "反身性", "记录研究者位置、假设和可能影响。"),
            ]
        )
    elif kind is MethodKind.QUANTITATIVE:
        common.extend(
            [
                MethodPlanSection(
                    "operationalization", "概念操作化", "请把理论概念映射为可观察变量及其操作定义。"
                ),
                MethodPlanSection(
                    "variables_indicators",
                    "变量与指标",
                    "请列出自变量、因变量、控制变量、指标和编码规则。",
                ),
                MethodPlanSection(
                    "hypotheses", "研究假设", "请写出可检验假设、方向与理论依据。"
                ),
                MethodPlanSection(
                    "measurement", "测量与质量", "请说明量表/测量方式、信度效度与测量误差处理。"
                ),
                MethodPlanSection(
                    "sampling", "样本计划", "请说明总体、抽样方法、样本量依据与代表性边界。"
                ),
                MethodPlanSection(
                    "analysis_plan", "统计分析计划", "请说明模型、估计策略、缺失处理与稳健性检验。"
                ),
                MethodPlanSection(
                    "conditions", "适用条件", "请说明识别假设、模型前提与不满足时的处理。"
                ),
                MethodPlanSection(
                    "limitations", "局限", "请说明样本、测量、因果解释与外推的局限。"
                ),
            ]
        )
    elif kind is MethodKind.MIXED:
        common.extend(
            [
                MethodPlanSection(
                    "rationale",
                    "采用理由",
                    "请说明为何需要同时采用质性与定量方法，以及各自回答的问题。",
                ),
                MethodPlanSection(
                    "sequence", "先后顺序", "请说明两类方法的先后、并行关系与阶段交接。"
                ),
                MethodPlanSection(
                    "weight", "方法权重", "请说明两类证据在整体推理中的相对权重与调整原则。"
                ),
                MethodPlanSection(
                    "integration",
                    "混合整合",
                    "请说明在何处、以何种对象或矩阵整合两类结果。",
                ),
                MethodPlanSection(
                    "conflict_handling",
                    "冲突处理",
                    "请说明质性与定量结果冲突时的核查、解释与保留边界。",
                ),
                MethodPlanSection(
                    "common_conclusions",
                    "共同结论边界",
                    "请说明两类证据可以共同支持什么，以及不能合并推出什么。",
                )
            ]
        )
    else:
        common.extend(
            [
                MethodPlanSection(
                    "decision", "方法决定", "尚未决定方法；保留比较条件和下一次决定所需信息。"
                )
            ]
        )
    return tuple(
        replace(
            section,
            content=_contextual_prompt(section.key, section.content, shared_context),
        )
        for section in common
    )


def _normalize_sections(
    kind: MethodKind,
    sections: tuple[MethodPlanSection, ...],
    *,
    shared_context: tuple[MethodPlanContextItem, ...] = (),
) -> tuple[MethodPlanSection, ...]:
    provided: dict[str, MethodPlanSection] = {}
    for section in sections:
        if section.key in provided:
            raise ValueError(f"duplicate method plan section: {section.key}")
        provided[section.key] = section
    defaults = _default_sections(kind, shared_context=shared_context)
    normalized = [
        replace(
            default,
            **{
                "content": provided[default.key].content,
                "source": provided[default.key].source,
            },
        )
        if default.key in provided
        else default
        for default in defaults
    ]
    extras = [section for section in sections if section.key not in {item.key for item in defaults}]
    return tuple((*normalized, *extras))


_CONTEXT_KEYS_BY_SECTION: dict[str, tuple[str, ...]] = {
    "design": (
        "methodology",
        "research_object_and_field",
        "questions_or_hypotheses",
        "theory_plan",
    ),
    "research_object": ("research_object_and_field", "theory_plan"),
    "sampling": ("research_object_and_field", "sample_and_sources", "theory_plan"),
    "material_acquisition": ("sample_and_sources", "evidence_gaps", "theory_plan"),
    "analysis": ("analysis_steps", "mechanisms", "questions_or_hypotheses", "theory_plan"),
    "credibility": ("evidence_gaps", "limitations", "analysis_steps", "theory_plan"),
    "reflexivity": ("research_object_and_field", "ethics", "limitations", "theory_plan"),
    "ethics": ("ethics", "sample_and_sources", "theory_plan"),
    "operationalization": ("core_concepts", "mechanisms", "questions_or_hypotheses", "theory_plan"),
    "variables_indicators": ("core_concepts", "mechanisms", "theory_plan"),
    "hypotheses": ("questions_or_hypotheses", "mechanisms", "theory_plan"),
    "measurement": ("core_concepts", "limitations", "theory_plan"),
    "analysis_plan": ("methodology", "analysis_steps", "limitations", "theory_plan"),
    "conditions": ("methodology", "limitations", "evidence_gaps", "theory_plan"),
    "limitations": ("limitations", "evidence_gaps", "theory_plan"),
    "rationale": ("research_question", "theoretical_perspective", "mechanisms", "theory_plan"),
    "sequence": ("methodology", "analysis_steps", "theory_plan"),
    "weight": ("theoretical_perspective", "core_concepts", "evidence_gaps", "theory_plan"),
    "integration": ("analysis_steps", "questions_or_hypotheses", "theory_plan"),
    "conflict_handling": ("evidence_gaps", "limitations", "theory_plan"),
    "common_conclusions": ("research_question", "limitations", "evidence_gaps", "theory_plan"),
    "decision": ("research_question", "methodology", "theoretical_perspective", "theory_plan"),
}


def _contextual_prompt(
    key: str,
    prompt: str,
    shared_context: tuple[MethodPlanContextItem, ...],
) -> str:
    wanted = set(_CONTEXT_KEYS_BY_SECTION.get(key, ()))
    if not wanted:
        return prompt
    context = [item for item in shared_context if item.key in wanted]
    if not context:
        return prompt
    lines = [prompt, "", "当前已确认依据（系统建议，必须由用户改写或确认）："]
    for item in context:
        refs = ", ".join(ref.evidence_ref_id for ref in item.evidence_refs)
        suffix = f"；证据引用：{refs}" if refs else ""
        lines.append(f"- {item.title}：{item.content}{suffix}")
    return "\n".join(lines)


def _missing_user_sections(plan: MethodPlanSnapshot) -> tuple[str, ...]:
    """Confirmation requires every method-specific decision to be user-owned.

    System prompts remain useful while drafting, but they are not research
    decisions.  Keeping the check in the domain prevents an API or UI caller
    from promoting untouched suggestions into a formal plan.
    """

    required = {
        MethodKind.QUALITATIVE: (
            "design",
            "research_object",
            "sampling",
            "material_acquisition",
            "analysis",
            "credibility",
            "reflexivity",
            "ethics",
        ),
        MethodKind.QUANTITATIVE: (
            "design",
            "operationalization",
            "variables_indicators",
            "hypotheses",
            "measurement",
            "sampling",
            "analysis_plan",
            "conditions",
            "limitations",
            "ethics",
        ),
        MethodKind.MIXED: (
            "design",
            "rationale",
            "sequence",
            "weight",
            "integration",
            "conflict_handling",
            "common_conclusions",
            "ethics",
        ),
        MethodKind.UNDECIDED: ("decision",),
    }[plan.method_kind]
    sections = {item.key: item for item in plan.sections}
    return tuple(
        key
        for key in required
        if key not in sections or sections[key].source != "user"
    )
