import json
from collections.abc import Callable
from hashlib import sha256
from typing import Protocol
from uuid import UUID, uuid4

from qunxue_api.application.research_start import ResearchStartApplication
from qunxue_api.application.theory_matching import (
    MatchingCatalogNotReady,
    TheoryMatchingApplication,
)
from qunxue_api.modules.agent_conversation import AgentRun, Conversation
from qunxue_api.modules.research_intake import (
    ConfirmedPhenomenonSnapshot,
    PhenomenonService,
    ResearchStartProposal,
    ResearchTaskRepository,
    ResearchTaskService,
    ResearchTaskStatus,
)
from qunxue_api.modules.theory_matching import (
    MatchRunSnapshot,
    MatchRunStatus,
    TheoryDecisionAction,
    TheoryDecisionCommand,
    TheoryRelationCommand,
    TheoryUseAssignment,
)


class ConversationResearchBinding(Protocol):
    def get(self, *, user_id: UUID, conversation_id: UUID) -> Conversation: ...

    def find_run_by_id(self, *, user_id: UUID, run_id: UUID) -> AgentRun | None: ...

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
        state = self.get_project_state(user_id=user_id, task_id=task_id)
        pending = self._displayed_plan(user_id=user_id, conversation_id=conversation_id)
        if pending is not None and state["theory_plan_id"] is None:
            match = self._matching.get(UUID(pending[1]["match_run_id"]), user_id=user_id)
            if self._allows_saved_model_result is None or self._allows_saved_model_result(
                user_id, match
            ):
                state["pending_theory_plan"] = pending[1]
        return state

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

    def _displayed_plan(self, *, user_id: UUID, conversation_id: UUID):
        conversation = self._bindings.get(user_id=user_id, conversation_id=conversation_id)
        for turn in reversed(conversation.turns):
            for event in reversed(turn.tool_summary):
                if event.get("tool") == "propose_theory_plan" and event.get("phase") == "finished":
                    proposal = event["output"]
                    if proposal["display_text"] in turn.assistant_message.content:
                        return turn, proposal
        return None

    def propose_theory_plan(
        self, *, user_id: UUID, conversation_id: UUID,
        decisions: list[dict[str, object]], use_assignments: list[dict[str, object]],
        relations: list[dict[str, object]],
    ) -> dict[str, object]:
        task_id = self.restore(user_id=user_id, conversation_id=conversation_id)["task_id"]
        if task_id is None:
            return {"error": "research_task_missing"}
        task = self._tasks.get(task_id, user_id=user_id)
        if task.current_match_run_id is None:
            return {"error": "match_run_missing"}
        match = self._matching.get(task.current_match_run_id, user_id=user_id)
        if self._allows_saved_model_result is not None and not self._allows_saved_model_result(
            user_id, match
        ):
            return {"error": "theory_plan_context_unavailable"}
        content = {
            "decisions": decisions, "use_assignments": use_assignments, "relations": relations,
        }
        return {
            "plan_id": str(uuid4()), "content_hash": _plan_hash(match, content),
            "status": "draft", "match_run_id": str(match.match_run_id),
            "content": content, "display_text": _plan_display(match, content),
        }

    def save_theory_plan(
        self, *, user_id: UUID, conversation_id: UUID, agent_run_id: UUID,
        plan_id: str, content_hash: str, decisions: list[dict[str, object]],
        use_assignments: list[dict[str, object]], relations: list[dict[str, object]],
    ) -> dict[str, object]:
        pending = self._displayed_plan(user_id=user_id, conversation_id=conversation_id)
        run = self._bindings.find_run_by_id(user_id=user_id, run_id=agent_run_id)
        conversation = self._bindings.get(user_id=user_id, conversation_id=conversation_id)
        # This receipt is captured when the real chat request arrives, not when a
        # model calls a tool or an interrupted request resumes.
        received_after = run.request_snapshot.get("_received_after_turn_id") if run else None
        if pending is None or run is None or run.status != "running" or (
            run.conversation_id != conversation_id
            or not str(run.request_snapshot.get("message", "")).strip()
            or received_after not in {
                str(turn.turn_id) for turn in conversation.turns
                if turn.user_message.sequence >= pending[0].user_message.sequence
            }
        ):
            return {"status": "draft", "message": "请先查看本版方案，再在聊天里确认。"}
        proposal = pending[1]
        task_id = self.restore(user_id=user_id, conversation_id=conversation_id)["task_id"]
        task = self._tasks.get(task_id, user_id=user_id)
        if task.current_theory_plan_id is not None:
            return self.get_state(user_id=user_id, conversation_id=conversation_id)
        if task.current_match_run_id is None:
            return {"status": "draft", "message": "研究现象已变化，请完成匹配并展示新版方案。"}
        match = self._matching.get(task.current_match_run_id, user_id=user_id)
        content = {
            "decisions": decisions, "use_assignments": use_assignments, "relations": relations,
        }
        if plan_id != proposal["plan_id"] or content_hash != proposal["content_hash"] or (
            _plan_hash(match, content) != proposal["content_hash"]
        ):
            return {"status": "draft", "message": "方案内容或版本已变化，请展示新版后再确认。"}
        if self._allows_saved_model_result is not None and not self._allows_saved_model_result(
            user_id, match
        ):
            return {"status": "draft", "message": "本版方案的来源当前不可用于正式保存。"}
        if match.status not in {MatchRunStatus.AWAITING_DECISION, MatchRunStatus.PARTIAL_FAILURE}:
            return {"status": "draft", "message": "理论匹配尚未进入可保存决定的状态。"}
        if match.status is MatchRunStatus.PARTIAL_FAILURE and not (
            match.partial_completion_acknowledged
        ):
            return {"status": "draft", "message": "本次匹配仍有未确认的缺失候选。"}
        versions = {str(item.candidate_id): item.candidate_version for item in match.candidates}
        decision_set = self._matching.record_decisions(
            user_id=user_id, match_run_id=match.match_run_id, expected_version=match.version,
            completion_basis=match.completion_basis,
            decisions=tuple(TheoryDecisionCommand(
                candidate_id=UUID(item["candidate_id"]),
                candidate_version=versions[item["candidate_id"]],
                action=TheoryDecisionAction(item["action"]), reason=item["reason"],
                related_source_ids=tuple(item.get("related_source_ids", [])),
                revised_applicability=item.get("revised_applicability"),
                related_candidate_ids=tuple(UUID(value) for value in item.get(
                    "related_candidate_ids", []
                )),
            ) for item in decisions),
            use_assignments=tuple(TheoryUseAssignment(
                candidate_id=UUID(item["candidate_id"]), role_code=item["role_code"],
                responsibility=item["responsibility"],
            ) for item in use_assignments),
            relations=tuple(TheoryRelationCommand(
                candidate_ids=tuple(UUID(value) for value in item["candidate_ids"]),
                relation_kind=item["relation_kind"], explanation=item["explanation"],
                premise_compatibility=item["premise_compatibility"],
                supporting_evidence=tuple(item.get("supporting_evidence", [])),
                excluding_evidence=tuple(item.get("excluding_evidence", [])),
                distinguishing_evidence=tuple(item.get("distinguishing_evidence", [])),
            ) for item in relations),
            idempotency_key=f"chat-decisions:{plan_id}",
        )
        plan = self._matching.confirm_plan(
            user_id=user_id, decision_set_id=decision_set.decision_set_id,
            expected_version=decision_set.version, idempotency_key=f"chat-plan:{plan_id}",
        )
        return {
            "status": "confirmed", "task_id": str(plan.task_id),
            "theory_plan_id": str(plan.theory_plan_id),
            "knowledge_release_id": plan.knowledge_release.knowledge_release_id,
        }


