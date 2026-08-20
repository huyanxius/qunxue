from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from qunxue_api.application.research_document_mutations import (
    ResearchDocumentMutationRepository,
    mutation_request_hash,
)
from qunxue_api.modules.research_framework import (
    ResearchDocumentProposalAcceptance,
    ResearchDocumentProposalService,
    ResearchDocumentProposalSnapshot,
)
from qunxue_api.modules.research_intake import ResearchTaskRepository, ResearchTaskStatus


class ResearchDocumentProposalApplication:
    """Exposes user-owned proposal decisions without bypassing the domain gate."""

    def __init__(
        self,
        proposals: ResearchDocumentProposalService,
        research_tasks: ResearchTaskRepository,
        mutations: ResearchDocumentMutationRepository,
    ) -> None:
        self._proposals = proposals
        self._research_tasks = research_tasks
        self._mutations = mutations

    def get(self, *, user_id: UUID, proposal_id: UUID) -> ResearchDocumentProposalSnapshot:
        return self._proposals.get(proposal_id, user_id=user_id)

    def list_for_document(
        self, *, user_id: UUID, document_id: UUID
    ) -> tuple[ResearchDocumentProposalSnapshot, ...]:
        return self._proposals.list_for_document(document_id, user_id=user_id)

    def list_for_task(
        self, *, user_id: UUID, task_id: UUID
    ) -> tuple[ResearchDocumentProposalSnapshot, ...]:
        return self._proposals.list_for_task(task_id, user_id=user_id)

    def accept(
        self,
        *,
        user_id: UUID,
        proposal_id: UUID,
        expected_document_version: int | None,
        idempotency_key: str,
    ) -> ResearchDocumentProposalAcceptance:
        receipt = self._mutations.claim(
            user_id=user_id,
            idempotency_key=idempotency_key,
            operation=f"accept_document_proposal:{proposal_id}",
            request_hash=mutation_request_hash(
                {"expected_document_version": expected_document_version}
            ),
        )
        try:
            accepted = self._proposals.accept(
                proposal_id=proposal_id,
                user_id=user_id,
                expected_document_version=expected_document_version,
            )
        except Exception:
            if receipt.status == "pending":
                self._mutations.fail(request_id=receipt.request_id)
            raise
        task = self._research_tasks.get(accepted.proposal.task_id, user_id)
        if task is None:
            raise RuntimeError("owned research task disappeared while accepting proposal")
        if (
            accepted.proposal.result_document_id is not None
            and task.current_framework_id != accepted.proposal.result_document_id
        ):
            saved_task = self._research_tasks.save_progress(
                replace(
                    task,
                    status=ResearchTaskStatus.FRAMEWORK_DRAFT,
                    version=task.version + 1,
                    updated_at=datetime.now(UTC),
                    current_framework_id=accepted.proposal.result_document_id,
                )
            )
            if saved_task is None:
                raise RuntimeError("research task changed while accepting document proposal")
        if receipt.status != "completed":
            self._mutations.complete(
                request_id=receipt.request_id,
                result_id=accepted.proposal.proposal_id,
                result_version=accepted.document.version,
            )
        return accepted

    def reject(
        self,
        *,
        user_id: UUID,
        proposal_id: UUID,
        reason: str,
        idempotency_key: str,
    ) -> ResearchDocumentProposalSnapshot:
        receipt = self._mutations.claim(
            user_id=user_id,
            idempotency_key=idempotency_key,
            operation=f"reject_document_proposal:{proposal_id}",
            request_hash=mutation_request_hash({"reason": reason}),
        )
        try:
            rejected = self._proposals.reject(
                proposal_id=proposal_id,
                user_id=user_id,
                reason=reason,
            )
        except Exception:
            if receipt.status == "pending":
                self._mutations.fail(request_id=receipt.request_id)
            raise
        if receipt.status != "completed":
            self._mutations.complete(
                request_id=receipt.request_id,
                result_id=rejected.proposal_id,
                result_version=(
                    rejected.result_document_version
                    or rejected.base_document_version
                    or 0
                ),
            )
        return rejected
