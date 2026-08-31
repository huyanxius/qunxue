from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from qunxue_api.application.research_document_mutations import (
    ResearchDocumentMutationReceipt,
    ResearchDocumentMutationRepository,
    mutation_request_hash,
)
from qunxue_api.modules.research_framework import ResearchDocumentSnapshot, ResearchDocumentStatus
from qunxue_api.modules.research_intake import (
    ResearchTask,
    ResearchTaskRepository,
    ResearchTaskStatus,
)
from qunxue_api.modules.research_method import (
    MethodKind,
    MethodPlanContextItem,
    MethodPlanEvidenceRef,
    MethodPlanSection,
    MethodPlanService,
    MethodPlanSnapshot,
)
from qunxue_api.modules.theory_matching import ConfirmedTheoryPlanSnapshot


class ResearchMethodPlanApplication:
    def __init__(
        self,
        *,
        plans: MethodPlanService,
        research_tasks: ResearchTaskRepository,
        mutations: ResearchDocumentMutationRepository,
        get_framework: Callable[[UUID], ResearchDocumentSnapshot | None],
        get_theory_plan: Callable[[UUID], ConfirmedTheoryPlanSnapshot | None],
    ) -> None:
        self._plans = plans
        self._tasks = research_tasks
        self._mutations = mutations
        self._get_framework = get_framework
        self._get_theory_plan = get_theory_plan

    def create(
        self,
        *,
        user_id: UUID,
        task: ResearchTask,
        framework_id: UUID,
        theory_plan_id: UUID,
        method_kind: MethodKind,
        idempotency_key: str,
    ) -> MethodPlanSnapshot:
        self._require_task(task, user_id)
        receipt = self._mutations.claim(
            user_id=user_id,
            idempotency_key=idempotency_key,
            operation=f"create_method_plan:{task.task_id}",
            request_hash=mutation_request_hash(
                {
                    "framework_id": str(framework_id),
                    "theory_plan_id": str(theory_plan_id),
                    "method_kind": method_kind.value,
                }
            ),
        )
        replayed = self._replayed(receipt)
        if replayed is not None:
            return replayed
        with self._mutation_scope(receipt):
            return self._create(
                task=task,
                framework_id=framework_id,
                theory_plan_id=theory_plan_id,
                method_kind=method_kind,
                receipt=receipt,
            )

    def _create(
        self,
        *,
        task: ResearchTask,
        framework_id: UUID,
        theory_plan_id: UUID,
        method_kind: MethodKind,
        receipt: ResearchDocumentMutationReceipt,
    ) -> MethodPlanSnapshot:
        framework = self._get_framework(framework_id)
        theory = self._get_theory_plan(theory_plan_id)
        if (
            framework is None
            or framework.task_id != task.task_id
            or framework.status is not ResearchDocumentStatus.CONFIRMED
        ):
            raise ValueError("confirmed research framework is required")
        if theory is None or theory.task_id != task.task_id:
            raise ValueError("confirmed theory plan is required")
        if task.current_framework_id != framework.document_id:
            raise ValueError("method plan framework does not match current task framework")
        if task.status is not ResearchTaskStatus.FRAMEWORK_CONFIRMED:
            raise ValueError("research task must be framework-confirmed before method design")
        value = self._plans.create(
            task_id=task.task_id,
            framework_id=framework.document_id,
            framework_version=framework.version,
            theory_plan_id=theory.theory_plan_id,
            theory_plan_version=theory.version,
            research_question=_framework_section(framework, "research_question"),
            theory_summary=_framework_section(framework, "theoretical_perspective"),
            material_constraints=(_framework_section(framework, "sample_and_sources"),),
            ethical_constraints=(_framework_section(framework, "ethics"),),
            theory_concepts=_shared_theory_concepts(framework, theory),
            evidence_ref_ids=_shared_evidence_refs(framework, theory),
            knowledge_release_id=theory.knowledge_release.knowledge_release_id,
            shared_context=_shared_context(framework, theory),
            method_kind=method_kind,
            framework_confirmed=True,
        )
        self._save_task_method_state(user_id=task.user_id, plan=value)
        self._mutations.complete(
            request_id=receipt.request_id,
            result_id=value.plan_id,
            result_version=value.version,
        )
        return value

    def get(self, *, user_id: UUID, plan_id: UUID) -> MethodPlanSnapshot:
        value = self._plans.get(plan_id)
        self._require_task_id(value.task_id, user_id)
        framework = self._get_framework(value.framework_id)
        theory = self._get_theory_plan(value.theory_plan_id)
        if framework is None or (
            framework.version != value.framework_version
            or framework.status is not ResearchDocumentStatus.CONFIRMED
        ):
            stale = self._plans.mark_stale(
                plan_id=plan_id, reason="研究框架版本已变化，请从当前框架重新制定方法计划。"
            )
            self._save_task_method_state(user_id=user_id, plan=stale)
            return stale
        if theory is None or theory.version != value.theory_plan_version:
            stale = self._plans.mark_stale(
                plan_id=plan_id, reason="理论方案版本已变化，请重新确认方法计划。"
            )
            self._save_task_method_state(user_id=user_id, plan=stale)
            return stale
        return value

    def latest_for_task(self, *, user_id: UUID, task: ResearchTask) -> MethodPlanSnapshot | None:
        self._require_task(task, user_id)
        value = self._plans.latest_for_task(task.task_id)
        return self.get(user_id=user_id, plan_id=value.plan_id) if value else None

    def revise(
        self,
        *,
        user_id: UUID,
        plan_id: UUID,
        expected_version: int,
        method_kind: MethodKind,
        sections: tuple[MethodPlanSection, ...],
        rationale: str,
        change_summary: str,
        idempotency_key: str,
    ) -> MethodPlanSnapshot:
        receipt = self._mutations.claim(
            user_id=user_id,
            idempotency_key=idempotency_key,
            operation=f"revise_method_plan:{plan_id}",
            request_hash=mutation_request_hash(
                {
                    "expected_version": expected_version,
                    "method_kind": method_kind.value,
                    "sections": _sections_payload(sections),
                    "rationale": rationale,
                    "change_summary": change_summary,
                }
            ),
        )
        replayed = self._replayed(receipt)
        if replayed is not None:
            return replayed
        with self._mutation_scope(receipt):
            self.get(user_id=user_id, plan_id=plan_id)
            value = self._plans.revise(
                plan_id=plan_id,
                expected_version=expected_version,
                method_kind=method_kind,
                sections=sections,
                rationale=rationale,
                change_summary=change_summary,
                actor="user",
            )
            self._save_task_method_state(user_id=user_id, plan=value)
            self._mutations.complete(
                request_id=receipt.request_id,
                result_id=value.plan_id,
                result_version=value.version,
            )
            return value

    def review(
        self,
        *,
        user_id: UUID,
        plan_id: UUID,
        expected_version: int,
        note: str,
        blocking: bool,
        idempotency_key: str,
    ) -> MethodPlanSnapshot:
        receipt = self._mutations.claim(
            user_id=user_id,
            idempotency_key=idempotency_key,
            operation=f"review_method_plan:{plan_id}",
            request_hash=mutation_request_hash(
                {"expected_version": expected_version, "note": note, "blocking": blocking}
            ),
        )
        replayed = self._replayed(receipt)
        if replayed is not None:
            return replayed
        with self._mutation_scope(receipt):
            current = self.get(user_id=user_id, plan_id=plan_id)
            value = self._plans.submit_review(
                plan_id=current.plan_id,
                expected_version=expected_version,
                note=note,
                blocking=blocking,
            )
            self._save_task_method_state(user_id=user_id, plan=value)
            self._mutations.complete(
                request_id=receipt.request_id,
                result_id=value.plan_id,
                result_version=value.version,
            )
            return value

    def resolve_review(
        self,
        *,
        user_id: UUID,
        plan_id: UUID,
        review_id: UUID,
        expected_version: int,
        reason: str,
        idempotency_key: str,
    ) -> MethodPlanSnapshot:
        receipt = self._mutations.claim(
            user_id=user_id,
            idempotency_key=idempotency_key,
            operation=f"resolve_method_plan_review:{plan_id}:{review_id}",
            request_hash=mutation_request_hash(
                {
                    "expected_version": expected_version,
                    "review_id": str(review_id),
                    "reason": reason,
                }
            ),
        )
        replayed = self._replayed(receipt)
        if replayed is not None:
            return replayed
        with self._mutation_scope(receipt):
            current = self.get(user_id=user_id, plan_id=plan_id)
            value = self._plans.resolve_review(
                plan_id=current.plan_id,
                expected_version=expected_version,
                review_id=review_id,
                reason=reason,
            )
            self._save_task_method_state(user_id=user_id, plan=value)
            self._mutations.complete(
                request_id=receipt.request_id,
                result_id=value.plan_id,
                result_version=value.version,
            )
            return value

    def confirm(
        self,
        *,
        user_id: UUID,
        plan_id: UUID,
        expected_version: int,
        reason: str,
        idempotency_key: str,
    ) -> MethodPlanSnapshot:
        receipt = self._mutations.claim(
            user_id=user_id,
            idempotency_key=idempotency_key,
            operation=f"confirm_method_plan:{plan_id}",
            request_hash=mutation_request_hash(
                {"expected_version": expected_version, "reason": reason}
            ),
        )
        replayed = self._replayed(receipt)
        if replayed is not None:
            return replayed
        with self._mutation_scope(receipt):
            current = self.get(user_id=user_id, plan_id=plan_id)
            value = self._plans.confirm(
                plan_id=current.plan_id,
                expected_version=expected_version,
                reason=reason,
            )
            self._save_task_method_state(user_id=user_id, plan=value)
            self._mutations.complete(
                request_id=receipt.request_id,
                result_id=value.plan_id,
                result_version=value.version,
            )
            return value

    def restore(
        self,
        *,
        user_id: UUID,
        plan_id: UUID,
        source_version: int,
        expected_version: int,
        reason: str,
        idempotency_key: str,
    ) -> MethodPlanSnapshot:
        receipt = self._mutations.claim(
            user_id=user_id,
            idempotency_key=idempotency_key,
            operation=f"restore_method_plan:{plan_id}",
            request_hash=mutation_request_hash(
                {
                    "source_version": source_version,
                    "expected_version": expected_version,
                    "reason": reason,
                }
            ),
        )
        replayed = self._replayed(receipt)
        if replayed is not None:
            return replayed
        with self._mutation_scope(receipt):
            current = self.get(user_id=user_id, plan_id=plan_id)
            value = self._plans.restore(
                plan_id=current.plan_id,
                source_version=source_version,
                expected_version=expected_version,
                reason=reason,
            )
            self._save_task_method_state(user_id=user_id, plan=value)
            self._mutations.complete(
                request_id=receipt.request_id,
                result_id=value.plan_id,
                result_version=value.version,
            )
            return value

    def versions(self, *, user_id: UUID, plan_id: UUID) -> tuple[MethodPlanSnapshot, ...]:
        current = self.get(user_id=user_id, plan_id=plan_id)
        return self._plans.list_versions(current.plan_id)

    def _require_task(self, task: ResearchTask, user_id: UUID) -> None:
        if task.user_id != user_id:
            raise LookupError(task.task_id)

    def _require_task_id(self, task_id: UUID, user_id: UUID) -> None:
        task = self._tasks.get(task_id, user_id)
        if task is None:
            raise LookupError(task_id)

    def _save_task_method_state(
        self, *, user_id: UUID, plan: MethodPlanSnapshot
    ) -> ResearchTask:
        """Project the immutable plan version into task navigation atomically."""

        task = self._tasks.get(plan.task_id, user_id)
        if task is None:
            raise LookupError(plan.task_id)
        if (
            task.current_method_plan_id == plan.plan_id
            and task.current_method_plan_status == plan.status.value
        ):
            return task
        saved_task = self._tasks.save_progress(
            replace(
                task,
                version=task.version + 1,
                updated_at=datetime.now(UTC),
                current_method_plan_id=plan.plan_id,
                current_method_plan_status=plan.status.value,
            )
        )
        if saved_task is None:
            raise ValueError("research task changed while saving method plan")
        return saved_task

    def _replayed(self, receipt: ResearchDocumentMutationReceipt) -> MethodPlanSnapshot | None:
        if receipt.status != "completed":
            return None
        if receipt.result_id is None or receipt.result_version is None:
            raise RuntimeError("completed method plan mutation is missing its result")
        return self._plans.get_version(receipt.result_id, receipt.result_version)

    @contextmanager
    def _mutation_scope(self, receipt: ResearchDocumentMutationReceipt):
        try:
            yield
        except Exception:
            if receipt.status == "pending":
                self._mutations.fail(request_id=receipt.request_id)
            raise