def _plan_hash(match, content) -> str:
    encoded = json.dumps({
        "task_id": str(match.task_id), "match_run_id": str(match.match_run_id),
        "match_run_version": match.version,
        "knowledge_release_id": match.knowledge_release.knowledge_release_id, **content,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"sha256:{sha256(encoded.encode()).hexdigest()}"


def _plan_display(match, content) -> str:
    labels = {
        "decisions": "候选取舍", "use_assignments": "理论分工", "relations": "理论关系",
        "candidate_id": "理论", "candidate_ids": "理论", "action": "决定", "reason": "理由",
        "related_source_ids": "来源", "revised_applicability": "修订适用条件",
        "related_candidate_ids": "相关理论", "role_code": "角色", "responsibility": "解释责任",
        "relation_kind": "关系", "explanation": "说明", "premise_compatibility": "前提相容性",
        "supporting_evidence": "支持证据", "excluding_evidence": "排除证据",
        "distinguishing_evidence": "区分证据",
    }
    values = {
        str(item.candidate_id): item.content.title for item in match.candidates
    } | {
        "adopt": "采用", "exclude": "排除", "retain": "保留", "combine": "组合",
        "defer": "暂缓", "request_more_evidence": "补充证据",
        "revise_applicability": "修订适用条件", "primary": "主理论",
    }
    lines = ["### 待确认的理论方案"]
    for key, items in content.items():
        lines.extend(("", f"**{labels[key]}**"))
        for item in items:
            parts = []
            for field, value in item.items():
                text = "、".join(values.get(str(v), str(v)) for v in value) if isinstance(
                    value, list
                ) else values.get(str(value), str(value))
                parts.append(f"{labels.get(field, field)}：{text}")
            lines.append(f"- {'；'.join(parts)}")
        if not items:
            lines.append("无")
    lines.extend(("", "同意这版方案后，请在聊天里说“确认”；如需修改，我会先展示新版。"))
    return "\n".join(lines)


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
