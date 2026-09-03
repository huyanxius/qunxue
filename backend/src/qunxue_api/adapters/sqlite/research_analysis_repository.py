"""SQLite persistence for qualitative analysis records."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, TypeVar, cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite.research_analysis_model import (
    ResearchAnalysisAuditEventRow,
    ResearchAnalysisWriteRequestRow,
    ResearchAnnotationRow,
    ResearchBatchCodingRunRow,
    ResearchCaseProfileRow,
    ResearchCodebookEntryRow,
    ResearchCodeRow,
    ResearchCodingPlanRow,
    ResearchComparisonRow,
    ResearchMatrixCellRow,
    ResearchMemoLinkRow,
    ResearchMemoRow,
    ResearchMethodPresetRow,
    ResearchThemeRow,
)
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
    BatchCodingRun,
    BatchCodingStatus,
    CaseComparison,
    CaseThemeMatrixCell,
    CodebookEntry,
    CodebookLifecycle,
    ComparisonFinding,
    ComparisonFindingKind,
    MatrixSubjectKind,
    MemoTargetKind,
    MethodPresetSelection,
    NextResearchStep,
    QualitativeMethod,
    ResearchAnalysisIdempotencyConflict,
)
from qunxue_api.modules.research_materials import MaterialLocator

DecisionRecord = AnalysisCode | AnalysisMemo | CaseComparison
DecisionRow = ResearchCodeRow | ResearchMemoRow | ResearchComparisonRow
DecisionModel = type[ResearchCodeRow] | type[ResearchMemoRow] | type[ResearchComparisonRow]
DecisionT = TypeVar("DecisionT", AnalysisCode, AnalysisMemo, CaseComparison)


def _batch_values(value: BatchCodingRun) -> dict[str, object]:
    return {
        "run_id": str(value.run_id),
        "user_id": str(value.user_id),
        "task_id": str(value.task_id),
        "material_id": str(value.material_id),
        "parse_id": str(value.parse_id),
        "parse_version": value.parse_version,
        "idempotency_key": value.idempotency_key,
        "status": value.status.value,
        "total_segments": value.total_segments,
        "processed_segments": value.processed_segments,
        "annotation_ids": [str(item) for item in value.annotation_ids],
        "code_ids": [str(item) for item in value.code_ids],
        "low_confidence_segments": list(value.low_confidence_segments),
        "error_code": value.error_code,
        "retry_count": value.retry_count,
        "created_at": value.created_at,
        "updated_at": value.updated_at,
        "completed_at": value.completed_at,
    }


def _coding_plan_values(value: AnalysisCodingPlan) -> dict[str, object]:
    return {
        "plan_id": str(value.plan_id),
        "user_id": str(value.user_id),
        "task_id": str(value.task_id),
        "title": value.title,
        "rationale": value.rationale,
        "items": [
            {
                "item_id": str(item.item_id),
                "material_id": str(item.material_id),
                "parse_id": str(item.parse_id),
                "segment_id": item.segment_id,
                "segment_content_hash": item.segment_content_hash,
                "quote": item.quote,
                "quote_hash": item.quote_hash,
                "quote_start": item.quote_start,
                "quote_end": item.quote_end,
                "locator": item.locator.as_dict(),
                "code_id": str(item.code_id),
                "code_label": item.code_label,
                "code_definition": item.code_definition,
                "codebook_version": item.codebook_version,
                "confidence": item.confidence,
                "rationale": item.rationale,
                "status": item.status.value,
                "annotation_id": _uuid_text(item.annotation_id),
                "decision_reason": item.decision_reason,
            }
            for item in value.items
        ],
        "source": value.source,
        "status": value.status.value,
        "version": value.version,
        "created_at": value.created_at,
        "conversation_id": _uuid_text(value.conversation_id),
        "agent_run_id": _uuid_text(value.agent_run_id),
        "agent_turn_id": _uuid_text(value.agent_turn_id),
        "tool_call_id": value.tool_call_id,
        "decided_at": value.decided_at,
        "decision_reason": value.decision_reason,
    }


def _audit_values(value: AnalysisAuditEvent) -> dict[str, object]:
    return {
        "event_id": str(value.event_id),
        "user_id": str(value.user_id),
        "task_id": str(value.task_id),
        "actor": value.actor,
        "action": value.action,
        "entity_kind": value.entity_kind,
        "entity_id": str(value.entity_id),
        "plan_id": _uuid_text(value.plan_id),
        "item_id": _uuid_text(value.item_id),
        "annotation_id": _uuid_text(value.annotation_id),
        "code_id": _uuid_text(value.code_id),
        "idempotency_key": value.idempotency_key,
        "provenance": dict(value.provenance),
        "payload": dict(value.payload),
        "created_at": value.created_at,
    }


def _batch(row: ResearchBatchCodingRunRow | None) -> BatchCodingRun | None:
    if row is None:
        return None
    return BatchCodingRun(
        run_id=UUID(row.run_id),
        user_id=UUID(row.user_id),
        task_id=UUID(row.task_id),
        material_id=UUID(row.material_id),
        parse_id=UUID(row.parse_id),
        parse_version=row.parse_version,
        idempotency_key=row.idempotency_key,
        status=BatchCodingStatus(row.status),
        total_segments=row.total_segments,
        processed_segments=row.processed_segments,
        annotation_ids=tuple(UUID(item) for item in row.annotation_ids),
        code_ids=tuple(UUID(item) for item in row.code_ids),
        low_confidence_segments=tuple(row.low_confidence_segments),
        error_code=row.error_code,
        retry_count=row.retry_count,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
        completed_at=_utc(row.completed_at),
    )


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _same_decision_subject(left: DecisionRecord, right: DecisionRecord) -> bool:
    if type(left) is not type(right):
        return False
    return (
        replace(
            left,
            status=right.status,
            version=right.version,
            decided_at=right.decided_at,
            decision_reason=right.decision_reason,
        )
        == right
    )


class SqliteResearchAnalysisRepository:
    """Persist immutable subjects and compare-and-set their user decisions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def reserve_write(self, value: AnalysisWriteRequest) -> AnalysisWriteRequest:
        self._session.execute(
            insert(ResearchAnalysisWriteRequestRow)
            .values(
                user_id=str(value.user_id),
                task_id=str(value.task_id),
                namespace=value.namespace,
                idempotency_key=value.idempotency_key,
                operation=value.operation,
                request_hash=value.request_hash,
                result_kind=value.result_kind,
                result_id=str(value.result_id),
                created_at=value.created_at,
            )
            .on_conflict_do_nothing(
                index_elements=["user_id", "task_id", "namespace", "idempotency_key"]
            )
        )
        row = self._session.scalar(
            select(ResearchAnalysisWriteRequestRow).where(
                ResearchAnalysisWriteRequestRow.user_id == str(value.user_id),
                ResearchAnalysisWriteRequestRow.task_id == str(value.task_id),
                ResearchAnalysisWriteRequestRow.namespace == value.namespace,
                ResearchAnalysisWriteRequestRow.idempotency_key == value.idempotency_key,
            )
        )
        persisted = _write_request(row)
        if persisted is None:
            raise RuntimeError("research analysis write identity was not persisted")
        if (
            persisted.operation != value.operation
            or persisted.request_hash != value.request_hash
            or persisted.result_kind != value.result_kind
        ):
            raise ResearchAnalysisIdempotencyConflict(
                "idempotency key was already used for a different analysis write"
            )
        return persisted

    def get_write(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        namespace: str,
        idempotency_key: str,
    ) -> AnalysisWriteRequest | None:
        return _write_request(
            self._session.scalar(
                select(ResearchAnalysisWriteRequestRow).where(
                    ResearchAnalysisWriteRequestRow.user_id == str(user_id),
                    ResearchAnalysisWriteRequestRow.task_id == str(task_id),
                    ResearchAnalysisWriteRequestRow.namespace == namespace,
                    ResearchAnalysisWriteRequestRow.idempotency_key == idempotency_key,
                )
            )
        )

    def add_batch(self, value: BatchCodingRun) -> BatchCodingRun:
        self._session.execute(
            insert(ResearchBatchCodingRunRow)
            .values(**_batch_values(value))
            .on_conflict_do_nothing(index_elements=["run_id"])
        )
        persisted = _batch(self._row_by_id(ResearchBatchCodingRunRow, "run_id", value.run_id))
        if persisted is None:
            raise RuntimeError("batch coding run was not persisted")
        return persisted

    def get_batch(self, run_id: UUID, *, user_id: UUID, task_id: UUID) -> BatchCodingRun | None:
        return _batch(
            self._owned_row(ResearchBatchCodingRunRow, "run_id", run_id, user_id, task_id)
        )

    def get_batch_by_idempotency(
        self, *, user_id: UUID, task_id: UUID, material_id: UUID, idempotency_key: str
    ) -> BatchCodingRun | None:
        row = self._session.scalar(
            select(ResearchBatchCodingRunRow).where(
                ResearchBatchCodingRunRow.user_id == str(user_id),
                ResearchBatchCodingRunRow.task_id == str(task_id),
                ResearchBatchCodingRunRow.material_id == str(material_id),
                ResearchBatchCodingRunRow.idempotency_key == idempotency_key,
            )
        )
        return _batch(row)

    def save_batch(self, value: BatchCodingRun) -> BatchCodingRun:
        self._session.execute(
            update(ResearchBatchCodingRunRow)
            .where(ResearchBatchCodingRunRow.run_id == str(value.run_id))
            .values(**_batch_values(value))
        )
        persisted = _batch(self._row_by_id(ResearchBatchCodingRunRow, "run_id", value.run_id))
        if persisted is None:
            raise RuntimeError("batch coding run was not persisted")
        return persisted

    # BatchCodingRepository protocol aliases keep the application independent
    # from the broader analysis repository's historical method names.
    add = add_batch
    get = get_batch
    get_by_idempotency = get_batch_by_idempotency
    save = save_batch

    def add_annotation(self, value: AnalysisAnnotation) -> AnalysisAnnotation:
        self._session.execute(
            insert(ResearchAnnotationRow)
            .values(
                annotation_id=str(value.annotation_id),
                user_id=str(value.user_id),
                task_id=str(value.task_id),
                material_id=str(value.material_id),
                parse_id=str(value.parse_id),
                segment_id=value.segment_id,
                segment_content_hash=value.segment_content_hash,
                quote=value.quote,
                quote_hash=value.quote_hash,
                quote_start=value.quote_start,
                quote_end=value.quote_end,
                locator=value.locator.as_dict(),
                annotation_kind=value.annotation_kind.value,
                case_label=value.case_label,
                observed_at=value.observed_at,
                note=value.note,
                reflection=value.reflection,
                created_at=value.created_at,
            )
            .on_conflict_do_nothing(index_elements=["annotation_id"])
        )
        persisted = _annotation(
            self._row_by_id(
                ResearchAnnotationRow,
                "annotation_id",
                value.annotation_id,
            )
        )
        if persisted is None:
            raise RuntimeError("research annotation was not persisted")
        self._ensure_same_scope(persisted, value)
        if persisted != value:
            raise ValueError("analysis annotation identity already contains different content")
        return persisted

    def add_code(self, value: AnalysisCode) -> AnalysisCode:
        return self._save_decision(
            model=ResearchCodeRow,
            key_name="code_id",
            value=value,
            values={
                "code_id": str(value.code_id),
                "user_id": str(value.user_id),
                "task_id": str(value.task_id),
                "label": value.label,
                "definition": value.definition,
                "annotation_ids": [str(item) for item in value.annotation_ids],
                "rationale": value.rationale,
                "source": value.source,
                "status": value.status.value,
                "version": value.version,
                "created_at": value.created_at,
                "conversation_id": _uuid_text(value.conversation_id),
                "agent_run_id": _uuid_text(value.agent_run_id),
                "agent_turn_id": _uuid_text(value.agent_turn_id),
                "tool_call_id": value.tool_call_id,
                "decided_at": value.decided_at,
                "decision_reason": value.decision_reason,
            },
            converter=_code,
        )

    def add_memo(self, value: AnalysisMemo) -> AnalysisMemo:
        return self._save_decision(
            model=ResearchMemoRow,
            key_name="memo_id",
            value=value,
            values={
                "memo_id": str(value.memo_id),
                "user_id": str(value.user_id),
                "task_id": str(value.task_id),
                "title": value.title,
                "content": value.content,
                "memo_kind": value.memo_kind.value,
                "annotation_ids": [str(item) for item in value.annotation_ids],
                "code_ids": [str(item) for item in value.code_ids],
                "source": value.source,
                "status": value.status.value,
                "version": value.version,
                "created_at": value.created_at,
                "conversation_id": _uuid_text(value.conversation_id),
                "agent_run_id": _uuid_text(value.agent_run_id),
                "agent_turn_id": _uuid_text(value.agent_turn_id),
                "tool_call_id": value.tool_call_id,
                "decided_at": value.decided_at,
                "decision_reason": value.decision_reason,
            },
            converter=_memo,
        )

    def add_comparison(self, value: CaseComparison) -> CaseComparison:
        return self._save_decision(
            model=ResearchComparisonRow,
            key_name="comparison_id",
            value=value,
            values={
                "comparison_id": str(value.comparison_id),
                "user_id": str(value.user_id),
                "task_id": str(value.task_id),
                "title": value.title,
                "question": value.question,
                "case_labels": list(value.case_labels),
                "time_labels": list(value.time_labels),
                "findings": [
                    {
                        "kind": finding.kind.value,
                        "statement": finding.statement,
                        "annotation_ids": [
                            str(annotation_id) for annotation_id in finding.annotation_ids
                        ],
                    }
                    for finding in value.findings
                ],
                "competing_explanations": list(value.competing_explanations),
                "evidence_gaps": list(value.evidence_gaps),
                "next_steps": [
                    {
                        "kind": step.kind,
                        "action": step.action,
                        "priority": step.priority,
                    }
                    for step in value.next_steps
                ],
                "theory_implication": value.theory_implication,
                "source": value.source,
                "status": value.status.value,
                "version": value.version,
                "created_at": value.created_at,
                "conversation_id": _uuid_text(value.conversation_id),
                "agent_run_id": _uuid_text(value.agent_run_id),
                "agent_turn_id": _uuid_text(value.agent_turn_id),
                "tool_call_id": value.tool_call_id,
                "decided_at": value.decided_at,
                "decision_reason": value.decision_reason,
            },
            converter=_comparison,
        )

    def add_coding_plan(self, value: AnalysisCodingPlan) -> AnalysisCodingPlan:
        self._session.execute(
            insert(ResearchCodingPlanRow)
            .values(**_coding_plan_values(value))
            .on_conflict_do_update(
                index_elements=["plan_id"],
                set_={
                    key: item
                    for key, item in _coding_plan_values(value).items()
                    if key != "plan_id"
                },
                where=ResearchCodingPlanRow.version < value.version,
            )
        )
        persisted = _coding_plan(self._row_by_id(ResearchCodingPlanRow, "plan_id", value.plan_id))
        if persisted is None:
            raise RuntimeError("coding plan was not persisted")
        self._ensure_same_scope(persisted, value)
        return persisted

    def get_coding_plan(
        self, plan_id: UUID, *, user_id: UUID, task_id: UUID
    ) -> AnalysisCodingPlan | None:
        return _coding_plan(
            self._owned_row(ResearchCodingPlanRow, "plan_id", plan_id, user_id, task_id)
        )

    def list_coding_plans(self, *, user_id: UUID, task_id: UUID) -> tuple[AnalysisCodingPlan, ...]:
        return tuple(
            _coding_plan(row) for row in self._owned_rows(ResearchCodingPlanRow, user_id, task_id)
        )

    def add_audit_event(self, value: AnalysisAuditEvent) -> AnalysisAuditEvent:
        self._session.execute(
            insert(ResearchAnalysisAuditEventRow)
            .values(**_audit_values(value))
            .on_conflict_do_nothing(index_elements=["event_id"])
        )
        row = self._row_by_id(ResearchAnalysisAuditEventRow, "event_id", value.event_id)
        persisted = _audit(row)
        if persisted is None:
            raise RuntimeError("analysis audit event was not persisted")
        self._ensure_same_scope(persisted, value)
        return persisted

    def list_audit_events(self, *, user_id: UUID, task_id: UUID) -> tuple[AnalysisAuditEvent, ...]:
        return tuple(
            _audit(row) for row in self._owned_rows(ResearchAnalysisAuditEventRow, user_id, task_id)
        )

    def get_code(
        self,
        code_id: UUID,
        *,
        user_id: UUID,
        task_id: UUID,
    ) -> AnalysisCode | None:
        return _code(
            self._owned_row(
                ResearchCodeRow,
                "code_id",
                code_id,
                user_id,
                task_id,
            )
        )

    def get_annotation(
        self,
        annotation_id: UUID,
        *,
        user_id: UUID,
        task_id: UUID,
    ) -> AnalysisAnnotation | None:
        return _annotation(
            self._owned_row(
                ResearchAnnotationRow,
                "annotation_id",
                annotation_id,
                user_id,
                task_id,
            )
        )

    def get_memo(
        self,
        memo_id: UUID,
        *,
        user_id: UUID,
        task_id: UUID,
    ) -> AnalysisMemo | None:
        return _memo(
            self._owned_row(
                ResearchMemoRow,
                "memo_id",
                memo_id,
                user_id,
                task_id,
            )
        )

    def get_comparison(
        self,
        comparison_id: UUID,
        *,
        user_id: UUID,
        task_id: UUID,
    ) -> CaseComparison | None:
        return _comparison(
            self._owned_row(
                ResearchComparisonRow,
                "comparison_id",
                comparison_id,
                user_id,
                task_id,
            )
        )

    def list_annotations(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
    ) -> tuple[AnalysisAnnotation, ...]:
        rows = self._owned_rows(ResearchAnnotationRow, user_id, task_id)
        return tuple(_annotation(row) for row in rows)

    def list_codes(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
    ) -> tuple[AnalysisCode, ...]:
        rows = self._owned_rows(ResearchCodeRow, user_id, task_id)
        return tuple(_code(row) for row in rows)

    def list_memos(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
    ) -> tuple[AnalysisMemo, ...]:
        rows = self._owned_rows(ResearchMemoRow, user_id, task_id)
        return tuple(_memo(row) for row in rows)

    def list_comparisons(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
    ) -> tuple[CaseComparison, ...]:
        rows = self._owned_rows(ResearchComparisonRow, user_id, task_id)
        return tuple(_comparison(row) for row in rows)

    def add_codebook_entry(self, value: CodebookEntry) -> CodebookEntry:
        values = {
            "code_id": str(value.code_id),
            "user_id": str(value.user_id),
            "task_id": str(value.task_id),
            "inclusion_rules": list(value.inclusion_rules),
            "exclusion_rules": list(value.exclusion_rules),
            "parent_code_id": _uuid_text(value.parent_code_id),
            "positive_example_annotation_ids": [
                str(item) for item in value.positive_example_annotation_ids
            ],
            "negative_example_annotation_ids": [
                str(item) for item in value.negative_example_annotation_ids
            ],
            "lifecycle": value.lifecycle.value,
            "related_code_ids": [str(item) for item in value.related_code_ids],
            "version": value.version,
            "updated_at": value.updated_at,
            "revision_reason": value.revision_reason,
        }
        self._upsert_workspace_version(
            model=ResearchCodebookEntryRow,
            index_elements=["code_id"],
            values=values,
            version=value.version,
        )
        persisted = _codebook_entry(
            self._session.scalar(
                select(ResearchCodebookEntryRow)
                .where(ResearchCodebookEntryRow.code_id == str(value.code_id))
                .execution_options(populate_existing=True)
            )
        )
        if persisted is None:
            raise RuntimeError("codebook entry was not persisted")
        self._ensure_same_scope(persisted, value)
        return persisted

    def get_codebook_entry(
        self, code_id: UUID, *, user_id: UUID, task_id: UUID
    ) -> CodebookEntry | None:
        return _codebook_entry(
            self._session.scalar(
                select(ResearchCodebookEntryRow).where(
                    ResearchCodebookEntryRow.code_id == str(code_id),
                    ResearchCodebookEntryRow.user_id == str(user_id),
                    ResearchCodebookEntryRow.task_id == str(task_id),
                )
            )
        )

    def list_codebook_entries(self, *, user_id: UUID, task_id: UUID) -> tuple[CodebookEntry, ...]:
        rows = self._session.scalars(
            select(ResearchCodebookEntryRow)
            .where(
                ResearchCodebookEntryRow.user_id == str(user_id),
                ResearchCodebookEntryRow.task_id == str(task_id),
            )
            .order_by(ResearchCodebookEntryRow.updated_at, ResearchCodebookEntryRow.code_id)
        )
        return tuple(_codebook_entry(row) for row in rows)

    def add_theme(self, value: AnalysisTheme) -> AnalysisTheme:
        values = {
            "theme_id": str(value.theme_id),
            "user_id": str(value.user_id),
            "task_id": str(value.task_id),
            "label": value.label,
            "central_concept": value.central_concept,
            "code_ids": [str(item) for item in value.code_ids],
            "annotation_ids": [str(item) for item in value.annotation_ids],
            "source": value.source,
            "status": value.status.value,
            "version": value.version,
            "created_at": value.created_at,
            "decided_at": value.decided_at,
            "decision_reason": value.decision_reason,
        }
        self._upsert_workspace_version(
            model=ResearchThemeRow,
            index_elements=["theme_id"],
            values=values,
            version=value.version,
        )
        persisted = _theme(
            self._session.scalar(
                select(ResearchThemeRow)
                .where(ResearchThemeRow.theme_id == str(value.theme_id))
                .execution_options(populate_existing=True)
            )
        )
        if persisted is None:
            raise RuntimeError("analysis theme was not persisted")
        self._ensure_same_scope(persisted, value)
        return persisted

    def get_theme(self, theme_id: UUID, *, user_id: UUID, task_id: UUID) -> AnalysisTheme | None:
        return _theme(
            self._session.scalar(
                select(ResearchThemeRow).where(
                    ResearchThemeRow.theme_id == str(theme_id),
                    ResearchThemeRow.user_id == str(user_id),
                    ResearchThemeRow.task_id == str(task_id),
                )
            )
        )

    def list_themes(self, *, user_id: UUID, task_id: UUID) -> tuple[AnalysisTheme, ...]:
        rows = self._session.scalars(
            select(ResearchThemeRow)
            .where(
                ResearchThemeRow.user_id == str(user_id),
                ResearchThemeRow.task_id == str(task_id),
            )
            .order_by(ResearchThemeRow.created_at, ResearchThemeRow.theme_id)
        )
        return tuple(_theme(row) for row in rows)

    def add_memo_link(self, value: AnalysisMemoLink) -> AnalysisMemoLink:
        self._session.execute(
            insert(ResearchMemoLinkRow)
            .values(
                link_id=str(value.link_id),
                user_id=str(value.user_id),
                task_id=str(value.task_id),
                memo_id=str(value.memo_id),
                target_kind=value.target_kind.value,
                target_ref=value.target_ref,
                annotation_ids=[str(item) for item in value.annotation_ids],
                created_at=value.created_at,
            )
            .on_conflict_do_nothing(index_elements=["link_id"])
        )
        persisted = _memo_link(
            self._session.scalar(
                select(ResearchMemoLinkRow).where(ResearchMemoLinkRow.link_id == str(value.link_id))
            )
        )
        if persisted is None:
            raise RuntimeError("analysis memo link was not persisted")
        self._ensure_same_scope(persisted, value)
        if persisted != value:
            raise ValueError("analysis memo link identity contains different content")
        return persisted

    def list_memo_links(self, *, user_id: UUID, task_id: UUID) -> tuple[AnalysisMemoLink, ...]:
        rows = self._session.scalars(
            select(ResearchMemoLinkRow)
            .where(
                ResearchMemoLinkRow.user_id == str(user_id),
                ResearchMemoLinkRow.task_id == str(task_id),
            )
            .order_by(ResearchMemoLinkRow.created_at, ResearchMemoLinkRow.link_id)
        )
        return tuple(_memo_link(row) for row in rows)

    def add_case_profile(self, value: AnalysisCaseProfile) -> AnalysisCaseProfile:
        values = {
            "profile_id": str(value.profile_id),
            "user_id": str(value.user_id),
            "task_id": str(value.task_id),
            "case_ref": value.case_ref,
            "display_label": value.display_label,
            "attributes": [list(item) for item in value.attributes],
            "summary": value.summary,
            "annotation_ids": [str(item) for item in value.annotation_ids],
            "memo_ids": [str(item) for item in value.memo_ids],
            "version": value.version,
            "updated_at": value.updated_at,
        }
        self._upsert_workspace_version(
            model=ResearchCaseProfileRow,
            index_elements=["profile_id"],
            values=values,
            version=value.version,
        )
        persisted = _case_profile(
            self._session.scalar(
                select(ResearchCaseProfileRow)
                .where(ResearchCaseProfileRow.profile_id == str(value.profile_id))
                .execution_options(populate_existing=True)
            )
        )
        if persisted is None:
            raise RuntimeError("analysis case profile was not persisted")
        self._ensure_same_scope(persisted, value)
        return persisted

    def get_case_profile(
        self, profile_id: UUID, *, user_id: UUID, task_id: UUID
    ) -> AnalysisCaseProfile | None:
        return _case_profile(
            self._session.scalar(
                select(ResearchCaseProfileRow).where(
                    ResearchCaseProfileRow.profile_id == str(profile_id),
                    ResearchCaseProfileRow.user_id == str(user_id),
                    ResearchCaseProfileRow.task_id == str(task_id),
                )
            )
        )

    def list_case_profiles(
        self, *, user_id: UUID, task_id: UUID
    ) -> tuple[AnalysisCaseProfile, ...]:
        rows = self._session.scalars(
            select(ResearchCaseProfileRow)
            .where(
                ResearchCaseProfileRow.user_id == str(user_id),
                ResearchCaseProfileRow.task_id == str(task_id),
            )
            .order_by(ResearchCaseProfileRow.updated_at, ResearchCaseProfileRow.profile_id)
        )
        return tuple(_case_profile(row) for row in rows)

    def add_matrix_cell(self, value: CaseThemeMatrixCell) -> CaseThemeMatrixCell:
        values = {
            "cell_id": str(value.cell_id),
            "user_id": str(value.user_id),
            "task_id": str(value.task_id),
            "case_profile_id": str(value.case_profile_id),
            "subject_kind": value.subject_kind.value,
            "subject_id": str(value.subject_id),
            "summary": value.summary,
            "annotation_ids": [str(item) for item in value.annotation_ids],
            "memo_ids": [str(item) for item in value.memo_ids],
            "finding_kinds": [item.value for item in value.finding_kinds],
            "version": value.version,
            "updated_at": value.updated_at,
        }
        self._upsert_workspace_version(
            model=ResearchMatrixCellRow,
            index_elements=["cell_id"],
            values=values,
            version=value.version,
        )
        persisted = _matrix_cell(
            self._session.scalar(
                select(ResearchMatrixCellRow)
                .where(ResearchMatrixCellRow.cell_id == str(value.cell_id))
                .execution_options(populate_existing=True)
            )
        )
        if persisted is None:
            raise RuntimeError("analysis matrix cell was not persisted")
        self._ensure_same_scope(persisted, value)
        return persisted

    def list_matrix_cells(self, *, user_id: UUID, task_id: UUID) -> tuple[CaseThemeMatrixCell, ...]:
        rows = self._session.scalars(
            select(ResearchMatrixCellRow)
            .where(
                ResearchMatrixCellRow.user_id == str(user_id),
                ResearchMatrixCellRow.task_id == str(task_id),
            )
            .order_by(ResearchMatrixCellRow.updated_at, ResearchMatrixCellRow.cell_id)
        )
        return tuple(_matrix_cell(row) for row in rows)

    def add_method_selection(self, value: MethodPresetSelection) -> MethodPresetSelection:
        values = {
            "user_id": str(value.user_id),
            "task_id": str(value.task_id),
            "method": value.method.value,
            "version": value.version,
            "updated_at": value.updated_at,
        }
        self._upsert_workspace_version(
            model=ResearchMethodPresetRow,
            index_elements=["user_id", "task_id"],
            values=values,
            version=value.version,
        )
        persisted = _method_selection(
            self._session.scalar(
                select(ResearchMethodPresetRow)
                .where(
                    ResearchMethodPresetRow.user_id == str(value.user_id),
                    ResearchMethodPresetRow.task_id == str(value.task_id),
                )
                .execution_options(populate_existing=True)
            )
        )
        if persisted is None:
            raise RuntimeError("analysis method preset was not persisted")
        return persisted

    def get_method_selection(self, *, user_id: UUID, task_id: UUID) -> MethodPresetSelection | None:
        return _method_selection(
            self._session.scalar(
                select(ResearchMethodPresetRow).where(
                    ResearchMethodPresetRow.user_id == str(user_id),
                    ResearchMethodPresetRow.task_id == str(task_id),
                )
            )
        )

    def _upsert_workspace_version(
        self,
        *,
        model: Any,
        index_elements: list[str],
        values: dict[str, object],
        version: int,
    ) -> None:
        self._session.execute(
            insert(model)
            .values(**values)
            .on_conflict_do_update(
                index_elements=index_elements,
                set_={key: value for key, value in values.items() if key not in index_elements},
                where=model.version < version,
            )
        )

    def _save_decision(
        self,
        *,
        model: DecisionModel | type[ResearchAnnotationRow],
        key_name: str,
        value: DecisionT,
        values: dict[str, object],
        converter: Callable[[Any], DecisionT | None],
    ) -> DecisionT:
        self._session.execute(
            insert(model).values(**values).on_conflict_do_nothing(index_elements=[key_name])
        )
        key_value = cast(UUID, getattr(value, key_name))
        persisted = converter(self._row_by_id(model, key_name, key_value))
        if persisted is None:
            raise RuntimeError("research analysis record was not persisted")
        self._ensure_same_scope(persisted, value)
        attachment_update = (
            isinstance(persisted, AnalysisCode)
            and isinstance(value, AnalysisCode)
            and persisted.status is AnalysisCodeStatus.CONFIRMED
            and value.status is AnalysisCodeStatus.CONFIRMED
            and value.version == persisted.version + 1
            and replace(
                persisted,
                annotation_ids=value.annotation_ids,
                version=value.version,
                decided_at=value.decided_at,
            )
            == value
        )
        if not _same_decision_subject(persisted, value) and not attachment_update:
            raise ValueError("analysis record identity already contains different content")
        if (
            persisted.status.value == "candidate"
            and value.status.value in {"confirmed", "rejected"}
            and value.version == persisted.version + 1
        ):
            result = self._session.execute(
                update(model)
                .where(
                    getattr(model, key_name) == str(key_value),
                    model.user_id == str(value.user_id),
                    model.task_id == str(value.task_id),
                    model.status == "candidate",
                    model.version == value.version - 1,
                )
                .values(
                    status=value.status.value,
                    version=value.version,
                    decided_at=value.decided_at,
                    decision_reason=value.decision_reason,
                )
            )
            if result.rowcount == 1:
                return value
        if attachment_update:
            result = self._session.execute(
                update(model)
                .where(
                    getattr(model, key_name) == str(key_value),
                    model.user_id == str(value.user_id),
                    model.task_id == str(value.task_id),
                    model.status == "confirmed",
                    model.version == value.version - 1,
                )
                .values(
                    annotation_ids=[str(item) for item in value.annotation_ids],
                    version=value.version,
                    decided_at=value.decided_at,
                )
            )
            if result.rowcount == 1:
                return value
        winner = converter(self._row_by_id(model, key_name, key_value, refresh=True))
        if winner is None:
            raise RuntimeError("research analysis record disappeared during update")
        return winner

    def _row_by_id(
        self,
        model: DecisionModel | type[ResearchAnnotationRow],
        key_name: str,
        value: UUID,
        *,
        refresh: bool = False,
    ) -> DecisionRow | ResearchAnnotationRow | None:
        query = select(model).where(getattr(model, key_name) == str(value))
        if refresh:
            query = query.execution_options(populate_existing=True)
        return self._session.scalar(query)

    def _owned_row(
        self,
        model: DecisionModel,
        key_name: str,
        value: UUID,
        user_id: UUID,
        task_id: UUID,
    ) -> DecisionRow | ResearchAnnotationRow | None:
        return self._session.scalar(
            select(model).where(
                getattr(model, key_name) == str(value),
                model.user_id == str(user_id),
                model.task_id == str(task_id),
            )
        )

    def _owned_rows(
        self,
        model: DecisionModel | type[ResearchAnnotationRow],
        user_id: UUID,
        task_id: UUID,
    ) -> tuple[DecisionRow | ResearchAnnotationRow, ...]:
        primary_key = tuple(model.__table__.primary_key.columns)[0]
        rows = self._session.scalars(
            select(model)
            .where(
                model.user_id == str(user_id),
                model.task_id == str(task_id),
            )
            .order_by(model.created_at, primary_key)
        )
        return tuple(rows)

    @staticmethod
    def _ensure_same_scope(left: Any, right: Any) -> None:
        if left.user_id != right.user_id or left.task_id != right.task_id:
            raise ValueError("analysis record identity already belongs to another research task")


