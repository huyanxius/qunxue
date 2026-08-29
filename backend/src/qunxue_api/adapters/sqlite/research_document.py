from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite.research_document_model import (
    ResearchDocumentIdentityRow,
    ResearchDocumentVersionRow,
)
from qunxue_api.modules.research_framework import (
    ResearchDocumentEvidenceRef,
    ResearchDocumentEvidenceSourceKind,
    ResearchDocumentSection,
    ResearchDocumentSectionStatus,
    ResearchDocumentSnapshot,
    ResearchDocumentStatus,
)


class SqliteResearchDocumentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, snapshot: ResearchDocumentSnapshot) -> ResearchDocumentSnapshot:
        if snapshot.version == 1:
            self._session.execute(
                insert(ResearchDocumentIdentityRow)
                .values(
                    task_id=str(snapshot.task_id),
                    theory_plan_id=str(snapshot.theory_plan_id),
                    document_id=str(snapshot.document_id),
                )
                .on_conflict_do_nothing(
                    index_elements=["task_id", "theory_plan_id"]
                )
            )
            identity = self._session.scalar(
                select(ResearchDocumentIdentityRow)
                .where(
                    ResearchDocumentIdentityRow.task_id == str(snapshot.task_id),
                    ResearchDocumentIdentityRow.theory_plan_id
                    == str(snapshot.theory_plan_id),
                )
                .execution_options(populate_existing=True)
            )
            if identity is None:
                raise RuntimeError("research document identity was not persisted")
            if identity.document_id != str(snapshot.document_id):
                persisted = self.latest(UUID(identity.document_id))
                if persisted is None:
                    raise RuntimeError("research document identity has no document")
                return persisted
        self._session.execute(
            insert(ResearchDocumentVersionRow).values(
                document_id=str(snapshot.document_id),
                version=snapshot.version,
                task_id=str(snapshot.task_id),
                theory_plan_id=str(snapshot.theory_plan_id),
                knowledge_release_id=snapshot.knowledge_release_id,
                revision_id=str(snapshot.revision_id),
                title=snapshot.title,
                sections=[_section_payload(section) for section in snapshot.sections],
                analysis_handoff=snapshot.analysis_handoff,
                status=snapshot.status.value,
                change_summary=snapshot.change_summary,
                actor=snapshot.actor,
                restored_from_version=snapshot.restored_from_version,
                created_at=snapshot.created_at,
                confirmed_at=snapshot.confirmed_at,
            )
            .on_conflict_do_nothing(index_elements=["document_id", "version"])
        )
        row = self._session.get(
            ResearchDocumentVersionRow,
            (str(snapshot.document_id), snapshot.version),
        )
        persisted = _snapshot(row)
        if persisted is None:
            persisted = self.find_for_task_and_plan(
                task_id=snapshot.task_id,
                theory_plan_id=snapshot.theory_plan_id,
            )
        if persisted is None:
            raise RuntimeError("research document version was not persisted")
        if persisted.revision_id != snapshot.revision_id:
            return persisted
        return snapshot

    def find_for_task_and_plan(
        self, *, task_id: UUID, theory_plan_id: UUID
    ) -> ResearchDocumentSnapshot | None:
        document_id = self._session.scalar(
            select(ResearchDocumentIdentityRow.document_id)
            .where(
                ResearchDocumentIdentityRow.task_id == str(task_id),
                ResearchDocumentIdentityRow.theory_plan_id == str(theory_plan_id),
            )
        )
        return self.latest(UUID(document_id)) if document_id is not None else None

    def latest(self, document_id: UUID) -> ResearchDocumentSnapshot | None:
        row = self._session.scalar(
            select(ResearchDocumentVersionRow)
            .where(ResearchDocumentVersionRow.document_id == str(document_id))
            .order_by(ResearchDocumentVersionRow.version.desc())
            .limit(1)
        )
        return _snapshot(row)

    def get_version(self, document_id: UUID, version: int) -> ResearchDocumentSnapshot | None:
        return _snapshot(self._session.get(ResearchDocumentVersionRow, (str(document_id), version)))

    def list_versions(self, document_id: UUID) -> tuple[ResearchDocumentSnapshot, ...]:
        rows = self._session.scalars(
            select(ResearchDocumentVersionRow)
            .where(ResearchDocumentVersionRow.document_id == str(document_id))
            .order_by(ResearchDocumentVersionRow.version.desc())
        )
        return tuple(item for row in rows if (item := _snapshot(row)) is not None)

    def list_for_task(self, task_id: UUID) -> tuple[ResearchDocumentSnapshot, ...]:
        document_ids = tuple(
            self._session.scalars(
                select(ResearchDocumentIdentityRow.document_id).where(
                    ResearchDocumentIdentityRow.task_id == str(task_id)
                )
            )
        )
        if not document_ids:
            return ()
        rows = self._session.scalars(
            select(ResearchDocumentVersionRow)
            .where(ResearchDocumentVersionRow.document_id.in_(document_ids))
            .order_by(
                ResearchDocumentVersionRow.document_id,
                ResearchDocumentVersionRow.version.desc(),
            )
        )
        latest: list[ResearchDocumentSnapshot] = []
        seen: set[str] = set()
        for row in rows:
            if row.document_id in seen:
                continue
            seen.add(row.document_id)
            snapshot = _snapshot(row)
            if snapshot is not None:
                latest.append(snapshot)
        return tuple(sorted(latest, key=lambda item: item.created_at, reverse=True))


