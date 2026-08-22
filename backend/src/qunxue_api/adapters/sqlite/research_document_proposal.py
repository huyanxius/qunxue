from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite.agent_conversation_model import (
    AgentConversationRow,
    AgentRunRow,
)
from qunxue_api.adapters.sqlite.research_document_proposal_model import (
    ResearchDocumentHandoffRow,
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
        if snapshot.kind is ResearchDocumentProposalKind.CREATE:
            self._session.execute(
                insert(ResearchDocumentHandoffRow)
                .values(
                    user_id=str(snapshot.user_id),
                    task_id=str(snapshot.task_id),
                    theory_plan_id=str(snapshot.theory_plan_id),
                    proposal_id=str(snapshot.proposal_id),
                )
                .on_conflict_do_nothing(
                    index_elements=["user_id", "task_id", "theory_plan_id"]
                )
            )
            handoff = self._session.scalar(
                select(ResearchDocumentHandoffRow)
                .where(
                    ResearchDocumentHandoffRow.user_id == str(snapshot.user_id),
                    ResearchDocumentHandoffRow.task_id == str(snapshot.task_id),
                    ResearchDocumentHandoffRow.theory_plan_id
                    == str(snapshot.theory_plan_id),
                )
                .execution_options(populate_existing=True)
            )
            if handoff is None:
                raise RuntimeError("research document handoff was not persisted")
            if handoff.proposal_id != str(snapshot.proposal_id):
                persisted = self.get(UUID(handoff.proposal_id))
                if persisted is None:
                    raise RuntimeError("research document handoff has no proposal")
                return persisted
        row = _row(snapshot)
        statement = insert(ResearchDocumentProposalRow).values(
            **{
                column.name: getattr(row, column.name)
                for column in ResearchDocumentProposalRow.__table__.columns
            }
        )
        if snapshot.kind is ResearchDocumentProposalKind.CREATE:
            statement = statement.on_conflict_do_nothing(index_elements=["proposal_id"])
        else:
            statement = statement.on_conflict_do_nothing(
                index_elements=[
                    "agent_run_id",
                    "document_id",
                    "base_document_version",
                    "target_section_id",
                ]
            )
        self._session.execute(
            statement
        )
        persisted = _snapshot(
            self._session.get(ResearchDocumentProposalRow, str(snapshot.proposal_id))
        )
        if persisted is None and snapshot.kind is ResearchDocumentProposalKind.CREATE:
            persisted = self.find_create_for_theory_plan(
                user_id=snapshot.user_id,
                task_id=snapshot.task_id,
                theory_plan_id=snapshot.theory_plan_id,
            )
        if persisted is None and (
            snapshot.document_id is not None
            and snapshot.base_document_version is not None
            and snapshot.target_section_id is not None
        ):
            persisted = self.find_revision_for_agent_target(
                agent_run_id=snapshot.agent_run_id,
                document_id=snapshot.document_id,
                base_document_version=snapshot.base_document_version,
                target_section_id=snapshot.target_section_id,
            )
        if persisted is None:
            raise RuntimeError("research document proposal was not persisted")
        return persisted

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
                document_id=(str(snapshot.document_id) if snapshot.document_id else None),
            )
        )
        if result.rowcount == 1:
            if (
                snapshot.kind is ResearchDocumentProposalKind.CREATE
                and snapshot.status
                in {
                    ResearchDocumentProposalStatus.REJECTED,
                    ResearchDocumentProposalStatus.ABORTED,
                }
            ):
                self._session.execute(
                    delete(ResearchDocumentHandoffRow).where(
                        ResearchDocumentHandoffRow.proposal_id
                        == str(snapshot.proposal_id)
                    )
                )
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

    def list_actionable_for_task(
        self, task_id: UUID
    ) -> tuple[ResearchDocumentProposalSnapshot, ...]:
        current_document_id = self._session.scalar(
            select(ResearchTaskRow.current_framework_id).where(
                ResearchTaskRow.task_id == str(task_id)
            )
        )
        canonical_create_ids = select(ResearchDocumentHandoffRow.proposal_id).where(
            ResearchDocumentHandoffRow.task_id == str(task_id)
        )
        rows = self._session.scalars(
            select(ResearchDocumentProposalRow)
            .where(
                ResearchDocumentProposalRow.task_id == str(task_id),
                ResearchDocumentProposalRow.status
                == ResearchDocumentProposalStatus.PENDING.value,
                or_(
                    and_(
                        ResearchDocumentProposalRow.kind
                        == ResearchDocumentProposalKind.CREATE.value,
                        ResearchDocumentProposalRow.proposal_id.in_(
                            canonical_create_ids
                        ),
                    ),
                    and_(
                        ResearchDocumentProposalRow.kind
                        == ResearchDocumentProposalKind.REVISE_SECTION.value,
                        ResearchDocumentProposalRow.document_id == current_document_id,
                    ),
                ),
            )
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

    def find_create_for_theory_plan(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        theory_plan_id: UUID,
    ) -> ResearchDocumentProposalSnapshot | None:
        proposal_id = self._session.scalar(
            select(ResearchDocumentHandoffRow.proposal_id)
            .where(
                ResearchDocumentHandoffRow.user_id == str(user_id),
                ResearchDocumentHandoffRow.task_id == str(task_id),
                ResearchDocumentHandoffRow.theory_plan_id == str(theory_plan_id),
            )
        )
        if proposal_id is None:
            return None
        snapshot = self.get(UUID(proposal_id))
        if snapshot is None or snapshot.status not in {
            ResearchDocumentProposalStatus.PENDING,
            ResearchDocumentProposalStatus.ACCEPTED,
        }:
            return None
        return snapshot

    def agent_run_status(self, agent_run_id: UUID) -> str | None:
        return self._session.scalar(
            select(AgentRunRow.status).where(AgentRunRow.run_id == str(agent_run_id))
        )

    def agent_run_model(self, agent_run_id: UUID) -> tuple[str, str] | None:
        row = self._session.execute(
            select(AgentRunRow.provider, AgentRunRow.model).where(
                AgentRunRow.run_id == str(agent_run_id)
            )
        ).one_or_none()
        return (row.provider, row.model) if row is not None else None


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
        model_provider=snapshot.model_provider,
        model_name=snapshot.model_name,
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
        model_provider=row.model_provider,
        model_name=row.model_name,
    )


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