def _annotation(row: ResearchAnnotationRow | None) -> AnalysisAnnotation | None:
    if row is None:
        return None
    created_at = _utc(row.created_at)
    if created_at is None:
        raise ValueError("research annotation is missing created_at")
    return AnalysisAnnotation(
        annotation_id=UUID(row.annotation_id),
        user_id=UUID(row.user_id),
        task_id=UUID(row.task_id),
        material_id=UUID(row.material_id),
        parse_id=UUID(row.parse_id),
        segment_id=row.segment_id,
        segment_content_hash=row.segment_content_hash,
        quote=row.quote,
        quote_hash=row.quote_hash,
        quote_start=row.quote_start,
        quote_end=row.quote_end,
        locator=MaterialLocator.from_dict(row.locator),
        annotation_kind=AnalysisAnnotationKind(row.annotation_kind),
        case_label=row.case_label,
        observed_at=row.observed_at,
        note=row.note,
        reflection=row.reflection,
        created_at=created_at,
    )


def _write_request(
    row: ResearchAnalysisWriteRequestRow | None,
) -> AnalysisWriteRequest | None:
    if row is None:
        return None
    created_at = _utc(row.created_at)
    if created_at is None:
        raise ValueError("research analysis write request is missing created_at")
    return AnalysisWriteRequest(
        user_id=UUID(row.user_id),
        task_id=UUID(row.task_id),
        namespace=row.namespace,
        idempotency_key=row.idempotency_key,
        operation=row.operation,
        request_hash=row.request_hash,
        result_kind=row.result_kind,
        result_id=UUID(row.result_id),
        created_at=created_at,
    )


