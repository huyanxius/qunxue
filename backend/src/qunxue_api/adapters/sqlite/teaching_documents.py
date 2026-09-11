"""Store classroom manuscripts in the existing immutable document versions."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from qunxue_api.adapters.sqlite.research_document import SqliteResearchDocumentRepository
from qunxue_api.modules.research_framework import (
    ResearchDocumentSection,
    ResearchDocumentSectionStatus,
    ResearchDocumentSnapshot,
    ResearchDocumentStatus,
)


class TeachingDocuments:
    def __init__(self, session):
        self.documents = SqliteResearchDocumentRepository(session)

    def save(self, activity, markdown):
        section = ResearchDocumentSection(
            section_id="lesson",
            key="lesson",
            title="教案",
            content=markdown,
            status=ResearchDocumentSectionStatus.DRAFT,
            evidence_refs=(),
        )
        document = (
            self.documents.latest(UUID(activity["document_id"]))
            if activity.get("document_id")
            else None
        )
        if document:
            snapshot = replace(
                document,
                version=document.version + 1,
                revision_id=uuid4(),
                sections=(section,),
                actor="user",
                change_summary="修订课堂教案",
                created_at=datetime.now(UTC),
            )
        else:
            snapshot = ResearchDocumentSnapshot(
                document_id=uuid4(),
                task_id=UUID(activity["task_id"]),
                theory_plan_id=None,
                knowledge_release_id="classroom-materials",
                revision_id=uuid4(),
                version=1,
                title=activity["input"].get("title") or "课堂教案",
                sections=(section,),
                status=ResearchDocumentStatus.DRAFT,
                change_summary="生成课堂教案",
                actor="agent",
                created_at=datetime.now(UTC),
            )
        saved = self.documents.add(snapshot)
        return str(saved.document_id)
