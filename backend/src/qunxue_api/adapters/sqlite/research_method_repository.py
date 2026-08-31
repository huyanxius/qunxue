from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite.research_method_model import (
    ResearchMethodPlanIdentityRow,
    ResearchMethodPlanVersionRow,
)
from qunxue_api.modules.research_method import (
    MethodKind,
    MethodPlanConstraints,
    MethodPlanContextItem,
    MethodPlanEvidenceRef,
    MethodPlanReview,
    MethodPlanSection,
    MethodPlanSnapshot,
    MethodPlanStatus,
)


class SqliteMethodPlanRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, snapshot: MethodPlanSnapshot) -> MethodPlanSnapshot:
        self._session.execute(
            insert(ResearchMethodPlanIdentityRow)
            .values(task_id=str(snapshot.task_id), plan_id=str(snapshot.plan_id))
            .on_conflict_do_nothing(index_elements=["task_id"])
        )
        identity = self._session.scalar(
            select(ResearchMethodPlanIdentityRow).where(
                ResearchMethodPlanIdentityRow.task_id == str(snapshot.task_id)
            )
        )
        if identity is None:
            raise RuntimeError("method plan identity was not persisted")
        if identity.plan_id != str(snapshot.plan_id):
            latest = self.latest(UUID(identity.plan_id))
            if latest is None:
                raise RuntimeError("method plan identity has no version")
            return latest
        self._session.execute(
            insert(ResearchMethodPlanVersionRow)
            .values(**_payload(snapshot))
            .on_conflict_do_nothing(index_elements=["plan_id", "version"])
        )
        row = self._session.get(
            ResearchMethodPlanVersionRow, (str(snapshot.plan_id), snapshot.version)
        )
        restored = _snapshot(row)
        if restored is None:
            raise RuntimeError("method plan version was not persisted")
        return restored

    def latest_for_task(self, task_id: UUID) -> MethodPlanSnapshot | None:
        plan_id = self._session.scalar(
            select(ResearchMethodPlanIdentityRow.plan_id).where(
                ResearchMethodPlanIdentityRow.task_id == str(task_id)
            )
        )
        return self.latest(UUID(plan_id)) if plan_id else None

    def latest(self, plan_id: UUID) -> MethodPlanSnapshot | None:
        row = self._session.scalar(
            select(ResearchMethodPlanVersionRow)
            .where(ResearchMethodPlanVersionRow.plan_id == str(plan_id))
            .order_by(ResearchMethodPlanVersionRow.version.desc())
            .limit(1)
        )
        return _snapshot(row)

    def get_version(self, plan_id: UUID, version: int) -> MethodPlanSnapshot | None:
        return _snapshot(self._session.get(ResearchMethodPlanVersionRow, (str(plan_id), version)))

    def list_versions(self, plan_id: UUID) -> tuple[MethodPlanSnapshot, ...]:
        rows = self._session.scalars(
            select(ResearchMethodPlanVersionRow)
            .where(ResearchMethodPlanVersionRow.plan_id == str(plan_id))
            .order_by(ResearchMethodPlanVersionRow.version.desc())
        )
        return tuple(item for row in rows if (item := _snapshot(row)) is not None)

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
        return self.add(stale)