def _uuid_text(value: UUID | None) -> str | None:
    return str(value) if value is not None else None


def _coding_plan(row: ResearchCodingPlanRow | None) -> AnalysisCodingPlan | None:
    if row is None:
        return None
    created_at = _utc(row.created_at)
    if created_at is None:
        raise ValueError("coding plan is missing created_at")
    return AnalysisCodingPlan(
        plan_id=UUID(row.plan_id),
        user_id=UUID(row.user_id),
        task_id=UUID(row.task_id),
        title=row.title,
        rationale=row.rationale,
        items=tuple(
            AnalysisCodingPlanItem(
                item_id=UUID(item["item_id"]),
                material_id=UUID(item["material_id"]),
                parse_id=UUID(item["parse_id"]),
                segment_id=item["segment_id"],
                segment_content_hash=item["segment_content_hash"],
                quote=item["quote"],
                quote_hash=item["quote_hash"],
                quote_start=item["quote_start"],
                quote_end=item["quote_end"],
                locator=MaterialLocator.from_dict(item["locator"]),
                code_id=UUID(item["code_id"]),
                code_label=item["code_label"],
                code_definition=item["code_definition"],
                codebook_version=item.get("codebook_version"),
                confidence=float(item["confidence"]),
                rationale=item["rationale"],
                status=AnalysisCodingPlanItemStatus(item.get("status", "candidate")),
                annotation_id=UUID(item["annotation_id"]) if item.get("annotation_id") else None,
                decision_reason=item.get("decision_reason"),
            )
            for item in row.items
        ),
        source=row.source,
        status=AnalysisCodingPlanStatus(row.status),
        version=row.version,
        created_at=created_at,
        conversation_id=UUID(row.conversation_id) if row.conversation_id else None,
        agent_run_id=UUID(row.agent_run_id) if row.agent_run_id else None,
        agent_turn_id=UUID(row.agent_turn_id) if row.agent_turn_id else None,
        tool_call_id=row.tool_call_id,
        decided_at=_utc(row.decided_at),
        decision_reason=row.decision_reason,
    )


