from dataclasses import replace
from typing import Protocol
from uuid import UUID

from qunxue_api.modules.research_framework import (
    ResearchDocumentEvidenceRef,
    ResearchDocumentProposalService,
    ResearchDocumentSection,
    ResearchDocumentSectionStatus,
    ResearchDocumentSnapshot,
)
from qunxue_api.modules.research_intake import ResearchStartProposal

from .catalog_tools import KnowledgeToolRegistry


class ResearchDocumentReader(Protocol):
    def get(
        self, *, user_id: UUID, document_id: UUID, version: int | None = None
    ) -> ResearchDocumentSnapshot: ...


class ResearchWorkflowCoordinator(Protocol):
    def restore(self, *, user_id: UUID, conversation_id: UUID) -> dict[str, object]: ...

    def prepare_start_proposal(self, **payload: object) -> ResearchStartProposal: ...

    def persist_completed_turn_proposal(
        self, proposal: ResearchStartProposal
    ) -> ResearchStartProposal: ...

    def get_state(self, **payload: object) -> dict[str, object]: ...

    def start_matching(self, **payload: object) -> dict[str, object]: ...

    def save_theory_plan(self, **payload: object) -> dict[str, object]: ...


class ResearchDocumentToolRegistry(KnowledgeToolRegistry):
    """Adds approval-gated research-document capabilities to the knowledge tools."""

    def __init__(
        self,
        *,
        catalog,
        documents: ResearchDocumentReader,
        proposals: ResearchDocumentProposalService,
        workflow: ResearchWorkflowCoordinator | None = None,
    ) -> None:
        super().__init__(catalog)
        self._documents = documents
        self._proposals = proposals
        self._workflow = workflow
        self._user_id: UUID | None = None
        self._conversation_id: UUID | None = None
        self._agent_run_id: UUID | None = None
        self._agent_turn_id: UUID | None = None
        self._task_id: UUID | None = None
        self._document_id: UUID | None = None
        self._section_id: str | None = None
        self._document_version: int | None = None
        self._theory_plan_id: UUID | None = None
        self._theory_plan_release_id: str | None = None
        self._pending_start_proposal: ResearchStartProposal | None = None
        self.research_document_tools_enabled = False

    def enable_research_document_tools(self) -> None:
        self.research_document_tools_enabled = True

    @property
    def document_prompt_context(self) -> dict[str, object] | None:
        if not self.research_document_tools_enabled or self._task_id is None:
            return None
        return {
            "task_id": str(self._task_id),
            "theory_plan_id": str(self._theory_plan_id) if self._theory_plan_id else None,
            "document_id": str(self._document_id) if self._document_id else None,
            "document_version": self._document_version,
            "section_id": self._section_id,
        }

    def bind_agent_context(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID,
        agent_run_id: UUID,
        agent_turn_id: UUID | None = None,
        task_id: UUID | None = None,
        document_id: UUID | None = None,
        section_id: str | None = None,
        document_version: int | None = None,
        theory_plan_id: UUID | None = None,
    ) -> None:
        self._user_id = user_id
        self._conversation_id = conversation_id
        self._agent_run_id = agent_run_id
        self._agent_turn_id = agent_turn_id
        self._task_id = task_id
        self._document_id = document_id
        self._section_id = section_id
        self._document_version = document_version
        self._theory_plan_id = theory_plan_id
        if self._workflow is not None and task_id is None:
            restored = self._workflow.restore(user_id=user_id, conversation_id=conversation_id)
            restored_task_id = restored.get("task_id")
            restored_theory_plan_id = restored.get("theory_plan_id")
            restored_release_id = restored.get("knowledge_release_id")
            self._task_id = (
                restored_task_id
                if isinstance(restored_task_id, UUID)
                else UUID(str(restored_task_id))
                if restored_task_id
                else None
            )
            self._theory_plan_id = (
                restored_theory_plan_id
                if isinstance(restored_theory_plan_id, UUID)
                else UUID(str(restored_theory_plan_id))
                if restored_theory_plan_id
                else None
            )
            self._theory_plan_release_id = str(restored_release_id) if restored_release_id else None

    def propose_start_research(
        self,
        *,
        phenomenon: str,
        research_intent: str | None,
        context: str | None,
    ) -> dict[str, object]:
        user_id, conversation_id, agent_run_id = self._context()
        if self._workflow is None:
            return {"error": "research_workflow_unavailable"}
        if self._task_id is not None:
            return {
                "error": "research_task_already_bound",
                "task_id": str(self._task_id),
                "message": "这段对话已经绑定研究任务，请从现有研究继续。",
            }
        if self._agent_turn_id is None:
            return {
                "error": "research_start_turn_unavailable",
                "message": "研究起点只能绑定到当前即将完成的 Agent turn。",
            }
        proposal = self._workflow.prepare_start_proposal(
            user_id=user_id,
            conversation_id=conversation_id,
            source_run_id=agent_run_id,
            source_turn_id=self._agent_turn_id,
            knowledge_release_id=self.release.knowledge_release_id,
            phenomenon=phenomenon,
            research_intent=research_intent,
            context=context,
        )
        if self._pending_start_proposal is not None:
            if _start_proposal_content(self._pending_start_proposal) != _start_proposal_content(
                proposal
            ):
                return {
                    "error": "research_start_proposal_already_prepared",
                    "message": "当前回答已经提出另一份研究起点，请先完成本轮对话。",
                }
            proposal = self._pending_start_proposal
        else:
            self._pending_start_proposal = proposal
        return _start_proposal_result(proposal)

    def finalize_agent_turn(self, *, source_turn_id: UUID) -> None:
        proposal = self._pending_start_proposal
        if proposal is None:
            return
        if proposal.source_turn_id != source_turn_id:
            raise RuntimeError("research-start proposal belongs to another Agent turn")
        self._pending_start_proposal = self._workflow.persist_completed_turn_proposal(proposal)

    def get_research_workflow_state(self) -> dict[str, object]:
        user_id, conversation_id, _ = self._context()
        if self._workflow is None:
            return {"error": "research_workflow_unavailable"}
        return self._workflow.get_state(user_id=user_id, conversation_id=conversation_id)

    def start_theory_matching(self) -> dict[str, object]:
        user_id, conversation_id, _ = self._context()
        if self._workflow is None:
            return {"error": "research_workflow_unavailable"}
        return self._workflow.start_matching(user_id=user_id, conversation_id=conversation_id)

    def save_confirmed_theory_plan(
        self,
        *,
        decisions: list[dict[str, object]],
        use_assignments: list[dict[str, object]],
        relations: list[dict[str, object]],
        user_confirmed: bool,
    ) -> dict[str, object]:
        user_id, conversation_id, _ = self._context()
        if not user_confirmed:
            return {
                "error": "user_confirmation_required",
                "message": "保存理论决定会正式写入，必须先获得用户明确确认。",
            }
        if self._workflow is None:
            return {"error": "research_workflow_unavailable"}
        result = self._workflow.save_theory_plan(
            user_id=user_id,
            conversation_id=conversation_id,
            decisions=decisions,
            use_assignments=use_assignments,
            relations=relations,
            user_confirmed=user_confirmed,
        )
        if result.get("theory_plan_id"):
            self._theory_plan_id = UUID(str(result["theory_plan_id"]))
            self._theory_plan_release_id = str(result["knowledge_release_id"])
        return result

    def read_research_document(self, document_id: str) -> dict[str, object]:
        user_id, _, _ = self._context()
        try:
            parsed_document_id = UUID(document_id)
            snapshot = self._documents.get(
                user_id=user_id,
                document_id=parsed_document_id,
            )
        except (LookupError, ValueError):
            return {
                "error": "research_document_not_found",
                "document_id": document_id,
            }
        if snapshot.knowledge_release_id != self.release.knowledge_release_id:
            return self._release_mismatch(snapshot.knowledge_release_id)
        return {
            "document_id": str(snapshot.document_id),
            "task_id": str(snapshot.task_id),
            "theory_plan_id": str(snapshot.theory_plan_id),
            "knowledge_release_id": snapshot.knowledge_release_id,
            "version": snapshot.version,
            "title": snapshot.title,
            "status": snapshot.status.value,
            "sections": [
                {
                    "section_id": section.section_id,
                    "key": section.key,
                    "title": section.title,
                    "content": section.content,
                    "status": section.status.value,
                    "evidence_refs": [
                        {
                            "evidence_ref_id": evidence.evidence_ref_id,
                            "source_id": evidence.source_id,
                            "knowledge_release_id": evidence.knowledge_release_id,
                        }
                        for evidence in section.evidence_refs
                    ],
                }
                for section in snapshot.sections
            ],
        }

    def propose_document_revision(
        self,
        *,
        document_id: str | None = None,
        expected_version: int | None = None,
        section_id: str | None = None,
        replacement_content: str,
        rationale: str,
    ) -> dict[str, object]:
        user_id, conversation_id, agent_run_id = self._context()
        document_id = document_id or (str(self._document_id) if self._document_id else "")
        expected_version = (
            expected_version if expected_version is not None else self._document_version
        )
        section_id = section_id or self._section_id or ""
        if not document_id or expected_version is None or not section_id:
            return {
                "error": "research_document_context_missing",
                "message": "当前 Agent 请求没有完整的文档章节上下文。",
            }
        try:
            parsed_document_id = UUID(document_id)
            current = self._documents.get(
                user_id=user_id,
                document_id=parsed_document_id,
            )
        except (LookupError, ValueError):
            return {
                "error": "research_document_not_found",
                "document_id": document_id,
            }
        if current.knowledge_release_id != self.release.knowledge_release_id:
            return self._release_mismatch(current.knowledge_release_id)
        target = next(
            (section for section in current.sections if section.section_id == section_id),
            None,
        )
        if target is None:
            return {
                "error": "research_document_section_not_found",
                "document_id": document_id,
                "section_id": section_id,
            }
        try:
            proposal = self._proposals.propose_revision(
                user_id=user_id,
                conversation_id=conversation_id,
                agent_run_id=agent_run_id,
                document_id=current.document_id,
                expected_version=expected_version,
                section=replace(target, content=replacement_content),
                rationale=rationale,
            )
        except ValueError as error:
            return {
                "error": "research_document_proposal_invalid",
                "message": str(error),
                "document_id": document_id,
                "section_id": section_id,
            }
        return {
            "proposal_id": str(proposal.proposal_id),
            "document_id": str(current.document_id),
            "base_document_version": proposal.base_document_version,
            "section_id": section_id,
            "status": proposal.status.value,
            "requires_user_approval": True,
            "before": target.content,
            "after": proposal.proposed_sections[0].content,
            "rationale": proposal.rationale,
            "knowledge_release_id": proposal.knowledge_release_id,
        }

    def propose_document_creation(
        self,
        *,
        title: str,
        sections: list[dict[str, object]],
        rationale: str,
    ) -> dict[str, object]:
        user_id, conversation_id, agent_run_id = self._context()
        if self._task_id is None or self._theory_plan_id is None:
            return {
                "error": "research_document_context_missing",
                "message": "创建研究框架需要当前任务与已确认理论方案。",
            }
        try:
            parsed_sections = tuple(_section_from_payload(item) for item in sections)
            proposal = self._proposals.propose_create(
                user_id=user_id,
                conversation_id=conversation_id,
                agent_run_id=agent_run_id,
                task_id=self._task_id,
                theory_plan_id=self._theory_plan_id,
                knowledge_release_id=(
                    self._theory_plan_release_id or self.release.knowledge_release_id
                ),
                title=title,
                sections=parsed_sections,
                rationale=rationale,
            )
        except (LookupError, ValueError) as error:
            return {"error": "research_document_proposal_invalid", "message": str(error)}
        return {
            "proposal_id": str(proposal.proposal_id),
            "kind": proposal.kind.value,
            "status": proposal.status.value,
            "title": proposal.title,
            "section_count": len(proposal.proposed_sections),
            "requires_user_approval": True,
            "knowledge_release_id": proposal.knowledge_release_id,
        }

    def _context(self) -> tuple[UUID, UUID, UUID]:
        if self._user_id is None or self._conversation_id is None or self._agent_run_id is None:
            raise RuntimeError("research document tools require a persisted Agent run")
        return self._user_id, self._conversation_id, self._agent_run_id

    def _release_mismatch(self, document_release_id: str) -> dict[str, object]:
        return {
            "error": "knowledge_release_mismatch",
            "document_knowledge_release_id": document_release_id,
            "agent_knowledge_release_id": self.release.knowledge_release_id,
            "message": "文档与当前 Agent 使用的知识发布版本不一致，未生成修改建议。",
        }


