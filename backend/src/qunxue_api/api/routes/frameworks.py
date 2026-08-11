from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from qunxue_api.api.contracts.common import (
    ErrorResponse,
    ModelCapability,
    ModelMetadata,
    TraceMetadata,
)
from qunxue_api.api.contracts.frameworks import (
    AuditFindingResponse,
    AuditResolutionInput,
    AuditResolutionSetResponse,
    ConceptMappingContract,
    ConfirmedFrameworkResponse,
    ConfirmFrameworkRequest,
    CreateFrameworkRequest,
    CurrentFrameworkAuditResponse,
    CurrentFrameworkFindingResponse,
    FormalFrameworkExportResponse,
    FrameworkAction,
    FrameworkAuditResponse,
    FrameworkDraftContract,
    FrameworkEvidenceRequirementContract,
    FrameworkInputResponse,
    FrameworkResponse,
    FrameworkReviewAction,
    FrameworkReviewResponse,
    FrameworkStatus,
    FrameworkVersionPageResponse,
    InferenceLinkContract,
    MethodIntentContract,
    MethodPlanContract,
    RetryFrameworkReviewRequest,
    StartFrameworkReviewRequest,
    SubmitAuditResolutionsRequest,
    UpdateFrameworkRequest,
)
from qunxue_api.api.dependencies import (
    CurrentSessionDependency,
    OwnedResearchTaskDependency,
    ResearchFrameworkApplicationDependency,
    ResearchTaskServiceDependency,
    get_current_session,
)
from qunxue_api.api.routes.stubs import IdempotencyKey, not_implemented_response
from qunxue_api.api.theory_plan_mapper import confirmed_theory_plan_response
from qunxue_api.modules.research_framework import (
    AuditResolution,
    AuditResolutionAction,
    ConfirmedFrameworkSnapshot,
    FrameworkAuditSnapshot,
    FrameworkRecord,
    FrameworkReviewRunSnapshot,
    FrameworkVersionSnapshot,
    ResearchFrameworkDraft,
)

router = APIRouter(
    tags=["frameworks"],
    responses={422: {"model": ErrorResponse}},
    dependencies=[Depends(get_current_session)],
)


@router.post(
    "/api/research-tasks/{task_id}/frameworks",
    operation_id="create_framework",
    response_model=FrameworkResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorResponse}},
)
def create_framework(
    task_id: UUID,
    owned_task: OwnedResearchTaskDependency,
    payload: CreateFrameworkRequest,
    _idempotency_key: IdempotencyKey,
    request: Request,
    application: ResearchFrameworkApplicationDependency,
) -> FrameworkResponse:
    if owned_task.task_id != task_id:
        raise RuntimeError("owned task dependency returned a different task")
    framework = application.create(
        task=owned_task,
        expected_task_version=payload.expected_task_version,
        theory_plan_id=payload.theory_plan_id,
        theory_plan_version=payload.theory_plan_version,
        original_research_question=payload.original_research_question,
        confirmed_research_question=payload.confirmed_research_question,
        question_adjustment_reason=payload.question_adjustment_reason,
        research_object=payload.research_object,
        analysis_unit=payload.analysis_unit,
        context=payload.context,
        method_intent=_method_intent(payload.method_intent),
    )
    return _framework_response(
        application.record(framework.framework_id),
        framework,
        model=_latest_model(request, framework.task_id, "framework_draft"),
        contract_version=request.app.state.settings.contract_version,
    )