def _audit(row: ResearchAnalysisAuditEventRow | None) -> AnalysisAuditEvent | None:
    if row is None:
        return None
    created_at = _utc(row.created_at)
    if created_at is None:
        raise ValueError("analysis audit event is missing created_at")
    return AnalysisAuditEvent(
        event_id=UUID(row.event_id),
        user_id=UUID(row.user_id),
        task_id=UUID(row.task_id),
        actor=row.actor,
        action=row.action,
        entity_kind=row.entity_kind,
        entity_id=UUID(row.entity_id),
        plan_id=UUID(row.plan_id) if row.plan_id else None,
        item_id=UUID(row.item_id) if row.item_id else None,
        annotation_id=UUID(row.annotation_id) if row.annotation_id else None,
        code_id=UUID(row.code_id) if row.code_id else None,
        idempotency_key=row.idempotency_key,
        provenance=dict(row.provenance),
        payload=dict(row.payload),
        created_at=created_at,
    )


def _code(row: ResearchCodeRow | None) -> AnalysisCode | None:
    if row is None:
        return None
    created_at = _utc(row.created_at)
    if created_at is None:
        raise ValueError("research code is missing created_at")
    return AnalysisCode(
        code_id=UUID(row.code_id),
        user_id=UUID(row.user_id),
        task_id=UUID(row.task_id),
        label=row.label,
        definition=row.definition,
        annotation_ids=tuple(UUID(item) for item in row.annotation_ids),
        rationale=row.rationale,
        source=row.source,
        status=AnalysisCodeStatus(row.status),
        version=row.version,
        created_at=created_at,
        conversation_id=UUID(row.conversation_id) if row.conversation_id else None,
        agent_run_id=UUID(row.agent_run_id) if row.agent_run_id else None,
        agent_turn_id=UUID(row.agent_turn_id) if row.agent_turn_id else None,
        tool_call_id=row.tool_call_id,
        decided_at=_utc(row.decided_at),
        decision_reason=row.decision_reason,
    )


