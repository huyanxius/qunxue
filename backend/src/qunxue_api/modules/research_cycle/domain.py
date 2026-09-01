"""Pure projections that connect confirmed analysis to theory and method work.

The loop never mutates material, QDA, theory, or method records. It copies the
public immutable snapshots into a versioned view, so consumers can show where a
claim came from and decide when a changed basis requires a new human decision.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from uuid import UUID

from qunxue_api.modules.research_analysis import (
    AnalysisCodeStatus,
    AnalysisRecordStatus,
    ComparisonFindingKind,
    ResearchAnalysisHandoff,
)
from qunxue_api.modules.research_materials import (
    MaterialKind,
    ProfessionalMaterialArchiveView,
    ResearchMaterial,
)
from qunxue_api.modules.theory_matching import ConfirmedTheoryPlanSnapshot


class CycleEvidenceKind(StrEnum):
    ANALYTIC_CODE = "analytic_code"
    ANALYTIC_MEMO = "analytic_memo"
    SUPPORT = "support"
    COUNTEREXAMPLE = "counterexample"
    CONTRADICTION = "contradiction"
    COMPETING_EXPLANATION = "competing_explanation"


class GapDestination(StrEnum):
    MATERIAL_SCREENING = "material_screening"
    NEXT_ROUND_SAMPLING = "next_round_sampling"


class ReportingCoverageStatus(StrEnum):
    PRESENT = "present"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class CycleEvidence:
    evidence_ref_id: str
    kind: CycleEvidenceKind
    statement: str
    source_kind: str
    source_id: str
    annotation_id: UUID
    material_id: UUID
    parse_id: UUID
    segment_id: str
    quote: str
    locator: str
    case_label: str | None
    observed_at: str | None
    confirmed: bool = True


@dataclass(frozen=True, slots=True)
class EvidenceGapSuggestion:
    gap_id: str
    source_kind: str
    source_id: str
    description: str
    suggested_action: str
    destination: GapDestination
    priority: str
    analysis_content_hash: str
    theory_plan_id: UUID | None
    theory_plan_version: int | None
    status: str = "open"


@dataclass(frozen=True, slots=True)
class ProjectResearchFacts:
    material_count: int
    material_kinds: tuple[tuple[str, int], ...]
    case_count: int
    case_material_coverage: tuple[tuple[str, int], ...]
    consent_scopes: tuple[tuple[str, int], ...]
    sensitivity_levels: tuple[tuple[str, int], ...]
    pending_deidentification_count: int
    sampling_batches: tuple[str, ...]
    analysis_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class ReportingCoverageHint:
    guideline: str
    item_key: str
    label: str
    status: ReportingCoverageStatus
    message: str
    blocking: bool = False


@dataclass(frozen=True, slots=True)
class ResearchCycleSnapshot:
    schema_version: str
    task_id: UUID
    version: int
    content_hash: str
    analysis_content_hash: str
    theory_plan_id: UUID | None
    theory_plan_version: int | None
    evidence: tuple[CycleEvidence, ...]
    gaps: tuple[EvidenceGapSuggestion, ...]
    project_facts: ProjectResearchFacts
    reporting_hints: tuple[ReportingCoverageHint, ...]
    research_map_patch: dict[str, list[dict[str, object]]]


class ResearchCycleService:
    def analysis_evidence(self, analysis: ResearchAnalysisHandoff) -> tuple[CycleEvidence, ...]:
        """Project the public #186 handoff without reading its repository."""

        return _analysis_evidence(analysis)

    def project(
        self,
        *,
        analysis: ResearchAnalysisHandoff,
        theory_plan: ConfirmedTheoryPlanSnapshot | None,
        materials: tuple[ResearchMaterial, ...],
        archive: ProfessionalMaterialArchiveView,
    ) -> ResearchCycleSnapshot:
        evidence = self.analysis_evidence(analysis)
        gaps = _gap_suggestions(analysis=analysis, theory_plan=theory_plan)
        facts = _project_facts(analysis=analysis, materials=materials, archive=archive)
        hints = _reporting_hints(facts=facts, materials=materials)
        map_patch = _research_map_patch(gaps)
        payload = {
            "schema_version": "research-cycle-v1",
            "task_id": str(analysis.task_id),
            "analysis_content_hash": analysis.content_hash,
            "theory_plan_id": str(theory_plan.theory_plan_id) if theory_plan else None,
            "theory_plan_version": theory_plan.version if theory_plan else None,
            "evidence": [asdict(item) for item in evidence],
            "gaps": [asdict(item) for item in gaps],
            "project_facts": asdict(facts),
            "reporting_hints": [asdict(item) for item in hints],
            "research_map_patch": map_patch,
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return ResearchCycleSnapshot(
            schema_version="research-cycle-v1",
            task_id=analysis.task_id,
            version=1,
            content_hash="sha256:" + hashlib.sha256(canonical.encode()).hexdigest(),
            analysis_content_hash=analysis.content_hash,
            theory_plan_id=theory_plan.theory_plan_id if theory_plan else None,
            theory_plan_version=theory_plan.version if theory_plan else None,
            evidence=evidence,
            gaps=gaps,
            project_facts=facts,
            reporting_hints=hints,
            research_map_patch=map_patch,
        )


def _analysis_evidence(analysis: ResearchAnalysisHandoff) -> tuple[CycleEvidence, ...]:
    annotations = {item.annotation_id: item for item in analysis.annotations}
    values: list[CycleEvidence] = []
    for code in analysis.codes:
        if code.status is not AnalysisCodeStatus.CONFIRMED:
            continue
        for annotation_id in code.annotation_ids:
            if annotation := annotations.get(annotation_id):
                values.append(
                    _evidence(
                        kind=CycleEvidenceKind.ANALYTIC_CODE,
                        statement=f"{code.label}：{code.definition}",
                        source_kind="analysis_code",
                        source_id=str(code.code_id),
                        annotation=annotation,
                    )
                )
    for memo in analysis.memos:
        if memo.status is not AnalysisRecordStatus.CONFIRMED:
            continue
        for annotation_id in memo.annotation_ids:
            if annotation := annotations.get(annotation_id):
                values.append(
                    _evidence(
                        kind=CycleEvidenceKind.ANALYTIC_MEMO,
                        statement=f"{memo.title}：{memo.content}",
                        source_kind="analysis_memo",
                        source_id=str(memo.memo_id),
                        annotation=annotation,
                    )
                )
    finding_kinds = {
        ComparisonFindingKind.SUPPORT: CycleEvidenceKind.SUPPORT,
        ComparisonFindingKind.COUNTEREXAMPLE: CycleEvidenceKind.COUNTEREXAMPLE,
        ComparisonFindingKind.CONTRADICT: CycleEvidenceKind.CONTRADICTION,
        ComparisonFindingKind.COMPETING_EXPLANATION: CycleEvidenceKind.COMPETING_EXPLANATION,
    }
    for comparison in analysis.comparisons:
        if comparison.status is not AnalysisRecordStatus.CONFIRMED:
            continue
        for finding_index, finding in enumerate(comparison.findings, start=1):
            kind = finding_kinds.get(finding.kind)
            if kind is None:
                continue
            for annotation_id in finding.annotation_ids:
                if annotation := annotations.get(annotation_id):
                    values.append(
                        _evidence(
                            kind=kind,
                            statement=finding.statement,
                            source_kind="case_comparison",
                            source_id=f"{comparison.comparison_id}:finding-{finding_index}",
                            annotation=annotation,
                        )
                    )
    return tuple(values)


def _evidence(*, kind, statement, source_kind, source_id, annotation) -> CycleEvidence:
    evidence_ref_id = f"cycle:{source_kind}:{source_id}:{annotation.annotation_id}"
    return CycleEvidence(
        evidence_ref_id=evidence_ref_id,
        kind=kind,
        statement=statement,
        source_kind=source_kind,
        source_id=source_id,
        annotation_id=annotation.annotation_id,
        material_id=annotation.material_id,
        parse_id=annotation.parse_id,
        segment_id=annotation.segment_id,
        quote=annotation.quote,
        locator=annotation.locator.display(),
        case_label=annotation.case_label,
        observed_at=annotation.observed_at,
    )


def _gap_suggestions(
    *,
    analysis: ResearchAnalysisHandoff,
    theory_plan: ConfirmedTheoryPlanSnapshot | None,
) -> tuple[EvidenceGapSuggestion, ...]:
    values: list[EvidenceGapSuggestion] = []
    for comparison in analysis.comparisons:
        if comparison.status is not AnalysisRecordStatus.CONFIRMED:
            continue
        for index, gap in enumerate(comparison.evidence_gaps, start=1):
            values.append(
                _gap(
                    analysis=analysis,
                    theory_plan=theory_plan,
                    source_kind="analysis",
                    source_id=f"{comparison.comparison_id}:gap-{index}",
                    description=gap,
                    action=f"筛选或补充能够回答此缺口的材料：{gap}",
                    destination=GapDestination.MATERIAL_SCREENING,
                    priority="medium",
                )
            )
        for index, step in enumerate(comparison.next_steps, start=1):
            destination = (
                GapDestination.MATERIAL_SCREENING
                if step.kind == "material_collection"
                else GapDestination.NEXT_ROUND_SAMPLING
            )
            values.append(
                _gap(
                    analysis=analysis,
                    theory_plan=theory_plan,
                    source_kind="analysis",
                    source_id=f"{comparison.comparison_id}:next-{index}",
                    description=step.action,
                    action=step.action,
                    destination=destination,
                    priority=step.priority,
                )
            )
    if theory_plan is not None:
        for candidate in theory_plan.candidates:
            groups = (
                (
                    "material",
                    candidate.judgement.material_requirements,
                    GapDestination.MATERIAL_SCREENING,
                ),
                ("gap", candidate.judgement.evidence_gaps, GapDestination.MATERIAL_SCREENING),
                (
                    "alternative",
                    candidate.judgement.alternative_explanations,
                    GapDestination.NEXT_ROUND_SAMPLING,
                ),
            )
            for group, items, destination in groups:
                for index, item in enumerate(items, start=1):
                    values.append(
                        _gap(
                            analysis=analysis,
                            theory_plan=theory_plan,
                            source_kind="theory",
                            source_id=f"{candidate.candidate_id}:{group}-{index}",
                            description=item,
                            action=(
                                f"筛选或补充材料：{item}"
                                if destination is GapDestination.MATERIAL_SCREENING
                                else f"在下一轮取样中检验竞争解释：{item}"
                            ),
                            destination=destination,
                            priority="medium",
                        )
                    )
    return tuple(values)


def _gap(
    *, analysis, theory_plan, source_kind, source_id, description, action, destination, priority
) -> EvidenceGapSuggestion:
    basis = (
        f"{analysis.content_hash}|{getattr(theory_plan, 'theory_plan_id', '')}|"
        f"{getattr(theory_plan, 'version', '')}|{source_kind}|{source_id}|{description}"
    )
    return EvidenceGapSuggestion(
        gap_id="gap:" + hashlib.sha256(basis.encode()).hexdigest()[:24],
        source_kind=source_kind,
        source_id=source_id,
        description=description,
        suggested_action=action,
        destination=destination,
        priority=priority,
        analysis_content_hash=analysis.content_hash,
        theory_plan_id=theory_plan.theory_plan_id if theory_plan else None,
        theory_plan_version=theory_plan.version if theory_plan else None,
    )


def _project_facts(*, analysis, materials, archive) -> ProjectResearchFacts:
    material_counts = _counts(item.material_kind.value for item in materials)
    profiles = archive.archive.profiles
    return ProjectResearchFacts(
        material_count=len(materials),
        material_kinds=material_counts,
        case_count=len(archive.archive.cases),
        case_material_coverage=tuple(
            (item.name, len(item.material_ids)) for item in archive.archive.cases
        ),
        consent_scopes=_counts(item.consent_scope.value for item in profiles),
        sensitivity_levels=_counts(item.sensitivity.value for item in profiles),
        pending_deidentification_count=sum(
            item.deidentification_status.value == "pending" for item in profiles
        ),
        sampling_batches=tuple(item.name for item in archive.archive.batches),
        analysis_counts=(
            ("codes", len(analysis.codes)),
            ("memos", len(analysis.memos)),
            ("comparisons", len(analysis.comparisons)),
        ),
    )


def _counts(values) -> tuple[tuple[str, int], ...]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return tuple(sorted(counts.items()))


def _reporting_hints(
    *, facts: ProjectResearchFacts, materials: tuple[ResearchMaterial, ...]
) -> tuple[ReportingCoverageHint, ...]:
    has_analysis = any(value for _key, value in facts.analysis_counts)
    has_ethics = bool(facts.consent_scopes)
    has_interviews = any(
        item.material_kind is MaterialKind.INTERVIEW_TRANSCRIPT for item in materials
    )
    values = [
        _hint("SRQR", "data_collection", "资料收集方法", facts.material_count > 0),
        _hint("SRQR", "data_analysis", "资料分析过程", has_analysis),
        _hint("SRQR", "ethics", "伦理与同意", has_ethics),
        _hint("SRQR", "sampling_strategy", "取样策略", bool(facts.sampling_batches)),
        _hint("SRQR", "researcher_reflexivity", "研究者反身性", False),
    ]
    if has_interviews:
        values.extend(
            (
                _hint("COREQ", "sample_description", "样本描述", facts.case_count > 0),
                _hint("COREQ", "data_collection", "访谈资料收集", True),
                _hint("COREQ", "coding_tree", "代码与主题形成", has_analysis),
                _hint("COREQ", "researcher_characteristics", "研究者特征与关系", False),
            )
        )
    else:
        values.append(
            ReportingCoverageHint(
                guideline="COREQ",
                item_key="applicability",
                label="访谈或焦点小组适用性",
                status=ReportingCoverageStatus.NOT_APPLICABLE,
                message="当前项目未识别到访谈材料；COREQ 仅作为适用性提示。",
            )
        )
    return tuple(values)


def _hint(guideline: str, item_key: str, label: str, present: bool) -> ReportingCoverageHint:
    return ReportingCoverageHint(
        guideline=guideline,
        item_key=item_key,
        label=label,
        status=(ReportingCoverageStatus.PRESENT if present else ReportingCoverageStatus.MISSING),
        message=(
            f"项目中已有可用于报告“{label}”的事实。"
            if present
            else f"尚未看到可用于报告“{label}”的项目事实；这不阻止研究继续。"
        ),
    )


def _research_map_patch(
    gaps: tuple[EvidenceGapSuggestion, ...],
) -> dict[str, list[dict[str, object]]]:
    return {
        "nodes": [
            {
                "id": item.gap_id,
                "kind": "gap",
                "title": item.description,
                "summary": item.suggested_action,
                "status": item.status,
                "citation_ids": [],
            }
            for item in gaps
        ],
        "relations": [],
    }
