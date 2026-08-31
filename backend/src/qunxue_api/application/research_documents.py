import json
from collections.abc import Callable
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from qunxue_api.application.research_document_mutations import (
    ResearchDocumentMutationReceipt,
    ResearchDocumentMutationRepository,
    mutation_request_hash,
)
from qunxue_api.modules.research_analysis import ResearchAnalysisHandoff
from qunxue_api.modules.research_framework import (
    ResearchDocumentCompletionCheck,
    ResearchDocumentCompletionGate,
    ResearchDocumentEvidenceSourceKind,
    ResearchDocumentFormatting,
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
from qunxue_api.modules.research_method import MethodPlanSnapshot, MethodPlanStatus
from qunxue_api.modules.theory_matching import (
    ConfirmedTheoryPlanSnapshot,
    EvidenceItemSnapshot,
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
        formal_analysis_handoff: Callable[..., ResearchAnalysisHandoff] | None = None,
        get_method_plan: Callable[[UUID], MethodPlanSnapshot | None] | None = None,
        invalidate_method_plan: Callable[[UUID, str], None] | None = None,
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
        self._formal_analysis_handoff = formal_analysis_handoff
        self._get_method_plan = get_method_plan
        self._invalidate_method_plan = invalidate_method_plan

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
            analysis_handoff = self._current_analysis_handoff(
                user_id=user_id,
                task_id=task.task_id,
            )
            self._validate_evidence_refs(
                sections,
                theory_plan=theory_plan,
                analysis_handoff=analysis_handoff,
            )
            snapshot = self._documents.create(
                task_id=task.task_id,
                theory_plan_id=theory_plan.theory_plan_id,
                knowledge_release_id=theory_plan.knowledge_release.knowledge_release_id,
                title=title,
                sections=sections,
                actor="user",
                analysis_handoff=analysis_handoff,
            )
            self._invalidate_method_plan_if_needed(
                task.task_id, "研究框架正在重建，旧方法计划需要重新确认。"
            )
            if task.current_framework_id != snapshot.document_id:
                saved_task = self._research_tasks.save_progress(
                    replace(
                        task,
                        status=ResearchTaskStatus.FRAMEWORK_DRAFT,
                        version=task.version + 1,
                        updated_at=datetime.now(UTC),
                        current_framework_id=snapshot.document_id,
                        current_method_plan_status=None,
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
        snapshot = self._get_owned_raw(
            user_id=user_id,
            document_id=document_id,
            version=version,
        )
        return self._with_live_analysis_availability(snapshot, user_id=user_id)

    def list_versions(
        self, *, user_id: UUID, document_id: UUID
    ) -> tuple[ResearchDocumentSnapshot, ...]:
        versions = self._documents.list_versions(document_id)
        self._require_owner(versions[0], user_id=user_id)
        live = self._current_analysis_handoff(
            user_id=user_id,
            task_id=versions[0].task_id,
        )
        return tuple(_with_analysis_availability(item, live) for item in versions)

    def list_for_task(
        self, *, user_id: UUID, task: ResearchTask
    ) -> tuple[ResearchDocumentSnapshot, ...]:
        if task.user_id != user_id:
            raise LookupError(task.task_id)
        live = self._current_analysis_handoff(user_id=user_id, task_id=task.task_id)
        return tuple(
            _with_analysis_availability(item, live)
            for item in self._documents.list_for_task(task.task_id)
        )

    def validate_proposal(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
        theory_plan_id: UUID,
        knowledge_release_id: str,
        sections: tuple[ResearchDocumentSection, ...],
    ) -> dict[str, object] | None:
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
        analysis_handoff = self._current_analysis_handoff(
            user_id=user_id,
            task_id=task_id,
        )
        self._validate_evidence_refs(
            sections,
            theory_plan=theory_plan,
            analysis_handoff=analysis_handoff,
        )
        return analysis_handoff

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
        formatting: ResearchDocumentFormatting | None = None,
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
                    "formatting": (
                        {
                            "template_id": formatting.template_id,
                            "csl_style_id": formatting.csl_style_id,
                            "locale": formatting.locale,
                            "custom_csl": formatting.custom_csl,
                            "custom_css": formatting.custom_css,
                        }
                        if formatting is not None
                        else None
                    ),
                }
            ),
        )
        replayed = self._replayed_document(receipt)
        if replayed is not None:
            return replayed
        with self._mutation_scope(receipt):
            current = self._get_owned_raw(
                user_id=user_id,
                document_id=document_id,
            )
            self._require_current_document(current, user_id=user_id)
            theory_plan = self._required_theory_plan(current.theory_plan_id)
            analysis_handoff = self._current_analysis_handoff(
                user_id=user_id,
                task_id=current.task_id,
            )
            self._validate_evidence_refs(
                sections,
                theory_plan=theory_plan,
                analysis_handoff=analysis_handoff,
            )
            snapshot = self._documents.revise(
                document_id=document_id,
                expected_version=expected_version,
                sections=sections,
                change_summary=change_summary,
                actor=actor,
                analysis_handoff=analysis_handoff,
                formatting=formatting,
            )
            self._invalidate_method_plan_if_needed(
                current.task_id, "研究框架版本已变化，旧方法计划需要重新确认。"
            )
            task = self._research_tasks.get(current.task_id, user_id)
            if task is None:
                raise LookupError(current.task_id)
            if (
                task.status is ResearchTaskStatus.FRAMEWORK_CONFIRMED
                or task.current_method_plan_status is not None
            ):
                saved_task = self._research_tasks.save_progress(
                    replace(
                        task,
                        status=ResearchTaskStatus.FRAMEWORK_DRAFT,
                        version=task.version + 1,
                        updated_at=datetime.now(UTC),
                        current_method_plan_status=None,
                    )
                )
                if saved_task is None:
                    raise ValueError("research task changed while revising document")
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
            # Restore is deliberately based only on the selected immutable
            # version.  Reading current analysis here would silently replace
            # the source version's handoff with newer qualitative decisions.
            current = self._get_owned_raw(
                user_id=user_id,
                document_id=document_id,
            )
            self._require_current_document(current, user_id=user_id)
            restored = self._documents.restore(
                document_id=document_id,
                source_version=source_version,
                expected_version=expected_version,
                reason=reason,
            )
            self._invalidate_method_plan_if_needed(
                current.task_id, "研究框架已恢复到新版本，旧方法计划需要重新确认。"
            )
            task = self._research_tasks.get(current.task_id, user_id)
            if task is not None and (
                task.status is ResearchTaskStatus.FRAMEWORK_CONFIRMED
                or task.current_method_plan_status is not None
            ):
                saved_task = self._research_tasks.save_progress(
                    replace(
                        task,
                        status=(
                            ResearchTaskStatus.FRAMEWORK_DRAFT
                            if task.status is ResearchTaskStatus.FRAMEWORK_CONFIRMED
                            else task.status
                        ),
                        version=task.version + 1,
                        updated_at=datetime.now(UTC),
                        current_method_plan_status=None,
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
            current = self._get_owned_raw(
                user_id=user_id,
                document_id=document_id,
            )
            self._require_current_document(current, user_id=user_id)
            gate = self.completion_gate(user_id=user_id, document_id=document_id)
            if not gate.ready:
                raise ValueError("completion gate blocked: " + " ".join(gate.blockers))
            theory_plan = self._required_theory_plan(current.theory_plan_id)
            analysis_handoff = self._current_analysis_handoff(
                user_id=user_id,
                task_id=current.task_id,
            )
            self._validate_evidence_refs(
                current.sections,
                theory_plan=theory_plan,
                analysis_handoff=analysis_handoff,
            )
            pending_proposal_count = self._pending_proposal_count(current)
            confirmed = self._documents.confirm(
                document_id=document_id,
                expected_version=expected_version,
                pending_proposal_count=pending_proposal_count,
                analysis_handoff=analysis_handoff,
            )
            self._invalidate_method_plan_if_needed(
                current.task_id, "研究框架版本已确认变化，旧方法计划需要重新确认。"
            )
            task = self._research_tasks.get(current.task_id, user_id)
            if task is None:
                raise LookupError(current.task_id)
            if (
                task.status is not ResearchTaskStatus.FRAMEWORK_CONFIRMED
                or task.current_method_plan_status is not None
            ):
                saved_task = self._research_tasks.save_progress(
                    replace(
                        task,
                        status=ResearchTaskStatus.FRAMEWORK_CONFIRMED,
                        version=task.version + 1,
                        updated_at=datetime.now(UTC),
                        current_framework_id=confirmed.document_id,
                        current_method_plan_status=None,
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
        package_blocker = "完整研究成果包暂时无法生成，请重新加载后再试。"
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
                method_plan=self._method_plan_for_export(
                    current, theory_plan=plan
                ),
            )
            method_plan = manifest.get("method_plan")
            if (
                method_plan is not None
                and method_plan.get("status") != MethodPlanStatus.CONFIRMED.value
            ):
                package_ready = False
                package_blocker = "方法计划尚未确认，确认后才能导出完整研究成果包。"
            else:
                package_ready = True
            json.dumps(manifest, ensure_ascii=False, sort_keys=True)
        except (LookupError, TypeError, ValueError):
            package_ready = False
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
        method_plan = self._method_plan_for_export(requested, theory_plan=plan)
        if method_plan is not None and method_plan.status is not MethodPlanStatus.CONFIRMED:
            raise ValueError("confirmed method plan is required before export")
        versions = self._documents.list_versions(document_id)
        proposals = self._document_proposals(requested)
        manifest = _export_manifest(
            document=requested,
            plan=plan,
            match_run=match_run,
            proposals=proposals,
            versions=versions,
            method_plan=method_plan,
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

    def _get_owned_raw(
        self,
        *,
        user_id: UUID,
        document_id: UUID,
        version: int | None = None,
    ) -> ResearchDocumentSnapshot:
        snapshot = self._documents.get(document_id, version=version)
        self._require_owner(snapshot, user_id=user_id)
        return snapshot

    def _current_analysis_handoff(
        self,
        *,
        user_id: UUID,
        task_id: UUID,
    ) -> dict[str, object] | None:
        if self._formal_analysis_handoff is None:
            return None
        handoff = self._formal_analysis_handoff(user_id=user_id, task_id=task_id)
        return _analysis_handoff_payload(handoff, expected_task_id=task_id)

    def _method_plan_for_export(
        self,
        document: ResearchDocumentSnapshot,
        *,
        theory_plan: ConfirmedTheoryPlanSnapshot,
    ) -> MethodPlanSnapshot | None:
        """Resolve the plan pinned to the exact framework/theory being exported.

        A callback is optional to keep historical document readers compatible,
        but when configured it must return a plan belonging to this task and
        the same immutable framework and theory versions.  Otherwise an
        unrelated or outdated method decision could be presented as part of a
        formal M5 package.
        """

        if self._get_method_plan is None:
            return None
        method_plan = self._get_method_plan(document.task_id)
        if method_plan is None:
            return None
        if (
            method_plan.task_id != document.task_id
            or method_plan.framework_id != document.document_id
            or method_plan.framework_version != document.version
            or method_plan.theory_plan_id != theory_plan.theory_plan_id
            or method_plan.theory_plan_version != theory_plan.version
        ):
            raise ValueError("method plan does not match the exported framework and theory")
        return method_plan

    def _with_live_analysis_availability(
        self,
        snapshot: ResearchDocumentSnapshot,
        *,
        user_id: UUID,
    ) -> ResearchDocumentSnapshot:
        if snapshot.analysis_handoff is None or self._formal_analysis_handoff is None:
            return snapshot
        live = self._current_analysis_handoff(
            user_id=user_id,
            task_id=snapshot.task_id,
        )
        return _with_analysis_availability(snapshot, live)

    def _require_current_document(
        self, snapshot: ResearchDocumentSnapshot, *, user_id: UUID
    ) -> None:
        task = self._research_tasks.get(snapshot.task_id, user_id)
        if task is None:
            raise LookupError(snapshot.document_id)
        if task.current_framework_id != snapshot.document_id:
            raise ValueError("research document is not the task's current framework")

    def _invalidate_method_plan_if_needed(self, task_id: UUID, reason: str) -> None:
        if self._invalidate_method_plan is not None:
            self._invalidate_method_plan(task_id, reason)

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
        analysis_handoff: dict[str, object] | None = None,
    ) -> None:
        release_id = theory_plan.knowledge_release.knowledge_release_id
        allowed = {
            (item.evidence_ref_id, item.source.source_id)
            for item in theory_plan.evidence_bundle.evidence_items
            if item.source is not None
        }
        analysis_annotations = {
            str(item.get("annotation_id")): item
            for item in (
                analysis_handoff.get("annotations", []) if analysis_handoff else []
            )
            if isinstance(item, dict) and item.get("annotation_id")
        }
        unavailable = {
            str(item)
            for item in (
                analysis_handoff.get("unavailable_annotation_ids", [])
                if analysis_handoff
                else []
            )
        }
        for section in sections:
            for evidence in section.evidence_refs:
                if (
                    evidence.source_kind
                    is ResearchDocumentEvidenceSourceKind.PUBLIC_KNOWLEDGE
                ):
                    if evidence.knowledge_release_id != release_id:
                        raise ValueError("evidence must use the confirmed knowledge release")
                    if (evidence.evidence_ref_id, evidence.source_id) not in allowed:
                        raise ValueError(
                            "evidence and source IDs must belong to the confirmed theory plan"
                        )
                    continue
                annotation_id = str(evidence.annotation_id)
                annotation = analysis_annotations.get(annotation_id)
                if (
                    annotation is None
                    or annotation_id in unavailable
                    or annotation.get("source_available") is False
                ):
                    raise ValueError(
                        "personal material evidence requires an available confirmed annotation"
                    )
                if (
                    annotation.get("material_id") != str(evidence.material_id)
                    or annotation.get("parse_id") != str(evidence.parse_id)
                    or annotation.get("segment_id") != evidence.segment_id
                    or annotation.get("locator") != evidence.locator
                    or evidence.evidence_ref_id
                    != f"analysis-annotation:{annotation_id}"
                    or evidence.source_id != f"material-segment:{evidence.segment_id}"
                ):
                    raise ValueError("personal material evidence locator does not match analysis")


def _analysis_handoff_payload(
    handoff: ResearchAnalysisHandoff,
    *,
    expected_task_id: UUID,
) -> dict[str, object] | None:
    if handoff.task_id != expected_task_id:
        raise ValueError("research analysis handoff belongs to another task")
    payload = _json_safe(asdict(handoff))
    if not isinstance(payload, dict):
        raise TypeError("research analysis handoff must serialize to an object")
    if payload.get("schema_version") != "research-analysis-v1":
        raise ValueError("unsupported research analysis handoff")
    for collection in ("codes", "memos", "comparisons"):
        values = payload.get(collection)
        if not isinstance(values, list):
            raise ValueError(f"research analysis {collection} must be a list")
        if any(
            not isinstance(item, dict) or item.get("status") != "confirmed"
            for item in values
        ):
            raise ValueError("research document can only pin confirmed analysis")
    annotations = payload.get("annotations")
    if not isinstance(annotations, list):
        raise ValueError("research analysis annotations must be a list")
    for annotation in annotations:
        if not isinstance(annotation, dict):
            raise ValueError("research analysis annotation must be an object")
        annotation.pop("quote", None)
    unavailable = payload.get("unavailable_annotation_ids")
    if not isinstance(unavailable, list):
        raise ValueError("research analysis unavailable annotations must be a list")
    if not any(
        payload.get(key) for key in ("annotations", "codes", "memos", "comparisons")
    ) and not unavailable:
        return None
    return payload


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported research analysis value: {type(value).__name__}")


def _with_analysis_availability(
    snapshot: ResearchDocumentSnapshot,
    live: dict[str, object] | None,
) -> ResearchDocumentSnapshot:
    if snapshot.analysis_handoff is None or live is None:
        return snapshot
    pinned = deepcopy(snapshot.analysis_handoff)
    unavailable = {
        str(item) for item in live.get("unavailable_annotation_ids", [])
    }
    if not unavailable:
        return snapshot
    annotations = pinned.get("annotations")
    if isinstance(annotations, list):
        for annotation in annotations:
            if not isinstance(annotation, dict):
                continue
            annotation_id = str(annotation.get("annotation_id"))
            if annotation_id in unavailable:
                annotation["source_available"] = False
                annotation["unavailable_reason"] = "source_deleted"
                annotation.pop("quote", None)
    recorded = [str(item) for item in pinned.get("unavailable_annotation_ids", [])]
    pinned["unavailable_annotation_ids"] = list(dict.fromkeys((*recorded, *unavailable)))
    return replace(snapshot, analysis_handoff=pinned)


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
                    "source_kind": evidence.source_kind.value,
                    "annotation_id": (
                        str(evidence.annotation_id) if evidence.annotation_id else None
                    ),
                    "material_id": (
                        str(evidence.material_id) if evidence.material_id else None
                    ),
                    "parse_id": str(evidence.parse_id) if evidence.parse_id else None,
                    "segment_id": evidence.segment_id,
                    "locator": evidence.locator,
                }
                for evidence in section.evidence_refs
            ],
            "citation_refs": [
                {
                    "citation_id": citation.citation_id,
                    "kind": citation.kind.value,
                    "source_id": citation.source_id,
                    "source_version": citation.source_version,
                    "locator": citation.locator,
                    "state": citation.state.value,
                }
                for citation in section.citation_refs
            ],
        }
        for section in sections
    ]


