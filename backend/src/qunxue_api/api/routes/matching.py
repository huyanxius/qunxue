from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from qunxue_api.api.contracts.common import (
    ErrorCode,
    ErrorDetail,
    ErrorResponse,
    ModelCapability,
    ModelMetadata,
    TraceMetadata,
)
from qunxue_api.api.contracts.knowledge import SourceRecordResponse
from qunxue_api.api.contracts.matching import (
    AcknowledgePartialMatchRequest,
    ConfirmedTheoryPlanResponse,
    ConfirmTheoryPlanRequest,
    CreateMatchRunRequest,
    CreateTheoryDecisionsRequest,
    DeferredTheoryPlanResponse,
    DeferTheoryPlanRequest,
    EvidenceReferenceResponse,
    MatchCandidatePageResponse,
    MatchRunAction,
    MatchRunResponse,
    RetryMatchCandidateRequest,
    TheoryCandidateResponse,
    TheoryDecisionPageResponse,
    TheoryDecisionRecordResponse,
    TheoryDecisionSetAction,
    TheoryDecisionSetResponse,
    TheoryPlanAction,
    TheoryRelationResponse,
    TheoryUseAssignmentResponse,
)
from qunxue_api.api.contracts.phenomena import (
    PhenomenonEvidenceReferenceResponse,
    PhenomenonSnapshotAction,
    PhenomenonSnapshotResponse,
)
from qunxue_api.api.dependencies import (
    CurrentSessionDependency,
    OwnedResearchTaskDependency,
    PhenomenonServiceDependency,
    TheoryMatchingApplicationDependency,
    get_current_session,
)
from qunxue_api.api.routes.stubs import IdempotencyKey, not_implemented_response
from qunxue_api.application import MatchingRequestConflict, MatchingSnapshotConflict
from qunxue_api.modules.theory_matching import (
    ConfirmedTheoryPlanSnapshot,
    DeferredTheoryPlanSnapshot,
    EvidenceItemSnapshot,
    MatchRunModelSnapshot,
    MatchRunSnapshot,
    MatchRunStatus,
    TheoryCandidateSnapshot,
    TheoryDecisionCommand,
    TheoryDecisionConflict,
    TheoryDecisionSetSnapshot,
    TheoryPlanGateViolation,
    TheoryRelationCommand,
    TheoryUseAssignment,
)

router = APIRouter(
    tags=["matching"],
    responses={422: {"model": ErrorResponse}},
    dependencies=[Depends(get_current_session)],
)


