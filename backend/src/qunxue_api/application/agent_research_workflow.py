from typing import Protocol
from uuid import UUID

from qunxue_api.application.research_start import ResearchStartApplication
from qunxue_api.application.theory_matching import (
    MatchingCatalogNotReady,
    TheoryMatchingApplication,
)
from qunxue_api.modules.research_intake import (
    PhenomenonService,
    ResearchStartProposal,
    ResearchTaskRepository,
    ResearchTaskService,
    ResearchTaskStatus,
)
from qunxue_api.modules.theory_matching import (
    MatchRunStatus,
    TheoryDecisionAction,
    TheoryDecisionCommand,
    TheoryRelationCommand,
    TheoryUseAssignment,
)


class ConversationResearchBinding(Protocol):
    def get_research_task_id(self, *, user_id: UUID, conversation_id: UUID) -> UUID | None: ...

    def link_research_task(
        self, *, user_id: UUID, conversation_id: UUID, task_id: UUID
    ) -> None: ...


class AgentResearchWorkflow:
    """Connects a persisted Agent conversation to the existing M4/M5 domain services."""

    def __init__(
        self,
        *,
        bindings: ConversationResearchBinding,
        tasks: ResearchTaskService,
        task_repository: ResearchTaskRepository,
        phenomena: PhenomenonService,
        matching: TheoryMatchingApplication,
        research_start: ResearchStartApplication,
    ) -> None:
        self._bindings = bindings
        self._tasks = tasks
        self._task_repository = task_repository
        self._phenomena = phenomena
        self._matching = matching
        self._research_start = research_start

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
            "project_title": task.project_title,
            "project_stage": task.project_stage,
            "method_orientation": task.method_orientation,
            "research_intent": progress.confirmed.research_intent if progress.confirmed else None,
            "context": progress.confirmed.context if progress.confirmed else None,
            "task_version": task.version,
            "phenomenon": progress.confirmed.phenomenon if progress.confirmed else None,
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
        return _match_result(match_run)

    def save_theory_plan(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        decisions: list[dict[str, object]],
        use_assignments: list[dict[str, object]],
        relations: list[dict[str, object]],
        user_confirmed: bool,
    ) -> dict[str, object]:
        if not user_confirmed:
            return {"error": "user_confirmation_required"}
        restored = self.restore(user_id=user_id, conversation_id=conversation_id)
        task_id = restored["task_id"]
        if task_id is None:
            return {"error": "research_task_missing"}
        task = self._tasks.get(task_id, user_id=user_id)
        if task.current_theory_plan_id is not None:
            return self.get_state(user_id=user_id, conversation_id=conversation_id)
        if task.current_match_run_id is None:
            return {"error": "match_run_missing"}
        match_run = self._matching.get(task.current_match_run_id, user_id=user_id)
        if match_run.status is MatchRunStatus.NO_RELIABLE_CANDIDATE:
            return {
                "error": "no_reliable_candidate",
                "message": (
                    "当前固定知识发布没有可正式采用的理论候选。请更新到已审校的知识发布，"
                    "或收窄/调整研究现象后重新匹配；未生成理论方案，也不会生成正式 M5 文档。"
                ),
                "match_run_id": str(match_run.match_run_id),
                "knowledge_release_id": match_run.knowledge_release.knowledge_release_id,
                "next_action": "update_knowledge_release_or_refine_phenomenon",
            }
        if (
            match_run.status is MatchRunStatus.PARTIAL_FAILURE
            and not match_run.partial_completion_acknowledged
        ):
            return {
                "error": "partial_match_acknowledgement_required",
                "failed_candidate_ids": [str(item) for item in match_run.failed_candidate_ids],
            }
        if match_run.status not in {
            MatchRunStatus.AWAITING_DECISION,
            MatchRunStatus.PARTIAL_FAILURE,
        }:
            return {
                "error": "match_run_not_ready",
                "message": "理论匹配尚未进入可保存用户决定的状态。",
                "match_run_id": str(match_run.match_run_id),
                "status": match_run.status.value,
            }
        candidate_versions = {
            str(item.candidate_id): item.candidate_version for item in match_run.candidates
        }
        decision_set = self._matching.record_decisions(
            user_id=user_id,
            match_run_id=match_run.match_run_id,
            expected_version=match_run.version,
            completion_basis=match_run.completion_basis,
            decisions=tuple(
                TheoryDecisionCommand(
                    candidate_id=UUID(str(item["candidate_id"])),
                    candidate_version=candidate_versions[str(item["candidate_id"])],
                    action=TheoryDecisionAction(str(item["action"])),
                    reason=str(item["reason"]),
                    related_source_ids=tuple(
                        str(value) for value in item.get("related_source_ids", [])
                    ),
                    revised_applicability=(
                        str(item["revised_applicability"])
                        if item.get("revised_applicability")
                        else None
                    ),
                    related_candidate_ids=tuple(
                        UUID(str(value)) for value in item.get("related_candidate_ids", [])
                    ),
                )
                for item in decisions
            ),
            use_assignments=tuple(
                TheoryUseAssignment(
                    candidate_id=UUID(str(item["candidate_id"])),
                    role_code=str(item["role_code"]),
                    responsibility=str(item["responsibility"]),
                )
                for item in use_assignments
            ),
            relations=tuple(
                TheoryRelationCommand(
                    candidate_ids=tuple(UUID(str(value)) for value in item["candidate_ids"]),
                    relation_kind=str(item["relation_kind"]),
                    explanation=str(item["explanation"]),
                    premise_compatibility=str(item["premise_compatibility"]),
                    supporting_evidence=tuple(
                        str(value) for value in item.get("supporting_evidence", [])
                    ),
                    excluding_evidence=tuple(
                        str(value) for value in item.get("excluding_evidence", [])
                    ),
                    distinguishing_evidence=tuple(
                        str(value) for value in item.get("distinguishing_evidence", [])
                    ),
                )
                for item in relations
            ),
            idempotency_key=f"agent-decisions:{conversation_id}:{match_run.version}",
        )
        plan = self._matching.confirm_plan(
            user_id=user_id,
            decision_set_id=decision_set.decision_set_id,
            expected_version=decision_set.version,
            idempotency_key=f"agent-plan:{conversation_id}:{decision_set.version}",
        )
        return {
            "task_id": str(plan.task_id),
            "theory_plan_id": str(plan.theory_plan_id),
            "status": "confirmed",
            "knowledge_release_id": plan.knowledge_release.knowledge_release_id,
            "selected_theories": [
                {
                    "candidate_id": str(item.candidate_id),
                    "title": item.content.title,
                    "source_ids": list(item.content.source_ids),
                }
                for item in plan.candidates
            ],
        }


def _match_result(match_run) -> dict[str, object]:
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
            for item in match_run.candidates
        ],
    }