def _memo(row: ResearchMemoRow | None) -> AnalysisMemo | None:
    if row is None:
        return None
    created_at = _utc(row.created_at)
    if created_at is None:
        raise ValueError("research memo is missing created_at")
    return AnalysisMemo(
        memo_id=UUID(row.memo_id),
        user_id=UUID(row.user_id),
        task_id=UUID(row.task_id),
        title=row.title,
        content=row.content,
        memo_kind=AnalysisMemoKind(row.memo_kind),
        annotation_ids=tuple(UUID(item) for item in row.annotation_ids),
        code_ids=tuple(UUID(item) for item in row.code_ids),
        source=row.source,
        status=AnalysisRecordStatus(row.status),
        version=row.version,
        created_at=created_at,
        conversation_id=UUID(row.conversation_id) if row.conversation_id else None,
        agent_run_id=UUID(row.agent_run_id) if row.agent_run_id else None,
        agent_turn_id=UUID(row.agent_turn_id) if row.agent_turn_id else None,
        tool_call_id=row.tool_call_id,
        decided_at=_utc(row.decided_at),
        decision_reason=row.decision_reason,
    )


def _comparison(row: ResearchComparisonRow | None) -> CaseComparison | None:
    if row is None:
        return None
    created_at = _utc(row.created_at)
    if created_at is None:
        raise ValueError("research comparison is missing created_at")
    return CaseComparison(
        comparison_id=UUID(row.comparison_id),
        user_id=UUID(row.user_id),
        task_id=UUID(row.task_id),
        title=row.title,
        question=row.question,
        case_labels=tuple(row.case_labels),
        time_labels=tuple(row.time_labels),
        findings=tuple(
            ComparisonFinding(
                kind=ComparisonFindingKind(item["kind"]),
                statement=cast(str, item["statement"]),
                annotation_ids=tuple(
                    UUID(annotation_id)
                    for annotation_id in cast(list[str], item.get("annotation_ids", []))
                ),
            )
            for item in row.findings
        ),
        competing_explanations=tuple(row.competing_explanations),
        evidence_gaps=tuple(row.evidence_gaps),
        next_steps=tuple(
            NextResearchStep(
                kind=cast(str, item["kind"]),
                action=cast(str, item["action"]),
                priority=cast(str, item["priority"]),
            )
            for item in row.next_steps
        ),
        theory_implication=row.theory_implication,
        source=row.source,
        status=AnalysisRecordStatus(row.status),
        version=row.version,
        created_at=created_at,
        conversation_id=UUID(row.conversation_id) if row.conversation_id else None,
        agent_run_id=UUID(row.agent_run_id) if row.agent_run_id else None,
        agent_turn_id=UUID(row.agent_turn_id) if row.agent_turn_id else None,
        tool_call_id=row.tool_call_id,
        decided_at=_utc(row.decided_at),
        decision_reason=row.decision_reason,
    )