@router.post(
    "/api/research-tasks/{task_id}/match-runs",
    operation_id="create_match_run",
    response_model=MatchRunResponse,
    responses={409: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def create_match_run(
    task_id: UUID,
    owned_task: OwnedResearchTaskDependency,
    payload: CreateMatchRunRequest,
    idempotency_key: IdempotencyKey,
    phenomenon_service: PhenomenonServiceDependency,
    application: TheoryMatchingApplicationDependency,
) -> MatchRunResponse | JSONResponse:
    phenomenon = phenomenon_service.progress(task_id).confirmed
    if phenomenon is None:
        body = ErrorResponse(
            error=ErrorDetail(
                code=ErrorCode.PHENOMENON_UNCONFIRMED,
                message="Confirm the phenomenon before starting theory matching.",
                trace_id=str(uuid4()),
            )
        )
        return JSONResponse(status_code=409, content=body.model_dump(mode="json"))
    try:
        match_run = application.start(
            user_id=owned_task.user_id,
            task=owned_task,
            phenomenon=phenomenon,
            idempotency_key=idempotency_key,
            expected_task_version=payload.expected_task_version,
            phenomenon_query_id=payload.phenomenon_query_id,
            phenomenon_version=payload.phenomenon_version,
            requested_knowledge_release_id=payload.knowledge_release_id,
        )
    except (MatchingRequestConflict, MatchingSnapshotConflict) as error:
        body = ErrorResponse(
            error=ErrorDetail(
                code=ErrorCode.VALIDATION_ERROR,
                message=str(error),
                trace_id=str(uuid4()),
            )
        )
        return JSONResponse(status_code=409, content=body.model_dump(mode="json"))
    return _match_run_response(match_run)


@router.get(
    "/api/match-runs/{match_run_id}",
    operation_id="get_match_run",
    response_model=MatchRunResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def get_match_run(
    match_run_id: UUID,
    current: CurrentSessionDependency,
    application: TheoryMatchingApplicationDependency,
) -> MatchRunResponse | JSONResponse:
    try:
        match_run = application.get(match_run_id, user_id=current.user.user_id)
    except LookupError:
        body = ErrorResponse(
            error=ErrorDetail(
                code=ErrorCode.NOT_FOUND,
                message="Match run was not found.",
                trace_id=str(uuid4()),
            )
        )
        return JSONResponse(status_code=404, content=body.model_dump(mode="json"))
    return _match_run_response(match_run)


@router.get(
    "/api/match-runs/{match_run_id}/candidates",
    operation_id="list_match_candidates",
    response_model=MatchCandidatePageResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def list_match_candidates(
    match_run_id: UUID,
    cursor: str | None = None,
    limit: int = Query(default=4, ge=1, le=8),
) -> JSONResponse:
    return not_implemented_response()


@router.post(
    "/api/match-runs/{match_run_id}/candidates/{candidate_id}/retry",
    operation_id="retry_match_candidate",
    response_model=TheoryCandidateResponse,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        501: {"model": ErrorResponse},
    },
)
def retry_match_candidate(
    match_run_id: UUID,
    candidate_id: UUID,
    payload: RetryMatchCandidateRequest,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return not_implemented_response()


@router.post(
    "/api/match-runs/{match_run_id}/partial-completion-acknowledgements",
    operation_id="acknowledge_partial_match",
    response_model=MatchRunResponse,
    responses={409: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def acknowledge_partial_match(
    match_run_id: UUID,
    payload: AcknowledgePartialMatchRequest,
    _idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return not_implemented_response()


@router.post(
    "/api/match-runs/{match_run_id}/decisions",
    operation_id="create_theory_decisions",
    response_model=TheoryDecisionSetResponse,
    status_code=201,
    responses={409: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def create_theory_decisions(
    match_run_id: UUID,
    payload: CreateTheoryDecisionsRequest,
    current: CurrentSessionDependency,
    application: TheoryMatchingApplicationDependency,
    idempotency_key: IdempotencyKey,
) -> TheoryDecisionSetResponse | JSONResponse:
    try:
        match_run = application.get(match_run_id, user_id=current.user.user_id)
        snapshot = application.record_decisions(
            match_run_id=match_run_id,
            user_id=current.user.user_id,
            idempotency_key=idempotency_key,
            expected_version=payload.expected_match_run_version,
            completion_basis=payload.completion_basis,
            decisions=tuple(
                TheoryDecisionCommand(
                    candidate_id=item.candidate_id,
                    candidate_version=item.candidate_version,
                    action=item.action,
                    reason=item.reason,
                    related_source_ids=tuple(item.related_source_ids),
                    related_candidate_ids=tuple(item.related_candidate_ids),
                    revised_applicability=item.revised_applicability,
                )
                for item in payload.decisions
            ),
            use_assignments=tuple(
                TheoryUseAssignment(
                    candidate_id=item.candidate_id,
                    role_code=item.role_code,
                    responsibility=item.responsibility,
                )
                for item in payload.use_assignments
            ),
            relations=tuple(
                TheoryRelationCommand(
                    candidate_ids=tuple(item.candidate_ids),
                    relation_kind=item.relation_kind,
                    explanation=item.explanation,
                    premise_compatibility=item.premise_compatibility,
                    supporting_evidence=tuple(item.supporting_evidence),
                    excluding_evidence=tuple(item.excluding_evidence),
                    distinguishing_evidence=tuple(item.distinguishing_evidence),
                )
                for item in payload.relations
            ),
        )
    except LookupError:
        return _matching_error(404, ErrorCode.NOT_FOUND, "Match run was not found.")
    except (MatchingRequestConflict, TheoryDecisionConflict) as error:
        return _matching_error(409, ErrorCode.VALIDATION_ERROR, str(error))
    return _decision_set_response(snapshot, match_run)


@router.get(
    "/api/match-runs/{match_run_id}/decisions",
    operation_id="list_theory_decisions",
    response_model=TheoryDecisionPageResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def list_theory_decisions(
    match_run_id: UUID,
    current: CurrentSessionDependency,
    application: TheoryMatchingApplicationDependency,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> TheoryDecisionPageResponse | JSONResponse:
    try:
        match_run = application.get(match_run_id, user_id=current.user.user_id)
        snapshots = application.list_decisions(
            match_run_id, user_id=current.user.user_id
        )
        confirmed = application.confirmed_plan(
            match_run_id, user_id=current.user.user_id
        )
        deferred = application.deferred_plan(
            match_run_id, user_id=current.user.user_id
        )
    except LookupError:
        return _matching_error(404, ErrorCode.NOT_FOUND, "Match run was not found.")
    return TheoryDecisionPageResponse(
        match_run_id=match_run_id,
        version=max((item.version for item in snapshots), default=0),
        allowed_actions=[],
        knowledge_release_id=match_run.knowledge_release.knowledge_release_id,
        decision_sets=[_decision_set_response(item, match_run) for item in snapshots],
        confirmed_plan=_confirmed_plan_response(confirmed) if confirmed else None,
        deferred_plan=_deferred_plan_response(deferred) if deferred else None,
        next_cursor=None,
    )


@router.post(
    "/api/match-runs/{match_run_id}/defer",
    operation_id="defer_theory_plan",
    response_model=DeferredTheoryPlanResponse,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        501: {"model": ErrorResponse},
    },
)
def defer_theory_plan(
    match_run_id: UUID,
    payload: DeferTheoryPlanRequest,
    current: CurrentSessionDependency,
    application: TheoryMatchingApplicationDependency,
    _idempotency_key: IdempotencyKey,
) -> DeferredTheoryPlanResponse | JSONResponse:
    try:
        snapshot = application.defer_plan(
            match_run_id=match_run_id,
            user_id=current.user.user_id,
            expected_version=payload.expected_match_run_version,
            reason=payload.reason,
        )
    except LookupError:
        return _matching_error(404, ErrorCode.NOT_FOUND, "Match run was not found.")
    except TheoryDecisionConflict as error:
        return _matching_error(409, ErrorCode.VALIDATION_ERROR, str(error))
    return _deferred_plan_response(snapshot)


def _deferred_plan_response(
    snapshot: DeferredTheoryPlanSnapshot,
) -> DeferredTheoryPlanResponse:
    return DeferredTheoryPlanResponse(
        task_id=snapshot.task_id,
        match_run_id=snapshot.match_run_id,
        version=snapshot.version,
        status="deferred",
        allowed_actions=[MatchRunAction.REFRESH],
        reason=snapshot.reason,
        deferred_at=snapshot.deferred_at,
    )


@router.post(
    "/api/decision-sets/{decision_set_id}/confirm",
    operation_id="confirm_theory_plan",
    response_model=ConfirmedTheoryPlanResponse,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        501: {"model": ErrorResponse},
    },
)
def confirm_theory_plan(
    decision_set_id: UUID,
    payload: ConfirmTheoryPlanRequest,
    current: CurrentSessionDependency,
    application: TheoryMatchingApplicationDependency,
    _idempotency_key: IdempotencyKey,
) -> ConfirmedTheoryPlanResponse | JSONResponse:
    try:
        snapshot = application.confirm_plan(
            decision_set_id=decision_set_id,
            user_id=current.user.user_id,
            expected_version=payload.expected_decision_set_version,
        )
    except LookupError:
        return _matching_error(404, ErrorCode.NOT_FOUND, "Decision set was not found.")
    except (
        MatchingRequestConflict,
        TheoryDecisionConflict,
        TheoryPlanGateViolation,
    ) as error:
        return _matching_error(409, ErrorCode.VALIDATION_ERROR, str(error))
    return _confirmed_plan_response(snapshot)


def _matching_error(status_code: int, code: ErrorCode, message: str) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorDetail(code=code, message=message, trace_id=str(uuid4()))
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


def _decision_set_response(
    snapshot: TheoryDecisionSetSnapshot,
    match_run: MatchRunSnapshot,
) -> TheoryDecisionSetResponse:
    return TheoryDecisionSetResponse(
        decision_set_id=snapshot.decision_set_id,
        match_run_id=snapshot.match_run_id,
        version=snapshot.version,
        allowed_actions=[TheoryDecisionSetAction.CONFIRM_THEORY_PLAN],
        knowledge_release_id=match_run.knowledge_release.knowledge_release_id,
        completion_basis=match_run.completion_basis,
        decisions=[
            TheoryDecisionRecordResponse(
                decision_id=item.decision_id,
                candidate_id=item.candidate_id,
                candidate_version=item.candidate_version,
                action=item.action,
                reason=item.reason,
                related_source_ids=list(item.related_source_ids),
                related_candidate_ids=list(item.related_candidate_ids),
                revised_applicability=item.revised_applicability,
                recorded_at=item.recorded_at,
            )
            for item in snapshot.decisions
        ],
        use_assignments=[
            TheoryUseAssignmentResponse(
                candidate_id=item.candidate_id,
                role_code=item.role_code,
                responsibility=item.responsibility,
            )
            for item in snapshot.use_assignments
        ],
        relations=[
            TheoryRelationResponse(
                relation_id=item.relation_id,
                candidate_ids=list(item.candidate_ids),
                relation_kind=item.relation_kind,
                explanation=item.explanation,
                premise_compatibility=item.premise_compatibility,
                supporting_evidence=list(item.supporting_evidence),
                excluding_evidence=list(item.excluding_evidence),
                distinguishing_evidence=list(item.distinguishing_evidence),
            )
            for item in snapshot.relations
        ],
    )


def _confirmed_plan_response(
    snapshot: ConfirmedTheoryPlanSnapshot,
) -> ConfirmedTheoryPlanResponse:
    adopted = {
        item.candidate_id
        for item in snapshot.decisions
        if item.action.value in {"adopt", "combine"}
    }
    source_ref_ids = list(
        dict.fromkeys(item.source_ref_id for item in snapshot.phenomenon.evidence_refs)
    )
    return ConfirmedTheoryPlanResponse(
        theory_plan_id=snapshot.theory_plan_id,
        task_id=snapshot.task_id,
        match_run_id=snapshot.match_run_id,
        decision_set_id=snapshot.decision_set_id,
        version=snapshot.version,
        allowed_actions=[TheoryPlanAction.CREATE_FRAMEWORK],
        phenomenon_query_id=snapshot.phenomenon.phenomenon_query_id,
        phenomenon_version=snapshot.phenomenon.version,
        knowledge_release_id=snapshot.knowledge_release.knowledge_release_id,
        adopted_candidate_ids=[
            item.candidate_id for item in snapshot.candidates if item.candidate_id in adopted
        ],
        confirmed_phenomenon=PhenomenonSnapshotResponse(
            phenomenon_query_id=snapshot.phenomenon.phenomenon_query_id,
            task_id=snapshot.phenomenon.task_id,
            version=snapshot.phenomenon.version,
            status="confirmed",
            allowed_actions=[PhenomenonSnapshotAction.START_MATCHING],
            phenomenon=snapshot.phenomenon.phenomenon,
            research_intent=snapshot.phenomenon.research_intent,
            context=snapshot.phenomenon.context,
            content_hash=snapshot.phenomenon.content_hash,
            source_ref_ids=source_ref_ids,
            evidence_refs=[
                PhenomenonEvidenceReferenceResponse(
                    evidence_ref_id=item.evidence_ref_id,
                    excerpt=item.excerpt,
                    source_ref_id=item.source_ref_id,
                    source_description=item.source_description,
                    locator=item.locator,
                    verification_status=item.verification_status,
                    use_boundary=item.use_boundary,
                )
                for item in snapshot.phenomenon.evidence_refs
            ],
            confirmed_at=snapshot.confirmed_at,
        ),
        decisions=[
            TheoryDecisionRecordResponse(
                decision_id=item.decision_id,
                candidate_id=item.candidate_id,
                candidate_version=item.candidate_version,
                action=item.action,
                reason=item.reason,
                related_source_ids=list(item.related_source_ids),
                related_candidate_ids=list(item.related_candidate_ids),
                revised_applicability=item.revised_applicability,
                recorded_at=item.recorded_at,
            )
            for item in snapshot.decisions
        ],
        use_assignments=[
            TheoryUseAssignmentResponse(
                candidate_id=item.candidate_id,
                role_code=item.role_code,
                responsibility=item.responsibility,
            )
            for item in snapshot.use_assignments
        ],
        relations=[
            TheoryRelationResponse(
                relation_id=item.relation_id,
                candidate_ids=list(item.candidate_ids),
                relation_kind=item.relation_kind,
                explanation=item.explanation,
                premise_compatibility=item.premise_compatibility,
                supporting_evidence=list(item.supporting_evidence),
                excluding_evidence=list(item.excluding_evidence),
                distinguishing_evidence=list(item.distinguishing_evidence),
            )
            for item in snapshot.relations
        ],
        confirmed_at=snapshot.confirmed_at,
    )


def _match_run_response(snapshot: MatchRunSnapshot) -> MatchRunResponse:
    allowed_actions = [MatchRunAction.REFRESH]
    model = _model_response(snapshot.model) if snapshot.model is not None else None
    candidate_page = MatchCandidatePageResponse(
        match_run_id=snapshot.match_run_id,
        version=snapshot.version,
        allowed_actions=allowed_actions,
        knowledge_release_id=snapshot.knowledge_release.knowledge_release_id,
        candidates=[_candidate_response(candidate, snapshot) for candidate in snapshot.candidates],
        stable_order=list(snapshot.stable_candidate_order),
        next_cursor=snapshot.next_cursor,
    )
    return MatchRunResponse(
        match_run_id=snapshot.match_run_id,
        task_id=snapshot.task_id,
        version=snapshot.version,
        status=snapshot.status,
        allowed_actions=allowed_actions,
        completion_basis=snapshot.completion_basis,
        partial_completion_acknowledged=snapshot.partial_completion_acknowledged,
        total_candidate_count=(
            0
            if snapshot.status is MatchRunStatus.NO_RELIABLE_CANDIDATE
            else len(snapshot.evidence_bundle.theory_profiles)
        ),
        completed_candidate_count=len(snapshot.candidates),
        failed_candidate_count=(
            0
            if snapshot.status is MatchRunStatus.NO_RELIABLE_CANDIDATE
            else len(snapshot.evidence_bundle.theory_profiles) - len(snapshot.candidates)
        ),
        phenomenon_query_id=snapshot.phenomenon.phenomenon_query_id,
        phenomenon_version=snapshot.phenomenon.version,
        knowledge_release_id=snapshot.knowledge_release.knowledge_release_id,
        candidate_page=candidate_page,
        model=model,
    )


def _candidate_response(
    candidate: TheoryCandidateSnapshot,
    snapshot: MatchRunSnapshot,
) -> TheoryCandidateResponse:
    if snapshot.model is None:
        raise RuntimeError("match run has no persisted model metadata")
    profile = candidate.content.reviewed_profile
    if profile is None:
        raise RuntimeError("M4-A candidate has no reviewed theory profile")
    evidence_by_id = {
        item.evidence_ref_id: item for item in snapshot.evidence_bundle.evidence_items
    }
    supporting = [
        _evidence_response(evidence_by_id[evidence_ref_id])
        for evidence_ref_id in candidate.judgement.evidence_ref_ids
        if evidence_ref_id in evidence_by_id
    ]
    return TheoryCandidateResponse(
        candidate_id=candidate.candidate_id,
        version=candidate.candidate_version,
        allowed_actions=[],
        judgement_run_status=candidate.judgement_run_status,
        knowledge_release_id=snapshot.knowledge_release.knowledge_release_id,
        knowledge_id=candidate.content.knowledge_id,
        theory_id=candidate.content.theory_id,
        seed_theory_id=candidate.content.seed_theory_id,
        origin=candidate.content.origin,
        content_status=candidate.content.content_status,
        title=candidate.content.title,
        problem_focus=candidate.content.problem_focus,
        core_claims=list(candidate.content.core_claims),
        analysis_levels=list(candidate.content.analysis_levels),
        prerequisites=list(profile.prerequisites),
        applicability_judgement=candidate.judgement.verdict,
        applicability_rationale=candidate.judgement.match_rationale,
        supporting_evidence=supporting,
        conflicting_evidence=[],
        missing_evidence=list(candidate.judgement.evidence_gaps),
        requested_material=list(candidate.judgement.material_requirements),
        limitations=list(candidate.judgement.limitations),
        misuse_boundaries=[*profile.exclusion_signals, *candidate.content.adoption_blockers],
        competing_theories=[],
        complementary_theories=[],
        source_ids=list(candidate.content.source_ids),
        formal_adoption_eligible=candidate.content.formal_adoption_eligible,
        adoption_blockers=list(candidate.content.adoption_blockers),
        model=_model_response(
            snapshot.model,
            trace_id=candidate.trace_id,
            request_id=candidate.request_id,
            contract_version=candidate.contract_version,
        ),
    )


def _evidence_response(item: EvidenceItemSnapshot) -> EvidenceReferenceResponse:
    source = item.source
    return EvidenceReferenceResponse(
        evidence_ref_id=item.evidence_ref_id,
        claim=item.claim,
        excerpt=item.excerpt,
        locator=item.locator,
        source_id=source.source_id if source is not None else None,
        source=(
            SourceRecordResponse(
                source_id=source.source_id,
                source_type=source.source_type,
                title=source.title,
                authors_or_institution=list(source.authors_or_institution),
                year=source.year,
                publication=source.publication,
                locator=source.locator,
                url=source.url,
                verification_status=source.verification_status,
                use_boundary=source.use_boundary,
            )
            if source is not None
            else None
        ),
        verification_status=item.verification_status,
        use_boundary=item.use_boundary,
    )


def _model_response(
    model: MatchRunModelSnapshot,
    *,
    trace_id: UUID | None = None,
    request_id: UUID | None = None,
    contract_version: str | None = None,
) -> ModelMetadata:
    return ModelMetadata(
        provider=model.provider,
        model_version=model.model_version,
        capability=ModelCapability(model.capability),
        degraded=model.degraded,
        knowledge_release_id=model.knowledge_release_id,
        trace=TraceMetadata(
            trace_id=trace_id or model.trace_id,
            request_id=request_id or model.request_id,
            contract_version=contract_version or model.contract_version,
        ),
    )