def _method_plan_payload(
    value: MethodPlanSnapshot | None,
) -> dict[str, object] | None:
    """Flatten a method snapshot into the stable export shape.

    The method module keeps shared constraints as a value object, while the
    delivery manifest deliberately exposes each field at the top level so a
    consumer can inspect the exported JSON without knowing internal domain
    nesting.  This also preserves the actor/source distinction for every
    generated or user-edited section.
    """

    if value is None:
        return None
    return {
        "plan_id": str(value.plan_id),
        "task_id": str(value.task_id),
        "framework_id": str(value.framework_id),
        "framework_version": value.framework_version,
        "theory_plan_id": str(value.theory_plan_id),
        "theory_plan_version": value.theory_plan_version,
        "method_kind": value.method_kind.value,
        "decision_source": value.decision_source,
        "rationale": value.rationale,
        "research_question": value.research_question,
        "theory_summary": value.theory_summary,
        "material_constraints": list(value.shared_constraints.material_constraints),
        "ethical_constraints": list(value.shared_constraints.ethical_constraints),
        "theory_concepts": list(value.shared_constraints.theory_concepts),
        "evidence_ref_ids": list(value.shared_constraints.evidence_ref_ids),
        "knowledge_release_id": value.shared_constraints.knowledge_release_id,
        "shared_context": [
            {
                "key": item.key,
                "title": item.title,
                "content": item.content,
                "evidence_refs": [
                    {
                        "evidence_ref_id": ref.evidence_ref_id,
                        "source_id": ref.source_id,
                        "source_kind": ref.source_kind,
                        "knowledge_release_id": ref.knowledge_release_id,
                        "annotation_id": ref.annotation_id,
                        "material_id": ref.material_id,
                        "parse_id": ref.parse_id,
                        "segment_id": ref.segment_id,
                        "locator": ref.locator,
                    }
                    for ref in item.evidence_refs
                ],
            }
            for item in value.shared_context
        ],
        "sections": [
            {
                "key": item.key,
                "title": item.title,
                "content": item.content,
                "source": item.source,
            }
            for item in value.sections
        ],
        "reviews": [
            {
                "review_id": str(item.review_id),
                "note": item.note,
                "blocking": item.blocking,
                "created_at": item.created_at.isoformat(),
                "resolved_at": item.resolved_at.isoformat()
                if item.resolved_at
                else None,
            }
            for item in value.reviews
        ],
        "status": value.status.value,
        "version": value.version,
        "revision_id": str(value.revision_id),
        "change_summary": value.change_summary,
        "actor": value.actor,
        "created_at": value.created_at.isoformat(),
        "restored_from_version": value.restored_from_version,
        "stale_reason": value.stale_reason,
        "confirmed_at": value.confirmed_at.isoformat()
        if value.confirmed_at
        else None,
    }


