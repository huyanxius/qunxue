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
    ResearchAnalysisWriteRequestRow,
    ResearchAnnotationRow,
    ResearchCodeRow,
    ResearchComparisonRow,
    ResearchMemoRow,
)
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
    NextResearchStep,
    ResearchAnalysisIdempotencyConflict,
)
from qunxue_api.modules.research_materials import MaterialLocator

DecisionRecord = AnalysisCode | AnalysisMemo | CaseComparison
DecisionRow = ResearchCodeRow | ResearchMemoRow | ResearchComparisonRow
DecisionModel = type[ResearchCodeRow] | type[ResearchMemoRow] | type[ResearchComparisonRow]
DecisionT = TypeVar("DecisionT", AnalysisCode, AnalysisMemo, CaseComparison)


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
        if not _same_decision_subject(persisted, value):
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