def _codebook_entry(row: ResearchCodebookEntryRow | None) -> CodebookEntry | None:
    if row is None:
        return None
    updated_at = _utc(row.updated_at)
    if updated_at is None:
        raise ValueError("codebook entry is missing updated_at")
    return CodebookEntry(
        user_id=UUID(row.user_id),
        task_id=UUID(row.task_id),
        code_id=UUID(row.code_id),
        inclusion_rules=tuple(row.inclusion_rules),
        exclusion_rules=tuple(row.exclusion_rules),
        parent_code_id=UUID(row.parent_code_id) if row.parent_code_id else None,
        positive_example_annotation_ids=tuple(
            UUID(item) for item in row.positive_example_annotation_ids
        ),
        negative_example_annotation_ids=tuple(
            UUID(item) for item in row.negative_example_annotation_ids
        ),
        lifecycle=CodebookLifecycle(row.lifecycle),
        related_code_ids=tuple(UUID(item) for item in row.related_code_ids),
        version=row.version,
        updated_at=updated_at,
        revision_reason=row.revision_reason,
    )


def _theme(row: ResearchThemeRow | None) -> AnalysisTheme | None:
    if row is None:
        return None
    created_at = _utc(row.created_at)
    if created_at is None:
        raise ValueError("analysis theme is missing created_at")
    return AnalysisTheme(
        theme_id=UUID(row.theme_id),
        user_id=UUID(row.user_id),
        task_id=UUID(row.task_id),
        label=row.label,
        central_concept=row.central_concept,
        code_ids=tuple(UUID(item) for item in row.code_ids),
        annotation_ids=tuple(UUID(item) for item in row.annotation_ids),
        source=row.source,
        status=AnalysisRecordStatus(row.status),
        version=row.version,
        created_at=created_at,
        decided_at=_utc(row.decided_at),
        decision_reason=row.decision_reason,
    )