def _framework_section(framework: ResearchDocumentSnapshot, key: str) -> str:
    section = next((item for item in framework.sections if item.key == key), None)
    return section.content if section is not None else "未在当前框架中明确。"


def _shared_context(
    framework: ResearchDocumentSnapshot,
    theory: ConfirmedTheoryPlanSnapshot,
) -> tuple[MethodPlanContextItem, ...]:
    """Copy the exact framework/theory inputs into one immutable handoff.

    Method design must not re-query mutable upstream records later.  The context
    therefore keeps every framework section and the confirmed theory bundle,
    including each evidence locator, while the top-level constraint fields offer
    a compact view for clients.
    """

    items = [
        MethodPlanContextItem(
            key=section.key,
            title=section.title,
            content=section.content,
            evidence_refs=tuple(_framework_evidence_ref(ref) for ref in section.evidence_refs),
        )
        for section in framework.sections
    ]
    phenomenon = getattr(theory, "phenomenon", None)
    theory_lines = [
        f"研究现象：{getattr(phenomenon, 'phenomenon', '未单独说明')}",
        f"研究意图：{getattr(phenomenon, 'research_intent', None) or '未单独说明'}",
    ]
    for candidate in getattr(theory, "candidates", ()):
        theory_lines.append(f"理论候选「{candidate.content.title}」：")
        theory_lines.extend(f"- {claim}" for claim in candidate.content.core_claims)
        theory_lines.extend(
            f"适用条件：{item}" for item in candidate.judgement.applicable_conditions
        )
        theory_lines.extend(f"局限：{item}" for item in candidate.judgement.limitations)
    for assignment in getattr(theory, "use_assignments", ()):
        theory_lines.append(
            f"理论分工（{assignment.role_code}）：{assignment.responsibility}"
        )
    for relation in getattr(theory, "relations", ()):
        theory_lines.append(f"理论关系（{relation.relation_kind}）：{relation.explanation}")
    items.append(
        MethodPlanContextItem(
            key="theory_plan",
            title="已确认理论方案",
            content="\n".join(theory_lines),
            evidence_refs=tuple(
                _theory_evidence_ref(item, theory.knowledge_release.knowledge_release_id)
                for item in getattr(getattr(theory, "evidence_bundle", None), "evidence_items", ())
            ),
        )
    )
    return tuple(items)


