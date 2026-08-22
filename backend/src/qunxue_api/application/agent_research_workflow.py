from typing import Protocol
from uuid import UUID

from qunxue_api.application.theory_matching import TheoryMatchingApplication
from qunxue_api.modules.research_intake import (
    EntryType,
    PhenomenonCandidateDraft,
    PhenomenonEvidenceRefSnapshot,
    PhenomenonEvidenceVerificationStatus,
    PhenomenonModelSnapshot,
    PhenomenonService,
    ResearchTaskRepository,
    ResearchTaskService,
)
from qunxue_api.modules.theory_matching import (
    MatchRunStatus,
    TheoryDecisionAction,
    TheoryDecisionCommand,
    TheoryRelationCommand,
    TheoryUseAssignment,
)


class ConversationResearchBinding(Protocol):
    def commit(self) -> None: ...

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
    ) -> None:
        self._bindings = bindings
        self._tasks = tasks
        self._task_repository = task_repository
        self._phenomena = phenomena
        self._matching = matching

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

    def create_confirmed_task(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        phenomenon: str,
        research_intent: str | None,
        context: str | None,
        user_confirmed: bool,
    ) -> dict[str, object]:
        if not user_confirmed:
            return {"error": "user_confirmation_required"}
        existing = self._bindings.get_research_task_id(
            user_id=user_id, conversation_id=conversation_id
        )
        if existing is not None:
            return self.get_state(user_id=user_id, conversation_id=conversation_id)
        task = self._tasks.create(
            user_id=user_id,
            entry_type=EntryType.DIRECT_INPUT,
            idempotency_key=f"agent-research:{conversation_id}",
        )
        direct = self._phenomena.submit_direct(
            task_id=task.task_id,
            phenomenon=phenomenon,
            research_intent=research_intent,
            context=context,
        )
        candidate = self._phenomena.save_candidate(
            task_id=task.task_id,
            task=task,
            draft=PhenomenonCandidateDraft(
                phenomenon=direct.phenomenon,
                research_intent=direct.research_intent,
                context=direct.context,
                source_ref_ids=("input:direct",),
            ),
            evidence_refs=(
                PhenomenonEvidenceRefSnapshot(
                    evidence_ref_id="input:direct",
                    excerpt=direct.phenomenon,
                    source_ref_id="input:direct",
                    source_description="用户在研究 Agent 中确认的直接输入",
                    locator=None,
                    verification_status=PhenomenonEvidenceVerificationStatus.USER_ATTESTED,
                    use_boundary="仅代表用户确认的研究现象，尚未经外部来源核验。",
                ),
            ),
            model=PhenomenonModelSnapshot(
                provider="user-confirmed-input",
                model_version="1",
                capability="user_attested",
                degraded=False,
                knowledge_release_id=None,
                trace_id=conversation_id,
                request_id=candidate_request_id(conversation_id),
                contract_version="agent-research-v1",
            ),
        )
        current_task = self._tasks.get(task.task_id, user_id=user_id)
        confirmed = self._phenomena.confirm_candidate(
            task_id=task.task_id,
            candidate_id=candidate.candidate_id,
            expected_version=candidate.version,
            task=current_task,
        )
        if confirmed is None:
            raise RuntimeError("confirmed Agent phenomenon could not be persisted")
        self._bindings.link_research_task(
            user_id=user_id,
            conversation_id=conversation_id,
            task_id=task.task_id,
        )
        # The existing model invocation recorder owns a separate SQLite session.
        # Commit the user-confirmed M3 boundary before M4 invokes that recorder,
        # otherwise SQLite correctly rejects two concurrent writers.
        self._bindings.commit()
        snapshot, _ = confirmed
        return {
            "task_id": str(task.task_id),
            "status": "phenomenon_confirmed",
            "phenomenon_query_id": str(snapshot.phenomenon_query_id),
            "phenomenon_version": snapshot.version,
            "phenomenon": snapshot.phenomenon,
            "evidence_refs": [
                {
                    "evidence_ref_id": item.evidence_ref_id,
                    "source_ref_id": item.source_ref_id,
                    "verification_status": item.verification_status.value,
                }
                for item in snapshot.evidence_refs
            ],
        }

    def get_state(self, *, user_id: UUID, conversation_id: UUID) -> dict[str, object]:
        restored = self.restore(user_id=user_id, conversation_id=conversation_id)
        task_id = restored["task_id"]
        if task_id is None:
            return {"status": "not_started", **restored}
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
        if task.current_match_run_id is None:
            match_run = self._matching.start(
                user_id=user_id,
                task=task,
                phenomenon=phenomenon,
                idempotency_key=f"agent-match:{conversation_id}:{task.version}",
                expected_task_version=task.version,
                phenomenon_query_id=phenomenon.phenomenon_query_id,
                phenomenon_version=phenomenon.version,
                requested_knowledge_release_id=None,
            )
        else:
            match_run = self._matching.get(task.current_match_run_id, user_id=user_id)
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
        if match_run.status is not MatchRunStatus.AWAITING_DECISION:
            return {
                "error": "match_run_not_ready",
                "message": "理论匹配尚未进入可保存用户决定的状态。",
                "match_run_id": str(match_run.match_run_id),
                "status": match_run.status.value,
            }
        if (
            match_run.status is MatchRunStatus.PARTIAL_FAILURE
            and not match_run.partial_completion_acknowledged
        ):
            return {
                "error": "partial_match_acknowledgement_required",
                "failed_candidate_ids": [str(item) for item in match_run.failed_candidate_ids],
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


def candidate_request_id(conversation_id: UUID) -> UUID:
    return UUID(int=conversation_id.int ^ 1)


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