def _memo_link(row: ResearchMemoLinkRow | None) -> AnalysisMemoLink | None:
    if row is None:
        return None
    created_at = _utc(row.created_at)
    if created_at is None:
        raise ValueError("analysis memo link is missing created_at")
    return AnalysisMemoLink(
        link_id=UUID(row.link_id),
        user_id=UUID(row.user_id),
        task_id=UUID(row.task_id),
        memo_id=UUID(row.memo_id),
        target_kind=MemoTargetKind(row.target_kind),
        target_ref=row.target_ref,
        annotation_ids=tuple(UUID(item) for item in row.annotation_ids),
        created_at=created_at,
    )


def _case_profile(row: ResearchCaseProfileRow | None) -> AnalysisCaseProfile | None:
    if row is None:
        return None
    updated_at = _utc(row.updated_at)
    if updated_at is None:
        raise ValueError("analysis case profile is missing updated_at")
    return AnalysisCaseProfile(
        profile_id=UUID(row.profile_id),
        user_id=UUID(row.user_id),
        task_id=UUID(row.task_id),
        case_ref=row.case_ref,
        display_label=row.display_label,
        attributes=tuple((item[0], item[1]) for item in row.attributes),
        summary=row.summary,
        annotation_ids=tuple(UUID(item) for item in row.annotation_ids),
        memo_ids=tuple(UUID(item) for item in row.memo_ids),
        version=row.version,
        updated_at=updated_at,
    )