@router.get(
    "/api/frameworks/{framework_id}",
    operation_id="get_framework",
    response_model=FrameworkResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_framework(
    framework_id: UUID,
    request: Request,
    application: ResearchFrameworkApplicationDependency,
) -> FrameworkResponse:
    record = application.record(framework_id)
    return _framework_response(
        record,
        record.current,
        model=_latest_model(request, record.task_id, "framework_draft"),
        contract_version=request.app.state.settings.contract_version,
    )


@router.get(
    "/api/frameworks/{framework_id}/versions",
    operation_id="list_framework_versions",
    response_model=FrameworkVersionPageResponse,
    responses={404: {"model": ErrorResponse}},
)
def list_framework_versions(
    framework_id: UUID,
    request: Request,
    application: ResearchFrameworkApplicationDependency,
) -> FrameworkVersionPageResponse:
    record = application.record(framework_id)
    model = _latest_model(request, record.task_id, "framework_draft")
    return FrameworkVersionPageResponse(
        framework_id=framework_id,
        versions=[
            _framework_response(
                record,
                version,
                model=model if version.version == 1 else None,
                contract_version=request.app.state.settings.contract_version,
            )
            for version in record.versions
        ],
    )


@router.patch(
    "/api/frameworks/{framework_id}",
    operation_id="update_framework",
    response_model=FrameworkResponse,
    responses={409: {"model": ErrorResponse}},
)
def update_framework(
    framework_id: UUID,
    payload: UpdateFrameworkRequest,
    _idempotency_key: IdempotencyKey,
    request: Request,
    application: ResearchFrameworkApplicationDependency,
) -> FrameworkResponse:
    revised = application.revise(
        framework_id=framework_id,
        expected_revision_id=payload.expected_revision_id,
        expected_version=payload.expected_version,
        revised_draft=_draft(payload.draft),
        revision_reason=payload.revision_reason,
    )
    return _framework_response(
        application.record(framework_id),
        revised,
        model=None,
        contract_version=request.app.state.settings.contract_version,
    )


@router.post(
    "/api/frameworks/{framework_id}/reviews",
    operation_id="start_framework_review",
    response_model=FrameworkReviewResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorResponse}},
)
def start_framework_review(
    framework_id: UUID,
    payload: StartFrameworkReviewRequest,
    _idempotency_key: IdempotencyKey,
    request: Request,
    application: ResearchFrameworkApplicationDependency,
) -> FrameworkReviewResponse:
    review = application.start_review(
        framework_id=framework_id,
        expected_revision_id=payload.expected_revision_id,
        expected_version=payload.expected_version,
    )
    task_id = application.record(framework_id).task_id
    return _review_response(
        review,
        model=_latest_model(request, task_id, "framework_audit"),
        contract_version=request.app.state.settings.contract_version,
    )


