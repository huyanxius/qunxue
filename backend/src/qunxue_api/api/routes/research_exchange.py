from typing import Annotated
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import APIRouter, File, UploadFile, status
from fastapi.responses import JSONResponse, Response

from qunxue_api.api.contracts.common import ErrorCode, ErrorDetail, ErrorResponse
from qunxue_api.api.contracts.research_exchange import (
    QdpxImportPreviewResponse,
    QdpxProjectPreviewResponse,
    ResearchAuditEventListResponse,
    ResearchAuditEventResponse,
)
from qunxue_api.api.dependencies import (
    CurrentSessionDependency,
    OwnedResearchTaskDependency,
    ResearchProjectExchangeApplicationDependency,
)
from qunxue_api.api.routes.stubs import IdempotencyKey
from qunxue_api.application import ResearchExchangeIdempotencyConflict

router = APIRouter(
    prefix="/api/research-tasks/{task_id}/exchange",
    tags=["research-project-exchange"],
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)

MAX_QDPX_PREVIEW_BYTES = 100 * 1024 * 1024


def _error(status_code: int, code: ErrorCode, message: str) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message, trace_id=str(uuid4())))
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


@router.post(
    "/archive",
    operation_id="export_research_project_archive",
    response_class=Response,
    response_model=None,
    responses={
        200: {
            "description": "A BagIt research archive containing QDPX and native recovery data.",
            "content": {
                "application/zip": {
                    "schema": {"type": "string", "format": "binary"},
                }
            },
        },
        409: {"model": ErrorResponse},
    },
)
def export_research_project_archive(
    task_id: UUID,
    task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchProjectExchangeApplicationDependency,
    idempotency_key: IdempotencyKey,
) -> Response | JSONResponse:
    try:
        exported = application.export_archive(
            user_id=current.user.user_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
        )
    except ResearchExchangeIdempotencyConflict as error:
        return _error(status.HTTP_409_CONFLICT, ErrorCode.IDEMPOTENCY_CONFLICT, str(error))
    filename = quote(f"{task.project_title or 'research-project'}.zip")
    losses = exported.report.losses
    return Response(
        content=exported.archive.payload,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "X-Qunxue-Exchange-Id": str(exported.exchange.exchange_id),
            "X-Qunxue-Artifact-SHA256": exported.archive.sha256,
            "X-Qunxue-Exchange-Loss-Count": str(len(losses)),
            "X-Qunxue-Exchange-Blocking-Loss-Count": str(
                sum(loss.severity.value == "blocking" for loss in losses)
            ),
        },
    )


@router.get(
    "/audit",
    operation_id="list_research_project_audit_events",
    response_model=ResearchAuditEventListResponse,
)
def list_research_project_audit_events(
    task_id: UUID,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchProjectExchangeApplicationDependency,
) -> ResearchAuditEventListResponse:
    events = application.list_audit_events(
        user_id=current.user.user_id,
        task_id=task_id,
    )
    return ResearchAuditEventListResponse(
        task_id=task_id,
        items=[ResearchAuditEventResponse.from_domain(event) for event in events],
    )


@router.post(
    "/qdpx-preview",
    operation_id="preview_research_project_qdpx_import",
    response_model=QdpxImportPreviewResponse,
)
async def preview_research_project_qdpx_import(
    task_id: UUID,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchProjectExchangeApplicationDependency,
    idempotency_key: IdempotencyKey,
    file: Annotated[UploadFile, File()],
) -> QdpxImportPreviewResponse | JSONResponse:
    payload = await file.read(MAX_QDPX_PREVIEW_BYTES + 1)
    await file.close()
    if not payload:
        return _error(422, ErrorCode.VALIDATION_ERROR, "QDPX 文件为空。")
    if len(payload) > MAX_QDPX_PREVIEW_BYTES:
        return _error(413, ErrorCode.VALIDATION_ERROR, "QDPX 预览文件不能超过 100 MB。")
    try:
        preview = application.preview_qdpx_import(
            user_id=current.user.user_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
            payload=payload,
        )
    except ResearchExchangeIdempotencyConflict as error:
        return _error(status.HTTP_409_CONFLICT, ErrorCode.IDEMPOTENCY_CONFLICT, str(error))
    except ValueError as error:
        return _error(422, ErrorCode.VALIDATION_ERROR, str(error))
    project = preview.project
    return QdpxImportPreviewResponse(
        exchange_id=preview.exchange.exchange_id,
        project=QdpxProjectPreviewResponse(
            name=project.name,
            origin=project.origin,
            source_count=len(project.sources),
            code_count=len(project.codes),
            memo_count=len(project.memos),
            case_count=len(project.cases),
        ),
    )