def _unavailable_personal_source_ids(
    analysis_handoff: dict[str, object] | None,
) -> tuple[set[str], set[str], set[str]]:
    if analysis_handoff is None:
        return set(), set(), set()
    unavailable_annotation_ids = {
        str(item)
        for item in analysis_handoff.get("unavailable_annotation_ids", [])
    }
    unavailable_source_ids: set[str] = set()
    unavailable_evidence_ref_ids: set[str] = set()
    for annotation in analysis_handoff.get("annotations", []):
        if not isinstance(annotation, dict):
            continue
        annotation_id = str(annotation.get("annotation_id") or "")
        unavailable = (
            annotation.get("source_available") is False
            or annotation_id in unavailable_annotation_ids
        )
        material_id = annotation.get("material_id")
        parse_id = annotation.get("parse_id")
        segment_id = annotation.get("segment_id")
        if unavailable and material_id and parse_id and segment_id:
            unavailable_source_ids.add(
                f"research-material:{material_id}:{parse_id}:{segment_id}"
            )
    comparisons = analysis_handoff.get("comparisons", [])
    if isinstance(comparisons, list):
        for comparison in comparisons:
            if not isinstance(comparison, dict):
                continue
            comparison_id = str(comparison.get("comparison_id") or "")
            findings = comparison.get("findings", [])
            if not comparison_id or not isinstance(findings, list):
                continue
            for finding_index, finding in enumerate(findings):
                if not isinstance(finding, dict):
                    continue
                annotation_ids = finding.get("annotation_ids", [])
                if not isinstance(annotation_ids, list):
                    continue
                for annotation_id in annotation_ids:
                    normalized_id = str(annotation_id)
                    if normalized_id in unavailable_annotation_ids:
                        unavailable_evidence_ref_ids.add(
                            f"analysis:{comparison_id}:finding-{finding_index + 1}:{normalized_id}"
                        )
    return (
        unavailable_source_ids,
        unavailable_annotation_ids,
        unavailable_evidence_ref_ids,
    )


