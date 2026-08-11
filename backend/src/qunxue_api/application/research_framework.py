from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from qunxue_api.modules.research_framework import (
    AuditResolution,
    AuditResolutionSetSnapshot,
    ConfirmedFrameworkSnapshot,
    FrameworkAuditSnapshot,
    FrameworkRecord,
    FrameworkReviewRunSnapshot,
    FrameworkRevisionConflict,
    FrameworkVersionSnapshot,
    MethodIntentSnapshot,
    ResearchFrameworkDraft,
    ResearchFrameworkDraftInput,
    ResearchFrameworkService,
)
from qunxue_api.modules.research_intake import (
    ResearchTask,
    ResearchTaskRepository,
    ResearchTaskStatus,
)
from qunxue_api.modules.theory_matching import ConfirmedTheoryPlanReader


class FrameworkTheoryPlanUnavailable(ValueError):
    pass


class FrameworkTaskConflict(ValueError):
    pass


class ResearchFrameworkApplication:
    def __init__(
        self,
        *,
        workflow: ResearchFrameworkService,
        theory_plans: ConfirmedTheoryPlanReader,
        research_tasks: ResearchTaskRepository,
    ) -> None:
        self._workflow = workflow
        self._theory_plans = theory_plans
        self._research_tasks = research_tasks

    def create(
        self,
        *,
        task: ResearchTask,
        expected_task_version: int,
        theory_plan_id: UUID,
        theory_plan_version: int,
        original_research_question: str,
        confirmed_research_question: str,
        question_adjustment_reason: str | None,
        research_object: str,
        analysis_unit: str | None,
        context: str | None,
        method_intent: MethodIntentSnapshot,
    ) -> FrameworkVersionSnapshot:
        plan = self._theory_plans.get_confirmed(theory_plan_id)
        if plan is None:
            raise FrameworkTheoryPlanUnavailable("theory plan is not confirmed")
        if (
            task.version != expected_task_version
            or plan.version != theory_plan_version
            or plan.task_id != task.task_id
        ):
            raise FrameworkTaskConflict("framework input snapshot is stale")
        framework = self._workflow.create_draft(
            input=ResearchFrameworkDraftInput(
                theory_plan=plan,
                original_research_question=original_research_question,
                confirmed_research_question=confirmed_research_question,
                question_adjustment_reason=question_adjustment_reason,
                research_object=research_object,
                analysis_unit=analysis_unit,
                context=context,
                method_intent=method_intent,
            )
        )
        saved = self._research_tasks.save_progress(
            replace(
                task,
                status=ResearchTaskStatus.FRAMEWORK_DRAFT,
                version=task.version + 1,
                updated_at=datetime.now(UTC),
                current_framework_id=framework.framework_id,
            )
        )
        if saved is None:
            raise RuntimeError("research task disappeared while creating framework")
        return framework

    def get(self, framework_id: UUID) -> FrameworkVersionSnapshot:
        return self._workflow.get(framework_id)

    def record(self, framework_id: UUID) -> FrameworkRecord:
        return self._workflow.get_record(framework_id)

    def list_versions(self, framework_id: UUID) -> tuple[FrameworkVersionSnapshot, ...]:
        return self._workflow.list_versions(framework_id)

    def revise(
        self,
        *,
        framework_id: UUID,
        expected_revision_id: UUID,
        expected_version: int,
        revised_draft: ResearchFrameworkDraft,
        revision_reason: str,
    ) -> FrameworkVersionSnapshot:
        current = self._workflow.get(framework_id)
        if current.revision_id != expected_revision_id:
            raise FrameworkRevisionConflict("framework revision is stale")
        return self._workflow.edit(
            framework_id=framework_id,
            expected_version=expected_version,
            revised_draft=revised_draft,
            revision_reason=revision_reason,
        )

    def start_review(
        self,
        *,
        framework_id: UUID,
        expected_revision_id: UUID,
        expected_version: int,
    ) -> FrameworkReviewRunSnapshot:
        current = self._workflow.get(framework_id)
        if current.revision_id != expected_revision_id:
            raise FrameworkRevisionConflict("framework revision is stale")
        return self._workflow.start_review(
            framework_id=framework_id,
            expected_version=expected_version,
        )

    def get_review(self, framework_id: UUID, review_run_id: UUID) -> FrameworkReviewRunSnapshot:
        record = self.record(framework_id)
        for review in record.review_runs:
            if review.review_run_id == review_run_id:
                return review
        raise LookupError(review_run_id)

    def retry_review(
        self,
        *,
        framework_id: UUID,
        review_run_id: UUID,
        expected_revision_id: UUID,
        expected_review_version: int,
    ) -> FrameworkReviewRunSnapshot:
        return self._workflow.retry_review(
            framework_id=framework_id,
            review_run_id=review_run_id,
            expected_revision_id=expected_revision_id,
            expected_review_version=expected_review_version,
        )

    def confirm(
        self,
        *,
        task: ResearchTask,
        framework_id: UUID,
        expected_revision_id: UUID,
        expected_version: int,
        audit_id: UUID,
        resolutions: tuple[AuditResolution, ...],
    ) -> ConfirmedFrameworkSnapshot:
        current = self._workflow.get(framework_id)
        if current.revision_id != expected_revision_id:
            raise FrameworkRevisionConflict("framework revision is stale")
        confirmed = self._workflow.confirm(
            framework_id=framework_id,
            expected_version=expected_version,
            audit_id=audit_id,
            resolutions=resolutions,
        )
        saved = self._research_tasks.save_progress(
            replace(
                task,
                status=ResearchTaskStatus.FRAMEWORK_CONFIRMED,
                version=task.version + 1,
                updated_at=datetime.now(UTC),
                current_framework_id=framework_id,
            )
        )
        if saved is None:
            raise RuntimeError("research task disappeared while confirming framework")
        return confirmed

    def submit_resolutions(
        self,
        *,
        framework_id: UUID,
        expected_revision_id: UUID,
        expected_version: int,
        audit_id: UUID,
        resolutions: tuple[AuditResolution, ...],
    ) -> AuditResolutionSetSnapshot:
        return self._workflow.submit_resolutions(
            framework_id=framework_id,
            expected_revision_id=expected_revision_id,
            expected_version=expected_version,
            audit_id=audit_id,
            resolutions=resolutions,
        )

    def _latest_audit(
        self,
        framework_id: UUID,
        version: int,
    ) -> FrameworkAuditSnapshot | None:
        record = self.record(framework_id)
        return next(
            (
                run.audit
                for run in reversed(record.review_runs)
                if run.audit is not None and run.audit.framework_version == version
            ),
            None,
        )
