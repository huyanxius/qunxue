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
from qunxue_api.modules.research_framework import (
    ResearchDocumentMarkdownExport,
    ResearchDocumentSection,
    ResearchDocumentService,
    ResearchDocumentSnapshot,
)
from qunxue_api.modules.research_intake import (
    ResearchTask,
    ResearchTaskRepository,
    ResearchTaskStatus,
)
from qunxue_api.modules.theory_matching import ConfirmedTheoryPlanSnapshot


class ResearchDocumentApplication:
    def __init__(
        self,
        *,
        documents: ResearchDocumentService,
        research_tasks: ResearchTaskRepository,
        mutations: ResearchDocumentMutationRepository,
        get_theory_plan: Callable[[UUID], ConfirmedTheoryPlanSnapshot | None],
        owns_match_run: Callable[..., bool],
    ) -> None:
        self._documents = documents
        self._research_tasks = research_tasks
        self._mutations = mutations
        self._get_theory_plan = get_theory_plan
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
                raise RuntimeError("research task changed while creating document")
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
                    raise RuntimeError("research task changed while restoring document")
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
            theory_plan = self._required_theory_plan(current.theory_plan_id)
            self._validate_evidence_refs(current.sections, theory_plan=theory_plan)
            confirmed = self._documents.confirm(
                document_id=document_id, expected_version=expected_version
            )
            task = self._research_tasks.get(current.task_id, user_id)
            if task is None:
                raise RuntimeError("owned research task disappeared while confirming document")
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
                    raise RuntimeError("research task changed while confirming document")
            self._mutations.complete(
                request_id=receipt.request_id,
                result_id=confirmed.document_id,
                result_version=confirmed.version,
            )
            return confirmed

    def export_markdown(
        self, *, user_id: UUID, document_id: UUID, version: int | None
    ) -> ResearchDocumentMarkdownExport:
        self.get(user_id=user_id, document_id=document_id, version=version)
        return self._documents.export_markdown(document_id=document_id, version=version)

    def _require_owner(self, snapshot: ResearchDocumentSnapshot, *, user_id: UUID) -> None:
        if self._research_tasks.get(snapshot.task_id, user_id) is None:
            raise LookupError(snapshot.document_id)

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
