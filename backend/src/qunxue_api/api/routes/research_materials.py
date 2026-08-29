from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from fastapi.responses import JSONResponse, Response

from qunxue_api.api.contracts.common import ErrorCode, ErrorDetail, ErrorResponse
from qunxue_api.api.contracts.research_materials import (
    ResearchMaterialKindInput,
    ResearchMaterialListResponse,
    ResearchMaterialResponse,
    ResearchMaterialSegmentResponse,
)
from qunxue_api.api.dependencies import (
    CurrentSessionDependency,
    OwnedResearchTaskDependency,
    ResearchMaterialApplicationDependency,
)
from qunxue_api.api.routes.stubs import IdempotencyKey
from qunxue_api.modules.research_materials import (
    MaterialIdempotencyConflict,
    MaterialKind,
    MaterialNotFound,
    MaterialVersionConflict,
    UnsupportedMaterialFormat,
)
from qunxue_api.modules.research_materials import (
    MaterialParseError as DomainMaterialParseError,
)

router = APIRouter(
    prefix="/api/research-tasks/{task_id}/materials",
    tags=["research-materials"],
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)

MAX_MATERIAL_BYTES = 25 * 1024 * 1024


_PARSE_ERROR_CODE_MAP: dict[str, ErrorCode] = {
    "unsupported_format": ErrorCode.UNSUPPORTED_MATERIAL_FORMAT,
    "format_mismatch": ErrorCode.UNSUPPORTED_MATERIAL_FORMAT,
    "empty_material": ErrorCode.NO_EXTRACTABLE_TEXT,
    "no_extractable_text": ErrorCode.NO_EXTRACTABLE_TEXT,
    "invalid_encoding": ErrorCode.NO_EXTRACTABLE_TEXT,
    "invalid_docx": ErrorCode.NO_EXTRACTABLE_TEXT,
    "document_too_large": ErrorCode.NO_EXTRACTABLE_TEXT,
    "pdf_text_extraction_failed": ErrorCode.NO_EXTRACTABLE_TEXT,
}


def _public_error_code(code: str | ErrorCode) -> ErrorCode:
    if isinstance(code, ErrorCode):
        return code
    mapped = _PARSE_ERROR_CODE_MAP.get(code)
    if mapped is not None:
        return mapped
    try:
        return ErrorCode(code)
    except ValueError:
        return ErrorCode.VALIDATION_ERROR


def _error(status_code: int, code: str | ErrorCode, message: str) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorDetail(
            code=_public_error_code(code),
            message=message,
            trace_id=str(uuid4()),
        )
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


def _material_response(
    application,
    material,
    *,
    include_segments: bool = False,
    parse_id: UUID | None = None,
):
    parsed = application.get_parse(
        user_id=material.user_id,
        task_id=material.task_id,
        material_id=material.material_id,
        parse_id=parse_id,
    )
    segments = parsed.blocks if parsed is not None else ()
    return ResearchMaterialResponse.from_domain(
        material,
        segments=segments if include_segments else None,
        parse_id=parsed.parse_id if parsed is not None else None,
        parse_version=parsed.version if parsed is not None else None,
    ).model_copy(update={"segment_count": len(segments)})


