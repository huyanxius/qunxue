from typing import cast
from uuid import UUID, uuid4

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from qunxue_api.api.contracts.common import ErrorCode, ErrorDetail, ErrorResponse
from qunxue_api.api.contracts.research_analysis import (
    AnalysisAnnotationResponse,
    AnalysisCodeResponse,
    AnalysisMemoResponse,
    CaseComparisonResponse,
    CreateAnalysisAnnotationRequest,
    CreateAnalysisCodeRequest,
    CreateAnalysisMemoRequest,
    CreateCaseComparisonRequest,
    DecideAnalysisRecordRequest,
    ResearchAnalysisSnapshotResponse,
)
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
    AnalysisMemo,
    CaseComparison,
    ResearchAnalysisIdempotencyConflict,
)

router = APIRouter(
    prefix="/api/research-tasks/{task_id}/analysis",
    tags=["research-analysis"],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
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
    )


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
) -> AnalysisCodeResponse | JSONResponse:
    try:
        value = application.decide_code(
            user_id=current.user.user_id,
            task_id=task_id,
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
) -> AnalysisMemoResponse | JSONResponse:
    try:
        value = application.decide_memo(
            user_id=current.user.user_id,
            task_id=task_id,
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
) -> CaseComparisonResponse | JSONResponse:
    try:
        value = application.decide_comparison(
            user_id=current.user.user_id,
            task_id=task_id,
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


def _decision_error(error: ValueError) -> JSONResponse:
    message = str(error)
    if "stale" in message or "already decided" in message:
        return _error(409, ErrorCode.CONFLICT, message)
    return _error(422, ErrorCode.VALIDATION_ERROR, message)
