"""Task-owned orchestration for qualitative research analysis."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import UUID, uuid4

from qunxue_api.modules.research_analysis import (
    AnalysisAnnotation,
    AnalysisAnnotationKind,
    AnalysisAuditEvent,
    AnalysisCaseProfile,
    AnalysisCode,
    AnalysisCodeStatus,
    AnalysisCodingPlan,
    AnalysisCodingPlanItem,
    AnalysisCodingPlanItemStatus,
    AnalysisCodingPlanStatus,
    AnalysisMemo,
    AnalysisMemoKind,
    AnalysisMemoLink,
    AnalysisRecordStatus,
    AnalysisTheme,
    AnalysisWriteRequest,
    CaseComparison,
    CaseThemeMatrixCell,
    CodebookEntry,
    CodebookLifecycle,
    ComparisonFinding,
    ComparisonFindingKind,
    ConfirmedComparisonProjection,
    MatrixSubjectKind,
    MemoTargetKind,
    MethodPresetSelection,
    NextResearchStep,
    QualitativeMethod,
    ResearchAnalysisHandoff,
    ResearchAnalysisService,
)
from qunxue_api.modules.research_cycle import CycleEvidence, ResearchCycleService
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

    def propose_coding_plan_from_agent(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        title: str,
        rationale: str,
        items: tuple[Mapping[str, object], ...],
        conversation_id: UUID,
        agent_run_id: UUID,
        agent_turn_id: UUID,
        tool_call_id: str,
    ) -> AnalysisCodingPlan:
        """Create a source-pinned, approval-gated plan against existing codes."""

        self._require_task(user_id=user_id, task_id=task_id)
        resolved: list[AnalysisCodingPlanItem] = []
        for raw in items:
            try:
                material_id = UUID(str(raw["material_id"]))
                parse_id = UUID(str(raw["parse_id"]))
                segment_id = str(raw["segment_id"])
                code_id = UUID(str(raw["code_id"]))
                quote_start = int(raw["quote_start"])
                quote_end = int(raw["quote_end"])
                confidence = float(raw["confidence"])
                item_rationale = str(raw["rationale"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("coding plan item is malformed") from error
            material = self._materials.get(material_id, user_id=user_id, task_id=task_id)
            if material is None or material.status is not MaterialStatus.READY:
                raise LookupError(material_id)
            block = self._materials.get_segment(
                material_id, parse_id, segment_id, user_id=user_id, task_id=task_id
            )
            if block is None:
                raise LookupError(segment_id)
            if quote_start < 0 or quote_end > len(block.text) or quote_end <= quote_start:
                raise ValueError("coding plan selection is outside the source segment")
            code = self._analysis.get_code(user_id=user_id, task_id=task_id, code_id=code_id)
            if code is None or code.status is not AnalysisCodeStatus.CONFIRMED:
                raise ValueError("coding plan target code must be user-confirmed")
            codebook = self._analysis.get_codebook_entry(
                user_id=user_id, task_id=task_id, code_id=code_id
            )
            resolved.append(
                AnalysisCodingPlanItem.create(
                    material_id=material_id,
                    parse_id=parse_id,
                    segment_id=segment_id,
                    segment_content_hash=block.content_hash,
                    quote=block.text[quote_start:quote_end],
                    quote_start=quote_start,
                    quote_end=quote_end,
                    locator=block.locator,
                    code_id=code_id,
                    code_label=code.label,
                    code_definition=code.definition,
                    codebook_version=codebook.version if codebook else None,
                    confidence=confidence,
                    rationale=item_rationale,
                )
            )
        candidate = AnalysisCodingPlan.candidate(
            user_id=user_id,
            task_id=task_id,
            title=title,
            rationale=rationale,
            items=tuple(resolved),
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
            operation="propose_coding_plan",
            result_kind="coding_plan",
            payload={
                "title": title,
                "rationale": rationale,
                "items": [dict(item) for item in items],
            },
        )
        existing = self._analysis.get_coding_plan(
            user_id=user_id, task_id=task_id, plan_id=write.result_id
        )
        if existing is not None:
            return existing
        value = replace(candidate, plan_id=write.result_id, created_at=write.created_at)
        self._analysis.add_coding_plan(value)
        self._record_audit(
            user_id=user_id,
            task_id=task_id,
            actor="agent",
            action="coding_plan.proposed",
            entity_kind="coding_plan",
            entity_id=value.plan_id,
            plan_id=value.plan_id,
            provenance={
                "conversation_id": str(conversation_id),
                "agent_run_id": str(agent_run_id),
                "agent_turn_id": str(agent_turn_id),
                "tool_call_id": tool_call_id,
            },
            payload={"item_count": len(value.items)},
        )
        self._commit()
        return value

    def decide_coding_plan(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        idempotency_key: str,
        plan_id: UUID,
        expected_version: int,
        decisions: tuple[tuple[UUID, str, str], ...],
    ) -> AnalysisCodingPlan:
        """Apply/reject every submitted item only after an explicit user decision."""

        self._require_task(user_id=user_id, task_id=task_id)
        plan = self._analysis.get_coding_plan(user_id=user_id, task_id=task_id, plan_id=plan_id)
        if plan is None:
            raise LookupError(plan_id)
        prior_write = self._analysis.get_write(
            user_id=user_id, task_id=task_id, namespace="api", idempotency_key=idempotency_key
        )
        self._reserve_write(
            user_id=user_id,
            task_id=task_id,
            namespace="api",
            idempotency_key=idempotency_key,
            operation="decide_coding_plan",
            result_kind="coding_plan",
            result_id=plan_id,
            payload={
                "plan_id": plan_id,
                "expected_version": expected_version,
                "decisions": decisions,
            },
        )
        if prior_write is not None and plan.status is not AnalysisCodingPlanStatus.CANDIDATE:
            return plan
        if plan.version != expected_version:
            raise ValueError("stale coding plan version")
        if plan.status is not AnalysisCodingPlanStatus.CANDIDATE:
            return plan
        by_id = {item.item_id: item for item in plan.items}
        if not decisions or {item_id for item_id, _, _ in decisions} != set(by_id):
            raise ValueError("every coding plan item requires one decision")
        normalized: dict[UUID, tuple[str, str]] = {}
        for item_id, decision, reason in decisions:
            if item_id not in by_id or decision not in {"confirmed", "rejected"}:
                raise ValueError("coding plan decision is invalid")
            if not str(reason).strip():
                raise ValueError("coding plan decision reason is required")
            normalized[item_id] = (decision, str(reason).strip())
        now = self._clock()
        for item in plan.items:
            decision, _ = normalized[item.item_id]
            if decision != "confirmed":
                continue
            block = self._materials.get_segment(
                item.material_id,
                item.parse_id,
                item.segment_id,
                user_id=user_id,
                task_id=task_id,
            )
            if (
                block is None
                or block.content_hash != item.segment_content_hash
                or block.text[item.quote_start : item.quote_end] != item.quote
            ):
                raise ValueError("coding plan source anchor is no longer readable")
            target = self._analysis.get_code(user_id=user_id, task_id=task_id, code_id=item.code_id)
            if target is None or target.status is not AnalysisCodeStatus.CONFIRMED:
                raise ValueError("coding plan target code is no longer confirmed")
        updated_items: list[AnalysisCodingPlanItem] = []
        applied_count = 0
        rejected_count = 0
        for item in plan.items:
            decision, reason = normalized[item.item_id]
            if decision == "rejected":
                updated_items.append(
                    replace(
                        item, status=AnalysisCodingPlanItemStatus.REJECTED, decision_reason=reason
                    )
                )
                rejected_count += 1
                self._record_audit(
                    user_id=user_id,
                    task_id=task_id,
                    actor="user",
                    action="coding_item.rejected",
                    entity_kind="coding_plan_item",
                    entity_id=item.item_id,
                    plan_id=plan_id,
                    item_id=item.item_id,
                    code_id=item.code_id,
                    idempotency_key=idempotency_key,
                    provenance={},
                    payload={"reason": reason},
                )
                continue
            annotation = self.create_annotation(
                user_id=user_id,
                task_id=task_id,
                idempotency_key=f"coding-plan:{plan_id}:item:{item.item_id}",
                material_id=item.material_id,
                parse_id=item.parse_id,
                segment_id=item.segment_id,
                quote_start=item.quote_start,
                quote_end=item.quote_end,
                annotation_kind=AnalysisAnnotationKind.DESCRIPTIVE,
                note=f"Agent 编码计划：{plan.title}",
            )
            code = self._analysis.get_code(user_id=user_id, task_id=task_id, code_id=item.code_id)
            if code is None:
                raise LookupError(item.code_id)
            self._analysis.add_code(
                code.attach_annotation(annotation_id=annotation.annotation_id, now=now)
            )
            updated_items.append(
                replace(
                    item,
                    status=AnalysisCodingPlanItemStatus.APPLIED,
                    annotation_id=annotation.annotation_id,
                    decision_reason=reason,
                )
            )
            applied_count += 1
            self._record_audit(
                user_id=user_id,
                task_id=task_id,
                actor="user",
                action="coding_item.applied",
                entity_kind="coding_plan_item",
                entity_id=item.item_id,
                plan_id=plan_id,
                item_id=item.item_id,
                annotation_id=annotation.annotation_id,
                code_id=item.code_id,
                idempotency_key=idempotency_key,
                provenance={},
                payload={"reason": reason},
            )
        status = (
            AnalysisCodingPlanStatus.APPLIED
            if applied_count == len(plan.items)
            else AnalysisCodingPlanStatus.REJECTED
            if rejected_count == len(plan.items)
            else AnalysisCodingPlanStatus.PARTIALLY_APPLIED
        )
        value = replace(
            plan,
            items=tuple(updated_items),
            status=status,
            version=plan.version + 1,
            decided_at=now,
            decision_reason="用户逐条确认编码计划",
        )
        self._analysis.add_coding_plan(value)
        self._record_audit(
            user_id=user_id,
            task_id=task_id,
            actor="user",
            action="coding_plan.decided",
            entity_kind="coding_plan",
            entity_id=plan_id,
            plan_id=plan_id,
            idempotency_key=idempotency_key,
            provenance={},
            payload={"status": status.value},
        )
        self._commit()
        return value

    def retrieve_coded_segments(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        code_ids: tuple[UUID, ...] = (),
        material_id: UUID | None = None,
        query: str | None = None,
        limit: int = 50,
    ) -> tuple[dict[str, object], ...]:
        self._require_task(user_id=user_id, task_id=task_id)
        codes = {
            item.code_id: item
            for item in self._analysis.list_codes(user_id=user_id, task_id=task_id)
            if item.status is AnalysisCodeStatus.CONFIRMED
        }
        selected = set(code_ids) or set(codes)
        annotations = {
            item.annotation_id: item
            for item in self._analysis.list_annotations(user_id=user_id, task_id=task_id)
        }
        plans = self._analysis.list_coding_plans(user_id=user_id, task_id=task_id)
        plan_by_annotation = {
            item.annotation_id: (plan.plan_id, item)
            for plan in plans
            for item in plan.items
            if item.annotation_id
        }
        needle = (query or "").strip().lower()
        rows: list[dict[str, object]] = []
        for code_id in selected:
            code = codes.get(code_id)
            if code is None:
                continue
            for annotation_id in code.annotation_ids:
                annotation = annotations.get(annotation_id)
                if (
                    annotation is None
                    or not annotation.source_available
                    or (material_id and annotation.material_id != material_id)
                ):
                    continue
                if (
                    needle
                    and needle not in (annotation.quote or "").lower()
                    and needle not in code.label.lower()
                ):
                    continue
                plan_ref = plan_by_annotation.get(annotation_id)
                plan = plan_ref[1] if plan_ref else None
                rows.append(
                    {
                        "annotation_id": annotation.annotation_id,
                        "code_id": code.code_id,
                        "code_label": code.label,
                        "quote": annotation.quote,
                        "material_id": annotation.material_id,
                        "parse_id": annotation.parse_id,
                        "segment_id": annotation.segment_id,
                        "locator": annotation.locator,
                        "confidence": plan.confidence if plan else None,
                        "plan_id": plan_ref[0] if plan_ref else None,
                    }
                )
        return tuple(rows[: max(1, min(limit, 200))])

    def revoke_coding_plan(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        idempotency_key: str,
        plan_id: UUID,
        expected_version: int,
        reason: str,
    ) -> AnalysisCodingPlan:
        """Revoke only the code assignments created by one applied plan."""

        self._require_task(user_id=user_id, task_id=task_id)
        plan = self._analysis.get_coding_plan(user_id=user_id, task_id=task_id, plan_id=plan_id)
        if plan is None:
            raise LookupError(plan_id)
        prior_write = self._analysis.get_write(
            user_id=user_id, task_id=task_id, namespace="api", idempotency_key=idempotency_key
        )
        self._reserve_write(
            user_id=user_id,
            task_id=task_id,
            namespace="api",
            idempotency_key=idempotency_key,
            operation="revoke_coding_plan",
            result_kind="coding_plan",
            result_id=plan_id,
            payload={"plan_id": plan_id, "expected_version": expected_version, "reason": reason},
        )
        if prior_write is not None and plan.status is AnalysisCodingPlanStatus.REVOKED:
            return plan
        if plan.version != expected_version:
            raise ValueError("stale coding plan version")
        if plan.status not in {
            AnalysisCodingPlanStatus.APPLIED,
            AnalysisCodingPlanStatus.PARTIALLY_APPLIED,
        }:
            raise ValueError("only an applied coding plan can be revoked")
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise ValueError("coding plan revocation reason is required")
        now = self._clock()
        items: list[AnalysisCodingPlanItem] = []
        for item in plan.items:
            if (
                item.status is not AnalysisCodingPlanItemStatus.APPLIED
                or item.annotation_id is None
            ):
                items.append(item)
                continue
            code = self._analysis.get_code(user_id=user_id, task_id=task_id, code_id=item.code_id)
            if code is None:
                raise LookupError(item.code_id)
            self._analysis.add_code(
                code.detach_annotation(annotation_id=item.annotation_id, now=now)
            )
            items.append(
                replace(
                    item,
                    status=AnalysisCodingPlanItemStatus.REVOKED,
                    decision_reason=normalized_reason,
                )
            )
            self._record_audit(
                user_id=user_id,
                task_id=task_id,
                actor="user",
                action="coding_item.revoked",
                entity_kind="coding_plan_item",
                entity_id=item.item_id,
                plan_id=plan_id,
                item_id=item.item_id,
                annotation_id=item.annotation_id,
                code_id=item.code_id,
                idempotency_key=idempotency_key,
                provenance={},
                payload={"reason": normalized_reason},
            )
        value = replace(
            plan,
            items=tuple(items),
            status=AnalysisCodingPlanStatus.REVOKED,
            version=plan.version + 1,
            decided_at=now,
            decision_reason=normalized_reason,
        )
        self._analysis.add_coding_plan(value)
        self._record_audit(
            user_id=user_id,
            task_id=task_id,
            actor="user",
            action="coding_plan.revoked",
            entity_kind="coding_plan",
            entity_id=plan_id,
            plan_id=plan_id,
            idempotency_key=idempotency_key,
            provenance={},
            payload={"reason": normalized_reason},
        )
        self._commit()
        return value

    def list_audit_events(self, *, user_id: UUID, task_id: UUID) -> tuple[AnalysisAuditEvent, ...]:
        self._require_task(user_id=user_id, task_id=task_id)
        return self._analysis.list_audit_events(user_id=user_id, task_id=task_id)

    def _record_audit(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        actor: str,
        action: str,
        entity_kind: str,
        entity_id: UUID,
        plan_id: UUID | None = None,
        item_id: UUID | None = None,
        annotation_id: UUID | None = None,
        code_id: UUID | None = None,
        idempotency_key: str | None = None,
        provenance: dict[str, object] | None = None,
        payload: dict[str, object] | None = None,
    ) -> AnalysisAuditEvent:
        return self._analysis.add_audit_event(
            AnalysisAuditEvent(
                event_id=uuid4(),
                user_id=user_id,
                task_id=task_id,
                actor=actor,
                action=action,
                entity_kind=entity_kind,
                entity_id=entity_id,
                plan_id=plan_id,
                item_id=item_id,
                annotation_id=annotation_id,
                code_id=code_id,
                idempotency_key=idempotency_key,
                provenance=provenance or {},
                payload=payload or {},
                created_at=self._clock(),
            )
        )

    def list_snapshot(self, *, user_id: UUID, task_id: UUID) -> dict[str, object]:
        self._require_task(user_id=user_id, task_id=task_id)
        snapshot = self._analysis.snapshot(user_id=user_id, task_id=task_id)
        annotations = cast(tuple[AnalysisAnnotation, ...], snapshot["annotations"])
        return {
            **snapshot,
            "workspace": self._analysis.qualitative_workspace_snapshot(
                user_id=user_id,
                task_id=task_id,
            ),
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

    def configure_codebook_entry(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        code_id: UUID,
        inclusion_rules: tuple[str, ...],
        exclusion_rules: tuple[str, ...],
        positive_example_annotation_ids: tuple[UUID, ...],
        negative_example_annotation_ids: tuple[UUID, ...],
        parent_code_id: UUID | None,
        expected_version: int | None,
    ) -> CodebookEntry:
        self._require_task(user_id=user_id, task_id=task_id)
        value = self._analysis.configure_codebook_entry(
            user_id=user_id,
            task_id=task_id,
            code_id=code_id,
            inclusion_rules=inclusion_rules,
            exclusion_rules=exclusion_rules,
            positive_example_annotation_ids=positive_example_annotation_ids,
            negative_example_annotation_ids=negative_example_annotation_ids,
            parent_code_id=parent_code_id,
            expected_version=expected_version,
            now=self._clock(),
        )
        self._commit()
        return value

    def transition_codebook_entry(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        code_id: UUID,
        lifecycle: CodebookLifecycle,
        related_code_ids: tuple[UUID, ...],
        expected_version: int,
        reason: str,
    ) -> CodebookEntry:
        self._require_task(user_id=user_id, task_id=task_id)
        value = self._analysis.transition_codebook_entry(
            user_id=user_id,
            task_id=task_id,
            code_id=code_id,
            lifecycle=lifecycle,
            related_code_ids=related_code_ids,
            expected_version=expected_version,
            reason=reason,
            now=self._clock(),
        )
        self._commit()
        return value

    def create_user_theme(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        label: str,
        central_concept: str,
        code_ids: tuple[UUID, ...],
        annotation_ids: tuple[UUID, ...],
    ) -> AnalysisTheme:
        self._require_task(user_id=user_id, task_id=task_id)
        value = self._analysis.create_theme(
            user_id=user_id,
            task_id=task_id,
            label=label,
            central_concept=central_concept,
            code_ids=code_ids,
            annotation_ids=annotation_ids,
            source="user",
            now=self._clock(),
        )
        self._commit()
        return value

    def propose_theme_from_agent(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        label: str,
        central_concept: str,
        code_ids: tuple[UUID, ...],
        annotation_ids: tuple[UUID, ...],
    ) -> AnalysisTheme:
        self._require_task(user_id=user_id, task_id=task_id)
        value = self._analysis.create_theme(
            user_id=user_id,
            task_id=task_id,
            label=label,
            central_concept=central_concept,
            code_ids=code_ids,
            annotation_ids=annotation_ids,
            source="agent",
            now=self._clock(),
        )
        self._commit()
        return value

    def confirm_theme(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        theme_id: UUID,
        expected_version: int,
        reason: str,
    ) -> AnalysisTheme:
        self._require_task(user_id=user_id, task_id=task_id)
        value = self._analysis.confirm_theme(
            user_id=user_id,
            task_id=task_id,
            theme_id=theme_id,
            expected_version=expected_version,
            user_confirmed=True,
            reason=reason,
        )
        self._commit()
        return value

    def attach_memo(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        memo_id: UUID,
        target_kind: MemoTargetKind,
        target_ref: str,
        annotation_ids: tuple[UUID, ...],
    ) -> AnalysisMemoLink:
        self._require_task(user_id=user_id, task_id=task_id)
        value = self._analysis.attach_memo(
            user_id=user_id,
            task_id=task_id,
            memo_id=memo_id,
            target_kind=target_kind,
            target_ref=target_ref,
            annotation_ids=annotation_ids,
            now=self._clock(),
        )
        self._commit()
        return value

    def save_case_profile(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        case_ref: str,
        display_label: str,
        attributes: tuple[tuple[str, str], ...],
        summary: str,
        annotation_ids: tuple[UUID, ...],
        memo_ids: tuple[UUID, ...],
        expected_version: int | None,
    ) -> AnalysisCaseProfile:
        self._require_task(user_id=user_id, task_id=task_id)
        value = self._analysis.save_case_profile(
            user_id=user_id,
            task_id=task_id,
            case_ref=case_ref,
            display_label=display_label,
            attributes=attributes,
            summary=summary,
            annotation_ids=annotation_ids,
            memo_ids=memo_ids,
            expected_version=expected_version,
            now=self._clock(),
        )
        self._commit()
        return value

    def save_matrix_cell(
        self,
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
        expected_version: int | None,
    ) -> CaseThemeMatrixCell:
        self._require_task(user_id=user_id, task_id=task_id)
        value = self._analysis.save_matrix_cell(
            user_id=user_id,
            task_id=task_id,
            case_profile_id=case_profile_id,
            subject_kind=subject_kind,
            subject_id=subject_id,
            summary=summary,
            annotation_ids=annotation_ids,
            memo_ids=memo_ids,
            finding_kinds=finding_kinds,
            expected_version=expected_version,
            now=self._clock(),
        )
        self._commit()
        return value

    def set_method_preset(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        method: QualitativeMethod,
        expected_version: int | None,
    ) -> MethodPresetSelection:
        self._require_task(user_id=user_id, task_id=task_id)
        value = self._analysis.set_method_preset(
            user_id=user_id,
            task_id=task_id,
            method=method,
            expected_version=expected_version,
            now=self._clock(),
        )
        self._commit()
        return value

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

    def confirmed_cycle_evidence(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
    ) -> tuple[CycleEvidence, ...]:
        """Expose confirmed analysis to M4 through the immutable public handoff."""

        return ResearchCycleService().analysis_evidence(
            self.formal_handoff(user_id=user_id, task_id=task_id)
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
                annotation_id for finding in findings for annotation_id in finding.annotation_ids
            )
        )
        self._validate_links(
            user_id=user_id,
            task_id=task_id,
            annotation_ids=annotation_ids,
        )
        if any(
            finding.kind is not ComparisonFindingKind.EVIDENCE_GAP and not finding.annotation_ids
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
