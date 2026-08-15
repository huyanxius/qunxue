from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from qunxue_api.adapters.sqlite.research_framework_model import ResearchFrameworkRow
from qunxue_api.modules.research_framework import (
    AuditFindingSeverity,
    AuditFindingSnapshot,
    AuditFindingType,
    AuditOverallStatus,
    AuditResolution,
    AuditResolutionAction,
    AuditResolutionSetSnapshot,
    ConceptMappingDraft,
    ConfirmedFrameworkSnapshot,
    FrameworkAuditSnapshot,
    FrameworkContentOrigin,
    FrameworkEvidenceRequirementDraft,
    FrameworkRecord,
    FrameworkReviewFailureCode,
    FrameworkReviewFailureSnapshot,
    FrameworkReviewRunSnapshot,
    FrameworkReviewRunStatus,
    FrameworkVersionSnapshot,
    InferenceLinkDraft,
    MethodIntentSnapshot,
    MethodPlanDraft,
    ResearchFrameworkDraft,
    ResearchFrameworkDraftInput,
)
from qunxue_api.modules.theory_matching import ConfirmedTheoryPlanReader


class SqliteFrameworkRepository:
    def __init__(
        self,
        session: Session,
        *,
        user_id: UUID,
        theory_plans: ConfirmedTheoryPlanReader,
    ) -> None:
        self._session = session
        self._user_id = user_id
        self._theory_plans = theory_plans

    def add(self, record: FrameworkRecord) -> FrameworkRecord:
        now = record.current.created_at or datetime.now(UTC)
        self._session.add(
            ResearchFrameworkRow(
                framework_id=str(record.framework_id),
                task_id=str(record.task_id),
                user_id=str(self._user_id),
                current_version=record.current.version,
                record=_record_payload(record),
                created_at=now,
                updated_at=now,
            )
        )
        self._session.flush()
        return record

    def get(self, framework_id: UUID) -> FrameworkRecord | None:
        row = self._session.scalar(
            select(ResearchFrameworkRow).where(
                ResearchFrameworkRow.framework_id == str(framework_id),
                ResearchFrameworkRow.user_id == str(self._user_id),
            )
        )
        return self._from_row(row) if row is not None else None

    def save(
        self,
        record: FrameworkRecord,
        *,
        expected_version: int,
    ) -> FrameworkRecord | None:
        result = self._session.execute(
            update(ResearchFrameworkRow)
            .where(
                ResearchFrameworkRow.framework_id == str(record.framework_id),
                ResearchFrameworkRow.user_id == str(self._user_id),
                ResearchFrameworkRow.current_version == expected_version,
            )
            .values(
                current_version=record.current.version,
                record=_record_payload(record),
                updated_at=datetime.now(UTC),
            )
        )
        if result.rowcount != 1:
            return None
        self._session.flush()
        return record

    def all(self) -> tuple[FrameworkRecord, ...]:
        rows = self._session.scalars(
            select(ResearchFrameworkRow).where(
                ResearchFrameworkRow.user_id == str(self._user_id)
            )
        )
        return tuple(self._from_row(row) for row in rows)

    def _from_row(self, row: ResearchFrameworkRow) -> FrameworkRecord:
        payload = row.record
        versions = tuple(
            _version_from_payload(item, self._theory_plans)
            for item in _dict_list(payload["versions"])
        )
        reviews = tuple(
            _review_from_payload(item) for item in _dict_list(payload["review_runs"])
        )
        resolution_sets = tuple(
            _resolution_set_from_payload(item)
            for item in _dict_list(payload.get("resolution_sets", []))
        )
        confirmed_payload = payload.get("confirmed")
        confirmed = None
        if isinstance(confirmed_payload, dict):
            audit_id = UUID(str(confirmed_payload["audit_id"]))
            audit = next(
                run.audit
                for run in reviews
                if run.audit is not None and run.audit.audit_id == audit_id
            )
            version = next(
                item
                for item in versions
                if item.version == int(confirmed_payload["framework_version"])
            )
            confirmed = ConfirmedFrameworkSnapshot(
                framework=version,
                audit=audit,
                resolutions=tuple(
                    _resolution_from_payload(item)
                    for item in _dict_list(confirmed_payload["resolutions"])
                ),
                confirmed_at=_datetime(confirmed_payload["confirmed_at"]),
                unresolved_finding_ids=tuple(
                    UUID(str(value))
                    for value in confirmed_payload["unresolved_finding_ids"]
                ),
            )
        return FrameworkRecord(
            framework_id=UUID(row.framework_id),
            task_id=UUID(row.task_id),
            versions=versions,
            review_runs=reviews,
            resolution_sets=resolution_sets,
            confirmed=confirmed,
        )