@router.post(
    "",
    operation_id="upload_research_material",
    response_model=ResearchMaterialResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_research_material(
    task_id: UUID,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchMaterialApplicationDependency,
    idempotency_key: IdempotencyKey,
    file: Annotated[UploadFile, File()],
    material_kind: Annotated[ResearchMaterialKindInput, Form()] = MaterialKind.OTHER,
) -> ResearchMaterialResponse | JSONResponse:
    content = await file.read(MAX_MATERIAL_BYTES + 1)
    await file.close()
    if len(content) > MAX_MATERIAL_BYTES:
        return _error(413, "research_material_too_large", "单份研究材料不能超过 25 MB。")
    if not content:
        return _error(422, ErrorCode.NO_EXTRACTABLE_TEXT, "材料为空，无法解析。")
    try:
        material = application.upload(
            user_id=current.user.user_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
            filename=file.filename or "",
            media_type=file.content_type or "",
            content=content,
            material_kind=material_kind,
        )
    except UnsupportedMaterialFormat as error:
        return _error(422, error.code, "仅支持 PDF、DOCX、TXT 和 Markdown。")
    except DomainMaterialParseError as error:
        return _error(422, error.code, str(error).split(": ", 1)[-1])
    except MaterialIdempotencyConflict as error:
        return _error(409, error.code, str(error))
    except MaterialVersionConflict as error:
        # A second request can observe an in-flight parse for the same
        # idempotency key. Keep that normal race explicit and retryable instead
        # of leaking it as an unhandled 500.
        return _error(409, error.code, str(error))
    return _material_response(application, material)


@router.get(
    "",
    operation_id="list_research_materials",
    response_model=ResearchMaterialListResponse,
)
def list_research_materials(
    task_id: UUID,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchMaterialApplicationDependency,
) -> ResearchMaterialListResponse:
    materials = application.list(user_id=current.user.user_id, task_id=task_id)
    return ResearchMaterialListResponse(
        task_id=task_id,
        items=[_material_response(application, item) for item in materials],
    )


@router.get(
    "/{material_id}",
    operation_id="get_research_material",
    response_model=ResearchMaterialResponse,
)
def get_research_material(
    task_id: UUID,
    material_id: UUID,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchMaterialApplicationDependency,
    parse_id: Annotated[UUID | None, Query()] = None,
) -> ResearchMaterialResponse | JSONResponse:
    try:
        material = application.get(
            user_id=current.user.user_id,
            task_id=task_id,
            material_id=material_id,
        )
    except MaterialNotFound:
        return _error(404, "research_material_not_found", "研究材料不存在或无权访问。")
    try:
        return _material_response(
            application,
            material,
            include_segments=True,
            parse_id=parse_id,
        )
    except MaterialNotFound:
        return _error(404, "research_material_not_found", "原文解析版本不存在或无权访问。")


@router.get(
    "/{material_id}/segments/{segment_id}",
    operation_id="get_research_material_segment",
    response_model=ResearchMaterialSegmentResponse,
)
def get_research_material_segment(
    task_id: UUID,
    material_id: UUID,
    segment_id: str,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchMaterialApplicationDependency,
    parse_id: Annotated[UUID | None, Query()] = None,
) -> ResearchMaterialSegmentResponse | JSONResponse:
    try:
        block = application.get_segment(
            user_id=current.user.user_id,
            task_id=task_id,
            material_id=material_id,
            segment_id=segment_id,
            parse_id=parse_id,
        )
    except MaterialNotFound:
        return _error(404, "research_material_not_found", "原文片段不存在或无权访问。")
    return ResearchMaterialSegmentResponse.from_domain(block)


@router.post(
    "/{material_id}/reparse",
    operation_id="reparse_research_material",
    response_model=ResearchMaterialResponse,
)
def reparse_research_material(
    task_id: UUID,
    material_id: UUID,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchMaterialApplicationDependency,
    idempotency_key: IdempotencyKey,
) -> ResearchMaterialResponse | JSONResponse:
    try:
        material = application.reparse(
            user_id=current.user.user_id,
            task_id=task_id,
            material_id=material_id,
            idempotency_key=idempotency_key,
        )
    except MaterialNotFound:
        return _error(404, "research_material_not_found", "研究材料不存在或无权访问。")
    except DomainMaterialParseError as error:
        return _error(422, error.code, str(error).split(": ", 1)[-1])
    except MaterialVersionConflict as error:
        return _error(409, error.code, str(error))
    except MaterialIdempotencyConflict as error:
        return _error(409, error.code, str(error))
    return _material_response(application, material)


@router.delete(
    "/{material_id}",
    operation_id="delete_research_material",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
def delete_research_material(
    task_id: UUID,
    material_id: UUID,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchMaterialApplicationDependency,
    idempotency_key: IdempotencyKey,
) -> Response | JSONResponse:
    try:
        application.delete(
            user_id=current.user.user_id,
            task_id=task_id,
            material_id=material_id,
            idempotency_key=idempotency_key,
        )
    except MaterialNotFound:
        return _error(404, "research_material_not_found", "研究材料不存在或无权访问。")
    except MaterialIdempotencyConflict as error:
        return _error(409, error.code, str(error))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