def _annotation_id_from_evidence_ref(evidence_ref_id: str) -> str | None:
    if evidence_ref_id.startswith("analysis:"):
        value = evidence_ref_id.rsplit(":", 1)[-1].strip()
        if value:
            return value
    return None


def _export_evidence(
    item: EvidenceItemSnapshot,
    *,
    unavailable_personal_source_ids: set[str],
    unavailable_personal_annotation_ids: set[str],
    unavailable_personal_evidence_ref_ids: set[str],
) -> dict[str, object]:
    source = item.source
    personal = source is not None and source.source_type == "personal_research_material"
    annotation_id = _annotation_id_from_evidence_ref(item.evidence_ref_id)
    source_available = not (
        personal
        and (
            source.source_id in unavailable_personal_source_ids
            or annotation_id in unavailable_personal_annotation_ids
            or item.evidence_ref_id in unavailable_personal_evidence_ref_ids
        )
    )
    payload: dict[str, object] = {
        "evidence_ref_id": item.evidence_ref_id,
        "claim": item.claim,
        "excerpt": item.excerpt if source_available else None,
        "locator": item.locator,
        "verification_status": item.verification_status.value,
        "use_boundary": item.use_boundary,
        "source": (
            {
                "source_id": source.source_id,
                "source_type": source.source_type,
                "title": source.title,
                "authors_or_institution": list(source.authors_or_institution),
                "year": source.year,
                "publication": source.publication,
                "locator": source.locator,
                "url": source.url,
                "verification_status": source.verification_status.value,
                "use_boundary": source.use_boundary,
            }
            if source is not None
            else None
        ),
    }
    if personal:
        payload["source_available"] = source_available
        payload["unavailable_reason"] = None if source_available else "source_deleted"
    return payload