def _record_payload(record: FrameworkRecord) -> dict[str, object]:
    confirmed = record.confirmed
    return {
        "versions": [_version_payload(item) for item in record.versions],
        "review_runs": [_review_payload(item) for item in record.review_runs],
        "resolution_sets": [
            _resolution_set_payload(item) for item in record.resolution_sets
        ],
        "confirmed": (
            {
                "framework_version": confirmed.framework.version,
                "audit_id": str(confirmed.audit.audit_id),
                "resolutions": [
                    _resolution_payload(item) for item in confirmed.resolutions
                ],
                "confirmed_at": confirmed.confirmed_at.isoformat(),
                "unresolved_finding_ids": [
                    str(value) for value in confirmed.unresolved_finding_ids
                ],
            }
            if confirmed is not None
            else None
        ),
    }


def _version_payload(version: FrameworkVersionSnapshot) -> dict[str, object]:
    input = version.input
    return {
        "framework_id": str(version.framework_id),
        "task_id": str(version.task_id),
        "version": version.version,
        "revision_id": str(version.revision_id),
        "previous_revision_id": (
            str(version.previous_revision_id) if version.previous_revision_id else None
        ),
        "content_origin": version.content_origin.value,
        "revision_reason": version.revision_reason,
        "created_at": version.created_at.isoformat() if version.created_at else None,
        "input": {
            "theory_plan_id": str(input.theory_plan.theory_plan_id),
            "theory_plan_version": input.theory_plan.version,
            "original_research_question": input.original_research_question,
            "confirmed_research_question": input.confirmed_research_question,
            "question_adjustment_reason": input.question_adjustment_reason,
            "research_object": input.research_object,
            "analysis_unit": input.analysis_unit,
            "context": input.context,
            "method_intent": {
                "method_kind": input.method_intent.method_kind,
                "constraints": list(input.method_intent.constraints),
                "source": input.method_intent.source,
            },
        },
        "draft": _draft_payload(version.draft),
    }


def _version_from_payload(
    payload: dict[str, object],
    theory_plans: ConfirmedTheoryPlanReader,
) -> FrameworkVersionSnapshot:
    input_payload = _dict(payload["input"])
    theory_plan_id = UUID(str(input_payload["theory_plan_id"]))
    plan = theory_plans.get_confirmed(theory_plan_id)
    if plan is None or plan.version != int(input_payload["theory_plan_version"]):
        raise RuntimeError("persisted framework references a missing theory plan")
    method = _dict(input_payload["method_intent"])
    input_snapshot = ResearchFrameworkDraftInput(
        theory_plan=plan,
        original_research_question=str(input_payload["original_research_question"]),
        confirmed_research_question=str(input_payload["confirmed_research_question"]),
        question_adjustment_reason=_optional(input_payload.get("question_adjustment_reason")),
        research_object=str(input_payload["research_object"]),
        analysis_unit=_optional(input_payload.get("analysis_unit")),
        context=_optional(input_payload.get("context")),
        method_intent=MethodIntentSnapshot(
            method_kind=_optional(method.get("method_kind")),
            constraints=_strings(method["constraints"]),
            source=str(method["source"]),
        ),
    )
    return FrameworkVersionSnapshot(
        framework_id=UUID(str(payload["framework_id"])),
        task_id=UUID(str(payload["task_id"])),
        version=int(payload["version"]),
        input=input_snapshot,
        draft=_draft_from_payload(_dict(payload["draft"])),
        revision_id=UUID(str(payload["revision_id"])),
        previous_revision_id=(
            UUID(str(payload["previous_revision_id"]))
            if payload.get("previous_revision_id")
            else None
        ),
        content_origin=FrameworkContentOrigin(str(payload["content_origin"])),
        revision_reason=_optional(payload.get("revision_reason")),
        created_at=(
            _datetime(payload["created_at"]) if payload.get("created_at") else None
        ),
    )