def _section_from_payload(payload: dict[str, object]) -> ResearchDocumentSection:
    section_id = str(payload.get("section_id", "")).strip()
    key = str(payload.get("key", section_id)).strip()
    title = str(payload.get("title", key)).strip()
    content = str(payload.get("content", "")).strip()
    if not section_id or not key or not title or not content:
        raise ValueError("each proposed section needs section_id, key, title, and content")
    return ResearchDocumentSection(
        section_id=section_id,
        key=key,
        title=title,
        content=content,
        status=ResearchDocumentSectionStatus.DRAFT,
        evidence_refs=tuple(
            ResearchDocumentEvidenceRef(
                evidence_ref_id=str(item["evidence_ref_id"]),
                source_id=str(item["source_id"]),
                knowledge_release_id=str(item["knowledge_release_id"]),
            )
            for item in payload.get("evidence_refs", [])
            if isinstance(item, dict)
        ),
    )


def _start_proposal_result(proposal: ResearchStartProposal) -> dict[str, object]:
    return {
        "proposal_id": str(proposal.proposal_id),
        "conversation_id": str(proposal.conversation_id),
        "source_run_id": str(proposal.source_run_id),
        "source_turn_id": str(proposal.source_turn_id),
        "knowledge_release_id": proposal.knowledge_release_id,
        "phenomenon": proposal.phenomenon,
        "research_intent": proposal.research_intent,
        "context": proposal.context,
        "version": proposal.version,
        "status": proposal.status.value,
        "requires_user_confirmation": True,
        "confirmed_task_id": (
            str(proposal.confirmed_task_id) if proposal.confirmed_task_id else None
        ),
        "created_at": _json_datetime(proposal.created_at),
        "confirmed_at": _json_datetime(proposal.confirmed_at) if proposal.confirmed_at else None,
    }


def _start_proposal_content(proposal: ResearchStartProposal) -> tuple[object, ...]:
    return proposal.phenomenon, proposal.research_intent, proposal.context


def _json_datetime(value) -> str:
    return value.isoformat().replace("+00:00", "Z")
