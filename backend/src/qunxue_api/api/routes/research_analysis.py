from typing import Annotated, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse

from qunxue_api.api.contracts.common import ErrorCode, ErrorDetail, ErrorResponse
from qunxue_api.api.contracts.research_analysis import (
    AnalysisAnnotationResponse,
    AnalysisAuditEventResponse,
    AnalysisCaseProfileResponse,
    AnalysisCodeResponse,
    AnalysisCodingPlanResponse,
    AnalysisMemoLinkResponse,
    AnalysisMemoResponse,
    AnalysisThemeResponse,
    CaseComparisonResponse,
    CaseThemeMatrixCellResponse,
    CodebookEntryResponse,
    ConfigureCodebookEntryRequest,
    CreateAnalysisAnnotationRequest,
    CreateAnalysisCodeRequest,
    CreateAnalysisMemoLinkRequest,
    CreateAnalysisMemoRequest,
    CreateAnalysisThemeRequest,
    CreateCaseComparisonRequest,
    DecideAnalysisRecordRequest,
    DecideCodingPlanRequest,
    MethodPresetSelectionResponse,
    QualitativeMethodPresetResponse,
    QualitativeWorkspaceSnapshotResponse,
    ResearchAnalysisSnapshotResponse,
    RetrievedCodedSegmentResponse,
    RevokeCodingPlanRequest,
    SaveAnalysisCaseProfileRequest,
    SaveCaseThemeMatrixCellRequest,
    SetQualitativeMethodRequest,
    TransitionCodebookEntryRequest,
)
from qunxue_api.api.contracts.research_materials import ResearchMaterialLocatorResponse
from qunxue_api.api.dependencies import (
    CurrentSessionDependency,
    OwnedResearchTaskDependency,
    ResearchAnalysisApplicationDependency,
)
from qunxue_api.api.routes.stubs import IdempotencyKey
from qunxue_api.modules.research_analysis import (
    AnalysisAnnotation,
    AnalysisCode,
    AnalysisCodeStatus,
    AnalysisCodingPlan,
    AnalysisMemo,
    CaseComparison,
    QualitativeWorkspaceSnapshot,
    ResearchAnalysisIdempotencyConflict,
    qualitative_method_presets,
)

router = APIRouter(
    prefix="/api/research-tasks/{task_id}/analysis",
    tags=["research-analysis"],
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)


def _error(status_code: int, code: ErrorCode, message: str) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message, trace_id=str(uuid4())))
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


@router.get(
    "",
    operation_id="get_research_analysis",
    response_model=ResearchAnalysisSnapshotResponse,
)
def get_research_analysis(
    task_id: UUID,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchAnalysisApplicationDependency,
) -> ResearchAnalysisSnapshotResponse:
    value = application.list_snapshot(user_id=current.user.user_id, task_id=task_id)
    workspace = cast(QualitativeWorkspaceSnapshot, value["workspace"])
    return ResearchAnalysisSnapshotResponse(
        task_id=task_id,
        annotations=[
            AnalysisAnnotationResponse.from_domain(item)
            for item in cast(tuple[AnalysisAnnotation, ...], value["annotations"])
        ],
        codes=[
            AnalysisCodeResponse.from_domain(item)
            for item in cast(tuple[AnalysisCode, ...], value["codes"])
        ],
        memos=[
            AnalysisMemoResponse.from_domain(item)
            for item in cast(tuple[AnalysisMemo, ...], value["memos"])
        ],
        comparisons=[
            CaseComparisonResponse.from_domain(item)
            for item in cast(tuple[CaseComparison, ...], value["comparisons"])
        ],
        coding_plans=[
            AnalysisCodingPlanResponse.from_domain(item)
            for item in cast(tuple[AnalysisCodingPlan, ...], value.get("coding_plans", ()))
        ],
        workspace=QualitativeWorkspaceSnapshotResponse.from_domain(workspace),
        method_presets=[
            QualitativeMethodPresetResponse.from_domain(item)
            for item in qualitative_method_presets().values()
        ],
    )


