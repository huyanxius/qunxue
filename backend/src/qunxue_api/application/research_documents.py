import json
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID

from qunxue_api.application.research_document_mutations import (
    ResearchDocumentMutationReceipt,
    ResearchDocumentMutationRepository,
    mutation_request_hash,
)
from qunxue_api.modules.research_framework import (
    ResearchDocumentCompletionCheck,
    ResearchDocumentCompletionGate,
    ResearchDocumentMarkdownExport,
    ResearchDocumentProposalSnapshot,
    ResearchDocumentProposalStatus,
    ResearchDocumentSection,
    ResearchDocumentService,
    ResearchDocumentSnapshot,
)
from qunxue_api.modules.research_intake import (
    ResearchTask,
    ResearchTaskRepository,
    ResearchTaskStatus,
)
from qunxue_api.modules.theory_matching import (
    ConfirmedTheoryPlanSnapshot,
    MatchRunSnapshot,
)


@dataclass(frozen=True, slots=True)
class ResearchDocumentDeliveryExport:
    document_id: UUID
    task_id: UUID
    theory_plan_id: UUID
    knowledge_release_id: str
    version: int
    filename: str
    media_type: str
    markdown: str
    manifest: dict[str, object]


class ResearchDocumentApplication:
    def __init__(
        self,
        *,
        documents: ResearchDocumentService,
        research_tasks: ResearchTaskRepository,
        mutations: ResearchDocumentMutationRepository,
        get_theory_plan: Callable[[UUID], ConfirmedTheoryPlanSnapshot | None],
        get_match_run: Callable[[UUID], MatchRunSnapshot | None],
        list_proposals_for_task: Callable[
            [UUID], tuple[ResearchDocumentProposalSnapshot, ...]
        ],
        list_actionable_proposals_for_task: Callable[
            [UUID], tuple[ResearchDocumentProposalSnapshot, ...]
        ],
        owns_match_run: Callable[..., bool],
    ) -> None:
        self._documents = documents
        self._research_tasks = research_tasks
        self._mutations = mutations
        self._get_theory_plan = get_theory_plan
        self._get_match_run = get_match_run
        self._list_proposals_for_task = list_proposals_for_task
        self._list_actionable_proposals_for_task = (
            list_actionable_proposals_for_task
        )
        self._owns_match_run = owns_match_run

    def create(
        self,
        *,
        user_id: UUID,
        task: ResearchTask,
        theory_plan_id: UUID,
        title: str,
        sections: tuple[ResearchDocumentSection, ...],
        idempotency_key: str,
    ) -> ResearchDocumentSnapshot:
        receipt = self._mutations.claim(
            user_id=user_id,
            idempotency_key=idempotency_key,
            operation=f"create_document:{task.task_id}",
            request_hash=mutation_request_hash(
                {
                    "theory_plan_id": str(theory_plan_id),
                    "title": title,
                    "sections": _sections_payload(sections),
                }
            ),
        )
        replayed = self._replayed_document(receipt)
        if replayed is not None:
            return replayed
        with self._mutation_scope(receipt):
            theory_plan = self._get_theory_plan(theory_plan_id)
            if theory_plan is None or theory_plan.task_id != task.task_id:
                raise LookupError(theory_plan_id)
            if not self._owns_match_run(
                user_id=user_id, match_run_id=theory_plan.match_run_id
            ):
                raise LookupError(theory_plan_id)
            self._validate_evidence_refs(sections, theory_plan=theory_plan)
            snapshot = self._documents.create(
                task_id=task.task_id,
                theory_plan_id=theory_plan.theory_plan_id,
                knowledge_release_id=theory_plan.knowledge_release.knowledge_release_id,
                title=title,
                sections=sections,
                actor="user",
            )
            if task.current_framework_id != snapshot.document_id:
                saved_task = self._research_tasks.save_progress(
                    replace(
                        task,
                        status=ResearchTaskStatus.FRAMEWORK_DRAFT,
                        version=task.version + 1,
                        updated_at=datetime.now(UTC),
                        current_framework_id=snapshot.document_id,
                    )
                )
                if saved_task is None:
                    latest_task = self._research_tasks.get(task.task_id, user_id)
                    if (
                        latest_task is None
                        or latest_task.current_framework_id != snapshot.document_id
                    ):
                        raise ValueError("research task changed while creating document")
            self._mutations.complete(
                request_id=receipt.request_id,
                result_id=snapshot.document_id,
                result_version=snapshot.version,
            )
            return snapshot

    def get(
        self, *, user_id: UUID, document_id: UUID, version: int | None = None
    ) -> ResearchDocumentSnapshot:
        snapshot = self._documents.get(document_id, version=version)
        self._require_owner(snapshot, user_id=user_id)
        return snapshot

    def list_versions(
        self, *, user_id: UUID, document_id: UUID
    ) -> tuple[ResearchDocumentSnapshot, ...]:
        versions = self._documents.list_versions(document_id)
        self._require_owner(versions[0], user_id=user_id)
        return versions

    def list_for_task(
        self, *, user_id: UUID, task: ResearchTask
    ) -> tuple[ResearchDocumentSnapshot, ...]:
        if task.user_id != user_id:
            raise LookupError(task.task_id)
        return self._documents.list_for_task(task.task_id)

    def validate_proposal(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        theory_plan_id: UUID,
        knowledge_release_id: str,
        sections: tuple[ResearchDocumentSection, ...],
    ) -> None:
        theory_plan = self._get_theory_plan(theory_plan_id)
        if (
            theory_plan is None
            or theory_plan.task_id != task_id
            or theory_plan.knowledge_release.knowledge_release_id != knowledge_release_id
            or not self._owns_match_run(
                user_id=user_id,
                match_run_id=theory_plan.match_run_id,
            )
        ):
            raise LookupError(theory_plan_id)
        self._validate_evidence_refs(sections, theory_plan=theory_plan)

    def get_theory_plan_for_agent(
        self, *, user_id: UUID, theory_plan_id: UUID
    ) -> ConfirmedTheoryPlanSnapshot:
        """Return the immutable M4 handoff only after checking task ownership."""

        theory_plan = self._required_theory_plan(theory_plan_id)
        if (
            self._research_tasks.get(theory_plan.task_id, user_id) is None
            or not self._owns_match_run(
                user_id=user_id,
                match_run_id=theory_plan.match_run_id,
            )
        ):
            raise LookupError(theory_plan_id)
        return theory_plan

    def revise(
        self,
        *,
        user_id: UUID,
        document_id: UUID,
        expected_version: int,
        sections: tuple[ResearchDocumentSection, ...],
        change_summary: str,
        actor: str,
        idempotency_key: str,
    ) -> ResearchDocumentSnapshot:
        receipt = self._mutations.claim(
            user_id=user_id,
            idempotency_key=idempotency_key,
            operation=f"revise_document:{document_id}",
            request_hash=mutation_request_hash(
                {
                    "expected_version": expected_version,
                    "sections": _sections_payload(sections),
                    "change_summary": change_summary,
                    "actor": actor,
                }
            ),
        )
        replayed = self._replayed_document(receipt)
        if replayed is not None:
            return replayed
        with self._mutation_scope(receipt):
            current = self.get(user_id=user_id, document_id=document_id)
            self._require_current_document(current, user_id=user_id)
            theory_plan = self._required_theory_plan(current.theory_plan_id)
            self._validate_evidence_refs(sections, theory_plan=theory_plan)
            snapshot = self._documents.revise(
                document_id=document_id,
                expected_version=expected_version,
                sections=sections,
                change_summary=change_summary,
                actor=actor,
            )
            self._mutations.complete(
                request_id=receipt.request_id,
                result_id=snapshot.document_id,
                result_version=snapshot.version,
            )
            return snapshot

    def restore(
        self,
        *,
        user_id: UUID,
        document_id: UUID,
        source_version: int,
        expected_version: int,
        reason: str,
        idempotency_key: str,
    ) -> ResearchDocumentSnapshot:
        receipt = self._mutations.claim(
            user_id=user_id,
            idempotency_key=idempotency_key,
            operation=f"restore_document:{document_id}",
            request_hash=mutation_request_hash(
                {
                    "source_version": source_version,
                    "expected_version": expected_version,
                    "reason": reason,
                }
            ),
        )
        replayed = self._replayed_document(receipt)
        if replayed is not None:
            return replayed
        with self._mutation_scope(receipt):
            current = self.get(user_id=user_id, document_id=document_id)
            self._require_current_document(current, user_id=user_id)
            restored = self._documents.restore(
                document_id=document_id,
                source_version=source_version,
                expected_version=expected_version,
                reason=reason,
            )
            task = self._research_tasks.get(current.task_id, user_id)
            if task is not None and task.status is ResearchTaskStatus.FRAMEWORK_CONFIRMED:
                saved_task = self._research_tasks.save_progress(
                    replace(
                        task,
                        status=ResearchTaskStatus.FRAMEWORK_DRAFT,
                        version=task.version + 1,
                        updated_at=datetime.now(UTC),
                    )
                )
                if saved_task is None:
                    raise ValueError("research task changed while restoring document")
            self._mutations.complete(
                request_id=receipt.request_id,
                result_id=restored.document_id,
                result_version=restored.version,
            )
            return restored

    def confirm(
        self,
        *,
        user_id: UUID,
        document_id: UUID,
        expected_version: int,
        idempotency_key: str,
    ) -> ResearchDocumentSnapshot:
        receipt = self._mutations.claim(
            user_id=user_id,
            idempotency_key=idempotency_key,
            operation=f"confirm_document:{document_id}",
            request_hash=mutation_request_hash({"expected_version": expected_version}),
        )
        replayed = self._replayed_document(receipt)
        if replayed is not None:
            return replayed
        with self._mutation_scope(receipt):
            current = self.get(user_id=user_id, document_id=document_id)
            self._require_current_document(current, user_id=user_id)
            gate = self.completion_gate(user_id=user_id, document_id=document_id)
            if not gate.ready:
                raise ValueError("completion gate blocked: " + " ".join(gate.blockers))
            theory_plan = self._required_theory_plan(current.theory_plan_id)
            self._validate_evidence_refs(current.sections, theory_plan=theory_plan)
            pending_proposal_count = self._pending_proposal_count(current)
            confirmed = self._documents.confirm(
                document_id=document_id,
                expected_version=expected_version,
                pending_proposal_count=pending_proposal_count,
            )
            task = self._research_tasks.get(current.task_id, user_id)
            if task is None:
                raise LookupError(current.task_id)
            if task.status is not ResearchTaskStatus.FRAMEWORK_CONFIRMED:
                saved_task = self._research_tasks.save_progress(
                    replace(
                        task,
                        status=ResearchTaskStatus.FRAMEWORK_CONFIRMED,
                        version=task.version + 1,
                        updated_at=datetime.now(UTC),
                        current_framework_id=confirmed.document_id,
                    )
                )
                if saved_task is None:
                    raise ValueError("research task changed while confirming document")
            self._mutations.complete(
                request_id=receipt.request_id,
                result_id=confirmed.document_id,
                result_version=confirmed.version,
            )
            return confirmed

    def completion_gate(
        self, *, user_id: UUID, document_id: UUID
    ) -> ResearchDocumentCompletionGate:
        current = self.get(user_id=user_id, document_id=document_id)
        self._require_current_document(current, user_id=user_id)
        gate = self._documents.completion_gate(
            document_id=document_id,
            pending_proposal_count=self._pending_proposal_count(current),
        )
        package_ready = False
        try:
            plan = self.get_theory_plan_for_agent(
                user_id=user_id,
                theory_plan_id=current.theory_plan_id,
            )
            match_run = self._get_match_run(plan.match_run_id)
            if match_run is None:
                raise LookupError(plan.match_run_id)
            manifest = _export_manifest(
                document=current,
                plan=plan,
                match_run=match_run,
                proposals=self._document_proposals(current),
                versions=self._documents.list_versions(document_id),
            )
            json.dumps(manifest, ensure_ascii=False, sort_keys=True)
            package_ready = True
        except (LookupError, TypeError, ValueError):
            package_ready = False
        package_blocker = "完整研究成果包暂时无法生成，请重新加载后再试。"
        return replace(
            gate,
            ready=gate.ready and package_ready,
            blockers=(
                gate.blockers if package_ready else (*gate.blockers, package_blocker)
            ),
            checks=(
                *gate.checks,
                ResearchDocumentCompletionCheck(
                    code="delivery_package",
                    label="完整成果包可生成",
                    passed=package_ready,
                    detail=(
                        "Markdown 与机器可读 manifest 均可从当前版本生成。"
                        if package_ready
                        else package_blocker
                    ),
                ),
            ),
        )

    def export_markdown(
        self, *, user_id: UUID, document_id: UUID, version: int | None
    ) -> ResearchDocumentDeliveryExport:
        requested = self.get(user_id=user_id, document_id=document_id, version=version)
        self._require_current_document(requested, user_id=user_id)
        base = self._documents.export_markdown(document_id=document_id, version=version)
        plan = self.get_theory_plan_for_agent(
            user_id=user_id,
            theory_plan_id=requested.theory_plan_id,
        )
        match_run = self._get_match_run(plan.match_run_id)
        if match_run is None:
            raise LookupError(plan.match_run_id)
        versions = self._documents.list_versions(document_id)
        proposals = self._document_proposals(requested)
        manifest = _export_manifest(
            document=requested,
            plan=plan,
            match_run=match_run,
            proposals=proposals,
            versions=versions,
        )
        return ResearchDocumentDeliveryExport(
            document_id=base.document_id,
            task_id=base.task_id,
            theory_plan_id=base.theory_plan_id,
            knowledge_release_id=base.knowledge_release_id,
            version=base.version,
            filename=base.filename,
            media_type=base.media_type,
            markdown=_export_markdown(base=base, manifest=manifest),
            manifest=manifest,
        )

    def _require_owner(self, snapshot: ResearchDocumentSnapshot, *, user_id: UUID) -> None:
        if self._research_tasks.get(snapshot.task_id, user_id) is None:
            raise LookupError(snapshot.document_id)

    def _require_current_document(
        self, snapshot: ResearchDocumentSnapshot, *, user_id: UUID
    ) -> None:
        task = self._research_tasks.get(snapshot.task_id, user_id)
        if task is None:
            raise LookupError(snapshot.document_id)
        if task.current_framework_id != snapshot.document_id:
            raise ValueError("research document is not the task's current framework")

    def _document_proposals(
        self, snapshot: ResearchDocumentSnapshot
    ) -> tuple[ResearchDocumentProposalSnapshot, ...]:
        return tuple(
            proposal
            for proposal in self._list_proposals_for_task(snapshot.task_id)
            if proposal.theory_plan_id == snapshot.theory_plan_id
        )

    def _pending_proposal_count(self, snapshot: ResearchDocumentSnapshot) -> int:
        return sum(
            proposal.status is ResearchDocumentProposalStatus.PENDING
            and proposal.theory_plan_id == snapshot.theory_plan_id
            and (
                proposal.document_id in {None, snapshot.document_id}
                or proposal.result_document_id == snapshot.document_id
            )
            for proposal in self._list_actionable_proposals_for_task(snapshot.task_id)
        )

    def _replayed_document(
        self, receipt: ResearchDocumentMutationReceipt
    ) -> ResearchDocumentSnapshot | None:
        if receipt.status != "completed":
            return None
        if receipt.result_id is None or receipt.result_version is None:
            raise RuntimeError("completed document mutation is missing its result")
        return self._documents.get(receipt.result_id, version=receipt.result_version)

    @contextmanager
    def _mutation_scope(self, receipt: ResearchDocumentMutationReceipt):
        try:
            yield
        except Exception:
            if receipt.status == "pending":
                self._mutations.fail(request_id=receipt.request_id)
            raise

    def _required_theory_plan(
        self, theory_plan_id: UUID
    ) -> ConfirmedTheoryPlanSnapshot:
        theory_plan = self._get_theory_plan(theory_plan_id)
        if theory_plan is None:
            raise LookupError(theory_plan_id)
        return theory_plan

    @staticmethod
    def _validate_evidence_refs(
        sections: tuple[ResearchDocumentSection, ...],
        *,
        theory_plan: ConfirmedTheoryPlanSnapshot,
    ) -> None:
        release_id = theory_plan.knowledge_release.knowledge_release_id
        allowed = {
            (item.evidence_ref_id, item.source.source_id)
            for item in theory_plan.evidence_bundle.evidence_items
            if item.source is not None
        }
        for section in sections:
            for evidence in section.evidence_refs:
                if evidence.knowledge_release_id != release_id:
                    raise ValueError("evidence must use the confirmed knowledge release")
                if (evidence.evidence_ref_id, evidence.source_id) not in allowed:
                    raise ValueError(
                        "evidence and source IDs must belong to the confirmed theory plan"
                    )


