from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass, replace
from datetime import datetime
from enum import Enum
from typing import Protocol
from uuid import UUID

from qunxue_api.modules.agent_conversation import AgentEvidence, AgentMaterialAttachment
from qunxue_api.modules.research_analysis import (
    ComparisonFinding,
    ComparisonFindingKind,
    NextResearchStep,
)
from qunxue_api.modules.research_framework import (
    ResearchDocumentEvidenceRef,
    ResearchDocumentProposalService,
    ResearchDocumentSection,
    ResearchDocumentSectionStatus,
    ResearchDocumentSnapshot,
)
from qunxue_api.modules.research_intake import ResearchStartProposal
from qunxue_api.modules.research_materials import (
    MaterialBlock,
    MaterialParseVersion,
    MaterialStatus,
    ResearchMaterial,
    ResearchMaterialSearchResult,
)
from qunxue_api.modules.theory_matching import ConfirmedTheoryPlanSnapshot

from .catalog_tools import KnowledgeToolRegistry


class ResearchDocumentReader(Protocol):
    def get(
        self, *, user_id: UUID, document_id: UUID, version: int | None = None
    ) -> ResearchDocumentSnapshot: ...

    def get_theory_plan_for_agent(
        self, *, user_id: UUID, theory_plan_id: UUID
    ) -> ConfirmedTheoryPlanSnapshot: ...