@router.post(
    "/coding-plans/{plan_id}/decision",
    operation_id="decide_research_coding_plan",
    response_model=AnalysisCodingPlanResponse,
)
def decide_research_coding_plan(
    task_id: UUID,
    plan_id: UUID,
    payload: DecideCodingPlanRequest,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchAnalysisApplicationDependency,
    idempotency_key: IdempotencyKey,
) -> AnalysisCodingPlanResponse | JSONResponse:
    try:
        value = application.decide_coding_plan(
            user_id=current.user.user_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
            plan_id=plan_id,
            expected_version=payload.expected_version,
            decisions=tuple(
                (item.item_id, item.decision, item.reason) for item in payload.decisions
            ),
        )
    except LookupError:
        return _error(404, ErrorCode.NOT_FOUND, "编码计划不存在或无权访问。")
    except ValueError as error:
        if isinstance(error, ResearchAnalysisIdempotencyConflict):
            return _error(409, ErrorCode.IDEMPOTENCY_CONFLICT, str(error))
        return _decision_error(error)
    return AnalysisCodingPlanResponse.from_domain(value)


@router.post(
    "/coding-plans/{plan_id}/revoke",
    operation_id="revoke_research_coding_plan",
    response_model=AnalysisCodingPlanResponse,
)
def revoke_research_coding_plan(
    task_id: UUID,
    plan_id: UUID,
    payload: RevokeCodingPlanRequest,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchAnalysisApplicationDependency,
    idempotency_key: IdempotencyKey,
) -> AnalysisCodingPlanResponse | JSONResponse:
    try:
        value = application.revoke_coding_plan(
            user_id=current.user.user_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
            plan_id=plan_id,
            expected_version=payload.expected_version,
            reason=payload.reason,
        )
    except LookupError:
        return _error(404, ErrorCode.NOT_FOUND, "编码计划不存在或无权访问。")
    except ValueError as error:
        if isinstance(error, ResearchAnalysisIdempotencyConflict):
            return _error(409, ErrorCode.IDEMPOTENCY_CONFLICT, str(error))
        return _decision_error(error)
    return AnalysisCodingPlanResponse.from_domain(value)