def _sections_payload(
    sections: tuple[ResearchDocumentSection, ...],
) -> list[dict[str, object]]:
    return [
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
        for section in sections
    ]


def _export_manifest(
    *,
    document: ResearchDocumentSnapshot,
    plan: ConfirmedTheoryPlanSnapshot,
    match_run: MatchRunSnapshot,
    proposals: tuple[ResearchDocumentProposalSnapshot, ...],
    versions: tuple[ResearchDocumentSnapshot, ...],
) -> dict[str, object]:
    phenomenon = plan.phenomenon
    model = match_run.model
    candidate_title = {
        candidate.candidate_id: candidate.content.title for candidate in match_run.candidates
    }
    return {
        "schema_version": "research-delivery-v1",
        "phenomenon": {
            "phenomenon_query_id": str(phenomenon.phenomenon_query_id),
            "version": phenomenon.version,
            "phenomenon": phenomenon.phenomenon,
            "research_intent": phenomenon.research_intent,
            "context": phenomenon.context,
            "content_hash": phenomenon.content_hash,
            "evidence_refs": [
                {
                    "evidence_ref_id": item.evidence_ref_id,
                    "excerpt": item.excerpt,
                    "source_ref_id": item.source_ref_id,
                    "source_description": item.source_description,
                    "locator": item.locator,
                    "verification_status": item.verification_status.value,
                    "use_boundary": item.use_boundary,
                }
                for item in phenomenon.evidence_refs
            ],
        },
        "knowledge_release": {
            "knowledge_release_id": plan.knowledge_release.knowledge_release_id,
            "level": plan.knowledge_release.level.value,
            "content_hash": plan.knowledge_release.content_hash,
        },
        "model": (
            {
                "provider": model.provider,
                "model_version": model.model_version,
                "capability": model.capability,
                "degraded": model.degraded,
                "knowledge_release_id": model.knowledge_release_id,
                "trace_id": str(model.trace_id),
                "request_id": str(model.request_id),
                "contract_version": model.contract_version,
            }
            if model is not None
            else None
        ),
        "theory_candidates": [
            {
                "candidate_id": str(candidate.candidate_id),
                "version": candidate.candidate_version,
                "theory_id": candidate.content.theory_id,
                "title": candidate.content.title,
                "origin": candidate.content.origin.value,
                "content_status": candidate.content.content_status.value,
                "problem_focus": candidate.content.problem_focus,
                "core_claims": list(candidate.content.core_claims),
                "analysis_levels": list(candidate.content.analysis_levels),
                "source_ids": list(candidate.content.source_ids),
                "formal_adoption_eligible": candidate.content.formal_adoption_eligible,
                "adoption_blockers": list(candidate.content.adoption_blockers),
                "verdict": candidate.judgement.verdict.value,
                "match_rationale": candidate.judgement.match_rationale,
                "applicable_conditions": list(candidate.judgement.applicable_conditions),
                "limitations": list(candidate.judgement.limitations),
                "material_requirements": list(candidate.judgement.material_requirements),
                "evidence_gaps": list(candidate.judgement.evidence_gaps),
                "alternative_explanations": list(
                    candidate.judgement.alternative_explanations
                ),
                "evidence_ref_ids": list(candidate.judgement.evidence_ref_ids),
                "trace_id": str(candidate.trace_id),
                "request_id": str(candidate.request_id),
                "contract_version": candidate.contract_version,
            }
            for candidate in match_run.candidates
        ],
        "theory_decisions": [
            {
                "decision_id": str(decision.decision_id),
                "candidate_id": str(decision.candidate_id),
                "candidate_title": candidate_title.get(decision.candidate_id),
                "candidate_version": decision.candidate_version,
                "action": decision.action.value,
                "reason": decision.reason,
                "related_source_ids": list(decision.related_source_ids),
                "revised_applicability": decision.revised_applicability,
                "related_candidate_ids": [
                    str(item) for item in decision.related_candidate_ids
                ],
                "recorded_at": decision.recorded_at.isoformat(),
            }
            for decision in plan.decisions
        ],
        "theory_assignments": [
            {
                "candidate_id": str(item.candidate_id),
                "candidate_title": candidate_title.get(item.candidate_id),
                "role_code": item.role_code,
                "responsibility": item.responsibility,
            }
            for item in plan.use_assignments
        ],
        "theory_relations": [
            {
                "relation_id": str(item.relation_id),
                "candidate_ids": [str(candidate_id) for candidate_id in item.candidate_ids],
                "candidate_titles": [
                    candidate_title.get(candidate_id) for candidate_id in item.candidate_ids
                ],
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
                "verification_status": item.verification_status.value,
                "use_boundary": item.use_boundary,
                "source": (
                    {
                        "source_id": item.source.source_id,
                        "source_type": item.source.source_type,
                        "title": item.source.title,
                        "authors_or_institution": list(
                            item.source.authors_or_institution
                        ),
                        "year": item.source.year,
                        "publication": item.source.publication,
                        "locator": item.source.locator,
                        "url": item.source.url,
                        "verification_status": item.source.verification_status.value,
                        "use_boundary": item.source.use_boundary,
                    }
                    if item.source is not None
                    else None
                ),
            }
            for item in plan.evidence_bundle.evidence_items
        ],
        "agent_proposals": [
            {
                "proposal_id": str(item.proposal_id),
                "kind": item.kind.value,
                "status": item.status.value,
                "title": item.title,
                "rationale": item.rationale,
                "document_id": str(item.document_id) if item.document_id else None,
                "base_document_version": item.base_document_version,
                "target_section_id": item.target_section_id,
                "decision_reason": item.decision_reason,
                "result_document_id": (
                    str(item.result_document_id) if item.result_document_id else None
                ),
                "result_document_version": item.result_document_version,
                "conversation_id": str(item.conversation_id),
                "agent_run_id": str(item.agent_run_id),
                "model_provider": item.model_provider,
                "model_name": item.model_name,
                "created_at": item.created_at.isoformat(),
                "decided_at": item.decided_at.isoformat() if item.decided_at else None,
                "proposed_sections": _sections_payload(item.proposed_sections),
            }
            for item in proposals
        ],
        "document_versions": [
            {
                "version": item.version,
                "revision_id": str(item.revision_id),
                "status": item.status.value,
                "change_summary": item.change_summary,
                "actor": item.actor,
                "restored_from_version": item.restored_from_version,
                "created_at": item.created_at.isoformat(),
                "confirmed_at": (
                    item.confirmed_at.isoformat() if item.confirmed_at else None
                ),
            }
            for item in versions
        ],
        "formal_document": {
            "document_id": str(document.document_id),
            "task_id": str(document.task_id),
            "theory_plan_id": str(document.theory_plan_id),
            "knowledge_release_id": document.knowledge_release_id,
            "version": document.version,
            "title": document.title,
            "status": document.status.value,
            "sections": _sections_payload(document.sections),
            "confirmed_at": (
                document.confirmed_at.isoformat() if document.confirmed_at else None
            ),
        },
    }


