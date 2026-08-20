from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite.agent_conversation_model import (
    AgentConversationRow,
    AgentRunRow,
)
from qunxue_api.adapters.sqlite.research_document_proposal_model import (
    ResearchDocumentProposalRow,
)
from qunxue_api.adapters.sqlite.research_intake_model import ResearchTaskRow
from qunxue_api.modules.research_framework import (
    ResearchDocumentEvidenceRef,
    ResearchDocumentProposalKind,
    ResearchDocumentProposalSnapshot,
    ResearchDocumentProposalStatus,
    ResearchDocumentSection,
    ResearchDocumentSectionStatus,
)


class SqliteResearchDocumentProposalRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, snapshot: ResearchDocumentProposalSnapshot) -> ResearchDocumentProposalSnapshot:
        self._session.add(_row(snapshot))
        self._session.flush()
        return snapshot

    def get(self, proposal_id: UUID) -> ResearchDocumentProposalSnapshot | None:
        return _snapshot(self._session.get(ResearchDocumentProposalRow, str(proposal_id)))

    def save(self, snapshot: ResearchDocumentProposalSnapshot) -> ResearchDocumentProposalSnapshot:
        result = self._session.execute(
            update(ResearchDocumentProposalRow)
            .where(
                ResearchDocumentProposalRow.proposal_id == str(snapshot.proposal_id),
                ResearchDocumentProposalRow.status
                == ResearchDocumentProposalStatus.PENDING.value,
            )
            .values(
                status=snapshot.status.value,
                decision_reason=snapshot.decision_reason,
                decided_at=snapshot.decided_at,
                result_document_id=(
                    str(snapshot.result_document_id) if snapshot.result_document_id else None
                ),
                result_document_version=snapshot.result_document_version,
            )
        )
        if result.rowcount == 1:
            return snapshot
        row = self._session.scalar(
            select(ResearchDocumentProposalRow)
            .where(ResearchDocumentProposalRow.proposal_id == str(snapshot.proposal_id))
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise LookupError(snapshot.proposal_id)
        persisted = _snapshot(row)
        if persisted is None:
            raise LookupError(snapshot.proposal_id)
        return persisted

    def list_for_document(
        self, document_id: UUID
    ) -> tuple[ResearchDocumentProposalSnapshot, ...]:
        rows = self._session.scalars(
            select(ResearchDocumentProposalRow)
            .where(ResearchDocumentProposalRow.document_id == str(document_id))
            .order_by(ResearchDocumentProposalRow.created_at.desc())
        )
        return tuple(item for row in rows if (item := _snapshot(row)) is not None)

    def list_for_task(
        self, task_id: UUID
    ) -> tuple[ResearchDocumentProposalSnapshot, ...]:
        rows = self._session.scalars(
            select(ResearchDocumentProposalRow)
            .where(ResearchDocumentProposalRow.task_id == str(task_id))
            .order_by(ResearchDocumentProposalRow.created_at.desc())
        )
        return tuple(item for row in rows if (item := _snapshot(row)) is not None)

    def validate_agent_context(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        agent_run_id: UUID,
        task_id: UUID,
        knowledge_release_id: str,
    ) -> bool:
        conversation = self._session.get(AgentConversationRow, str(conversation_id))
        run = self._session.get(AgentRunRow, str(agent_run_id))
        task = self._session.get(ResearchTaskRow, str(task_id))
        return bool(
            conversation is not None
            and run is not None
            and task is not None
            and conversation.user_id == str(user_id)
            and run.user_id == str(user_id)
            and run.conversation_id == str(conversation_id)
            and run.knowledge_release_id == knowledge_release_id
            and task.user_id == str(user_id)
        )

    def find_revision_for_agent_target(
        self,
        *,
        agent_run_id: UUID,
        document_id: UUID,
        base_document_version: int,
        target_section_id: str,
    ) -> ResearchDocumentProposalSnapshot | None:
        row = self._session.scalar(
            select(ResearchDocumentProposalRow).where(
                ResearchDocumentProposalRow.agent_run_id == str(agent_run_id),
                ResearchDocumentProposalRow.document_id == str(document_id),
                ResearchDocumentProposalRow.base_document_version == base_document_version,
                ResearchDocumentProposalRow.target_section_id == target_section_id,
            )
        )
        return _snapshot(row)


def _row(snapshot: ResearchDocumentProposalSnapshot) -> ResearchDocumentProposalRow:
    return ResearchDocumentProposalRow(
        proposal_id=str(snapshot.proposal_id),
        kind=snapshot.kind.value,
        status=snapshot.status.value,
        user_id=str(snapshot.user_id),
        conversation_id=str(snapshot.conversation_id),
        agent_run_id=str(snapshot.agent_run_id),
        task_id=str(snapshot.task_id),
        theory_plan_id=str(snapshot.theory_plan_id),
        knowledge_release_id=snapshot.knowledge_release_id,
        title=snapshot.title,
        proposed_sections=[_section_payload(item) for item in snapshot.proposed_sections],
        rationale=snapshot.rationale,
        request_hash=snapshot.request_hash,
        document_id=str(snapshot.document_id) if snapshot.document_id else None,
        base_document_version=snapshot.base_document_version,
        target_section_id=snapshot.target_section_id,
        decision_reason=snapshot.decision_reason,
        result_document_id=(
            str(snapshot.result_document_id) if snapshot.result_document_id else None
        ),
        result_document_version=snapshot.result_document_version,
        created_at=snapshot.created_at,
        decided_at=snapshot.decided_at,
    )


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


def _snapshot(
    row: ResearchDocumentProposalRow | None,
) -> ResearchDocumentProposalSnapshot | None:
    if row is None:
        return None
    return ResearchDocumentProposalSnapshot(
        proposal_id=UUID(row.proposal_id),
        kind=ResearchDocumentProposalKind(row.kind),
        status=ResearchDocumentProposalStatus(row.status),
        user_id=UUID(row.user_id),
        conversation_id=UUID(row.conversation_id),
        agent_run_id=UUID(row.agent_run_id),
        task_id=UUID(row.task_id),
        theory_plan_id=UUID(row.theory_plan_id),
        knowledge_release_id=row.knowledge_release_id,
        title=row.title,
        proposed_sections=tuple(
            ResearchDocumentSection(
                section_id=str(item["section_id"]),
                key=str(item["key"]),
                title=str(item["title"]),
                content=str(item["content"]),
                status=ResearchDocumentSectionStatus(str(item["status"])),
                evidence_refs=tuple(
                    ResearchDocumentEvidenceRef(
                        evidence_ref_id=str(evidence["evidence_ref_id"]),
                        source_id=str(evidence["source_id"]),
                        knowledge_release_id=str(evidence["knowledge_release_id"]),
                    )
                    for evidence in item.get("evidence_refs", [])
                ),
            )
            for item in row.proposed_sections
        ),
        rationale=row.rationale,
        created_at=_utc(row.created_at),
        document_id=UUID(row.document_id) if row.document_id else None,
        base_document_version=row.base_document_version,
        target_section_id=row.target_section_id,
        decision_reason=row.decision_reason,
        decided_at=_utc(row.decided_at) if row.decided_at is not None else None,
        result_document_id=(UUID(row.result_document_id) if row.result_document_id else None),
        result_document_version=row.result_document_version,
        request_hash=row.request_hash,
    )


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
