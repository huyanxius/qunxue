import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol
from uuid import UUID, uuid4

from qunxue_api.modules.research_intake import (
    EntryType,
    PhenomenonCandidateDraft,
    PhenomenonEvidenceRefSnapshot,
    PhenomenonEvidenceVerificationStatus,
    PhenomenonModelSnapshot,
    PhenomenonProgress,
    PhenomenonService,
    ProjectLifecycleStatus,
    ResearchCentralTool,
    ResearchEntryMode,
    ResearchStartConfirmation,
    ResearchStartIdempotencyConflict,
    ResearchStartProposal,
    ResearchStartProposalConflict,
    ResearchStartProposalNotFound,
    ResearchStartProposalRepository,
    ResearchStartProposalStatus,
    ResearchTask,
    ResearchTaskService,
    ResearchTaskStatus,
)


class ConversationResearchBinding(Protocol):
    def get_research_task_id(self, *, user_id: UUID, conversation_id: UUID) -> UUID | None: ...

    def link_research_task(
        self, *, user_id: UUID, conversation_id: UUID, task_id: UUID
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class ResearchStartConfirmationResult:
    proposal: ResearchStartProposal
    task: ResearchTask
    progress: PhenomenonProgress


@dataclass(frozen=True, slots=True)
class ResearchStartJourneyState:
    conversation_id: UUID
    proposal: ResearchStartProposal | None
    task: ResearchTask | None
    progress: PhenomenonProgress | None


class ResearchStartApplication:
    """Owns the explicit, atomic boundary from an Agent proposal to one task."""

    def __init__(
        self,
        *,
        proposals: ResearchStartProposalRepository,
        bindings: ConversationResearchBinding,
        tasks: ResearchTaskService,
        phenomena: PhenomenonService,
        clock=None,
        id_factory=None,
    ) -> None:
        self._proposals = proposals
        self._bindings = bindings
        self._tasks = tasks
        self._phenomena = phenomena
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or uuid4

    def prepare_proposal(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        source_run_id: UUID,
        source_turn_id: UUID,
        knowledge_release_id: str,
        phenomenon: str,
        research_intent: str | None,
        context: str | None,
    ) -> ResearchStartProposal:
        normalized_phenomenon = phenomenon.strip()
        if not normalized_phenomenon:
            raise ValueError("phenomenon must not be empty")
        return ResearchStartProposal(
            proposal_id=self._id_factory(),
            user_id=user_id,
            conversation_id=conversation_id,
            source_run_id=source_run_id,
            source_turn_id=source_turn_id,
            knowledge_release_id=knowledge_release_id,
            phenomenon=normalized_phenomenon,
            research_intent=_optional_text(research_intent),
            context=_optional_text(context),
            version=1,
            status=ResearchStartProposalStatus.PENDING_CONFIRMATION,
            created_at=self._clock(),
        )

    def ensure_draft_project(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        project_title: str,
    ) -> ResearchTask:
        bound_task_id = self._bindings.get_research_task_id(
            user_id=user_id,
            conversation_id=conversation_id,
        )
        if bound_task_id is not None:
            return self._tasks.get(bound_task_id, user_id=user_id)
        task = self._tasks.create(
            user_id=user_id,
            entry_type=EntryType.DIRECT_INPUT,
            entry_mode=ResearchEntryMode.FROM_SCRATCH,
            lifecycle_status=ProjectLifecycleStatus.DRAFT,
            project_title=project_title.strip()[:300] or "未命名研究",
            last_central_tool=ResearchCentralTool.AGENT,
            idempotency_key=f"research-entry:{conversation_id}",
            conversation_id=conversation_id,
        )
        self._bindings.link_research_task(
            user_id=user_id,
            conversation_id=conversation_id,
            task_id=task.task_id,
        )
        return task

    def bind_material_first_draft(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        task_id: UUID,
    ) -> ResearchTask:
        task = self._tasks.get(task_id, user_id=user_id)
        if (
            task.entry_mode is not ResearchEntryMode.FROM_SCRATCH
            or task.status is not ResearchTaskStatus.DRAFT
            or task.lifecycle_status is not ProjectLifecycleStatus.DRAFT
            or task.conversation_id not in {None, conversation_id}
        ):
            raise ValueError("Only an unbound from-scratch draft can adopt a conversation.")
        if task.conversation_id is None:
            saved = self._tasks.save_progress(
                replace(
                    task,
                    version=task.version + 1,
                    updated_at=self._clock(),
                    conversation_id=conversation_id,
                    last_central_tool=ResearchCentralTool.AGENT,
                )
            )
            if saved is None:
                raise ResearchStartProposalConflict(
                    "The material-first draft changed before conversation binding."
                )
            task = saved
        self._bindings.link_research_task(
            user_id=user_id,
            conversation_id=conversation_id,
            task_id=task.task_id,
        )
        return task

    def persist_completed_turn_proposal(
        self, proposal: ResearchStartProposal
    ) -> ResearchStartProposal:
        return self._proposals.add_from_completed_run(proposal)

    def get_proposal(self, *, user_id: UUID, proposal_id: UUID) -> ResearchStartProposal:
        proposal = self._proposals.get(user_id=user_id, proposal_id=proposal_id)
        if proposal is None:
            raise ResearchStartProposalNotFound(str(proposal_id))
        return proposal

    def get_conversation_proposal(
        self, *, user_id: UUID, conversation_id: UUID
    ) -> ResearchStartProposal:
        # The binding read establishes conversation ownership even when no task exists yet.
        self._bindings.get_research_task_id(user_id=user_id, conversation_id=conversation_id)
        proposal = self._proposals.latest_for_conversation(
            user_id=user_id, conversation_id=conversation_id
        )
        if proposal is None:
            raise ResearchStartProposalNotFound(str(conversation_id))
        return proposal

    def get_journey(self, *, user_id: UUID, conversation_id: UUID) -> ResearchStartJourneyState:
        task_id = self._bindings.get_research_task_id(
            user_id=user_id, conversation_id=conversation_id
        )
        proposal = self._proposals.latest_for_conversation(
            user_id=user_id, conversation_id=conversation_id
        )
        if task_id is None:
            return ResearchStartJourneyState(
                conversation_id=conversation_id,
                proposal=proposal,
                task=None,
                progress=None,
            )
        task = self._tasks.get(task_id, user_id=user_id)
        return ResearchStartJourneyState(
            conversation_id=conversation_id,
            proposal=proposal,
            task=task,
            progress=self._phenomena.progress(task.task_id),
        )

    def confirm(
        self,
        *,
        user_id: UUID,
        proposal_id: UUID,
        idempotency_key: str,
        expected_version: int,
        phenomenon: str,
        research_intent: str | None,
        context: str | None,
    ) -> ResearchStartConfirmationResult:
        normalized_phenomenon = phenomenon.strip()
        if not normalized_phenomenon:
            raise ValueError("phenomenon must not be empty")
        normalized_intent = _optional_text(research_intent)
        normalized_context = _optional_text(context)
        request_hash = _confirmation_hash(
            proposal_id=proposal_id,
            expected_version=expected_version,
            phenomenon=normalized_phenomenon,
            research_intent=normalized_intent,
            context=normalized_context,
        )
        replay = self._proposals.get_confirmation(user_id=user_id, idempotency_key=idempotency_key)
        if replay is not None:
            if replay.proposal_id != proposal_id or replay.request_hash != request_hash:
                raise ResearchStartIdempotencyConflict()
            proposal = self.get_proposal(user_id=user_id, proposal_id=proposal_id)
            task = self._tasks.get(replay.task_id, user_id=user_id)
            return ResearchStartConfirmationResult(
                proposal=proposal,
                task=task,
                progress=self._phenomena.progress(task.task_id),
            )

        proposal = self.get_proposal(user_id=user_id, proposal_id=proposal_id)
        self._proposals.assert_source_completed(proposal)
        if (
            normalized_phenomenon != proposal.phenomenon
            or normalized_intent != proposal.research_intent
            or normalized_context != proposal.context
        ):
            raise ResearchStartProposalConflict(
                "Confirmation must match the persisted Agent proposal."
            )
        if proposal.status is ResearchStartProposalStatus.CONFIRMED:
            if proposal.confirmed_request_hash != request_hash:
                raise ResearchStartProposalConflict(
                    "This proposal was already confirmed with different content."
                )
            if proposal.confirmed_task_id is None:
                raise RuntimeError("confirmed research-start proposal has no task")
            confirmation = self._proposals.add_confirmation(
                ResearchStartConfirmation(
                    user_id=user_id,
                    idempotency_key=idempotency_key,
                    proposal_id=proposal.proposal_id,
                    request_hash=request_hash,
                    task_id=proposal.confirmed_task_id,
                    created_at=self._clock(),
                )
            )
            if confirmation.request_hash != request_hash:
                raise ResearchStartIdempotencyConflict()
            task = self._tasks.get(proposal.confirmed_task_id, user_id=user_id)
            return ResearchStartConfirmationResult(
                proposal=proposal,
                task=task,
                progress=self._phenomena.progress(task.task_id),
            )
        if proposal.version != expected_version:
            raise ResearchStartProposalConflict()

        bound_task_id = self._bindings.get_research_task_id(
            user_id=user_id,
            conversation_id=proposal.conversation_id,
        )
        task = (
            self._tasks.get(bound_task_id, user_id=user_id)
            if bound_task_id is not None
            else self._tasks.create(
                user_id=user_id,
                entry_type=EntryType.DIRECT_INPUT,
                idempotency_key=f"research-start:{proposal.conversation_id}",
                knowledge_release_id=proposal.knowledge_release_id,
                conversation_id=proposal.conversation_id,
                source_turn_id=proposal.source_turn_id,
                source_agent_run_id=proposal.source_run_id,
            )
        )
        if task.status is ResearchTaskStatus.DRAFT:
            if task.source_agent_run_id is None:
                saved = self._tasks.save_progress(
                    replace(
                        task,
                        version=task.version + 1,
                        updated_at=self._clock(),
                        knowledge_release_id=proposal.knowledge_release_id,
                        conversation_id=proposal.conversation_id,
                        source_turn_id=proposal.source_turn_id,
                        source_agent_run_id=proposal.source_run_id,
                    )
                )
                if saved is None:
                    task = self._tasks.get(task.task_id, user_id=user_id)
                    if task.status is ResearchTaskStatus.DRAFT:
                        raise ResearchStartProposalConflict(
                            "The draft research task changed before confirmation."
                        )
                else:
                    task = saved
            if task.status is ResearchTaskStatus.DRAFT:
                task = self._confirm_phenomenon(
                    task=task,
                    proposal=proposal,
                    phenomenon=normalized_phenomenon,
                    research_intent=normalized_intent,
                    context=normalized_context,
                )
            else:
                _validate_replayed_task(
                    task=task,
                    proposal=proposal,
                    phenomenon=normalized_phenomenon,
                    research_intent=normalized_intent,
                )
        else:
            _validate_replayed_task(
                task=task,
                proposal=proposal,
                phenomenon=normalized_phenomenon,
                research_intent=normalized_intent,
            )

        self._bindings.link_research_task(
            user_id=user_id,
            conversation_id=proposal.conversation_id,
            task_id=task.task_id,
        )
        confirmed_at = self._clock()
        confirmed_proposal = self._proposals.mark_confirmed(
            user_id=user_id,
            proposal_id=proposal.proposal_id,
            expected_version=proposal.version,
            task_id=task.task_id,
            request_hash=request_hash,
            confirmed_at=confirmed_at,
        )
        if confirmed_proposal is None:
            current = self.get_proposal(user_id=user_id, proposal_id=proposal.proposal_id)
            if (
                current.confirmed_task_id != task.task_id
                or current.confirmed_request_hash != request_hash
            ):
                raise ResearchStartProposalConflict()
            confirmed_proposal = current
        confirmation = self._proposals.add_confirmation(
            ResearchStartConfirmation(
                user_id=user_id,
                idempotency_key=idempotency_key,
                proposal_id=proposal.proposal_id,
                request_hash=request_hash,
                task_id=task.task_id,
                created_at=confirmed_at,
            )
        )
        if (
            confirmation.proposal_id != proposal.proposal_id
            or confirmation.request_hash != request_hash
            or confirmation.task_id != task.task_id
        ):
            raise ResearchStartIdempotencyConflict()
        return ResearchStartConfirmationResult(
            proposal=confirmed_proposal,
            task=task,
            progress=self._phenomena.progress(task.task_id),
        )

    def _confirm_phenomenon(
        self,
        *,
        task: ResearchTask,
        proposal: ResearchStartProposal,
        phenomenon: str,
        research_intent: str | None,
        context: str | None,
    ) -> ResearchTask:
        direct = self._phenomena.submit_direct(
            task_id=task.task_id,
            phenomenon=phenomenon,
            research_intent=research_intent,
            context=context,
        )
        source_ref_id = f"agent-proposal:{proposal.proposal_id}"
        candidate = self._phenomena.save_candidate(
            task_id=task.task_id,
            task=task,
            draft=PhenomenonCandidateDraft(
                phenomenon=direct.phenomenon,
                research_intent=direct.research_intent,
                context=direct.context,
                source_ref_ids=(source_ref_id,),
            ),
            evidence_refs=(
                PhenomenonEvidenceRefSnapshot(
                    evidence_ref_id=source_ref_id,
                    excerpt=direct.phenomenon,
                    source_ref_id=source_ref_id,
                    source_description="用户确认的研究起点",
                    locator=f"Agent turn {proposal.source_turn_id}",
                    verification_status=PhenomenonEvidenceVerificationStatus.USER_ATTESTED,
                    use_boundary="仅代表用户明确确认的研究现象，尚未经外部来源核验。",
                ),
            ),
            model=PhenomenonModelSnapshot(
                provider="user-confirmed-agent-proposal",
                model_version="1",
                capability="user_attested",
                degraded=False,
                knowledge_release_id=proposal.knowledge_release_id,
                trace_id=proposal.source_run_id,
                request_id=proposal.source_turn_id,
                contract_version="research-start.v1",
            ),
        )
        current = self._tasks.get(task.task_id, user_id=task.user_id)
        result = self._phenomena.confirm_candidate(
            task_id=task.task_id,
            candidate_id=candidate.candidate_id,
            expected_version=candidate.version,
            task=current,
        )
        if result is None:
            raise RuntimeError("research-start phenomenon could not be confirmed")
        return self._tasks.get(task.task_id, user_id=task.user_id)


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _confirmation_hash(
    *,
    proposal_id: UUID,
    expected_version: int,
    phenomenon: str,
    research_intent: str | None,
    context: str | None,
) -> str:
    payload = json.dumps(
        {
            "proposal_id": str(proposal_id),
            "expected_version": expected_version,
            "phenomenon": phenomenon,
            "research_intent": research_intent,
            "context": context,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"sha256:{sha256(payload.encode()).hexdigest()}"


def _validate_replayed_task(
    *,
    task: ResearchTask,
    proposal: ResearchStartProposal,
    phenomenon: str,
    research_intent: str | None,
) -> None:
    if (
        task.conversation_id != proposal.conversation_id
        or task.source_agent_run_id != proposal.source_run_id
        or task.source_turn_id != proposal.source_turn_id
        or task.knowledge_release_id != proposal.knowledge_release_id
        or task.phenomenon_summary != phenomenon
        or task.phenomenon_research_intent != research_intent
    ):
        raise ResearchStartProposalConflict(
            "The conversation is already bound to a different research task."
        )
