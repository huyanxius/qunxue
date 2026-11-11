from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from qunxue_api.application.research_start import ResearchStartApplication
from qunxue_api.application.theory_matching import (
    MatchingCatalogNotReady,
    TheoryMatchingApplication,
)
from qunxue_api.modules.research_intake import (
    ConfirmedPhenomenonSnapshot,
    PhenomenonService,
    ResearchStartProposal,
    ResearchTaskRepository,
    ResearchTaskService,
    ResearchTaskStatus,
)
from qunxue_api.modules.theory_matching import MatchRunSnapshot, MatchRunStatus


class ConversationResearchBinding(Protocol):
    def get_research_task_id(self, *, user_id: UUID, conversation_id: UUID) -> UUID | None: ...

    def link_research_task(
        self, *, user_id: UUID, conversation_id: UUID, task_id: UUID
    ) -> None: ...


class AgentResearchWorkflow:
    """Connects an Agent conversation to theory candidates and user-confirmed plans."""

    def __init__(
        self,
        *,
        bindings: ConversationResearchBinding,
        tasks: ResearchTaskService,
        task_repository: ResearchTaskRepository,
        phenomena: PhenomenonService,
        matching: TheoryMatchingApplication,
        research_start: ResearchStartApplication,
        allows_model_phenomenon: Callable[[UUID, ConfirmedPhenomenonSnapshot], bool] | None = None,
        allows_saved_model_result: Callable[[UUID, MatchRunSnapshot], bool] | None = None,
    ) -> None:
        self._bindings = bindings
        self._tasks = tasks
        self._task_repository = task_repository
        self._phenomena = phenomena
        self._matching = matching
        self._research_start = research_start
        self._allows_model_phenomenon = allows_model_phenomenon
        self._allows_saved_model_result = allows_saved_model_result

    def restore(self, *, user_id: UUID, conversation_id: UUID) -> dict[str, object]:
        task_id = self._bindings.get_research_task_id(
            user_id=user_id, conversation_id=conversation_id
        )
        if task_id is None:
            return {"task_id": None, "theory_plan_id": None}
        task = self._tasks.get(task_id, user_id=user_id)
        release_id = None
        if task.current_theory_plan_id is not None:
            release_id = self._matching.get_confirmed_plan(
                user_id=user_id, theory_plan_id=task.current_theory_plan_id
            ).knowledge_release.knowledge_release_id
        return {
            "task_id": task.task_id,
            "theory_plan_id": task.current_theory_plan_id,
            "knowledge_release_id": release_id,
        }

    def prepare_start_proposal(
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
        return self._research_start.prepare_proposal(
            user_id=user_id,
            conversation_id=conversation_id,
            source_run_id=source_run_id,
            source_turn_id=source_turn_id,
            knowledge_release_id=knowledge_release_id,
            phenomenon=phenomenon,
            research_intent=research_intent,
            context=context,
        )

    def can_prepare_start_proposal(
        self, *, user_id: UUID, conversation_id: UUID
    ) -> bool:
        task_id = self._bindings.get_research_task_id(
            user_id=user_id,
            conversation_id=conversation_id,
        )
        if task_id is None:
            return True
        task = self._tasks.get(task_id, user_id=user_id)
        return task.status is ResearchTaskStatus.DRAFT

    def persist_completed_turn_proposal(
        self, proposal: ResearchStartProposal
    ) -> ResearchStartProposal:
        return self._research_start.persist_completed_turn_proposal(proposal)

    def get_state(self, *, user_id: UUID, conversation_id: UUID) -> dict[str, object]:
        restored = self.restore(user_id=user_id, conversation_id=conversation_id)
        task_id = restored["task_id"]
        if task_id is None:
            return {"status": "not_started", **restored}
        return self.get_project_state(user_id=user_id, task_id=task_id)

    def get_project_state(self, *, user_id: UUID, task_id: UUID) -> dict[str, object]:
        task = self._tasks.get(task_id, user_id=user_id)
        progress = self._phenomena.progress(task.task_id)
        phenomenon = progress.confirmed
        withheld_phenomenon = (
            phenomenon is not None
            and self._allows_model_phenomenon is not None
            and not self._allows_model_phenomenon(user_id, phenomenon)
        )
        if withheld_phenomenon:
            phenomenon = None
        match_status = None
        workflow_status = task.status.value
        if task.current_match_run_id is not None:
            match = self._matching.get(task.current_match_run_id, user_id=user_id)
            match_status = match.status.value
            if match.status is MatchRunStatus.NO_RELIABLE_CANDIDATE:
                workflow_status = "no_reliable_candidate"
        return {
            "task_id": str(task.task_id),
            "status": workflow_status,
            "project_title": None if withheld_phenomenon else task.project_title,
            "project_stage": task.project_stage,
            "method_orientation": task.method_orientation,
            "research_intent": phenomenon.research_intent if phenomenon else None,
            "context": phenomenon.context if phenomenon else None,
            "task_version": task.version,
            "phenomenon": phenomenon.phenomenon if phenomenon else None,
            "match_run_id": str(task.current_match_run_id) if task.current_match_run_id else None,
            "match_status": match_status,
            "theory_plan_id": (
                str(task.current_theory_plan_id) if task.current_theory_plan_id else None
            ),
        }

    def start_matching(self, *, user_id: UUID, conversation_id: UUID) -> dict[str, object]:
        task_id = self.restore(user_id=user_id, conversation_id=conversation_id)["task_id"]
        if task_id is None:
            return {
                "error": "research_task_missing",
                "message": "请先确认研究现象并建立研究任务。",
            }
        task = self._tasks.get(task_id, user_id=user_id)
        phenomenon = self._phenomena.progress(task.task_id).confirmed
        if phenomenon is None:
            return {"error": "phenomenon_unconfirmed"}
        current_match = (
            self._matching.get(task.current_match_run_id, user_id=user_id)
            if task.current_match_run_id is not None
            else None
        )
        if current_match is None or current_match.status is MatchRunStatus.NO_RELIABLE_CANDIDATE:
            try:
                match_run = self._matching.start(
                    user_id=user_id,
                    task=task,
                    phenomenon=phenomenon,
                    idempotency_key=f"agent-match:{conversation_id}:{task.version}",
                    expected_task_version=task.version,
                    phenomenon_query_id=phenomenon.phenomenon_query_id,
                    phenomenon_version=phenomenon.version,
                    requested_knowledge_release_id=task.knowledge_release_id,
                )
            except MatchingCatalogNotReady as error:
                return {
                    "error": "matching_catalog_not_ready",
                    "message": str(error),
                    "task_id": str(task.task_id),
                    "knowledge_release_id": task.knowledge_release_id,
                    "next_action": "install_pre_reviewed_release_then_start_matching",
                }
        else:
            match_run = current_match
        return _match_result(
            match_run,
            include_judgements=(
                self._allows_saved_model_result is None
                or self._allows_saved_model_result(user_id, match_run)
            ),
        )


def _match_result(match_run, *, include_judgements: bool = True) -> dict[str, object]:
    return {
        "match_run_id": str(match_run.match_run_id),
        "task_id": str(match_run.task_id),
        "version": match_run.version,
        "status": match_run.status.value,
        "completion_basis": match_run.completion_basis.value,
        "knowledge_release_id": match_run.knowledge_release.knowledge_release_id,
        "failed_candidate_ids": [str(item) for item in match_run.failed_candidate_ids],
        "requires_partial_acknowledgement": (
            match_run.status is MatchRunStatus.PARTIAL_FAILURE
            and not match_run.partial_completion_acknowledged
        ),
        "candidates": [
            {
                "candidate_id": str(item.candidate_id),
                "candidate_version": item.candidate_version,
                "title": item.content.title,
                "origin": item.content.origin.value,
                "core_claims": list(item.content.core_claims),
                "source_ids": list(item.content.source_ids),
                "verdict": item.judgement.verdict.value,
                "match_rationale": item.judgement.match_rationale,
                "applicable_conditions": list(item.judgement.applicable_conditions),
                "limitations": list(item.judgement.limitations),
                "evidence_gaps": list(item.judgement.evidence_gaps),
                "alternative_explanations": list(item.judgement.alternative_explanations),
                "evidence_ref_ids": list(item.judgement.evidence_ref_ids),
                "formal_adoption_eligible": item.content.formal_adoption_eligible,
                "adoption_blockers": list(item.content.adoption_blockers),
            }
            for item in (match_run.candidates if include_judgements else ())
        ],
    }