def _draft_payload(draft: ResearchFrameworkDraft) -> dict[str, object]:
    return {
        "concept_mappings": [
            {
                "candidate_id": str(item.candidate_id),
                "theory_concept": item.theory_concept,
                "meaning_in_study": item.meaning_in_study,
                "empirical_indicators": list(item.empirical_indicators),
                "unresolved_questions": list(item.unresolved_questions),
            }
            for item in draft.concept_mappings
        ],
        "evidence_requirements": [
            {
                "requirement_id": item.requirement_id,
                "related_candidate_ids": [str(value) for value in item.related_candidate_ids],
                "purpose": item.purpose,
                "required_material": item.required_material,
                "supporting_signal": item.supporting_signal,
                "excluding_signal": item.excluding_signal,
                "distinguishing_signal": item.distinguishing_signal,
                "current_gap": item.current_gap,
            }
            for item in draft.evidence_requirements
        ],
        "inference_links": [
            {
                "from_ref": item.from_ref,
                "to_ref": item.to_ref,
                "relation": item.relation,
                "rationale": item.rationale,
                "unresolved": item.unresolved,
            }
            for item in draft.inference_links
        ],
        "alternative_explanations": list(draft.alternative_explanations),
        "method_plan": (
            {
                "method_kind": draft.method_plan.method_kind,
                "rationale": draft.method_plan.rationale,
                "material_plan": list(draft.method_plan.material_plan),
                "analysis_plan": list(draft.method_plan.analysis_plan),
                "integration_points": list(draft.method_plan.integration_points),
            }
            if draft.method_plan else None
        ),
        "scope_and_limitations": list(draft.scope_and_limitations),
        "ethical_boundaries": list(draft.ethical_boundaries),
        "unresolved_items": list(draft.unresolved_items),
        "next_actions": list(draft.next_actions),
    }


def _draft_from_payload(payload: dict[str, object]) -> ResearchFrameworkDraft:
    raw_method = payload.get("method_plan")
    method = _dict(raw_method) if isinstance(raw_method, dict) else None
    return ResearchFrameworkDraft(
        concept_mappings=tuple(
            ConceptMappingDraft(
                candidate_id=UUID(str(item["candidate_id"])),
                theory_concept=str(item["theory_concept"]),
                meaning_in_study=str(item["meaning_in_study"]),
                empirical_indicators=_strings(item["empirical_indicators"]),
                unresolved_questions=_strings(item["unresolved_questions"]),
            )
            for item in _dict_list(payload["concept_mappings"])
        ),
        evidence_requirements=tuple(
            FrameworkEvidenceRequirementDraft(
                requirement_id=str(item["requirement_id"]),
                related_candidate_ids=tuple(
                    UUID(str(value)) for value in item["related_candidate_ids"]
                ),
                purpose=str(item["purpose"]),
                required_material=str(item["required_material"]),
                supporting_signal=str(item["supporting_signal"]),
                excluding_signal=str(item["excluding_signal"]),
                distinguishing_signal=_optional(item.get("distinguishing_signal")),
                current_gap=_optional(item.get("current_gap")),
            )
            for item in _dict_list(payload["evidence_requirements"])
        ),
        inference_links=tuple(
            InferenceLinkDraft(
                from_ref=str(item["from_ref"]),
                to_ref=str(item["to_ref"]),
                relation=str(item["relation"]),
                rationale=str(item["rationale"]),
                unresolved=bool(item["unresolved"]),
            )
            for item in _dict_list(payload["inference_links"])
        ),
        alternative_explanations=_strings(payload["alternative_explanations"]),
        method_plan=(
            MethodPlanDraft(
                method_kind=str(method["method_kind"]),
                rationale=str(method["rationale"]),
                material_plan=_strings(method["material_plan"]),
                analysis_plan=_strings(method["analysis_plan"]),
                integration_points=_strings(method["integration_points"]),
            )
            if method else None
        ),
        scope_and_limitations=_strings(payload["scope_and_limitations"]),
        ethical_boundaries=_strings(payload["ethical_boundaries"]),
        unresolved_items=_strings(payload["unresolved_items"]),
        next_actions=_strings(payload["next_actions"]),
    )


def _review_payload(review: FrameworkReviewRunSnapshot) -> dict[str, object]:
    return {
        "review_run_id": str(review.review_run_id),
        "framework_id": str(review.framework_id),
        "framework_version": review.framework_version,
        "trace_id": str(review.trace_id),
        "idempotency_key": review.idempotency_key,
        "version": review.version,
        "status": review.status.value,
        "audit": _audit_payload(review.audit) if review.audit else None,
        "revision_id": str(review.revision_id) if review.revision_id else None,
        "retry_of_review_run_id": (
            str(review.retry_of_review_run_id) if review.retry_of_review_run_id else None
        ),
        "attempt": review.attempt,
        "failure": (
            {
                "code": review.failure.code.value,
                "message": review.failure.message,
                "retryable": review.failure.retryable,
                "requested_source_ids": list(review.failure.requested_source_ids),
            }
            if review.failure else None
        ),
    }


