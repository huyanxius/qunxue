from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from qunxue_api.modules.research_framework.domain import (
    AuditFindingSnapshot,
    AuditResolution,
    AuditResolutionAction,
    AuditResolutionSetSnapshot,
    ConfirmedFrameworkSnapshot,
    FrameworkAuditSnapshot,
    FrameworkContentOrigin,
    FrameworkRecord,
    FrameworkRepository,
    FrameworkReviewRunSnapshot,
    FrameworkReviewRunStatus,
    FrameworkVersionSnapshot,
    ResearchFrameworkAuditor,
    ResearchFrameworkDraft,
    ResearchFrameworkDrafter,
    ResearchFrameworkDraftInput,
)
from qunxue_api.modules.research_framework.errors import (
    FrameworkAuditConflict,
    FrameworkConfirmationBlocked,
    FrameworkNotFound,
    FrameworkRevisionConflict,
)
from qunxue_api.modules.theory_matching import ConfirmedTheoryPlanSnapshot


class ResearchFrameworkService:
    """Owns append-only revisions, review invalidation, and confirmation gates."""

    def __init__(
        self,
        *,
        drafter: ResearchFrameworkDrafter,
        auditor: ResearchFrameworkAuditor,
        repository: FrameworkRepository,
        id_factory: Callable[[], UUID] = uuid4,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._drafter = drafter
        self._auditor = auditor
        self._repository = repository
        self._id_factory = id_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def create_draft(
        self,
        *,
        input: ResearchFrameworkDraftInput,
    ) -> FrameworkVersionSnapshot:
        if not isinstance(input.theory_plan, ConfirmedTheoryPlanSnapshot):
            raise TypeError("a confirmed theory plan snapshot is required")
        now = self._clock()
        framework = FrameworkVersionSnapshot(
            framework_id=self._id_factory(),
            task_id=input.theory_plan.task_id,
            version=1,
            input=input,
            draft=self._drafter.draft(input=input),
            revision_id=self._id_factory(),
            content_origin=FrameworkContentOrigin.SYSTEM_GENERATED,
            created_at=now,
        )
        self._repository.add(
            FrameworkRecord(
                framework_id=framework.framework_id,
                task_id=framework.task_id,
                versions=(framework,),
            )
        )
        return framework

    def get(self, framework_id: UUID) -> FrameworkVersionSnapshot:
        return self._record(framework_id).current

    def get_record(self, framework_id: UUID) -> FrameworkRecord:
        return self._record(framework_id)

    def list_versions(self, framework_id: UUID) -> tuple[FrameworkVersionSnapshot, ...]:
        return self._record(framework_id).versions

    def revise(
        self,
        *,
        framework_id: UUID,
        expected_version: int,
        audit_id: UUID,
        revised_draft: ResearchFrameworkDraft,
        resolutions: tuple[AuditResolution, ...],
        revision_reason: str,
    ) -> FrameworkVersionSnapshot:
        record = self._record(framework_id)
        self._require_version(record, expected_version)
        audit = self._audit(record, audit_id)
        if audit.framework_version != expected_version or audit.is_stale:
            raise FrameworkAuditConflict("audit does not apply to the current revision")
        self._validate_resolution_ids(audit, resolutions)

        return self.edit(
            framework_id=framework_id,
            expected_version=expected_version,
            revised_draft=revised_draft,
            revision_reason=revision_reason,
        )

    def edit(
        self,
        *,
        framework_id: UUID,
        expected_version: int,
        revised_draft: ResearchFrameworkDraft,
        revision_reason: str,
    ) -> FrameworkVersionSnapshot:
        record = self._record(framework_id)
        self._require_version(record, expected_version)

        current = record.current
        revised = FrameworkVersionSnapshot(
            framework_id=framework_id,
            task_id=current.task_id,
            version=current.version + 1,
            input=current.input,
            draft=revised_draft,
            revision_id=self._id_factory(),
            previous_revision_id=current.revision_id,
            content_origin=FrameworkContentOrigin.USER_MODIFIED,
            revision_reason=revision_reason.strip(),
            created_at=self._clock(),
        )
        stale_runs = tuple(
            replace(run, audit=replace(run.audit, is_stale=True))
            if run.audit is not None and run.audit.framework_version == current.version
            else run
            for run in record.review_runs
        )
        updated = replace(
            record,
            versions=(*record.versions, revised),
            review_runs=stale_runs,
        )
        if self._repository.save(updated, expected_version=expected_version) is None:
            raise FrameworkRevisionConflict("framework revision is stale")
        return revised

    def start_review(
        self,
        *,
        framework_id: UUID,
        expected_version: int,
    ) -> FrameworkReviewRunSnapshot:
        record = self._record(framework_id)
        self._require_version(record, expected_version)
        framework = record.current
        draft = self._auditor.audit(framework=framework)
        audit = FrameworkAuditSnapshot(
            audit_id=self._id_factory(),
            framework_id=framework_id,
            framework_version=framework.version,
            overall_status=draft.overall_status,
            findings=tuple(
                AuditFindingSnapshot(
                    finding_id=self._id_factory(),
                    summary=finding.summary,
                    reason=finding.reason,
                    impact=finding.impact,
                    recommendation=finding.recommendation,
                    blocking=finding.blocking,
                    finding_type=finding.finding_type,
                    severity=finding.severity,
                )
                for finding in draft.findings
            ),
            revision_id=framework.revision_id,
        )
        review = FrameworkReviewRunSnapshot(
            review_run_id=self._id_factory(),
            framework_id=framework_id,
            framework_version=framework.version,
            trace_id=self._id_factory(),
            idempotency_key=f"framework-review:{framework.revision_id}",
            version=1,
            status=FrameworkReviewRunStatus.SUCCEEDED,
            audit=audit,
            revision_id=framework.revision_id,
        )
        updated = replace(record, review_runs=(*record.review_runs, review))
        if self._repository.save(updated, expected_version=expected_version) is None:
            raise FrameworkRevisionConflict("framework revision is stale")
        return review

    def get_review_run(self, review_run_id: UUID) -> FrameworkReviewRunSnapshot:
        for record in self._all_records():
            for run in record.review_runs:
                if run.review_run_id == review_run_id:
                    return run
        raise FrameworkNotFound(str(review_run_id))

    def retry_review(
        self,
        *,
        framework_id: UUID,
        review_run_id: UUID,
        expected_revision_id: UUID,
        expected_review_version: int,
    ) -> FrameworkReviewRunSnapshot:
        record = self._record(framework_id)
        previous = next(
            (run for run in record.review_runs if run.review_run_id == review_run_id),
            None,
        )
        if previous is None:
            raise FrameworkNotFound(str(review_run_id))
        if (
            record.current.revision_id != expected_revision_id
            or previous.version != expected_review_version
        ):
            raise FrameworkRevisionConflict("framework review is stale")
        retried = self.start_review(
            framework_id=framework_id,
            expected_version=record.current.version,
        )
        refreshed = replace(
            retried,
            retry_of_review_run_id=review_run_id,
            attempt=previous.attempt + 1,
        )
        current_record = self._record(framework_id)
        runs = tuple(
            refreshed if run.review_run_id == retried.review_run_id else run
            for run in current_record.review_runs
        )
        self._repository.save(
            replace(current_record, review_runs=runs),
            expected_version=current_record.current.version,
        )
        return refreshed

    def get_audit(self, audit_id: UUID) -> FrameworkAuditSnapshot:
        for record in self._all_records():
            for run in record.review_runs:
                if run.audit is not None and run.audit.audit_id == audit_id:
                    return run.audit
        raise FrameworkNotFound(str(audit_id))

    def confirm(
        self,
        *,
        framework_id: UUID,
        expected_version: int,
        audit_id: UUID,
        resolutions: tuple[AuditResolution, ...],
    ) -> ConfirmedFrameworkSnapshot:
        record = self._record(framework_id)
        self._require_version(record, expected_version)
        audit = self._audit(record, audit_id)
        if audit.is_stale or audit.framework_version != expected_version:
            raise FrameworkAuditConflict("a fresh review is required")
        self._validate_resolution_ids(audit, resolutions)
        resolution_by_id = {item.finding_id: item for item in resolutions}
        blocked = tuple(
            finding.finding_id
            for finding in audit.findings
            if finding.blocking
            and (
                finding.finding_id not in resolution_by_id
                or resolution_by_id[finding.finding_id].action
                is not AuditResolutionAction.OVERRIDE
            )
        )
        if blocked:
            raise FrameworkConfirmationBlocked(blocked)
        unresolved = tuple(
            finding.finding_id
            for finding in audit.findings
            if resolution_by_id.get(finding.finding_id) is not None
            and resolution_by_id[finding.finding_id].action
            in {
                AuditResolutionAction.REJECT,
                AuditResolutionAction.DEFER,
                AuditResolutionAction.OVERRIDE,
            }
        )
        confirmed = ConfirmedFrameworkSnapshot(
            framework=record.current,
            audit=audit,
            resolutions=resolutions,
            confirmed_at=self._clock(),
            unresolved_finding_ids=unresolved,
        )
        updated = replace(record, confirmed=confirmed)
        if self._repository.save(updated, expected_version=expected_version) is None:
            raise FrameworkRevisionConflict("framework revision is stale")
        return confirmed

    def submit_resolutions(
        self,
        *,
        framework_id: UUID,
        expected_version: int,
        expected_revision_id: UUID,
        audit_id: UUID,
        resolutions: tuple[AuditResolution, ...],
    ) -> AuditResolutionSetSnapshot:
        record = self._record(framework_id)
        self._require_version(record, expected_version)
        if record.current.revision_id != expected_revision_id:
            raise FrameworkRevisionConflict("framework revision is stale")
        audit = self._audit(record, audit_id)
        if audit.is_stale or audit.framework_version != expected_version:
            raise FrameworkAuditConflict("audit does not apply to the current revision")
        self._validate_resolution_ids(audit, resolutions)
        resolution_by_id = {item.finding_id: item for item in resolutions}
        unresolved_blocking = any(
            finding.blocking
            and (
                resolution_by_id.get(finding.finding_id) is None
                or resolution_by_id[finding.finding_id].action
                is not AuditResolutionAction.OVERRIDE
            )
            for finding in audit.findings
        )
        snapshot = AuditResolutionSetSnapshot(
            resolution_set_id=self._id_factory(),
            framework_id=framework_id,
            revision_id=expected_revision_id,
            version=len(record.resolution_sets) + 1,
            audit_id=audit_id,
            resolutions=resolutions,
            unresolved_blocking=unresolved_blocking,
            created_at=self._clock(),
        )
        updated = replace(
            record,
            resolution_sets=(*record.resolution_sets, snapshot),
        )
        if self._repository.save(updated, expected_version=expected_version) is None:
            raise FrameworkRevisionConflict("framework revision is stale")
        return snapshot

    def _record(self, framework_id: UUID) -> FrameworkRecord:
        record = self._repository.get(framework_id)
        if record is None:
            raise FrameworkNotFound(str(framework_id))
        return record

    def _all_records(self) -> tuple[FrameworkRecord, ...]:
        values = getattr(self._repository, "records", None)
        if isinstance(values, dict):
            return tuple(values.values())
        iterator = getattr(self._repository, "all", None)
        if iterator is not None:
            return tuple(iterator())
        return ()

    @staticmethod
    def _require_version(record: FrameworkRecord, expected_version: int) -> None:
        if record.current.version != expected_version:
            raise FrameworkRevisionConflict("framework revision is stale")

    @staticmethod
    def _audit(record: FrameworkRecord, audit_id: UUID) -> FrameworkAuditSnapshot:
        for run in record.review_runs:
            if run.audit is not None and run.audit.audit_id == audit_id:
                return run.audit
        raise FrameworkAuditConflict("audit does not belong to this framework")

    @staticmethod
    def _validate_resolution_ids(
        audit: FrameworkAuditSnapshot,
        resolutions: tuple[AuditResolution, ...],
    ) -> None:
        finding_ids = {finding.finding_id for finding in audit.findings}
        if any(resolution.finding_id not in finding_ids for resolution in resolutions):
            raise FrameworkAuditConflict("resolution references an unknown finding")
        if any(not resolution.reason.strip() for resolution in resolutions):
            raise FrameworkAuditConflict("resolution reason is required")