def _export_manifest(
    *,
    document: ResearchDocumentSnapshot,
    plan: ConfirmedTheoryPlanSnapshot,
    match_run: MatchRunSnapshot,
    proposals: tuple[ResearchDocumentProposalSnapshot, ...],
    versions: tuple[ResearchDocumentSnapshot, ...],
    method_plan: MethodPlanSnapshot | None = None,
) -> dict[str, object]:
    phenomenon = plan.phenomenon
    model = match_run.model
    candidate_title = {
        candidate.candidate_id: candidate.content.title for candidate in match_run.candidates
    }
    (
        unavailable_personal_source_ids,
        unavailable_personal_annotation_ids,
        unavailable_personal_evidence_ref_ids,
    ) = _unavailable_personal_source_ids(
        document.analysis_handoff
    )
    return {
        "schema_version": "research-delivery-v2",
        "document_identity": {
            "document_id": str(document.document_id),
            "revision_id": str(document.revision_id),
            "version": document.version,
        },
        "formatting": {
            "template_id": document.formatting.template_id,
            "csl_style_id": document.formatting.csl_style_id,
            "locale": document.formatting.locale,
            "custom_csl": document.formatting.custom_csl,
            "custom_css": document.formatting.custom_css,
        },
        "citation_audit": [
            {
                "section_id": section.section_id,
                "citation_id": citation.citation_id,
                "kind": citation.kind.value,
                "source_id": citation.source_id,
                "source_version": citation.source_version,
                "locator": citation.locator,
                "state": citation.state.value,
            }
            for section in document.sections
            for citation in section.citation_refs
        ],
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
            _export_evidence(
                item,
                unavailable_personal_source_ids=unavailable_personal_source_ids,
                unavailable_personal_annotation_ids=unavailable_personal_annotation_ids,
                unavailable_personal_evidence_ref_ids=unavailable_personal_evidence_ref_ids,
            )
            for item in plan.evidence_bundle.evidence_items
        ],
        "research_analysis": document.analysis_handoff,
        "method_plan": _method_plan_payload(method_plan),
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
                "research_analysis_content_hash": (
                    item.analysis_handoff.get("content_hash")
                    if item.analysis_handoff
                    else None
                ),
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
                "research_analysis_content_hash": (
                    item.analysis_handoff.get("content_hash")
                    if item.analysis_handoff
                    else None
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
    research_analysis = manifest["research_analysis"]
    method_plan = manifest.get("method_plan")
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
        excerpt = (
            "来源已删除（已保留引用定位，不包含原文）"
            if item.get("source_available") is False
            and item.get("unavailable_reason") == "source_deleted"
            else item.get("excerpt") or "未附摘录"
        )
        lines.extend(
            [
                f"- **{item['claim']}** — {source_label}",
                f"  - 摘录：{excerpt}",
                f"  - 定位：{item.get('locator') or '未附定位'}",
                f"  - 核验：{item['verification_status']}；使用边界：{item['use_boundary']}",
            ]
        )
    lines.extend(["", "### 个人材料分析依据", ""])
    if isinstance(research_analysis, dict):
        lines.append(
            f"- 分析版本：{research_analysis.get('content_hash') or '未记录'}"
        )
        lines.append(
            "- 已确认编码 / 备忘 / 案例比较："
            f"{len(research_analysis.get('codes', []))} / "
            f"{len(research_analysis.get('memos', []))} / "
            f"{len(research_analysis.get('comparisons', []))}"
        )
        unavailable_count = len(
            research_analysis.get("unavailable_annotation_ids", [])
        )
        lines.append(
            f"- 已删除来源墓碑：{unavailable_count} 处（不包含原文）"
        )
    else:
        lines.append("- 本版未纳入已确认的个人材料分析。")
    lines.extend(["", "## 正式研究方法计划", ""])
    if isinstance(method_plan, dict):
        lines.extend(
            [
                f"- 方法路径：{method_plan.get('method_kind') or '未记录'}",
                f"- 计划状态：{method_plan.get('status') or '未记录'}",
                f"- 决定来源：{method_plan.get('decision_source') or '未记录'}",
                f"- 计划版本：v{method_plan.get('version')}",
                f"- 研究问题：{method_plan.get('research_question') or '未记录'}",
                f"- 理论摘要：{method_plan.get('theory_summary') or '未记录'}",
                f"- 用户理由：{method_plan.get('rationale') or '未记录'}",
            ]
        )
        concepts = method_plan.get("theory_concepts")
        if isinstance(concepts, list):
            lines.append(f"- 共用理论概念：{'、'.join(str(item) for item in concepts) or '未记录'}")
        evidence_ids = method_plan.get("evidence_ref_ids")
        if isinstance(evidence_ids, list):
            lines.append(
                f"- 共用证据引用：{ '、'.join(str(item) for item in evidence_ids) or '未记录'}"
            )
        constraints = (
            ("材料约束", method_plan.get("material_constraints")),
            ("伦理约束", method_plan.get("ethical_constraints")),
        )
        for label, values in constraints:
            if isinstance(values, list):
                lines.append(f"- {label}：{'；'.join(str(item) for item in values) or '未记录'}")
        lines.extend(["", "### 方法计划章节", ""])
        sections = method_plan.get("sections")
        if isinstance(sections, list):
            for section in sections:
                if not isinstance(section, dict):
                    continue
                source = "用户决定" if section.get("source") == "user" else "系统建议"
                lines.extend(
                    [
                        "#### "
                        f"{section.get('title') or section.get('key') or '未命名章节'}"
                        f"（{source}）",
                        str(section.get("content") or ""),
                        "",
                    ]
                )
        reviews = method_plan.get("reviews")
        if isinstance(reviews, list) and reviews:
            lines.extend(["### 方法计划审校", ""])
            for review in reviews:
                if not isinstance(review, dict):
                    continue
                state = "已解决" if review.get("resolved_at") else "未解决"
                blocking = "阻断" if review.get("blocking") else "非阻断"
                lines.append(f"- {state} / {blocking}：{review.get('note') or '未记录'}")
    else:
        lines.append("- 本版未附已确认的 MethodPlan。")
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