@router.get(
    "/api/frameworks/{framework_id}/reviews/{review_run_id}",
    operation_id="get_framework_review",
    response_model=FrameworkReviewResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_framework_review(
    framework_id: UUID,
    review_run_id: UUID,
    request: Request,
    application: ResearchFrameworkApplicationDependency,
) -> FrameworkReviewResponse:
    review = application.get_review(framework_id, review_run_id)
    task_id = application.record(framework_id).task_id
    return _review_response(
        review,
        model=_latest_model(request, task_id, "framework_audit"),
        contract_version=request.app.state.settings.contract_version,
    )


@router.post(
    "/api/frameworks/{framework_id}/reviews/{review_run_id}/retry",
    operation_id="retry_framework_review",
    response_model=FrameworkReviewResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def retry_framework_review(
    framework_id: UUID,
    review_run_id: UUID,
    payload: RetryFrameworkReviewRequest,
    _idempotency_key: IdempotencyKey,
    request: Request,
    application: ResearchFrameworkApplicationDependency,
) -> FrameworkReviewResponse:
    review = application.retry_review(
        framework_id=framework_id,
        review_run_id=review_run_id,
        expected_revision_id=payload.expected_revision_id,
        expected_review_version=payload.expected_review_version,
    )
    task_id = application.record(framework_id).task_id
    return _review_response(
        review,
        model=_latest_model(request, task_id, "framework_audit"),
        contract_version=request.app.state.settings.contract_version,
    )


@router.post(
    "/api/frameworks/{framework_id}/audit-resolutions",
    operation_id="submit_audit_resolutions",
    response_model=AuditResolutionSetResponse,
    responses={409: {"model": ErrorResponse}},
)
def submit_audit_resolutions(
    framework_id: UUID,
    payload: SubmitAuditResolutionsRequest,
    _idempotency_key: IdempotencyKey,
    application: ResearchFrameworkApplicationDependency,
) -> AuditResolutionSetResponse:
    snapshot = application.submit_resolutions(
        framework_id=framework_id,
        expected_revision_id=payload.expected_revision_id,
        expected_version=payload.expected_version,
        audit_id=payload.audit_id,
        resolutions=tuple(_resolution(item) for item in payload.resolutions),
    )
    framework = application.get(framework_id)
    return AuditResolutionSetResponse(
        resolution_set_id=snapshot.resolution_set_id,
        framework_id=framework_id,
        revision_id=snapshot.revision_id,
        version=snapshot.version,
        allowed_actions=[FrameworkAction.UPDATE, FrameworkAction.CONFIRM],
        knowledge_release_id=(
            framework.input.theory_plan.knowledge_release.knowledge_release_id
        ),
        resolutions=[
            AuditResolutionInput(
                finding_id=item.finding_id,
                action=item.action.value,
                reason=item.reason,
            )
            for item in snapshot.resolutions
        ],
        unresolved_blocking=snapshot.unresolved_blocking,
    )


@router.post(
    "/api/frameworks/{framework_id}/confirm",
    operation_id="confirm_framework",
    response_model=ConfirmedFrameworkResponse,
    responses={409: {"model": ErrorResponse}},
)
def confirm_framework(
    framework_id: UUID,
    payload: ConfirmFrameworkRequest,
    _idempotency_key: IdempotencyKey,
    request: Request,
    current: CurrentSessionDependency,
    task_service: ResearchTaskServiceDependency,
    application: ResearchFrameworkApplicationDependency,
) -> ConfirmedFrameworkResponse:
    framework = application.get(framework_id)
    task = task_service.get(framework.task_id, user_id=current.user.user_id)
    confirmed = application.confirm(
        task=task,
        framework_id=framework_id,
        expected_revision_id=payload.expected_revision_id,
        expected_version=payload.expected_version,
        audit_id=payload.audit_id,
        resolutions=tuple(_resolution(item) for item in payload.resolutions),
    )
    return _confirmed_response(
        confirmed,
        contract_version=request.app.state.settings.contract_version,
    )


@router.get(
    "/api/frameworks/{framework_id}/export",
    operation_id="export_confirmed_framework",
    response_model=FormalFrameworkExportResponse,
    responses={409: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def export_confirmed_framework(
    framework_id: UUID,
    application: ResearchFrameworkApplicationDependency,
):
    application.get(framework_id)
    return not_implemented_response()


def _method_intent(value: MethodIntentContract):
    from qunxue_api.modules.research_framework import MethodIntentSnapshot

    return MethodIntentSnapshot(
        method_kind=value.method_kind,
        constraints=tuple(value.constraints),
        source=value.source,
    )


def _draft(value: FrameworkDraftContract) -> ResearchFrameworkDraft:
    from qunxue_api.modules.research_framework import (
        ConceptMappingDraft,
        FrameworkEvidenceRequirementDraft,
        InferenceLinkDraft,
        MethodPlanDraft,
    )

    return ResearchFrameworkDraft(
        concept_mappings=tuple(
            ConceptMappingDraft(
                candidate_id=item.candidate_id,
                theory_concept=item.theory_concept,
                meaning_in_study=item.meaning_in_study,
                empirical_indicators=tuple(item.empirical_indicators),
                unresolved_questions=tuple(item.unresolved_questions),
            ) for item in value.concept_mappings
        ),
        evidence_requirements=tuple(
            FrameworkEvidenceRequirementDraft(
                requirement_id=item.requirement_id,
                related_candidate_ids=tuple(item.related_candidate_ids),
                purpose=item.purpose,
                required_material=item.required_material,
                supporting_signal=item.supporting_signal,
                excluding_signal=item.excluding_signal,
                distinguishing_signal=item.distinguishing_signal,
                current_gap=item.current_gap,
            ) for item in value.evidence_requirements
        ),
        inference_links=tuple(
            InferenceLinkDraft(
                from_ref=item.from_ref,
                to_ref=item.to_ref,
                relation=item.relation,
                rationale=item.rationale,
                unresolved=item.unresolved,
            ) for item in value.inference_links
        ),
        alternative_explanations=tuple(value.alternative_explanations),
        method_plan=(
            MethodPlanDraft(
                method_kind=value.method_plan.method_kind,
                rationale=value.method_plan.rationale,
                material_plan=tuple(value.method_plan.material_plan),
                analysis_plan=tuple(value.method_plan.analysis_plan),
                integration_points=tuple(value.method_plan.integration_points),
            ) if value.method_plan else None
        ),
        scope_and_limitations=tuple(value.scope_and_limitations),
        ethical_boundaries=tuple(value.ethical_boundaries),
        unresolved_items=tuple(value.unresolved_items),
        next_actions=tuple(value.next_actions),
    )


def _resolution(value: AuditResolutionInput) -> AuditResolution:
    return AuditResolution(
        finding_id=value.finding_id,
        action=AuditResolutionAction(value.action.value),
        reason=value.reason,
    )


def _framework_response(
    record: FrameworkRecord,
    framework: FrameworkVersionSnapshot,
    *,
    model: ModelMetadata | None,
    contract_version: str,
) -> FrameworkResponse:
    status_value, actions = _framework_status(record, framework)
    latest_audit = next(
        (
            run.audit for run in reversed(record.review_runs)
            if run.audit is not None and run.audit.framework_version == framework.version
        ),
        None,
    )
    input = framework.input
    return FrameworkResponse(
        framework_id=framework.framework_id,
        task_id=framework.task_id,
        revision_id=framework.revision_id,
        version=framework.version,
        status=status_value,
        allowed_actions=actions,
        knowledge_release_id=input.theory_plan.knowledge_release.knowledge_release_id,
        input=FrameworkInputResponse(
            theory_plan_id=input.theory_plan.theory_plan_id,
            theory_plan_version=input.theory_plan.version,
            theory_plan=confirmed_theory_plan_response(input.theory_plan),
            original_research_question=input.original_research_question,
            confirmed_research_question=input.confirmed_research_question,
            question_adjustment_reason=input.question_adjustment_reason,
            research_object=input.research_object,
            analysis_unit=input.analysis_unit,
            context=input.context,
            method_intent=MethodIntentContract(
                method_kind=input.method_intent.method_kind,
                constraints=list(input.method_intent.constraints),
                source=input.method_intent.source,
            ),
        ),
        draft=_draft_response(framework.draft),
        unresolved_blocking_audit=(
            latest_audit is not None
            and not latest_audit.is_stale
            and any(item.blocking for item in latest_audit.findings)
        ),
        model=model,
        content_origin=framework.content_origin,
        previous_revision_id=framework.previous_revision_id,
        revision_reason=framework.revision_reason,
        created_at=framework.created_at,
        audit=(
            CurrentFrameworkAuditResponse(
                audit_id=latest_audit.audit_id,
                revision_id=latest_audit.revision_id,
                overall_status=latest_audit.overall_status,
                findings=[
                    CurrentFrameworkFindingResponse(
                        finding_id=item.finding_id,
                        finding_type=item.finding_type,
                        severity=item.severity,
                        summary=item.summary,
                        reason=item.reason,
                        impact=item.impact,
                        recommendation=item.recommendation,
                        blocking=item.blocking,
                    )
                    for item in latest_audit.findings
                ],
                is_stale=latest_audit.is_stale,
            )
            if latest_audit is not None
            else None
        ),
    )


def _framework_status(record: FrameworkRecord, framework: FrameworkVersionSnapshot):
    if record.confirmed is not None and record.confirmed.framework.version == framework.version:
        return FrameworkStatus.CONFIRMED, []
    audit = next(
        (
            run.audit for run in reversed(record.review_runs)
            if run.audit is not None and run.audit.framework_version == framework.version
        ),
        None,
    )
    if audit is None or audit.is_stale:
        return FrameworkStatus.DRAFT, [FrameworkAction.UPDATE, FrameworkAction.START_REVIEW]
    if any(item.blocking for item in audit.findings):
        return FrameworkStatus.REVISION_REQUIRED, [FrameworkAction.UPDATE, FrameworkAction.CONFIRM]
    return FrameworkStatus.READY_TO_CONFIRM, [FrameworkAction.UPDATE, FrameworkAction.CONFIRM]


def _draft_response(draft: ResearchFrameworkDraft) -> FrameworkDraftContract:
    return FrameworkDraftContract(
        concept_mappings=[ConceptMappingContract(**{
            "candidate_id": item.candidate_id,
            "theory_concept": item.theory_concept,
            "meaning_in_study": item.meaning_in_study,
            "empirical_indicators": list(item.empirical_indicators),
            "unresolved_questions": list(item.unresolved_questions),
        }) for item in draft.concept_mappings],
        evidence_requirements=[FrameworkEvidenceRequirementContract(**{
            "requirement_id": item.requirement_id,
            "related_candidate_ids": list(item.related_candidate_ids),
            "purpose": item.purpose,
            "required_material": item.required_material,
            "supporting_signal": item.supporting_signal,
            "excluding_signal": item.excluding_signal,
            "distinguishing_signal": item.distinguishing_signal,
            "current_gap": item.current_gap,
        }) for item in draft.evidence_requirements],
        inference_links=[InferenceLinkContract(**{
            "from_ref": item.from_ref,
            "to_ref": item.to_ref,
            "relation": item.relation,
            "rationale": item.rationale,
            "unresolved": item.unresolved,
        }) for item in draft.inference_links],
        alternative_explanations=list(draft.alternative_explanations),
        method_plan=(
            MethodPlanContract(
                method_kind=draft.method_plan.method_kind,
                rationale=draft.method_plan.rationale,
                material_plan=list(draft.method_plan.material_plan),
                analysis_plan=list(draft.method_plan.analysis_plan),
                integration_points=list(draft.method_plan.integration_points),
            ) if draft.method_plan else None
        ),
        scope_and_limitations=list(draft.scope_and_limitations),
        ethical_boundaries=list(draft.ethical_boundaries),
        unresolved_items=list(draft.unresolved_items),
        next_actions=list(draft.next_actions),
    )


def _audit_response(audit: FrameworkAuditSnapshot, contract_version: str) -> FrameworkAuditResponse:
    return FrameworkAuditResponse(
        audit_id=audit.audit_id,
        framework_id=audit.framework_id,
        revision_id=audit.revision_id,
        framework_version=audit.framework_version,
        overall_status=audit.overall_status,
        findings=[AuditFindingResponse(
            finding_id=item.finding_id,
            finding_type=item.finding_type,
            severity=item.severity,
            summary=item.summary,
            reason=item.reason,
            impact=item.impact,
            recommendation=item.recommendation,
            blocking=item.blocking,
        ) for item in audit.findings],
        unresolved_blocking=any(item.blocking for item in audit.findings),
        contract_version=contract_version,
        is_stale=audit.is_stale,
    )


def _review_response(
    review: FrameworkReviewRunSnapshot,
    *,
    model: ModelMetadata | None,
    contract_version: str,
) -> FrameworkReviewResponse:
    audit = review.audit
    return FrameworkReviewResponse(
        review_run_id=review.review_run_id,
        framework_id=review.framework_id,
        revision_id=review.revision_id,
        version=review.version,
        status=review.status,
        allowed_actions=[FrameworkReviewAction.REFRESH],
        knowledge_release_id=(model.knowledge_release_id if model else "unknown"),
        audit=_audit_response(audit, contract_version) if audit else None,
        retry_of_review_run_id=review.retry_of_review_run_id,
        attempt=review.attempt,
        failure=None,
        model=model,
        contract_version=contract_version,
    )


def _confirmed_response(
    confirmed: ConfirmedFrameworkSnapshot,
    *,
    contract_version: str,
) -> ConfirmedFrameworkResponse:
    framework = confirmed.framework
    return ConfirmedFrameworkResponse(
        framework_id=framework.framework_id,
        task_id=framework.task_id,
        revision_id=framework.revision_id,
        version=framework.version,
        status="confirmed",
        allowed_actions=[],
        knowledge_release_id=framework.input.theory_plan.knowledge_release.knowledge_release_id,
        draft=_draft_response(framework.draft),
        audit=_audit_response(confirmed.audit, contract_version),
        resolutions=[AuditResolutionInput(
            finding_id=item.finding_id,
            action=item.action.value,
            reason=item.reason,
        ) for item in confirmed.resolutions],
        confirmed_at=confirmed.confirmed_at,
        contract_version=contract_version,
        unresolved_finding_ids=list(confirmed.unresolved_finding_ids),
    )


def _latest_model(
    request: Request,
    task_id: UUID,
    capability: str,
) -> ModelMetadata | None:
    invocation = next(
        (
            item for item in reversed(
                request.app.state.model_invocation_recorder.list_for_task(task_id)
            ) if item.capability.value == capability and item.error_code is None
        ),
        None,
    )
    if invocation is None:
        return None
    return ModelMetadata(
        provider=invocation.provider,
        model_version=invocation.model_version,
        capability=ModelCapability(invocation.capability_tier),
        degraded=invocation.degraded,
        knowledge_release_id=invocation.knowledge_release_id,
        trace=TraceMetadata(
            trace_id=invocation.trace_id,
            request_id=invocation.request_id,
            contract_version=invocation.contract_version,
        ),
    )