def _export_markdown(
    *, base: ResearchDocumentMarkdownExport, manifest: dict[str, object]
) -> str:
    phenomenon = manifest["phenomenon"]
    release = manifest["knowledge_release"]
    model = manifest["model"]
    candidates = manifest["theory_candidates"]
    decisions = manifest["theory_decisions"]
    assignments = manifest["theory_assignments"]
    relations = manifest["theory_relations"]
    evidence = manifest["evidence"]
    proposals = manifest["agent_proposals"]
    versions = manifest["document_versions"]
    formal_document = manifest["formal_document"]
    assert isinstance(phenomenon, dict)
    assert isinstance(release, dict)
    assert isinstance(formal_document, dict)
    lines = [
        "---",
        f"schema_version: {manifest['schema_version']}",
        f"document_id: {base.document_id}",
        f"version: {base.version}",
        f"knowledge_release_id: {base.knowledge_release_id}",
        "---",
        "",
        f"# {formal_document['title']}",
        "",
        "## 研究过程与来源",
        "",
        f"**已确认现象：** {phenomenon['phenomenon']}",
        f"**研究意图：** {phenomenon.get('research_intent') or '未单独说明'}",
        f"**研究语境：** {phenomenon.get('context') or '未单独说明'}",
        (
            f"**知识版本：** {release['knowledge_release_id']} "
            f"({release['level']}, hash {release['content_hash']})"
        ),
    ]
    if isinstance(model, dict):
        lines.append(
            f"**理论判断模型：** {model['provider']} / {model['model_version']} "
            f"(contract {model['contract_version']})"
        )
    lines.extend(["", "### 理论候选与用户决定", ""])
    decision_by_candidate = {
        item["candidate_id"]: item for item in decisions if isinstance(item, dict)
    }
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        decision = decision_by_candidate.get(candidate["candidate_id"])
        lines.extend(
            [
                f"#### {candidate['title']}",
                str(candidate["match_rationale"]),
                (
                    f"- 用户决定：{decision['action']}；{decision['reason']}"
                    if decision
                    else "- 用户决定：未记录"
                ),
                f"- 局限：{'；'.join(candidate['limitations']) or '未记录'}",
                "",
            ]
        )
    lines.extend(["### 理论分工与关系", ""])
    for item in assignments:
        if isinstance(item, dict):
            lines.append(
                f"- {item.get('candidate_title') or item['candidate_id']} "
                f"({item['role_code']})：{item['responsibility']}"
            )
    if not assignments:
        lines.append("- 未记录理论分工。")
    for item in relations:
        if isinstance(item, dict):
            titles = "、".join(
                str(title) for title in item["candidate_titles"] if title is not None
            )
            lines.append(
                f"- {titles or '候选理论'} · {item['relation_kind']}："
                f"{item['explanation']}"
            )
    lines.extend(["### 证据与引用", ""])
    for item in evidence:
        if not isinstance(item, dict):
            continue
        source = item.get("source")
        source_label = "来源未附着"
        if isinstance(source, dict):
            authors = "、".join(source["authors_or_institution"])
            source_label = (
                f"{source['title']} "
                f"({authors or '作者未载'}, {source['year'] or '年份未载'})"
            )
        lines.extend(
            [
                f"- **{item['claim']}** — {source_label}",
                f"  - 摘录：{item.get('excerpt') or '未附摘录'}",
                f"  - 定位：{item.get('locator') or '未附定位'}",
                f"  - 核验：{item['verification_status']}；使用边界：{item['use_boundary']}",
            ]
        )
    lines.extend(["", "## 正式研究框架", ""])
    formal_sections = formal_document.get("sections")
    if isinstance(formal_sections, list):
        for section in formal_sections:
            if not isinstance(section, dict):
                continue
            lines.extend([f"### {section['title']}", "", str(section["content"]), ""])
    lines.extend(["## 审批与版本记录", ""])
    for item in proposals:
        if isinstance(item, dict):
            lines.append(
                f"- Agent 建议「{item['title']}」：{item['status']}"
                + f"；理由：{item['rationale']}"
                + (f"；用户决定：{item['decision_reason']}" if item.get("decision_reason") else "")
            )
    for item in versions:
        if isinstance(item, dict):
            lines.append(
                f"- v{item['version']} · {item['status']} · "
                f"{item['change_summary']} · {item['actor']}"
            )
    return "\n".join(lines).strip() + "\n"