@router.get(
    "/retrieved-segments",
    operation_id="get_research_retrieved_segments",
    response_model=list[RetrievedCodedSegmentResponse],
)
def get_research_retrieved_segments(
    task_id: UUID,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchAnalysisApplicationDependency,
    code_id: Annotated[list[UUID] | None, Query()] = None,
    material_id: UUID | None = None,
    query: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[RetrievedCodedSegmentResponse]:
    rows = application.retrieve_coded_segments(
        user_id=current.user.user_id,
        task_id=task_id,
        code_ids=tuple(code_id or ()),
        material_id=material_id,
        query=query,
        limit=limit,
    )
    return [
        RetrievedCodedSegmentResponse(
            **{**row, "locator": ResearchMaterialLocatorResponse.from_domain(row["locator"])}
        )
        for row in rows
    ]


@router.get(
    "/audit",
    operation_id="get_research_analysis_audit",
    response_model=list[AnalysisAuditEventResponse],
)
def get_research_analysis_audit(
    task_id: UUID,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchAnalysisApplicationDependency,
) -> list[AnalysisAuditEventResponse]:
    return [
        AnalysisAuditEventResponse.from_domain(item)
        for item in application.list_audit_events(user_id=current.user.user_id, task_id=task_id)
    ]


@router.post(
    "/annotations",
    operation_id="create_research_analysis_annotation",
    response_model=AnalysisAnnotationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_research_analysis_annotation(
    task_id: UUID,
    payload: CreateAnalysisAnnotationRequest,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchAnalysisApplicationDependency,
    idempotency_key: IdempotencyKey,
) -> AnalysisAnnotationResponse | JSONResponse:
    try:
        value = application.create_annotation(
            user_id=current.user.user_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
            **payload.model_dump(),
        )
    except LookupError:
        return _error(404, ErrorCode.RESEARCH_MATERIAL_NOT_FOUND, "原文片段不存在或无权访问。")
    except ValueError as error:
        if isinstance(error, ResearchAnalysisIdempotencyConflict):
            return _error(409, ErrorCode.IDEMPOTENCY_CONFLICT, str(error))
        return _error(422, ErrorCode.VALIDATION_ERROR, str(error))
    return AnalysisAnnotationResponse.from_domain(value)


@router.post(
    "/codes",
    operation_id="create_research_analysis_code",
    response_model=AnalysisCodeResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_research_analysis_code(
    task_id: UUID,
    payload: CreateAnalysisCodeRequest,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchAnalysisApplicationDependency,
    idempotency_key: IdempotencyKey,
) -> AnalysisCodeResponse | JSONResponse:
    try:
        value = application.create_user_code(
            user_id=current.user.user_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
            label=payload.label,
            definition=payload.definition,
            annotation_ids=tuple(payload.annotation_ids),
            rationale=payload.rationale,
        )
    except ValueError as error:
        if isinstance(error, ResearchAnalysisIdempotencyConflict):
            return _error(409, ErrorCode.IDEMPOTENCY_CONFLICT, str(error))
        return _error(422, ErrorCode.VALIDATION_ERROR, str(error))
    return AnalysisCodeResponse.from_domain(value)


@router.post(
    "/codes/{code_id}/decision",
    operation_id="decide_research_analysis_code",
    response_model=AnalysisCodeResponse,
)
def decide_research_analysis_code(
    task_id: UUID,
    code_id: UUID,
    payload: DecideAnalysisRecordRequest,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchAnalysisApplicationDependency,
    _idempotency_key: IdempotencyKey,
) -> AnalysisCodeResponse | JSONResponse:
    try:
        value = application.decide_code(
            user_id=current.user.user_id,
            task_id=task_id,
            idempotency_key=_idempotency_key,
            code_id=code_id,
            expected_version=payload.expected_version,
            decision=AnalysisCodeStatus(payload.decision.value),
            reason=payload.reason,
        )
    except LookupError:
        return _error(404, ErrorCode.NOT_FOUND, "候选编码不存在或无权访问。")
    except ValueError as error:
        return _decision_error(error)
    return AnalysisCodeResponse.from_domain(value)


@router.post(
    "/memos",
    operation_id="create_research_analysis_memo",
    response_model=AnalysisMemoResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_research_analysis_memo(
    task_id: UUID,
    payload: CreateAnalysisMemoRequest,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchAnalysisApplicationDependency,
    idempotency_key: IdempotencyKey,
) -> AnalysisMemoResponse | JSONResponse:
    try:
        value = application.create_user_memo(
            user_id=current.user.user_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
            title=payload.title,
            content=payload.content,
            memo_kind=payload.memo_kind,
            annotation_ids=tuple(payload.annotation_ids),
            code_ids=tuple(payload.code_ids),
        )
    except ValueError as error:
        if isinstance(error, ResearchAnalysisIdempotencyConflict):
            return _error(409, ErrorCode.IDEMPOTENCY_CONFLICT, str(error))
        return _error(422, ErrorCode.VALIDATION_ERROR, str(error))
    return AnalysisMemoResponse.from_domain(value)


@router.post(
    "/memos/{memo_id}/decision",
    operation_id="decide_research_analysis_memo",
    response_model=AnalysisMemoResponse,
)
def decide_research_analysis_memo(
    task_id: UUID,
    memo_id: UUID,
    payload: DecideAnalysisRecordRequest,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchAnalysisApplicationDependency,
    _idempotency_key: IdempotencyKey,
) -> AnalysisMemoResponse | JSONResponse:
    try:
        value = application.decide_memo(
            user_id=current.user.user_id,
            task_id=task_id,
            idempotency_key=_idempotency_key,
            memo_id=memo_id,
            expected_version=payload.expected_version,
            decision=payload.decision,
            reason=payload.reason,
        )
    except LookupError:
        return _error(404, ErrorCode.NOT_FOUND, "候选备忘不存在或无权访问。")
    except ValueError as error:
        return _decision_error(error)
    return AnalysisMemoResponse.from_domain(value)


@router.post(
    "/comparisons",
    operation_id="create_research_case_comparison",
    response_model=CaseComparisonResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_research_case_comparison(
    task_id: UUID,
    payload: CreateCaseComparisonRequest,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchAnalysisApplicationDependency,
    idempotency_key: IdempotencyKey,
) -> CaseComparisonResponse | JSONResponse:
    try:
        value = application.create_user_comparison(
            user_id=current.user.user_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
            title=payload.title,
            question=payload.question,
            case_labels=tuple(payload.case_labels),
            time_labels=tuple(payload.time_labels),
            findings=tuple(item.to_domain() for item in payload.findings),
            competing_explanations=tuple(payload.competing_explanations),
            evidence_gaps=tuple(payload.evidence_gaps),
            next_steps=tuple(item.to_domain() for item in payload.next_steps),
            theory_implication=payload.theory_implication,
        )
    except ValueError as error:
        if isinstance(error, ResearchAnalysisIdempotencyConflict):
            return _error(409, ErrorCode.IDEMPOTENCY_CONFLICT, str(error))
        return _error(422, ErrorCode.VALIDATION_ERROR, str(error))
    return CaseComparisonResponse.from_domain(value)


@router.post(
    "/comparisons/{comparison_id}/decision",
    operation_id="decide_research_case_comparison",
    response_model=CaseComparisonResponse,
)
def decide_research_case_comparison(
    task_id: UUID,
    comparison_id: UUID,
    payload: DecideAnalysisRecordRequest,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchAnalysisApplicationDependency,
    _idempotency_key: IdempotencyKey,
) -> CaseComparisonResponse | JSONResponse:
    try:
        value = application.decide_comparison(
            user_id=current.user.user_id,
            task_id=task_id,
            idempotency_key=_idempotency_key,
            comparison_id=comparison_id,
            expected_version=payload.expected_version,
            decision=payload.decision,
            reason=payload.reason,
        )
    except LookupError:
        return _error(404, ErrorCode.NOT_FOUND, "候选比较不存在或无权访问。")
    except ValueError as error:
        return _decision_error(error)
    return CaseComparisonResponse.from_domain(value)


@router.put(
    "/workspace/codebook/{code_id}",
    operation_id="configure_research_codebook_entry",
    response_model=CodebookEntryResponse,
)
def configure_research_codebook_entry(
    task_id: UUID,
    code_id: UUID,
    payload: ConfigureCodebookEntryRequest,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchAnalysisApplicationDependency,
    _idempotency_key: IdempotencyKey,
) -> CodebookEntryResponse | JSONResponse:
    try:
        value = application.configure_codebook_entry(
            user_id=current.user.user_id,
            task_id=task_id,
            code_id=code_id,
            inclusion_rules=tuple(payload.inclusion_rules),
            exclusion_rules=tuple(payload.exclusion_rules),
            parent_code_id=payload.parent_code_id,
            positive_example_annotation_ids=tuple(payload.positive_example_annotation_ids),
            negative_example_annotation_ids=tuple(payload.negative_example_annotation_ids),
            expected_version=payload.expected_version,
        )
    except (LookupError, ValueError) as error:
        return _workspace_error(error)
    return CodebookEntryResponse.from_domain(value)


@router.post(
    "/workspace/codebook/{code_id}/transition",
    operation_id="transition_research_codebook_entry",
    response_model=CodebookEntryResponse,
)
def transition_research_codebook_entry(
    task_id: UUID,
    code_id: UUID,
    payload: TransitionCodebookEntryRequest,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchAnalysisApplicationDependency,
    _idempotency_key: IdempotencyKey,
) -> CodebookEntryResponse | JSONResponse:
    try:
        value = application.transition_codebook_entry(
            user_id=current.user.user_id,
            task_id=task_id,
            code_id=code_id,
            lifecycle=payload.lifecycle,
            related_code_ids=tuple(payload.related_code_ids),
            expected_version=payload.expected_version,
            reason=payload.reason,
        )
    except (LookupError, ValueError) as error:
        return _workspace_error(error)
    return CodebookEntryResponse.from_domain(value)


@router.post(
    "/workspace/themes",
    operation_id="create_research_analysis_theme",
    response_model=AnalysisThemeResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_research_analysis_theme(
    task_id: UUID,
    payload: CreateAnalysisThemeRequest,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchAnalysisApplicationDependency,
    _idempotency_key: IdempotencyKey,
) -> AnalysisThemeResponse | JSONResponse:
    try:
        value = application.create_user_theme(
            user_id=current.user.user_id,
            task_id=task_id,
            label=payload.label,
            central_concept=payload.central_concept,
            code_ids=tuple(payload.code_ids),
            annotation_ids=tuple(payload.annotation_ids),
        )
    except (LookupError, ValueError) as error:
        return _workspace_error(error)
    return AnalysisThemeResponse.from_domain(value)


@router.post(
    "/workspace/themes/{theme_id}/decision",
    operation_id="confirm_research_analysis_theme",
    response_model=AnalysisThemeResponse,
)
def confirm_research_analysis_theme(
    task_id: UUID,
    theme_id: UUID,
    payload: DecideAnalysisRecordRequest,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchAnalysisApplicationDependency,
    _idempotency_key: IdempotencyKey,
) -> AnalysisThemeResponse | JSONResponse:
    if payload.decision is not payload.decision.CONFIRMED:
        return _error(422, ErrorCode.VALIDATION_ERROR, "主题候选当前只能确认；拒绝仍保留原记录。")
    try:
        value = application.confirm_theme(
            user_id=current.user.user_id,
            task_id=task_id,
            theme_id=theme_id,
            expected_version=payload.expected_version,
            reason=payload.reason,
        )
    except (LookupError, ValueError) as error:
        return _workspace_error(error)
    return AnalysisThemeResponse.from_domain(value)


@router.post(
    "/workspace/memo-links",
    operation_id="create_research_analysis_memo_link",
    response_model=AnalysisMemoLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_research_analysis_memo_link(
    task_id: UUID,
    payload: CreateAnalysisMemoLinkRequest,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchAnalysisApplicationDependency,
    _idempotency_key: IdempotencyKey,
) -> AnalysisMemoLinkResponse | JSONResponse:
    try:
        value = application.attach_memo(
            user_id=current.user.user_id,
            task_id=task_id,
            memo_id=payload.memo_id,
            target_kind=payload.target_kind,
            target_ref=payload.target_ref,
            annotation_ids=tuple(payload.annotation_ids),
        )
    except (LookupError, ValueError) as error:
        return _workspace_error(error)
    return AnalysisMemoLinkResponse.from_domain(value)


@router.post(
    "/workspace/cases",
    operation_id="save_research_analysis_case_profile",
    response_model=AnalysisCaseProfileResponse,
)
def save_research_analysis_case_profile(
    task_id: UUID,
    payload: SaveAnalysisCaseProfileRequest,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchAnalysisApplicationDependency,
    _idempotency_key: IdempotencyKey,
) -> AnalysisCaseProfileResponse | JSONResponse:
    try:
        value = application.save_case_profile(
            user_id=current.user.user_id,
            task_id=task_id,
            case_ref=payload.case_ref,
            display_label=payload.display_label,
            attributes=tuple((item.name, item.value) for item in payload.attributes),
            summary=payload.summary,
            annotation_ids=tuple(payload.annotation_ids),
            memo_ids=tuple(payload.memo_ids),
            expected_version=payload.expected_version,
        )
    except (LookupError, ValueError) as error:
        return _workspace_error(error)
    return AnalysisCaseProfileResponse.from_domain(value)


@router.put(
    "/workspace/matrix-cell",
    operation_id="save_research_case_theme_matrix_cell",
    response_model=CaseThemeMatrixCellResponse,
)
def save_research_case_theme_matrix_cell(
    task_id: UUID,
    payload: SaveCaseThemeMatrixCellRequest,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchAnalysisApplicationDependency,
    _idempotency_key: IdempotencyKey,
) -> CaseThemeMatrixCellResponse | JSONResponse:
    try:
        value = application.save_matrix_cell(
            user_id=current.user.user_id,
            task_id=task_id,
            case_profile_id=payload.case_profile_id,
            subject_kind=payload.subject_kind,
            subject_id=payload.subject_id,
            summary=payload.summary,
            annotation_ids=tuple(payload.annotation_ids),
            memo_ids=tuple(payload.memo_ids),
            finding_kinds=tuple(payload.finding_kinds),
            expected_version=payload.expected_version,
        )
    except (LookupError, ValueError) as error:
        return _workspace_error(error)
    return CaseThemeMatrixCellResponse.from_domain(value)


@router.put(
    "/workspace/method",
    operation_id="set_research_qualitative_method",
    response_model=MethodPresetSelectionResponse,
)
def set_research_qualitative_method(
    task_id: UUID,
    payload: SetQualitativeMethodRequest,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchAnalysisApplicationDependency,
    _idempotency_key: IdempotencyKey,
) -> MethodPresetSelectionResponse | JSONResponse:
    try:
        value = application.set_method_preset(
            user_id=current.user.user_id,
            task_id=task_id,
            method=payload.method,
            expected_version=payload.expected_version,
        )
    except (LookupError, ValueError) as error:
        return _workspace_error(error)
    return MethodPresetSelectionResponse.from_domain(value)


def _decision_error(error: ValueError) -> JSONResponse:
    message = str(error)
    if "stale" in message or "already decided" in message:
        return _error(409, ErrorCode.CONFLICT, message)
    return _error(422, ErrorCode.VALIDATION_ERROR, message)


def _workspace_error(error: LookupError | ValueError) -> JSONResponse:
    if isinstance(error, LookupError):
        return _error(404, ErrorCode.NOT_FOUND, "质性分析对象不存在或无权访问。")
    message = str(error)
    if "stale" in message or "already" in message:
        return _error(409, ErrorCode.CONFLICT, message)
    return _error(422, ErrorCode.VALIDATION_ERROR, message)