def _section_payload(section: ResearchDocumentSection) -> dict[str, object]:
    return {
        "section_id": section.section_id,
        "key": section.key,
        "title": section.title,
        "content": section.content,
        "status": section.status.value,
        "evidence_refs": [
                {
                    "evidence_ref_id": item.evidence_ref_id,
                    "source_id": item.source_id,
                    "knowledge_release_id": item.knowledge_release_id,
                    "source_kind": item.source_kind.value,
                    "annotation_id": str(item.annotation_id) if item.annotation_id else None,
                    "material_id": str(item.material_id) if item.material_id else None,
                    "parse_id": str(item.parse_id) if item.parse_id else None,
                    "segment_id": item.segment_id,
                    "locator": item.locator,
                }
            for item in section.evidence_refs
        ],
    }


def _snapshot(row: ResearchDocumentVersionRow | None) -> ResearchDocumentSnapshot | None:
    if row is None:
        return None
    return ResearchDocumentSnapshot(
        document_id=UUID(row.document_id),
        task_id=UUID(row.task_id),
        theory_plan_id=UUID(row.theory_plan_id),
        knowledge_release_id=row.knowledge_release_id,
        revision_id=UUID(row.revision_id),
        version=row.version,
        title=row.title,
        sections=tuple(
            ResearchDocumentSection(
                section_id=str(section["section_id"]),
                key=str(section["key"]),
                title=str(section["title"]),
                content=str(section["content"]),
                status=ResearchDocumentSectionStatus(str(section["status"])),
                evidence_refs=tuple(
                    ResearchDocumentEvidenceRef(
                        evidence_ref_id=str(item["evidence_ref_id"]),
                        source_id=str(item["source_id"]),
                        knowledge_release_id=(
                            str(item["knowledge_release_id"])
                            if item.get("knowledge_release_id") is not None
                            else None
                        ),
                        source_kind=ResearchDocumentEvidenceSourceKind(
                            str(item.get("source_kind", "public_knowledge"))
                        ),
                        annotation_id=(
                            UUID(str(item["annotation_id"]))
                            if item.get("annotation_id")
                            else None
                        ),
                        material_id=(
                            UUID(str(item["material_id"]))
                            if item.get("material_id")
                            else None
                        ),
                        parse_id=(
                            UUID(str(item["parse_id"]))
                            if item.get("parse_id")
                            else None
                        ),
                        segment_id=(
                            str(item["segment_id"])
                            if item.get("segment_id") is not None
                            else None
                        ),
                        locator=(
                            dict(item["locator"])
                            if isinstance(item.get("locator"), dict)
                            else None
                        ),
                    )
                    for item in section.get("evidence_refs", [])
                ),
            )
            for section in row.sections
        ),
        status=ResearchDocumentStatus(row.status),
        change_summary=row.change_summary,
        actor=row.actor,
        created_at=_utc(row.created_at),
        analysis_handoff=(
            dict(row.analysis_handoff) if row.analysis_handoff is not None else None
        ),
        restored_from_version=row.restored_from_version,
        confirmed_at=_utc(row.confirmed_at) if row.confirmed_at is not None else None,
    )


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