class ResearchMaterialReader(Protocol):
    """Read-only, task-authorized material port used by Agent tools."""

    def list(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        include_deleted: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[ResearchMaterial]: ...

    def get(
        self,
        material_id: UUID,
        *,
        user_id: UUID,
        task_id: UUID,
        include_deleted: bool = False,
    ) -> ResearchMaterial | None: ...

    def get_parse(
        self,
        material_id: UUID,
        parse_id: UUID,
        *,
        user_id: UUID,
        task_id: UUID,
    ) -> MaterialParseVersion | None: ...

    def get_segment(
        self,
        material_id: UUID,
        parse_id: UUID,
        segment_id: str,
        *,
        user_id: UUID,
        task_id: UUID,
    ) -> MaterialBlock | None: ...

    def is_external_model_processable(
        self,
        material_id: UUID,
        *,
        user_id: UUID,
        task_id: UUID,
    ) -> bool: ...


class ResearchMaterialSearchReader(Protocol):
    """Persistent, authorization-aware material search projection."""

    def search(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        query: str,
        material_ids: tuple[UUID, ...] = (),
        material_parse_ids: tuple[tuple[UUID, UUID], ...] = (),
        limit: int = 20,
        offset: int = 0,
    ) -> ResearchMaterialSearchResult: ...


class ResearchWorkflowCoordinator(Protocol):
    def restore(self, *, user_id: UUID, conversation_id: UUID) -> dict[str, object]: ...

    def prepare_start_proposal(self, **payload: object) -> ResearchStartProposal: ...

    def can_prepare_start_proposal(self, *, user_id: UUID, conversation_id: UUID) -> bool: ...

    def persist_completed_turn_proposal(
        self, proposal: ResearchStartProposal
    ) -> ResearchStartProposal: ...

    def get_state(self, **payload: object) -> dict[str, object]: ...

    def start_matching(self, **payload: object) -> dict[str, object]: ...

    def save_theory_plan(self, **payload: object) -> dict[str, object]: ...


class ResearchAnalysisAgentFacade(Protocol):
    """Narrow approval-gated boundary exposed to the existing research Agent."""

    def get_for_agent(self, *, user_id: UUID, task_id: UUID) -> dict[str, object]: ...

    def propose_code_from_agent(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        label: str,
        definition: str,
        annotation_ids: tuple[UUID, ...],
        rationale: str,
        conversation_id: UUID,
        agent_run_id: UUID,
        agent_turn_id: UUID,
        tool_call_id: str,
    ) -> object: ...

    def propose_memo_from_agent(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        title: str,
        content: str,
        memo_kind: str,
        annotation_ids: tuple[UUID, ...],
        code_ids: tuple[UUID, ...],
        conversation_id: UUID,
        agent_run_id: UUID,
        agent_turn_id: UUID,
        tool_call_id: str,
    ) -> object: ...

    def propose_coding_plan_from_agent(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        title: str,
        rationale: str,
        items: tuple[Mapping[str, object], ...],
        conversation_id: UUID,
        agent_run_id: UUID,
        agent_turn_id: UUID,
        tool_call_id: str,
    ) -> object: ...

    def retrieve_coded_segments(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        code_ids: tuple[UUID, ...] = (),
        material_id: UUID | None = None,
        query: str | None = None,
        limit: int = 50,
    ) -> Sequence[Mapping[str, object]]: ...

    def get_comparison_context_for_agent(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        case_labels: tuple[str, ...],
        time_labels: tuple[str, ...],
    ) -> dict[str, object]: ...

    def propose_comparison_from_agent(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        title: str,
        question: str,
        case_labels: tuple[str, ...],
        time_labels: tuple[str, ...],
        findings: tuple[ComparisonFinding, ...],
        competing_explanations: tuple[str, ...],
        evidence_gaps: tuple[str, ...],
        next_steps: tuple[NextResearchStep, ...],
        theory_implication: str,
        conversation_id: UUID,
        agent_run_id: UUID,
        agent_turn_id: UUID,
        tool_call_id: str,
    ) -> object: ...


class ResearchDocumentToolRegistry(KnowledgeToolRegistry):
    """Adds approval-gated research-document capabilities to the knowledge tools."""

    def __init__(
        self,
        *,
        catalog,
        retriever=None,
        web_research=None,
        documents: ResearchDocumentReader,
        proposals: ResearchDocumentProposalService,
        workflow: ResearchWorkflowCoordinator | None = None,
        materials: ResearchMaterialReader | None = None,
        material_search: ResearchMaterialSearchReader | None = None,
        analysis: ResearchAnalysisAgentFacade | None = None,
    ) -> None:
        super().__init__(catalog, retriever=retriever, web_research=web_research)
        self._documents = documents
        self._proposals = proposals
        self._workflow = workflow
        self._materials = materials
        self._material_search = material_search
        self._analysis = analysis
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
        self._confirmed_plan: ConfirmedTheoryPlanSnapshot | None = None
        self._pending_start_proposal: ResearchStartProposal | None = None
        self._material_scope: dict[UUID, UUID] | None = None
        self.research_handoff_tools_enabled = False
        self.research_document_tools_enabled = False
        self.research_material_tools_enabled = False
        self.research_analysis_tools_enabled = False

    def enable_research_handoff_tools(self) -> None:
        self.research_handoff_tools_enabled = True

    def enable_research_document_tools(self) -> None:
        self.research_document_tools_enabled = True

    def enable_research_material_tools(self) -> None:
        """Expose task-scoped personal-material tools for the current turn."""

        self.research_material_tools_enabled = (
            self._materials is not None and self._task_id is not None
        )
        self._refresh_analysis_tools_enabled()

    def pin_research_material_scope(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        material_ids: Sequence[UUID],
    ) -> tuple[AgentMaterialAttachment, ...]:
        """Validate explicit attachments and freeze their current parse IDs."""

        if self._materials is None:
            raise ValueError("research material storage is unavailable")
        unique_ids = tuple(dict.fromkeys(material_ids))
        if len(unique_ids) > 20:
            raise ValueError("an Agent turn accepts at most 20 research materials")
        attachments: list[AgentMaterialAttachment] = []
        for material_id in unique_ids:
            material = self._materials.get(
                material_id,
                user_id=user_id,
                task_id=task_id,
            )
            if (
                material is None
                or material.status is not MaterialStatus.READY
                or material.current_parse_id is None
            ):
                raise ValueError("attached research material requires a ready current parse")
            parsed = self._materials.get_parse(
                material_id,
                material.current_parse_id,
                user_id=user_id,
                task_id=task_id,
            )
            if parsed is None or parsed.status is not MaterialStatus.READY:
                raise ValueError("attached research material requires a ready current parse")
            attachments.append(
                AgentMaterialAttachment(
                    material_id=material.material_id,
                    parse_id=parsed.parse_id,
                )
            )
        resolved = tuple(attachments)
        self.bind_research_material_scope(resolved)
        return resolved

    def bind_research_material_scope(
        self,
        attachments: Sequence[AgentMaterialAttachment],
    ) -> None:
        """Restore the immutable material scope saved on an Agent run."""

        self._material_scope = (
            {item.material_id: item.parse_id for item in attachments}
        )

    @property
    def document_prompt_context(self) -> dict[str, object] | None:
        if not self.research_document_tools_enabled or self._task_id is None:
            return None
        context: dict[str, object] = {
            "task_id": str(self._task_id),
            "theory_plan_id": str(self._theory_plan_id) if self._theory_plan_id else None,
            "document_id": str(self._document_id) if self._document_id else None,
            "document_version": self._document_version,
            "section_id": self._section_id,
        }
        if self._confirmed_plan is not None:
            context["confirmed_plan"] = _confirmed_plan_payload(self._confirmed_plan)
        return context

    def prepare_research_context(
        self,
        *,
        user_id: UUID,
        task_id: UUID | None,
        document_id: UUID | None,
        theory_plan_id: UUID | None,
    ) -> None:
        """Pin the confirmed M5 inputs before the Agent run is persisted."""

        document = None
        if document_id is not None:
            document = self._documents.get(user_id=user_id, document_id=document_id)
            theory_plan_id = theory_plan_id or document.theory_plan_id
            task_id = task_id or document.task_id
        if theory_plan_id is None:
            return
        plan = self._documents.get_theory_plan_for_agent(
            user_id=user_id,
            theory_plan_id=theory_plan_id,
        )
        if task_id is not None and plan.task_id != task_id:
            raise ValueError("confirmed theory plan does not belong to the research task")
        if document is not None and (
            document.task_id != plan.task_id or document.theory_plan_id != plan.theory_plan_id
        ):
            raise ValueError("research document does not belong to the confirmed theory plan")
        self._task_id = plan.task_id
        self._theory_plan_id = plan.theory_plan_id
        self._theory_plan_release_id = plan.knowledge_release.knowledge_release_id
        self._confirmed_plan = plan
        self.release = plan.knowledge_release

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
        if self._confirmed_plan is not None and (
            self._confirmed_plan.task_id != task_id
            or self._confirmed_plan.theory_plan_id != theory_plan_id
        ):
            raise ValueError("Agent context changed after the confirmed plan was pinned")
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
        # A restored conversation may acquire its task id from the workflow;
        # enable the material tools only after that binding is known.
        if self._materials is not None and self._task_id is not None:
            self.research_material_tools_enabled = True
        self._refresh_analysis_tools_enabled()

    def get_research_analysis(self) -> dict[str, object]:
        """Read the current task's analysis without changing user decisions."""

        user_id, task_id, _, _, _, analysis = self._analysis_context()
        result = _json_safe(analysis.get_for_agent(user_id=user_id, task_id=task_id))
        if not isinstance(result, dict):
            raise TypeError("research analysis snapshot must be an object")
        return result

    def propose_analysis_code(
        self,
        *,
        label: str,
        definition: str,
        annotation_ids: Sequence[str],
        rationale: str,
        tool_call_id: str,
    ) -> dict[str, object]:
        """Persist an Agent-authored code candidate for explicit user review."""

        user_id, task_id, conversation_id, run_id, turn_id, analysis = self._analysis_context()
        result = analysis.propose_code_from_agent(
            user_id=user_id,
            task_id=task_id,
            label=label,
            definition=definition,
            annotation_ids=_uuid_tuple(annotation_ids),
            rationale=rationale,
            conversation_id=conversation_id,
            agent_run_id=run_id,
            agent_turn_id=turn_id,
            tool_call_id=_required_tool_call_id(tool_call_id),
        )
        return _candidate_analysis_payload(result)

    def propose_source_code(
        self, *, material_id: str, parse_id: str, segment_id: str,
        quote_start: int, quote_end: int, label: str, definition: str,
        rationale: str, tool_call_id: str,
    ) -> dict[str, object]:
        """Create a pending interpretation directly from an authorized source span."""
        user_id, task_id, conversation_id, run_id, turn_id, analysis = self._analysis_context()
        result = analysis.propose_source_code_from_agent(
            user_id=user_id, task_id=task_id, material_id=UUID(material_id), parse_id=UUID(parse_id),
            segment_id=segment_id, quote_start=quote_start, quote_end=quote_end,
            label=label, definition=definition, rationale=rationale,
            conversation_id=conversation_id, agent_run_id=run_id, agent_turn_id=turn_id,
            tool_call_id=_required_tool_call_id(tool_call_id),
        )
        return _candidate_analysis_payload(result)

    def propose_analysis_memo(
        self,
        *,
        title: str,
        content: str,
        memo_kind: str,
        annotation_ids: Sequence[str],
        code_ids: Sequence[str],
        tool_call_id: str,
    ) -> dict[str, object]:
        """Persist an Agent-authored memo candidate for explicit user review."""

        user_id, task_id, conversation_id, run_id, turn_id, analysis = self._analysis_context()
        result = analysis.propose_memo_from_agent(
            user_id=user_id,
            task_id=task_id,
            title=title,
            content=content,
            memo_kind=memo_kind,
            annotation_ids=_uuid_tuple(annotation_ids),
            code_ids=_uuid_tuple(code_ids),
            conversation_id=conversation_id,
            agent_run_id=run_id,
            agent_turn_id=turn_id,
            tool_call_id=_required_tool_call_id(tool_call_id),
        )
        return _candidate_analysis_payload(result)

    def propose_coding_plan(
        self,
        *,
        title: str,
        rationale: str,
        items: Sequence[Mapping[str, object]],
        tool_call_id: str,
    ) -> dict[str, object]:
        """Persist an Agent plan; every item remains pending user review."""

        user_id, task_id, conversation_id, run_id, turn_id, analysis = self._analysis_context()
        result = analysis.propose_coding_plan_from_agent(
            user_id=user_id,
            task_id=task_id,
            title=title,
            rationale=rationale,
            items=tuple(items),
            conversation_id=conversation_id,
            agent_run_id=run_id,
            agent_turn_id=turn_id,
            tool_call_id=_required_tool_call_id(tool_call_id),
        )
        return _candidate_analysis_payload(result)

    def retrieve_coded_segments(
        self,
        *,
        code_ids: Sequence[str] = (),
        material_id: str | None = None,
        query: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, object]] | dict[str, object]:
        """Return confirmed code assignments with original source anchors."""

        user_id, task_id, _, _, _, analysis = self._analysis_context()
        parsed_material = UUID(material_id) if material_id else None
        result = analysis.retrieve_coded_segments(
            user_id=user_id,
            task_id=task_id,
            code_ids=_uuid_tuple(code_ids),
            material_id=parsed_material,
            query=query,
            limit=limit,
        )
        payload = _json_safe(result)
        if not isinstance(payload, list):
            raise TypeError("retrieved coding segments must be a list")
        return payload

    def get_research_comparison_context(
        self,
        *,
        case_labels: Sequence[str],
        time_labels: Sequence[str] = (),
    ) -> dict[str, object]:
        """Read the bounded cross-case/time context without changing analysis."""

        user_id, task_id, _, _, _, analysis = self._analysis_context()
        result = analysis.get_comparison_context_for_agent(
            user_id=user_id,
            task_id=task_id,
            case_labels=_required_text_tuple(case_labels, "case label"),
            time_labels=_required_text_tuple(
                time_labels,
                "time label",
                allow_empty=True,
            ),
        )
        payload = _json_safe(result)
        if not isinstance(payload, dict):
            raise TypeError("research comparison context must be an object")
        return payload

    def propose_case_comparison(
        self,
        *,
        title: str,
        question: str,
        case_labels: Sequence[str],
        time_labels: Sequence[str],
        findings: Sequence[Mapping[str, object]],
        competing_explanations: Sequence[str],
        evidence_gaps: Sequence[str],
        next_steps: Sequence[Mapping[str, object]],
        theory_implication: str,
        tool_call_id: str,
    ) -> dict[str, object]:
        """Persist an Agent-authored comparison candidate for user review."""

        user_id, task_id, conversation_id, run_id, turn_id, analysis = self._analysis_context()
        result = analysis.propose_comparison_from_agent(
            user_id=user_id,
            task_id=task_id,
            title=title,
            question=question,
            case_labels=_required_text_tuple(case_labels, "case label"),
            time_labels=_required_text_tuple(
                time_labels,
                "time label",
                allow_empty=True,
            ),
            findings=tuple(_comparison_finding(item) for item in findings),
            competing_explanations=_required_text_tuple(
                competing_explanations,
                "competing explanation",
                allow_empty=True,
            ),
            evidence_gaps=_required_text_tuple(
                evidence_gaps,
                "evidence gap",
                allow_empty=True,
            ),
            next_steps=tuple(_next_research_step(item) for item in next_steps),
            theory_implication=theory_implication,
            conversation_id=conversation_id,
            agent_run_id=run_id,
            agent_turn_id=turn_id,
            tool_call_id=_required_tool_call_id(tool_call_id),
        )
        return _candidate_analysis_payload(result)

    def _refresh_analysis_tools_enabled(self) -> None:
        self.research_analysis_tools_enabled = bool(
            self._analysis is not None
            and self._materials is not None
            and self.research_material_tools_enabled
            and self._user_id is not None
            and self._task_id is not None
            and self._conversation_id is not None
            and self._agent_run_id is not None
            and self._agent_turn_id is not None
        )

    def _analysis_context(
        self,
    ) -> tuple[
        UUID,
        UUID,
        UUID,
        UUID,
        UUID,
        ResearchAnalysisAgentFacade,
    ]:
        if (
            not self.research_analysis_tools_enabled
            or self._analysis is None
            or self._user_id is None
            or self._task_id is None
            or self._conversation_id is None
            or self._agent_run_id is None
            or self._agent_turn_id is None
        ):
            raise RuntimeError(
                "research analysis tools require material context and a persisted Agent turn"
            )
        return (
            self._user_id,
            self._task_id,
            self._conversation_id,
            self._agent_run_id,
            self._agent_turn_id,
            self._analysis,
        )

    def search_research_materials(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> list[dict[str, object]] | dict[str, object]:
        """Search the current task's readable material blocks.

        Authorization is applied before retrieval: deleted materials, stale
        parse versions, and blocks from another user/task never enter the
        candidate set.  The shared ``HybridRetriever.search_chunks`` method is
        used when configured; a deterministic lexical fallback keeps the
        zero-config local runner useful without introducing another index.
        """

        context = self._material_context()
        if context is None:
            return {
                "error": "research_material_context_missing",
                "message": "当前 Agent 没有绑定研究任务，无法检索个人研究材料。",
            }
        user_id, task_id, materials = context
        normalized_query = str(query or "").strip()
        if not normalized_query:
            return []
        safe_limit = max(1, min(int(limit), 50))
        chunks: list[object] = []
        metadata: dict[str, tuple[ResearchMaterial, MaterialBlock]] = {}
        try:
            rows = materials.list(
                user_id=user_id,
                task_id=task_id,
                include_deleted=False,
                limit=500,
                offset=0,
            )
        except TypeError:
            # Keep compatibility with narrow test doubles and older adapters;
            # ownership is still supplied to every subsequent read.
            rows = materials.list(user_id=user_id, task_id=task_id)

        allowed_materials: dict[UUID, ResearchMaterial] = {}
        for material in rows:
            scoped_parse_id = (
                self._material_scope.get(material.material_id)
                if self._material_scope is not None
                else None
            )
            if self._material_scope is not None:
                if scoped_parse_id is None:
                    continue
                scoped_parse = materials.get_parse(
                    material.material_id,
                    scoped_parse_id,
                    user_id=user_id,
                    task_id=task_id,
                )
                if scoped_parse is None or scoped_parse.status is not MaterialStatus.READY:
                    continue
            elif material.status is not MaterialStatus.READY or material.current_parse_id is None:
                continue
            if self._material_allows_external_model(
                materials,
                material.material_id,
                user_id=user_id,
                task_id=task_id,
            ):
                allowed_materials[material.material_id] = material
        if self._material_search is not None:
            if not allowed_materials:
                return []
            material_parse_ids = (
                tuple(
                    (material_id, parse_id)
                    for material_id, parse_id in self._material_scope.items()
                    if material_id in allowed_materials
                )
                if self._material_scope is not None
                else ()
            )
            result = self._material_search.search(
                user_id=user_id,
                task_id=task_id,
                query=normalized_query,
                material_ids=(
                    () if material_parse_ids else tuple(allowed_materials)
                ),
                material_parse_ids=material_parse_ids,
                limit=safe_limit,
                offset=0,
            )
            values: list[dict[str, object]] = []
            for hit in result.items:
                if hit.material_id not in allowed_materials:
                    continue
                citation_id = _material_citation_id(hit.material_id, hit.segment_id)
                source_id = f"material-segment:{hit.segment_id}"
                evidence = AgentEvidence(
                    citation_id=citation_id,
                    label=hit.title,
                    kind="research_material",
                    excerpt=hit.excerpt,
                    source_id=source_id,
                    source_kind="personal_material",
                    material_id=str(hit.material_id),
                    parse_id=str(hit.parse_id),
                    segment_id=hit.segment_id,
                    locator=hit.locator.as_dict(),
                )
                self.evidence[citation_id] = evidence
                values.append(
                    {
                        "citation_id": citation_id,
                        "source_id": source_id,
                        "source_kind": "personal_material",
                        "kind": "research_material",
                        "material_id": str(hit.material_id),
                        "parse_id": str(hit.parse_id),
                        "segment_id": hit.segment_id,
                        "title": hit.title,
                        "material_kind": hit.material_kind.value,
                        "material_format": hit.material_format.value,
                        "excerpt": hit.excerpt,
                        "locator": hit.locator.as_dict(),
                        "retrieval_index_id": "research-material-fts5",
                        "retrieval_mode": "fts5",
                        "retrieval_sources": ["lexical"],
                        "rerank_score": hit.score,
                        "embedding_model": None,
                        "reranker_model": None,
                        "evidence_status": "verified",
                    }
                )
            return values

        for material in rows:
            scoped_parse_id = (
                self._material_scope.get(material.material_id)
                if self._material_scope is not None
                else None
            )
            if self._material_scope is not None and scoped_parse_id is None:
                continue
            resolved_parse_id = scoped_parse_id or material.current_parse_id
            if resolved_parse_id is None or (
                self._material_scope is None and material.status is not MaterialStatus.READY
            ):
                continue
            if not self._material_allows_external_model(
                materials,
                material.material_id,
                user_id=user_id,
                task_id=task_id,
            ):
                continue
            parsed = materials.get_parse(
                material.material_id,
                resolved_parse_id,
                user_id=user_id,
                task_id=task_id,
            )
            if parsed is None or parsed.status is not MaterialStatus.READY:
                continue
            for block in parsed.blocks:
                if block.material_id != material.material_id or block.parse_id != parsed.parse_id:
                    continue
                chunk_id = _material_chunk_id(material.material_id, block.segment_id)
                chunk = _material_retrieval_chunk(material, parsed, block, chunk_id)
                chunks.append(chunk)
                metadata[chunk_id] = (material, block)

        if not chunks:
            return []
        result = self._search_material_chunks(
            query=normalized_query,
            chunks=chunks,
            limit=safe_limit,
            task_id=task_id,
        )
        values: list[dict[str, object]] = []
        for hit in result.hits:
            item = metadata.get(hit.chunk.chunk_id)
            if item is None:
                # A custom retriever must not be able to smuggle an
                # unauthorized chunk into the answer.
                continue
            material, block = item
            citation_id = _material_citation_id(material.material_id, block.segment_id)
            source_id = f"material-segment:{block.segment_id}"
            evidence = AgentEvidence(
                citation_id=citation_id,
                label=material.display_name or material.original_filename,
                kind="research_material",
                excerpt=block.text,
                source_id=source_id,
                source_kind="personal_material",
                material_id=str(material.material_id),
                parse_id=str(block.parse_id),
                segment_id=block.segment_id,
                locator=block.locator.as_dict(),
            )
            self.evidence[citation_id] = evidence
            values.append(
                {
                    "citation_id": citation_id,
                    "source_id": source_id,
                    "source_kind": "personal_material",
                    "kind": "research_material",
                    "material_id": str(material.material_id),
                    "parse_id": str(block.parse_id),
                    "segment_id": block.segment_id,
                    "title": material.display_name or material.original_filename,
                    "material_kind": material.material_kind.value,
                    "material_format": material.material_format.value,
                    "excerpt": block.text,
                    "locator": block.locator.as_dict(),
                    "retrieval_index_id": result.retrieval_index_id,
                    "retrieval_mode": result.mode,
                    "retrieval_sources": list(hit.retrieval_sources),
                    "rerank_score": hit.rerank_score,
                    "embedding_model": result.embedding_model,
                    "reranker_model": result.reranker_model,
                    "evidence_status": "verified",
                }
            )
        return values

    def read_research_material_context(
        self,
        material_id: str,
        segment_id: str,
        *,
        parse_id: str | None = None,
        before: int = 2,
        after: int = 2,
    ) -> dict[str, object]:
        """Read a target segment with bounded neighboring source blocks.

        A citation may point at an immutable parse that is no longer current.
        Callers should pass its ``parse_id`` when reopening that citation;
        omitting it intentionally resolves only the material's current parse.
        """

        context = self._material_context()
        if context is None:
            return {
                "error": "research_material_context_missing",
                "message": "当前 Agent 没有绑定研究任务，无法读取个人研究材料。",
            }
        user_id, task_id, materials = context
        try:
            parsed_material_id = UUID(material_id)
        except ValueError:
            return {"error": "research_material_not_found", "material_id": material_id}
        scoped_parse_id = (
            self._material_scope.get(parsed_material_id)
            if self._material_scope is not None
            else None
        )
        if self._material_scope is not None and scoped_parse_id is None:
            return {
                "error": "research_material_outside_turn_scope",
                "material_id": material_id,
            }
        material = materials.get(
            parsed_material_id,
            user_id=user_id,
            task_id=task_id,
        )
        if material is None or (
            scoped_parse_id is None and material.status is not MaterialStatus.READY
        ):
            return {"error": "research_material_not_found", "material_id": material_id}
        if not self._material_allows_external_model(
            materials,
            parsed_material_id,
            user_id=user_id,
            task_id=task_id,
        ):
            return {
                "error": "research_material_model_processing_restricted",
                "material_id": material_id,
                "message": "该材料仅可手动阅读，未进入外部模型上下文。",
            }
        if scoped_parse_id is None and material.current_parse_id is None and parse_id is None:
            return {"error": "research_material_not_found", "material_id": material_id}
        resolved_parse_id: UUID
        if scoped_parse_id is not None:
            if parse_id is not None and parse_id != str(scoped_parse_id):
                return {
                    "error": "research_material_outside_turn_scope",
                    "material_id": material_id,
                    "parse_id": parse_id,
                }
            resolved_parse_id = scoped_parse_id
        elif parse_id is None:
            # ``current_parse_id`` was checked above; keeping this branch
            # explicit makes the historical-parse path impossible to mistake
            # for a nullable UUID.
            assert material.current_parse_id is not None
            resolved_parse_id = material.current_parse_id
        else:
            try:
                resolved_parse_id = UUID(parse_id)
            except ValueError:
                return {
                    "error": "research_material_not_found",
                    "material_id": material_id,
                    "parse_id": parse_id,
                }
        parsed = materials.get_parse(
            parsed_material_id,
            resolved_parse_id,
            user_id=user_id,
            task_id=task_id,
        )
        if parsed is None or parsed.status is not MaterialStatus.READY:
            return {
                "error": "research_material_not_found",
                "material_id": material_id,
                "parse_id": parse_id,
            }
        target_index = next(
            (index for index, block in enumerate(parsed.blocks) if block.segment_id == segment_id),
            None,
        )
        if target_index is None:
            return {
                "error": "research_material_not_found",
                "material_id": material_id,
                "segment_id": segment_id,
            }
        target = parsed.blocks[target_index]
        bounded_before = max(0, min(int(before), 4))
        bounded_after = max(0, min(int(after), 4))
        start = max(0, target_index - bounded_before)
        end = min(len(parsed.blocks), target_index + bounded_after + 1)
        context_items = [
            _material_context_item(block, is_target=index == target_index)
            for index, block in enumerate(parsed.blocks[start:end], start=start)
        ]
        citation_id = _material_citation_id(material.material_id, target.segment_id)
        self.evidence[citation_id] = AgentEvidence(
            citation_id=citation_id,
            label=material.display_name or material.original_filename,
            kind="research_material",
            excerpt=target.text,
            source_id=f"material-segment:{target.segment_id}",
            source_kind="personal_material",
            material_id=str(material.material_id),
            parse_id=str(target.parse_id),
            segment_id=target.segment_id,
            locator=target.locator.as_dict(),
        )
        return {
            "citation_id": citation_id,
            "source_id": f"material-segment:{target.segment_id}",
            "source_kind": "personal_material",
            "kind": "research_material",
            "material_id": str(material.material_id),
            "parse_id": str(target.parse_id),
            "segment_id": target.segment_id,
            "title": material.display_name or material.original_filename,
            "material_kind": material.material_kind.value,
            "material_format": material.material_format.value,
            "text": target.text,
            "excerpt": target.text,
            "locator": target.locator.as_dict(),
            "context": context_items,
            "evidence_status": "verified",
        }

    def _material_context(
        self,
    ) -> tuple[UUID, UUID, ResearchMaterialReader] | None:
        if (
            self._materials is None
            or self._user_id is None
            or self._task_id is None
            or not self.research_material_tools_enabled
        ):
            return None
        return self._user_id, self._task_id, self._materials

    @staticmethod
    def _material_allows_external_model(
        materials: ResearchMaterialReader,
        material_id: UUID,
        *,
        user_id: UUID,
        task_id: UUID,
    ) -> bool:
        policy = getattr(materials, "is_external_model_processable", None)
        if not callable(policy):
            # Narrow test doubles and legacy adapters predate the professional
            # profile. Production SQLite exposes the policy method.
            return True
        return bool(policy(material_id, user_id=user_id, task_id=task_id))

    def _search_material_chunks(
        self,
        *,
        query: str,
        chunks: Sequence[object],
        limit: int,
        task_id: UUID,
    ):
        search_chunks = getattr(self._retriever, "search_chunks", None)
        if callable(search_chunks):
            return search_chunks(
                query=query,
                chunks=tuple(chunks),
                limit=limit,
            )
        # Test/local retrievers that predate the shared transient-chunk method
        # still receive deterministic lexical ranking; production configured
        # HybridRetriever always takes the branch above.
        from qunxue_api.adapters.research_agent.retrieval import lexical_relevance_score
        from qunxue_api.adapters.retrieval.hybrid import (
            HybridRetrievalHit,
            HybridRetrievalResult,
        )

        ranked = sorted(
            [
                (
                    lexical_relevance_score(query, title=chunk.title, text=chunk.text),
                    chunk,
                )
                for chunk in chunks
            ],
            key=lambda item: (-item[0], item[1].chunk_id),
        )
        selected = [item for score, item in ranked if score > 0][:limit]
        return HybridRetrievalResult(
            retrieval_index_id=f"research-materials:{task_id}",
            mode="lexical",
            embedding_model="not_configured",
            reranker_model=None,
            degraded_reason="shared_retriever_unavailable",
            hits=tuple(
                HybridRetrievalHit(
                    chunk=item,
                    fused_score=0.0,
                    retrieval_sources=("lexical",),
                    rerank_score=None,
                )
                for item in selected
            ),
        )

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
        can_prepare = getattr(self._workflow, "can_prepare_start_proposal", None)
        if self._task_id is not None and not (
            callable(can_prepare) and can_prepare(user_id=user_id, conversation_id=conversation_id)
        ):
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
                section=replace(
                    target,
                    content=replacement_content,
                    status=ResearchDocumentSectionStatus.DRAFT,
                    evidence_refs=(),
                ),
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


def _material_chunk_id(material_id: UUID, segment_id: str) -> str:
    return f"material-segment:{material_id}:{segment_id}"


def _material_citation_id(material_id: UUID, segment_id: str) -> str:
    return f"material:{material_id}:{segment_id}"


def _material_retrieval_chunk(
    material: ResearchMaterial,
    parsed: MaterialParseVersion,
    block: MaterialBlock,
    chunk_id: str,
):
    # Keep the retrieval adapter's stable shape.  Material identity and
    # locator stay in registry metadata/evidence rather than a second index
    # schema.
    from qunxue_api.adapters.retrieval import RetrievalChunk

    return RetrievalChunk(
        chunk_id=chunk_id,
        document_kind="research_material",
        knowledge_id=None,
        theory_id=None,
        content_version=parsed.version,
        content_hash=block.content_hash,
        title=material.display_name or material.original_filename,
        text=block.text,
        source_ids=(f"material-segment:{block.segment_id}",),
    )


def _material_context_item(block: MaterialBlock, *, is_target: bool) -> dict[str, object]:
    return {
        "segment_id": block.segment_id,
        "parse_id": str(block.parse_id),
        "ordinal": block.ordinal,
        "kind": block.kind,
        "text": block.text,
        "locator": block.locator.as_dict(),
        "is_target": is_target,
    }


def _uuid_tuple(values: Sequence[str]) -> tuple[UUID, ...]:
    return tuple(dict.fromkeys(UUID(str(value)) for value in values))


def _required_text_tuple(
    values: Sequence[str],
    name: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))
    if not normalized and not allow_empty:
        raise ValueError(f"{name} is required")
    return normalized