def _matrix_cell(row: ResearchMatrixCellRow | None) -> CaseThemeMatrixCell | None:
    if row is None:
        return None
    updated_at = _utc(row.updated_at)
    if updated_at is None:
        raise ValueError("analysis matrix cell is missing updated_at")
    return CaseThemeMatrixCell(
        cell_id=UUID(row.cell_id),
        user_id=UUID(row.user_id),
        task_id=UUID(row.task_id),
        case_profile_id=UUID(row.case_profile_id),
        subject_kind=MatrixSubjectKind(row.subject_kind),
        subject_id=UUID(row.subject_id),
        summary=row.summary,
        annotation_ids=tuple(UUID(item) for item in row.annotation_ids),
        memo_ids=tuple(UUID(item) for item in row.memo_ids),
        finding_kinds=tuple(ComparisonFindingKind(item) for item in row.finding_kinds),
        version=row.version,
        updated_at=updated_at,
    )


def _method_selection(row: ResearchMethodPresetRow | None) -> MethodPresetSelection | None:
    if row is None:
        return None
    updated_at = _utc(row.updated_at)
    if updated_at is None:
        raise ValueError("analysis method preset is missing updated_at")
    return MethodPresetSelection(
        user_id=UUID(row.user_id),
        task_id=UUID(row.task_id),
        method=QualitativeMethod(row.method),
        version=row.version,
        updated_at=updated_at,
    )