def _framework_evidence_ref(value: object) -> MethodPlanEvidenceRef:
    source_kind = getattr(getattr(value, "source_kind", None), "value", None) or str(
        getattr(value, "source_kind", "unknown")
    )
    locator = getattr(value, "locator", None)
    return MethodPlanEvidenceRef(
        evidence_ref_id=str(value.evidence_ref_id),
        source_id=str(value.source_id),
        source_kind=source_kind,
        knowledge_release_id=getattr(value, "knowledge_release_id", None),
        annotation_id=_string_or_none(getattr(value, "annotation_id", None)),
        material_id=_string_or_none(getattr(value, "material_id", None)),
        parse_id=_string_or_none(getattr(value, "parse_id", None)),
        segment_id=_string_or_none(getattr(value, "segment_id", None)),
        locator=_locator_text(locator),
    )


def _theory_evidence_ref(value: object, release_id: str) -> MethodPlanEvidenceRef:
    source = getattr(value, "source", None)
    source_id = getattr(source, "source_id", None) or value.evidence_ref_id
    locator = getattr(value, "locator", None)
    return MethodPlanEvidenceRef(
        evidence_ref_id=str(value.evidence_ref_id),
        source_id=str(source_id),
        source_kind="public_knowledge",
        knowledge_release_id=release_id,
        locator=str(locator) if locator is not None else None,
    )