def _review_from_payload(payload: dict[str, object]) -> FrameworkReviewRunSnapshot:
    raw_failure = payload.get("failure")
    failure = _dict(raw_failure) if isinstance(raw_failure, dict) else None
    raw_audit = payload.get("audit")
    return FrameworkReviewRunSnapshot(
        review_run_id=UUID(str(payload["review_run_id"])),
        framework_id=UUID(str(payload["framework_id"])),
        framework_version=int(payload["framework_version"]),
        trace_id=UUID(str(payload["trace_id"])),
        idempotency_key=str(payload["idempotency_key"]),
        version=int(payload["version"]),
        status=FrameworkReviewRunStatus(str(payload["status"])),
        audit=_audit_from_payload(_dict(raw_audit)) if isinstance(raw_audit, dict) else None,
        revision_id=UUID(str(payload["revision_id"])) if payload.get("revision_id") else None,
        retry_of_review_run_id=(
            UUID(str(payload["retry_of_review_run_id"]))
            if payload.get("retry_of_review_run_id") else None
        ),
        attempt=int(payload["attempt"]),
        failure=(
            FrameworkReviewFailureSnapshot(
                code=FrameworkReviewFailureCode(str(failure["code"])),
                message=str(failure["message"]),
                retryable=bool(failure["retryable"]),
                requested_source_ids=_strings(failure["requested_source_ids"]),
            )
            if failure else None
        ),
    )


def _audit_payload(audit: FrameworkAuditSnapshot) -> dict[str, object]:
    return {
        "audit_id": str(audit.audit_id),
        "framework_id": str(audit.framework_id),
        "framework_version": audit.framework_version,
        "overall_status": audit.overall_status.value,
        "revision_id": str(audit.revision_id) if audit.revision_id else None,
        "is_stale": audit.is_stale,
        "findings": [
            {
                "finding_id": str(item.finding_id),
                "summary": item.summary,
                "reason": item.reason,
                "impact": item.impact,
                "recommendation": item.recommendation,
                "blocking": item.blocking,
                "finding_type": item.finding_type.value,
                "severity": item.severity.value,
            }
            for item in audit.findings
        ],
    }


def _audit_from_payload(payload: dict[str, object]) -> FrameworkAuditSnapshot:
    return FrameworkAuditSnapshot(
        audit_id=UUID(str(payload["audit_id"])),
        framework_id=UUID(str(payload["framework_id"])),
        framework_version=int(payload["framework_version"]),
        overall_status=AuditOverallStatus(str(payload["overall_status"])),
        findings=tuple(
            AuditFindingSnapshot(
                finding_id=UUID(str(item["finding_id"])),
                summary=str(item["summary"]),
                reason=str(item["reason"]),
                impact=str(item["impact"]),
                recommendation=str(item["recommendation"]),
                blocking=bool(item["blocking"]),
                finding_type=AuditFindingType(str(item["finding_type"])),
                severity=AuditFindingSeverity(str(item["severity"])),
            )
            for item in _dict_list(payload["findings"])
        ),
        revision_id=UUID(str(payload["revision_id"])) if payload.get("revision_id") else None,
        is_stale=bool(payload["is_stale"]),
    )


def _resolution_payload(resolution: AuditResolution) -> dict[str, object]:
    return {
        "finding_id": str(resolution.finding_id),
        "action": resolution.action.value,
        "reason": resolution.reason,
    }


def _resolution_from_payload(payload: dict[str, object]) -> AuditResolution:
    return AuditResolution(
        finding_id=UUID(str(payload["finding_id"])),
        action=AuditResolutionAction(str(payload["action"])),
        reason=str(payload["reason"]),
    )


def _resolution_set_payload(
    snapshot: AuditResolutionSetSnapshot,
) -> dict[str, object]:
    return {
        "resolution_set_id": str(snapshot.resolution_set_id),
        "framework_id": str(snapshot.framework_id),
        "revision_id": str(snapshot.revision_id),
        "version": snapshot.version,
        "audit_id": str(snapshot.audit_id),
        "resolutions": [_resolution_payload(item) for item in snapshot.resolutions],
        "unresolved_blocking": snapshot.unresolved_blocking,
        "created_at": snapshot.created_at.isoformat(),
    }


def _resolution_set_from_payload(
    payload: dict[str, object],
) -> AuditResolutionSetSnapshot:
    return AuditResolutionSetSnapshot(
        resolution_set_id=UUID(str(payload["resolution_set_id"])),
        framework_id=UUID(str(payload["framework_id"])),
        revision_id=UUID(str(payload["revision_id"])),
        version=int(payload["version"]),
        audit_id=UUID(str(payload["audit_id"])),
        resolutions=tuple(
            _resolution_from_payload(item)
            for item in _dict_list(payload["resolutions"])
        ),
        unresolved_blocking=bool(payload["unresolved_blocking"]),
        created_at=_datetime(payload["created_at"]),
    )


def _dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RuntimeError("invalid persisted framework object")
    return value


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise RuntimeError("invalid persisted framework collection")
    return value


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise RuntimeError("invalid persisted string collection")
    return tuple(str(item) for item in value)


def _optional(value: object) -> str | None:
    return None if value is None else str(value)


def _datetime(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