def _comparison_finding(value: Mapping[str, object]) -> ComparisonFinding:
    annotation_ids = value.get("annotation_ids", ())
    if not isinstance(annotation_ids, Sequence) or isinstance(
        annotation_ids, (str, bytes, bytearray)
    ):
        raise ValueError("comparison finding annotation_ids must be a list")
    return ComparisonFinding(
        kind=ComparisonFindingKind(str(value.get("kind", ""))),
        statement=str(value.get("statement", "")),
        annotation_ids=_uuid_tuple(tuple(str(item) for item in annotation_ids)),
    )


def _next_research_step(value: Mapping[str, object]) -> NextResearchStep:
    return NextResearchStep(
        kind=str(value.get("kind", "")),
        action=str(value.get("action", "")),
        priority=str(value.get("priority", "medium")),
    )


def _required_tool_call_id(value: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError("tool_call_id is required for an analysis candidate")
    return normalized


def _candidate_analysis_payload(value: object) -> dict[str, object]:
    payload = _json_safe(value)
    if not isinstance(payload, dict):
        raise TypeError("research analysis candidate must be an object")
    payload["status"] = "candidate"
    payload["requires_user_confirmation"] = True
    return payload


def _json_safe(value: object) -> object:
    """Serialize domain records for model tools without coupling to one DTO."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _json_safe(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    raise TypeError(f"unsupported research analysis payload: {type(value).__name__}")


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


def _confirmed_plan_payload(plan: ConfirmedTheoryPlanSnapshot) -> dict[str, object]:
    candidate_titles = {item.candidate_id: item.content.title for item in plan.candidates}
    return {
        "theory_plan_id": str(plan.theory_plan_id),
        "version": plan.version,
        "confirmed_at": _serialized(plan.confirmed_at),
        "phenomenon": {
            "phenomenon_query_id": str(plan.phenomenon.phenomenon_query_id),
            "version": plan.phenomenon.version,
            "phenomenon": plan.phenomenon.phenomenon,
            "research_intent": plan.phenomenon.research_intent,
            "context": plan.phenomenon.context,
            "content_hash": plan.phenomenon.content_hash,
            "evidence": [
                {
                    "evidence_ref_id": item.evidence_ref_id,
                    "excerpt": item.excerpt,
                    "source_ref_id": item.source_ref_id,
                    "source_description": item.source_description,
                    "locator": item.locator,
                    "verification_status": _serialized(item.verification_status),
                    "use_boundary": item.use_boundary,
                }
                for item in plan.phenomenon.evidence_refs
            ],
        },
        "knowledge_release": {
            "knowledge_release_id": plan.knowledge_release.knowledge_release_id,
            "level": _serialized(plan.knowledge_release.level),
            "content_hash": plan.knowledge_release.content_hash,
        },
        "candidates": [
            {
                "candidate_id": str(item.candidate_id),
                "candidate_version": item.candidate_version,
                "theory_id": item.content.theory_id,
                "title": item.content.title,
                "origin": _serialized(item.content.origin),
                "problem_focus": item.content.problem_focus,
                "core_claims": list(item.content.core_claims),
                "analysis_levels": list(item.content.analysis_levels),
                "source_ids": list(item.content.source_ids),
                "verdict": _serialized(item.judgement.verdict),
                "match_rationale": item.judgement.match_rationale,
                "applicable_conditions": list(item.judgement.applicable_conditions),
                "limitations": list(item.judgement.limitations),
                "material_requirements": list(item.judgement.material_requirements),
                "evidence_gaps": list(item.judgement.evidence_gaps),
                "alternative_explanations": list(item.judgement.alternative_explanations),
                "evidence_ref_ids": list(item.judgement.evidence_ref_ids),
            }
            for item in plan.candidates
        ],
        "decisions": [
            {
                "candidate_id": str(item.candidate_id),
                "candidate_title": candidate_titles.get(item.candidate_id),
                "candidate_version": item.candidate_version,
                "action": _serialized(item.action),
                "reason": item.reason,
                "related_source_ids": list(item.related_source_ids),
                "revised_applicability": item.revised_applicability,
                "related_candidate_ids": [str(value) for value in item.related_candidate_ids],
            }
            for item in plan.decisions
        ],
        "use_assignments": [
            {
                "candidate_id": str(item.candidate_id),
                "candidate_title": candidate_titles.get(item.candidate_id),
                "role_code": item.role_code,
                "responsibility": item.responsibility,
            }
            for item in plan.use_assignments
        ],
        "relations": [
            {
                "relation_id": str(item.relation_id),
                "candidate_ids": [str(value) for value in item.candidate_ids],
                "candidate_titles": [candidate_titles.get(value) for value in item.candidate_ids],
                "relation_kind": item.relation_kind,
                "explanation": item.explanation,
                "premise_compatibility": item.premise_compatibility,
                "supporting_evidence": list(item.supporting_evidence),
                "excluding_evidence": list(item.excluding_evidence),
                "distinguishing_evidence": list(item.distinguishing_evidence),
            }
            for item in plan.relations
        ],
        "evidence": [
            {
                "evidence_ref_id": item.evidence_ref_id,
                "claim": item.claim,
                "excerpt": item.excerpt,
                "locator": item.locator,
                "verification_status": _serialized(item.verification_status),
                "use_boundary": item.use_boundary,
                "source": _source_payload(item.source),
            }
            for item in plan.evidence_bundle.evidence_items
        ],
        "generation_rule": (
            "Use this confirmed snapshot as immutable input. Propose a complete M5 draft, "
            "preserve uncertainty and evidence gaps, and never overwrite formal content "
            "without explicit user acceptance."
        ),
    }


def _source_payload(source) -> dict[str, object] | None:
    if source is None:
        return None
    return {
        "source_id": source.source_id,
        "source_type": source.source_type,
        "title": source.title,
        "authors_or_institution": list(source.authors_or_institution),
        "year": source.year,
        "publication": source.publication,
        "locator": source.locator,
        "url": source.url,
        "verification_status": _serialized(source.verification_status),
        "use_boundary": source.use_boundary,
    }


def _serialized(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    enum_value = getattr(value, "value", None)
    return enum_value if enum_value is not None else value


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
