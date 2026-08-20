from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite.research_document_model import ResearchDocumentVersionRow
from qunxue_api.modules.research_framework import (
    ResearchDocumentEvidenceRef,
    ResearchDocumentSection,
    ResearchDocumentSectionStatus,
    ResearchDocumentSnapshot,
    ResearchDocumentStatus,
)


class SqliteResearchDocumentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, snapshot: ResearchDocumentSnapshot) -> ResearchDocumentSnapshot:
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
            raise RuntimeError("research document version was not persisted")
        if persisted.revision_id != snapshot.revision_id:
            return persisted
        return snapshot

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
        rows = self._session.scalars(
            select(ResearchDocumentVersionRow)
            .where(ResearchDocumentVersionRow.task_id == str(task_id))
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
                        knowledge_release_id=str(item["knowledge_release_id"]),
                    )
                    for item in section.get("evidence_refs", [])
                ),
            )
            for section in row.sections
        ),
        status=ResearchDocumentStatus(row.status),
        change_summary=row.change_summary,
        actor=row.actor,
        created_at=row.created_at,
        restored_from_version=row.restored_from_version,
        confirmed_at=row.confirmed_at,
    )
