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

from .catalog_tools import KnowledgeToolRegistry


class ResearchDocumentReader(Protocol):
    def get(
        self, *, user_id: UUID, document_id: UUID, version: int | None = None
    ) -> ResearchDocumentSnapshot: ...


class ResearchDocumentToolRegistry(KnowledgeToolRegistry):
    """Adds approval-gated research-document capabilities to the knowledge tools."""

    def __init__(
        self,
        *,
        catalog,
        documents: ResearchDocumentReader,
        proposals: ResearchDocumentProposalService,
    ) -> None:
        super().__init__(catalog)
        self._documents = documents
        self._proposals = proposals
        self._user_id: UUID | None = None
        self._conversation_id: UUID | None = None
        self._agent_run_id: UUID | None = None
        self._task_id: UUID | None = None
        self._document_id: UUID | None = None
        self._section_id: str | None = None
        self._document_version: int | None = None
        self._theory_plan_id: UUID | None = None
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
        task_id: UUID | None = None,
        document_id: UUID | None = None,
        section_id: str | None = None,
        document_version: int | None = None,
        theory_plan_id: UUID | None = None,
    ) -> None:
        self._user_id = user_id
        self._conversation_id = conversation_id
        self._agent_run_id = agent_run_id
        self._task_id = task_id
        self._document_id = document_id
        self._section_id = section_id
        self._document_version = document_version
        self._theory_plan_id = theory_plan_id

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
                knowledge_release_id=self.release.knowledge_release_id,
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