def _payload(value: MethodPlanSnapshot) -> dict[str, object]:
    return {
        "plan_id": str(value.plan_id),
        "version": value.version,
        "task_id": str(value.task_id),
        "framework_id": str(value.framework_id),
        "framework_version": value.framework_version,
        "theory_plan_id": str(value.theory_plan_id),
        "theory_plan_version": value.theory_plan_version,
        "method_kind": value.method_kind.value,
        "decision_source": value.decision_source,
        "rationale": value.rationale,
        "research_question": value.research_question,
        "theory_summary": value.theory_summary,
        "material_constraints": list(value.shared_constraints.material_constraints),
        "ethical_constraints": list(value.shared_constraints.ethical_constraints),
        "theory_concepts": list(value.shared_constraints.theory_concepts),
        "evidence_ref_ids": list(value.shared_constraints.evidence_ref_ids),
        "knowledge_release_id": value.shared_constraints.knowledge_release_id,
        "shared_context": [
            {
                "key": item.key,
                "title": item.title,
                "content": item.content,
                "evidence_refs": [
                    {
                        "evidence_ref_id": ref.evidence_ref_id,
                        "source_id": ref.source_id,
                        "source_kind": ref.source_kind,
                        "knowledge_release_id": ref.knowledge_release_id,
                        "annotation_id": ref.annotation_id,
                        "material_id": ref.material_id,
                        "parse_id": ref.parse_id,
                        "segment_id": ref.segment_id,
                        "locator": ref.locator,
                    }
                    for ref in item.evidence_refs
                ],
            }
            for item in value.shared_context
        ],
        "sections": [
            {"key": item.key, "title": item.title, "content": item.content, "source": item.source}
            for item in value.sections
        ],
        "reviews": [
            {
                "review_id": str(item.review_id),
                "note": item.note,
                "blocking": item.blocking,
                "created_at": item.created_at.isoformat(),
                "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
            }
            for item in value.reviews
        ],
        "status": value.status.value,
        "revision_id": str(value.revision_id),
        "change_summary": value.change_summary,
        "actor": value.actor,
        "created_at": value.created_at,
        "restored_from_version": value.restored_from_version,
        "stale_reason": value.stale_reason,
        "confirmed_at": value.confirmed_at,
    }


def _snapshot(row: ResearchMethodPlanVersionRow | None) -> MethodPlanSnapshot | None:
    if row is None:
        return None
    return MethodPlanSnapshot(
        plan_id=UUID(row.plan_id),
        task_id=UUID(row.task_id),
        framework_id=UUID(row.framework_id),
        framework_version=row.framework_version,
        theory_plan_id=UUID(row.theory_plan_id),
        theory_plan_version=row.theory_plan_version,
        method_kind=MethodKind(row.method_kind),
        decision_source=row.decision_source,
        rationale=row.rationale,
        research_question=row.research_question,
        theory_summary=row.theory_summary,
        shared_constraints=MethodPlanConstraints(
            tuple(row.material_constraints),
            tuple(row.ethical_constraints),
            tuple(row.theory_concepts),
            tuple(row.evidence_ref_ids),
            row.knowledge_release_id,
        ),
        shared_context=tuple(
            MethodPlanContextItem(
                key=str(item["key"]),
                title=str(item["title"]),
                content=str(item["content"]),
                evidence_refs=tuple(
                    MethodPlanEvidenceRef(
                        evidence_ref_id=str(ref["evidence_ref_id"]),
                        source_id=str(ref["source_id"]),
                        source_kind=str(ref["source_kind"]),
                        knowledge_release_id=(
                            str(ref["knowledge_release_id"])
                            if ref.get("knowledge_release_id") is not None
                            else None
                        ),
                        annotation_id=(
                            str(ref["annotation_id"]) if ref.get("annotation_id") else None
                        ),
                        material_id=(
                            str(ref["material_id"]) if ref.get("material_id") else None
                        ),
                        parse_id=(str(ref["parse_id"]) if ref.get("parse_id") else None),
                        segment_id=(
                            str(ref["segment_id"]) if ref.get("segment_id") else None
                        ),
                        locator=(str(ref["locator"]) if ref.get("locator") else None),
                    )
                    for ref in item.get("evidence_refs", [])
                ),
            )
            for item in (row.shared_context or [])
        ),
        sections=tuple(MethodPlanSection(**item) for item in row.sections),
        reviews=tuple(
            MethodPlanReview(
                review_id=UUID(item["review_id"]),
                note=str(item["note"]),
                blocking=bool(item["blocking"]),
                created_at=_utc(datetime.fromisoformat(str(item["created_at"]))),
                resolved_at=_utc(datetime.fromisoformat(str(item["resolved_at"])))
                if item.get("resolved_at")
                else None,
            )
            for item in row.reviews
        ),
        status=MethodPlanStatus(row.status),
        version=row.version,
        revision_id=UUID(row.revision_id),
        change_summary=row.change_summary,
        actor=row.actor,
        created_at=_utc(row.created_at),
        restored_from_version=row.restored_from_version,
        stale_reason=row.stale_reason,
        confirmed_at=_utc(row.confirmed_at) if row.confirmed_at else None,
    )


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
