from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite.agent_conversation_model import AgentRunRow
from qunxue_api.adapters.sqlite.research_intake_model import (
    ResearchStartConfirmationRow,
    ResearchStartProposalRow,
)
from qunxue_api.modules.research_intake import (
    ResearchStartConfirmation,
    ResearchStartProposal,
    ResearchStartProposalConflict,
    ResearchStartProposalRepository,
    ResearchStartProposalStatus,
    ResearchStartSourceIncomplete,
)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class SqliteResearchStartProposalRepository(ResearchStartProposalRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def assert_source_completed(self, proposal: ResearchStartProposal) -> None:
        source = self._session.scalar(
            select(AgentRunRow).where(
                AgentRunRow.run_id == str(proposal.source_run_id),
                AgentRunRow.user_id == str(proposal.user_id),
                AgentRunRow.conversation_id == str(proposal.conversation_id),
                AgentRunRow.status == "completed",
                AgentRunRow.turn_id == str(proposal.source_turn_id),
                AgentRunRow.knowledge_release_id == proposal.knowledge_release_id,
            )
        )
        if source is None:
            raise ResearchStartSourceIncomplete()

    def add_from_completed_run(self, proposal: ResearchStartProposal) -> ResearchStartProposal:
        self.assert_source_completed(proposal)
        self._session.execute(
            insert(ResearchStartProposalRow)
            .values(
                proposal_id=str(proposal.proposal_id),
                user_id=str(proposal.user_id),
                conversation_id=str(proposal.conversation_id),
                source_run_id=str(proposal.source_run_id),
                source_turn_id=str(proposal.source_turn_id),
                knowledge_release_id=proposal.knowledge_release_id,
                phenomenon=proposal.phenomenon,
                research_intent=proposal.research_intent,
                context=proposal.context,
                version=proposal.version,
                status=proposal.status.value,
                confirmed_task_id=None,
                confirmed_request_hash=None,
                created_at=proposal.created_at,
                confirmed_at=None,
            )
            .on_conflict_do_nothing(index_elements=["source_run_id"])
        )
        row = self._session.scalar(
            select(ResearchStartProposalRow).where(
                ResearchStartProposalRow.source_run_id == str(proposal.source_run_id)
            )
        )
        if row is None:
            raise RuntimeError("research start proposal insert did not persist a row")
        persisted = _proposal(row)
        if _proposal_payload(persisted) != _proposal_payload(proposal):
            raise ResearchStartProposalConflict(
                "The completed Agent run already proposed different research-start content."
            )
        return persisted

    def get(self, *, user_id: UUID, proposal_id: UUID) -> ResearchStartProposal | None:
        row = self._session.scalar(
            select(ResearchStartProposalRow).where(
                ResearchStartProposalRow.proposal_id == str(proposal_id),
                ResearchStartProposalRow.user_id == str(user_id),
            )
        )
        return _proposal(row) if row is not None else None

    def latest_for_conversation(
        self, *, user_id: UUID, conversation_id: UUID
    ) -> ResearchStartProposal | None:
        row = self._session.scalar(
            select(ResearchStartProposalRow)
            .where(
                ResearchStartProposalRow.user_id == str(user_id),
                ResearchStartProposalRow.conversation_id == str(conversation_id),
            )
            .order_by(
                ResearchStartProposalRow.created_at.desc(),
                ResearchStartProposalRow.proposal_id.desc(),
            )
            .limit(1)
        )
        return _proposal(row) if row is not None else None

    def get_confirmation(
        self, *, user_id: UUID, idempotency_key: str
    ) -> ResearchStartConfirmation | None:
        row = self._session.scalar(
            select(ResearchStartConfirmationRow).where(
                ResearchStartConfirmationRow.user_id == str(user_id),
                ResearchStartConfirmationRow.idempotency_key == idempotency_key,
            )
        )
        return _confirmation(row) if row is not None else None

    def add_confirmation(
        self, confirmation: ResearchStartConfirmation
    ) -> ResearchStartConfirmation:
        self._session.execute(
            insert(ResearchStartConfirmationRow)
            .values(
                confirmation_id=str(uuid4()),
                user_id=str(confirmation.user_id),
                idempotency_key=confirmation.idempotency_key,
                proposal_id=str(confirmation.proposal_id),
                request_hash=confirmation.request_hash,
                task_id=str(confirmation.task_id),
                created_at=confirmation.created_at,
            )
            .on_conflict_do_nothing(index_elements=["user_id", "idempotency_key"])
        )
        row = self._session.scalar(
            select(ResearchStartConfirmationRow).where(
                ResearchStartConfirmationRow.user_id == str(confirmation.user_id),
                ResearchStartConfirmationRow.idempotency_key == confirmation.idempotency_key,
            )
        )
        if row is None:
            raise RuntimeError("research start confirmation did not persist")
        return _confirmation(row)

    def mark_confirmed(
        self,
        *,
        user_id: UUID,
        proposal_id: UUID,
        expected_version: int,
        task_id: UUID,
        request_hash: str,
        confirmed_at: datetime,
    ) -> ResearchStartProposal | None:
        result = self._session.execute(
            update(ResearchStartProposalRow)
            .where(
                ResearchStartProposalRow.proposal_id == str(proposal_id),
                ResearchStartProposalRow.user_id == str(user_id),
                ResearchStartProposalRow.version == expected_version,
                ResearchStartProposalRow.status
                == ResearchStartProposalStatus.PENDING_CONFIRMATION.value,
            )
            .values(
                version=expected_version + 1,
                status=ResearchStartProposalStatus.CONFIRMED.value,
                confirmed_task_id=str(task_id),
                confirmed_request_hash=request_hash,
                confirmed_at=confirmed_at,
            )
        )
        if result.rowcount != 1:
            return None
        row = self._session.get(ResearchStartProposalRow, str(proposal_id))
        return _proposal(row) if row is not None else None


def _proposal(row: ResearchStartProposalRow) -> ResearchStartProposal:
    return ResearchStartProposal(
        proposal_id=UUID(row.proposal_id),
        user_id=UUID(row.user_id),
        conversation_id=UUID(row.conversation_id),
        source_run_id=UUID(row.source_run_id),
        source_turn_id=UUID(row.source_turn_id),
        knowledge_release_id=row.knowledge_release_id,
        phenomenon=row.phenomenon,
        research_intent=row.research_intent,
        context=row.context,
        version=row.version,
        status=ResearchStartProposalStatus(row.status),
        confirmed_task_id=UUID(row.confirmed_task_id) if row.confirmed_task_id else None,
        confirmed_request_hash=row.confirmed_request_hash,
        created_at=_as_utc(row.created_at),
        confirmed_at=_as_utc(row.confirmed_at) if row.confirmed_at else None,
    )


def _confirmation(row: ResearchStartConfirmationRow) -> ResearchStartConfirmation:
    return ResearchStartConfirmation(
        user_id=UUID(row.user_id),
        idempotency_key=row.idempotency_key,
        proposal_id=UUID(row.proposal_id),
        request_hash=row.request_hash,
        task_id=UUID(row.task_id),
        created_at=_as_utc(row.created_at),
    )


def _proposal_payload(proposal: ResearchStartProposal) -> tuple[object, ...]:
    return (
        proposal.proposal_id,
        proposal.user_id,
        proposal.conversation_id,
        proposal.source_run_id,
        proposal.source_turn_id,
        proposal.knowledge_release_id,
        proposal.phenomenon,
        proposal.research_intent,
        proposal.context,
    )
