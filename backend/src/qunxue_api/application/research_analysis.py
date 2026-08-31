"""Task-owned orchestration for qualitative research analysis."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import UUID, uuid4

from qunxue_api.modules.research_analysis import (
    AnalysisAnnotation,
    AnalysisAnnotationKind,
    AnalysisCode,
    AnalysisCodeStatus,
    AnalysisMemo,
    AnalysisMemoKind,
    AnalysisRecordStatus,
    AnalysisWriteRequest,
    CaseComparison,
    ComparisonFinding,
    ComparisonFindingKind,
    ConfirmedComparisonProjection,
    NextResearchStep,
    ResearchAnalysisHandoff,
    ResearchAnalysisService,
)
from qunxue_api.modules.research_intake import (
    ResearchTaskNotFound,
    ResearchTaskRepository,
)
from qunxue_api.modules.research_materials import MaterialBlock, MaterialStatus, ResearchMaterial


class AnalysisMaterialReader(Protocol):
    def get(
        self,
        material_id: UUID,
        *,
        user_id: UUID,
        task_id: UUID,
        include_deleted: bool = False,
    ) -> ResearchMaterial | None: ...

    def get_segment(
        self,
        material_id: UUID,
        parse_id: UUID,
        segment_id: str,
        *,
        user_id: UUID,
        task_id: UUID,
    ) -> MaterialBlock | None: ...


class ResearchAnalysisApplication:
    """Authorizes source anchors and keeps Agent interpretations approval-gated."""

    def __init__(
        self,
        *,
        analysis: ResearchAnalysisService,
        materials: AnalysisMaterialReader,
        research_tasks: ResearchTaskRepository,
        commit: Callable[[], None] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._analysis = analysis
        self._materials = materials
        self._research_tasks = research_tasks
        self._commit = commit or (lambda: None)
        self._clock = clock or (lambda: datetime.now(UTC))

    def create_annotation(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        idempotency_key: str,
        material_id: UUID,
        parse_id: UUID,
        segment_id: str,
        quote_start: int,
        quote_end: int,
        annotation_kind: AnalysisAnnotationKind,
        note: str,
        reflection: str | None = None,
        case_label: str | None = None,
        observed_at: str | None = None,
    ) -> AnalysisAnnotation:
        self._require_task(user_id=user_id, task_id=task_id)
        material = self._materials.get(material_id, user_id=user_id, task_id=task_id)
        if material is None or material.status is not MaterialStatus.READY:
            raise LookupError(material_id)
        block = self._materials.get_segment(
            material_id,
            parse_id,
            segment_id,
            user_id=user_id,
            task_id=task_id,
        )
        if block is None:
            raise LookupError(segment_id)
        if quote_start < 0 or quote_end > len(block.text) or quote_end <= quote_start:
            raise ValueError("selection is outside the source segment")
        candidate = AnalysisAnnotation.create(
            user_id=user_id,
            task_id=task_id,
            material_id=material_id,
            parse_id=parse_id,
            segment_id=segment_id,
            segment_content_hash=block.content_hash,
            quote=block.text[quote_start:quote_end],
            quote_start=quote_start,
            quote_end=quote_end,
            locator=block.locator,
            annotation_kind=annotation_kind,
            case_label=case_label,
            observed_at=observed_at,
            note=note,
            reflection=reflection,
            now=self._clock(),
        )
        write = self._reserve_write(
            user_id=user_id,
            task_id=task_id,
            namespace="api",
            idempotency_key=idempotency_key,
            operation="create_annotation",
            result_kind="annotation",
            payload={
                "material_id": material_id,
                "parse_id": parse_id,
                "segment_id": segment_id,
                "quote_start": quote_start,
                "quote_end": quote_end,
                "annotation_kind": annotation_kind,
                "note": note,
                "reflection": reflection,
                "case_label": case_label,
                "observed_at": observed_at,
            },
        )
        existing = self._analysis.get_annotation(
            user_id=user_id,
            task_id=task_id,
            annotation_id=write.result_id,
        )
        if existing is not None:
            self._commit()
            return existing
        value = replace(
            candidate,
            annotation_id=write.result_id,
            created_at=write.created_at,
        )
        result = self._analysis.add_annotation(value)
        self._commit()
        return result

    def propose_code_from_agent(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        label: str,
        definition: str,
        annotation_ids: tuple[UUID, ...],
        rationale: str,
        conversation_id: UUID,
        agent_run_id: UUID,
        agent_turn_id: UUID,
        tool_call_id: str,
    ) -> AnalysisCode:
        self._require_task(user_id=user_id, task_id=task_id)
        self._validate_links(
            user_id=user_id,
            task_id=task_id,
            annotation_ids=annotation_ids,
        )
        candidate = AnalysisCode.candidate(
            user_id=user_id,
            task_id=task_id,
            label=label,
            definition=definition,
            annotation_ids=annotation_ids,
            rationale=rationale,
            source="agent",
            conversation_id=conversation_id,
            agent_run_id=agent_run_id,
            agent_turn_id=agent_turn_id,
            tool_call_id=tool_call_id,
            now=self._clock(),
        )
        write = self._reserve_agent_write(
            user_id=user_id,
            task_id=task_id,
            conversation_id=conversation_id,
            agent_run_id=agent_run_id,
            agent_turn_id=agent_turn_id,
            tool_call_id=tool_call_id,
            operation="propose_code",
            result_kind="code",
            payload={
                "label": label,
                "definition": definition,
                "annotation_ids": annotation_ids,
                "rationale": rationale,
            },
        )
        existing = self._analysis.get_code(
            user_id=user_id,
            task_id=task_id,
            code_id=write.result_id,
        )
        if existing is not None:
            self._commit()
            return existing
        value = self._analysis.add_code(
            replace(
                candidate,
                code_id=write.result_id,
                created_at=write.created_at,
            )
        )
        self._commit()
        return value

    def list_snapshot(self, *, user_id: UUID, task_id: UUID) -> dict[str, object]:
        self._require_task(user_id=user_id, task_id=task_id)
        snapshot = self._analysis.snapshot(user_id=user_id, task_id=task_id)
        annotations = cast(tuple[AnalysisAnnotation, ...], snapshot["annotations"])
        return {
            **snapshot,
            "annotations": tuple(
                annotation
                if self._annotation_is_readable(annotation)
                else annotation.source_tombstone(
                    reason=self._annotation_unavailable_reason(annotation)
                )
                for annotation in annotations
            ),
        }

    def get_for_agent(self, *, user_id: UUID, task_id: UUID) -> dict[str, object]:
        return self.list_snapshot(user_id=user_id, task_id=task_id)

    def create_user_code(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        idempotency_key: str,
        label: str,
        definition: str,
        annotation_ids: tuple[UUID, ...],
        rationale: str,
    ) -> AnalysisCode:
        self._require_task(user_id=user_id, task_id=task_id)
        self._validate_links(
            user_id=user_id,
            task_id=task_id,
            annotation_ids=annotation_ids,
        )
        now = self._clock()
        candidate = AnalysisCode.candidate(
            user_id=user_id,
            task_id=task_id,
            label=label,
            definition=definition,
            annotation_ids=annotation_ids,
            rationale=rationale,
            source="user",
            now=now,
        ).confirm(
            user_confirmed=True,
            expected_version=1,
            reason="用户创建并确认",
            now=now,
        )
        write = self._reserve_write(
            user_id=user_id,
            task_id=task_id,
            namespace="api",
            idempotency_key=idempotency_key,
            operation="create_user_code",
            result_kind="code",
            payload={
                "label": label,
                "definition": definition,
                "annotation_ids": annotation_ids,
                "rationale": rationale,
            },
        )
        existing = self._analysis.get_code(
            user_id=user_id,
            task_id=task_id,
            code_id=write.result_id,
        )
        if existing is not None:
            self._commit()
            return existing
        value = self._analysis.add_code(
            replace(
                candidate,
                code_id=write.result_id,
                created_at=write.created_at,
                decided_at=write.created_at,
            )
        )
        self._commit()
        return value

    def decide_code(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        idempotency_key: str,
        code_id: UUID,
        expected_version: int,
        decision: AnalysisCodeStatus,
        reason: str,
    ) -> AnalysisCode:
        self._require_task(user_id=user_id, task_id=task_id)
        replay = self._reserve_decision_write(
            user_id=user_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
            operation="decide_code",
            result_kind="code",
            record_id=code_id,
            expected_version=expected_version,
            decision=decision,
            reason=reason,
            get_record=lambda: self._analysis.get_code(
                user_id=user_id,
                task_id=task_id,
                code_id=code_id,
            ),
        )
        if replay is not None:
            return cast(AnalysisCode, replay)
        if decision is AnalysisCodeStatus.CONFIRMED:
            value = self._analysis.confirm_code(
                user_id=user_id,
                task_id=task_id,
                code_id=code_id,
                expected_version=expected_version,
                user_confirmed=True,
                reason=reason,
            )
        elif decision is AnalysisCodeStatus.REJECTED:
            value = self._analysis.reject_code(
                user_id=user_id,
                task_id=task_id,
                code_id=code_id,
                expected_version=expected_version,
                user_confirmed=True,
                reason=reason,
            )
        else:
            raise ValueError("decision must confirm or reject the candidate")
        self._commit()
        return value

    def create_user_memo(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        idempotency_key: str,
        title: str,
        content: str,
        memo_kind: AnalysisMemoKind,
        annotation_ids: tuple[UUID, ...] = (),
        code_ids: tuple[UUID, ...] = (),
    ) -> AnalysisMemo:
        self._require_task(user_id=user_id, task_id=task_id)
        self._validate_links(
            user_id=user_id,
            task_id=task_id,
            annotation_ids=annotation_ids,
            code_ids=code_ids,
        )
        now = self._clock()
        candidate = AnalysisMemo.create_candidate(
            user_id=user_id,
            task_id=task_id,
            title=title,
            content=content,
            memo_kind=memo_kind,
            annotation_ids=annotation_ids,
            code_ids=code_ids,
            source="user",
            now=now,
        ).confirm(
            user_confirmed=True,
            expected_version=1,
            reason="用户创建并确认",
            now=now,
        )
        write = self._reserve_write(
            user_id=user_id,
            task_id=task_id,
            namespace="api",
            idempotency_key=idempotency_key,
            operation="create_user_memo",
            result_kind="memo",
            payload={
                "title": title,
                "content": content,
                "memo_kind": memo_kind,
                "annotation_ids": annotation_ids,
                "code_ids": code_ids,
            },
        )
        existing = self._analysis.get_memo(
            user_id=user_id,
            task_id=task_id,
            memo_id=write.result_id,
        )
        if existing is not None:
            self._commit()
            return existing
        result = self._analysis.add_memo(
            replace(
                candidate,
                memo_id=write.result_id,
                created_at=write.created_at,
                decided_at=write.created_at,
            )
        )
        self._commit()
        return result

    def propose_memo_from_agent(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        title: str,
        content: str,
        memo_kind: str,
        annotation_ids: tuple[UUID, ...] = (),
        code_ids: tuple[UUID, ...] = (),
        conversation_id: UUID,
        agent_run_id: UUID,
        agent_turn_id: UUID,
        tool_call_id: str,
    ) -> AnalysisMemo:
        self._require_task(user_id=user_id, task_id=task_id)
        self._validate_links(
            user_id=user_id,
            task_id=task_id,
            annotation_ids=annotation_ids,
            code_ids=code_ids,
        )
        resolved_kind = AnalysisMemoKind(memo_kind)
        candidate = AnalysisMemo.create_candidate(
            user_id=user_id,
            task_id=task_id,
            title=title,
            content=content,
            memo_kind=resolved_kind,
            annotation_ids=annotation_ids,
            code_ids=code_ids,
            source="agent",
            conversation_id=conversation_id,
            agent_run_id=agent_run_id,
            agent_turn_id=agent_turn_id,
            tool_call_id=tool_call_id,
            now=self._clock(),
        )
        write = self._reserve_agent_write(
            user_id=user_id,
            task_id=task_id,
            conversation_id=conversation_id,
            agent_run_id=agent_run_id,
            agent_turn_id=agent_turn_id,
            tool_call_id=tool_call_id,
            operation="propose_memo",
            result_kind="memo",
            payload={
                "title": title,
                "content": content,
                "memo_kind": resolved_kind,
                "annotation_ids": annotation_ids,
                "code_ids": code_ids,
            },
        )
        existing = self._analysis.get_memo(
            user_id=user_id,
            task_id=task_id,
            memo_id=write.result_id,
        )
        if existing is not None:
            self._commit()
            return existing
        value = replace(
            candidate,
            memo_id=write.result_id,
            created_at=write.created_at,
        )
        result = self._analysis.add_memo(value)
        self._commit()
        return result

    def decide_memo(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        idempotency_key: str,
        memo_id: UUID,
        expected_version: int,
        decision: AnalysisRecordStatus,
        reason: str,
    ) -> AnalysisMemo:
        self._require_task(user_id=user_id, task_id=task_id)
        replay = self._reserve_decision_write(
            user_id=user_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
            operation="decide_memo",
            result_kind="memo",
            record_id=memo_id,
            expected_version=expected_version,
            decision=decision,
            reason=reason,
            get_record=lambda: self._analysis.get_memo(
                user_id=user_id,
                task_id=task_id,
                memo_id=memo_id,
            ),
        )
        if replay is not None:
            return cast(AnalysisMemo, replay)
        if decision is AnalysisRecordStatus.CONFIRMED:
            value = self._analysis.confirm_memo(
                user_id=user_id,
                task_id=task_id,
                memo_id=memo_id,
                expected_version=expected_version,
                user_confirmed=True,
                reason=reason,
            )
        elif decision is AnalysisRecordStatus.REJECTED:
            value = self._analysis.reject_memo(
                user_id=user_id,
                task_id=task_id,
                memo_id=memo_id,
                expected_version=expected_version,
                user_confirmed=True,
                reason=reason,
            )
        else:
            raise ValueError("decision must confirm or reject the candidate")
        self._commit()
        return value

    def create_user_comparison(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        idempotency_key: str,
        title: str,
        question: str,
        case_labels: tuple[str, ...],
        findings: tuple[ComparisonFinding, ...],
        theory_implication: str,
        time_labels: tuple[str, ...] = (),
        competing_explanations: tuple[str, ...] = (),
        evidence_gaps: tuple[str, ...] = (),
        next_steps: tuple[NextResearchStep, ...] = (),
    ) -> CaseComparison:
        self._require_task(user_id=user_id, task_id=task_id)
        self._validate_comparison_anchors(
            user_id=user_id,
            task_id=task_id,
            case_labels=case_labels,
            time_labels=time_labels,
            findings=findings,
        )
        now = self._clock()
        candidate = CaseComparison.create(
            user_id=user_id,
            task_id=task_id,
            title=title,
            question=question,
            case_labels=case_labels,
            time_labels=time_labels,
            findings=findings,
            competing_explanations=competing_explanations,
            evidence_gaps=evidence_gaps,
            next_steps=next_steps,
            theory_implication=theory_implication,
            source="user",
            now=now,
        ).confirm(
            user_confirmed=True,
            expected_version=1,
            reason="用户创建并确认",
            now=now,
        )
        write = self._reserve_write(
            user_id=user_id,
            task_id=task_id,
            namespace="api",
            idempotency_key=idempotency_key,
            operation="create_user_comparison",
            result_kind="comparison",
            payload={
                "title": title,
                "question": question,
                "case_labels": case_labels,
                "time_labels": time_labels,
                "findings": findings,
                "competing_explanations": competing_explanations,
                "evidence_gaps": evidence_gaps,
                "next_steps": next_steps,
                "theory_implication": theory_implication,
            },
        )
        existing = self._analysis.get_comparison(
            user_id=user_id,
            task_id=task_id,
            comparison_id=write.result_id,
        )
        if existing is not None:
            self._commit()
            return existing
        result = self._analysis.add_comparison(
            replace(
                candidate,
                comparison_id=write.result_id,
                created_at=write.created_at,
                decided_at=write.created_at,
            )
        )
        self._commit()
        return result

    def propose_comparison_from_agent(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        title: str,
        question: str,
        case_labels: tuple[str, ...],
        findings: tuple[ComparisonFinding, ...],
        theory_implication: str,
        time_labels: tuple[str, ...] = (),
        competing_explanations: tuple[str, ...] = (),
        evidence_gaps: tuple[str, ...] = (),
        next_steps: tuple[NextResearchStep, ...] = (),
        conversation_id: UUID,
        agent_run_id: UUID,
        agent_turn_id: UUID,
        tool_call_id: str,
    ) -> CaseComparison:
        self._require_task(user_id=user_id, task_id=task_id)
        self._validate_comparison_anchors(
            user_id=user_id,
            task_id=task_id,
            case_labels=case_labels,
            time_labels=time_labels,
            findings=findings,
        )
        candidate = CaseComparison.create(
            user_id=user_id,
            task_id=task_id,
            title=title,
            question=question,
            case_labels=case_labels,
            time_labels=time_labels,
            findings=findings,
            competing_explanations=competing_explanations,
            evidence_gaps=evidence_gaps,
            next_steps=next_steps,
            theory_implication=theory_implication,
            source="agent",
            conversation_id=conversation_id,
            agent_run_id=agent_run_id,
            agent_turn_id=agent_turn_id,
            tool_call_id=tool_call_id,
            now=self._clock(),
        )
        write = self._reserve_agent_write(
            user_id=user_id,
            task_id=task_id,
            conversation_id=conversation_id,
            agent_run_id=agent_run_id,
            agent_turn_id=agent_turn_id,
            tool_call_id=tool_call_id,
            operation="propose_comparison",
            result_kind="comparison",
            payload={
                "title": title,
                "question": question,
                "case_labels": case_labels,
                "time_labels": time_labels,
                "findings": findings,
                "competing_explanations": competing_explanations,
                "evidence_gaps": evidence_gaps,
                "next_steps": next_steps,
                "theory_implication": theory_implication,
            },
        )
        existing = self._analysis.get_comparison(
            user_id=user_id,
            task_id=task_id,
            comparison_id=write.result_id,
        )
        if existing is not None:
            self._commit()
            return existing
        result = self._analysis.add_comparison(
            replace(
                candidate,
                comparison_id=write.result_id,
                created_at=write.created_at,
            )
        )
        self._commit()
        return result

    def get_comparison_context_for_agent(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        case_labels: tuple[str, ...],
        time_labels: tuple[str, ...] = (),
    ) -> dict[str, object]:
        """Read a bounded cross-case/time context without making a decision."""

        normalized_cases = tuple(
            dict.fromkeys(item.strip() for item in case_labels if item.strip())
        )
        if len(normalized_cases) < 2:
            raise ValueError("comparison context requires at least two cases")
        normalized_times = tuple(
            dict.fromkeys(item.strip() for item in time_labels if item.strip())
        )
        if normalized_times and len(normalized_times) < 2:
            raise ValueError("comparison context requires at least two time labels")
        snapshot = self.list_snapshot(user_id=user_id, task_id=task_id)
        annotations = tuple(
            item
            for item in cast(tuple[AnalysisAnnotation, ...], snapshot["annotations"])
            if item.case_label in normalized_cases
            and (not normalized_times or item.observed_at in normalized_times)
        )
        annotation_ids = {item.annotation_id for item in annotations}
        codes = tuple(
            item
            for item in cast(tuple[AnalysisCode, ...], snapshot["codes"])
            if annotation_ids.intersection(item.annotation_ids)
        )
        memos = tuple(
            item
            for item in cast(tuple[AnalysisMemo, ...], snapshot["memos"])
            if annotation_ids.intersection(item.annotation_ids)
            or any(code.code_id in item.code_ids for code in codes)
        )
        comparisons = tuple(
            item
            for item in cast(tuple[CaseComparison, ...], snapshot["comparisons"])
            if set(normalized_cases) <= set(item.case_labels)
            and (not normalized_times or set(normalized_times) <= set(item.time_labels))
        )
        return {
            "schema_version": "research-comparison-context-v1",
            "case_labels": normalized_cases,
            "time_labels": normalized_times,
            "annotations": annotations,
            "codes": codes,
            "memos": memos,
            "comparisons": comparisons,
        }

    def decide_comparison(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        idempotency_key: str,
        comparison_id: UUID,
        expected_version: int,
        decision: AnalysisRecordStatus,
        reason: str,
    ) -> CaseComparison:
        self._require_task(user_id=user_id, task_id=task_id)
        replay = self._reserve_decision_write(
            user_id=user_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
            operation="decide_comparison",
            result_kind="comparison",
            record_id=comparison_id,
            expected_version=expected_version,
            decision=decision,
            reason=reason,
            get_record=lambda: self._analysis.get_comparison(
                user_id=user_id,
                task_id=task_id,
                comparison_id=comparison_id,
            ),
        )
        if replay is not None:
            return cast(CaseComparison, replay)
        if decision is AnalysisRecordStatus.CONFIRMED:
            value = self._analysis.confirm_comparison(
                user_id=user_id,
                task_id=task_id,
                comparison_id=comparison_id,
                expected_version=expected_version,
                user_confirmed=True,
                reason=reason,
            )
        elif decision is AnalysisRecordStatus.REJECTED:
            value = self._analysis.reject_comparison(
                user_id=user_id,
                task_id=task_id,
                comparison_id=comparison_id,
                expected_version=expected_version,
                user_confirmed=True,
                reason=reason,
            )
        else:
            raise ValueError("decision must confirm or reject the candidate")
        self._commit()
        return value

    def formal_handoff(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
    ) -> ResearchAnalysisHandoff:
        self._require_task(user_id=user_id, task_id=task_id)
        snapshot = self._analysis.snapshot(user_id=user_id, task_id=task_id)
        annotations = cast(tuple[AnalysisAnnotation, ...], snapshot["annotations"])
        unavailable = tuple(
            annotation.annotation_id
            for annotation in annotations
            if not self._annotation_is_readable(annotation)
        )
        return self._analysis.formal_handoff(
            user_id=user_id,
            task_id=task_id,
            unavailable_annotation_ids=unavailable,
        )

    def get_confirmed_comparison_projection(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
    ) -> ConfirmedComparisonProjection:
        """Return an owner-checked, confirmed-only M4/ResearchMap projection."""

        self._require_task(user_id=user_id, task_id=task_id)
        snapshot = self._analysis.snapshot(user_id=user_id, task_id=task_id)
        annotations = cast(tuple[AnalysisAnnotation, ...], snapshot["annotations"])
        unavailable = tuple(
            annotation.annotation_id
            for annotation in annotations
            if not self._annotation_is_readable(annotation)
        )
        return self._analysis.confirmed_comparison_projection(
            user_id=user_id,
            task_id=task_id,
            unavailable_annotation_ids=unavailable,
        )

    def _annotation_is_readable(self, annotation: AnalysisAnnotation) -> bool:
        material = self._materials.get(
            annotation.material_id,
            user_id=annotation.user_id,
            task_id=annotation.task_id,
        )
        if material is None or material.status is not MaterialStatus.READY:
            return False
        block = self._materials.get_segment(
            annotation.material_id,
            annotation.parse_id,
            annotation.segment_id,
            user_id=annotation.user_id,
            task_id=annotation.task_id,
        )
        return bool(
            block
            and block.content_hash == annotation.segment_content_hash
            and block.text[annotation.quote_start : annotation.quote_end] == annotation.quote
        )

    def _annotation_unavailable_reason(self, annotation: AnalysisAnnotation) -> str:
        material = self._materials.get(
            annotation.material_id,
            user_id=annotation.user_id,
            task_id=annotation.task_id,
            include_deleted=True,
        )
        if material is None or material.status is MaterialStatus.DELETED:
            return "source_deleted"
        return "source_unavailable"

    def _reserve_agent_write(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        conversation_id: UUID,
        agent_run_id: UUID,
        agent_turn_id: UUID,
        tool_call_id: str,
        operation: str,
        result_kind: str,
        payload: dict[str, object],
    ) -> AnalysisWriteRequest:
        identity = _request_hash(
            {
                "conversation_id": conversation_id,
                "agent_run_id": agent_run_id,
                "agent_turn_id": agent_turn_id,
                "tool_call_id": tool_call_id,
            }
        )
        return self._reserve_write(
            user_id=user_id,
            task_id=task_id,
            namespace="agent_tool",
            idempotency_key=identity,
            operation=operation,
            result_kind=result_kind,
            payload=payload,
        )

    def _reserve_write(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        namespace: str,
        idempotency_key: str,
        operation: str,
        result_kind: str,
        payload: dict[str, object],
        result_id: UUID | None = None,
    ) -> AnalysisWriteRequest:
        return self._analysis.reserve_write(
            AnalysisWriteRequest.create(
                user_id=user_id,
                task_id=task_id,
                namespace=namespace,
                idempotency_key=idempotency_key,
                operation=operation,
                request_hash=_request_hash(payload),
                result_kind=result_kind,
                result_id=result_id or uuid4(),
                now=self._clock(),
            )
        )

    def _reserve_decision_write(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        idempotency_key: str,
        operation: str,
        result_kind: str,
        record_id: UUID,
        expected_version: int,
        decision: AnalysisCodeStatus | AnalysisRecordStatus,
        reason: str,
        get_record: Callable[[], AnalysisCode | AnalysisMemo | CaseComparison | None],
    ) -> AnalysisCode | AnalysisMemo | CaseComparison | None:
        """Reserve a decision before CAS; replay returns the already decided record.

        A fresh random result identity lets a concurrent request distinguish a new
        reservation from an existing one without making the decision itself
        non-durable.  If a reservation exists but the record is still a candidate,
        the operation is retried so a transaction interrupted between reservation
        and the record update can safely recover.
        """

        proposed_result_id = uuid4()
        write = self._reserve_write(
            user_id=user_id,
            task_id=task_id,
            namespace="api",
            idempotency_key=idempotency_key,
            operation=operation,
            result_kind=result_kind,
            result_id=proposed_result_id,
            payload={
                "record_id": record_id,
                "expected_version": expected_version,
                "decision": decision,
                "reason": reason,
            },
        )
        if write.result_id == proposed_result_id:
            return None
        existing = get_record()
        if existing is None:
            raise LookupError(record_id)
        if existing.status.value != "candidate":
            self._commit()
            return existing
        return None

    def _validate_links(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        annotation_ids: tuple[UUID, ...] = (),
        code_ids: tuple[UUID, ...] = (),
    ) -> None:
        snapshot = self._analysis.snapshot(user_id=user_id, task_id=task_id)
        owned_annotations = {
            item.annotation_id
            for item in cast(tuple[AnalysisAnnotation, ...], snapshot["annotations"])
        }
        owned_codes = {item.code_id for item in cast(tuple[AnalysisCode, ...], snapshot["codes"])}
        if not set(annotation_ids) <= owned_annotations or not set(code_ids) <= owned_codes:
            raise ValueError("analysis link does not belong to this research task")

    def _validate_comparison_anchors(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        case_labels: tuple[str, ...],
        time_labels: tuple[str, ...],
        findings: tuple[ComparisonFinding, ...],
    ) -> None:
        annotation_ids = tuple(
            dict.fromkeys(
                annotation_id
                for finding in findings
                for annotation_id in finding.annotation_ids
            )
        )
        self._validate_links(
            user_id=user_id,
            task_id=task_id,
            annotation_ids=annotation_ids,
        )
        if any(
            finding.kind is not ComparisonFindingKind.EVIDENCE_GAP
            and not finding.annotation_ids
            for finding in findings
        ):
            raise ValueError("comparison evidence finding requires an annotation anchor")
        snapshot = self._analysis.snapshot(user_id=user_id, task_id=task_id)
        by_id = {
            item.annotation_id: item
            for item in cast(tuple[AnalysisAnnotation, ...], snapshot["annotations"])
        }
        annotations = tuple(by_id[item] for item in annotation_ids)
        if len({item.material_id for item in annotations}) < 2:
            raise ValueError("comparison requires evidence from at least two materials")
        declared_cases = {item.strip() for item in case_labels if item.strip()}
        anchored_cases = {item.case_label for item in annotations if item.case_label}
        if not declared_cases <= anchored_cases:
            raise ValueError("comparison case labels require matching annotation anchors")
        declared_times = {item.strip() for item in time_labels if item.strip()}
        anchored_times = {item.observed_at for item in annotations if item.observed_at}
        if declared_times and not declared_times <= anchored_times:
            raise ValueError("comparison time labels require matching annotation anchors")

    def _require_task(self, *, user_id: UUID, task_id: UUID) -> None:
        if self._research_tasks.get(task_id, user_id) is None:
            raise ResearchTaskNotFound(str(task_id))


def _request_hash(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda value: getattr(value, "value", str(value)),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