def _string_or_none(value: object) -> str | None:
    return str(value) if value is not None else None


def _locator_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _sections_payload(sections: tuple[MethodPlanSection, ...]) -> list[dict[str, str]]:
    return [
        {"key": item.key, "title": item.title, "content": item.content, "source": item.source}
        for item in sections
    ]


def _shared_theory_concepts(
    framework: ResearchDocumentSnapshot,
    theory: ConfirmedTheoryPlanSnapshot,
) -> tuple[str, ...]:
    values = _context_lines(_framework_section(framework, "core_concepts"))
    for candidate in theory.candidates:
        values.extend(
            item
            for item in (
                candidate.content.title,
                *candidate.content.core_claims,
            )
            if item and item.strip()
        )
    return _unique(values)


def _shared_evidence_refs(
    framework: ResearchDocumentSnapshot,
    theory: ConfirmedTheoryPlanSnapshot,
) -> tuple[str, ...]:
    values = [
        evidence.evidence_ref_id
        for section in framework.sections
        for evidence in section.evidence_refs
    ]
    values.extend(item.evidence_ref_id for item in theory.evidence_bundle.evidence_items)
    return _unique(values)


def _context_lines(value: str) -> list[str]:
    lines = [line.strip().lstrip("-•* ").strip() for line in value.splitlines()]
    return [line for line in lines if line]


def _unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value.strip() for value in values if value.strip()))
