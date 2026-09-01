from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, File, UploadFile, status
from fastapi.responses import JSONResponse

from qunxue_api.api.contracts.common import ErrorCode, ErrorDetail, ErrorResponse
from qunxue_api.api.contracts.transcription import (
    CreateTranscriptVersionRequest,
    TranscriptionWorkspaceResponse,
    TranscriptVersionResponse,
)
from qunxue_api.api.dependencies import (
    CurrentSessionDependency,
    OwnedResearchTaskDependency,
    TranscriptionApplicationDependency,
)
from qunxue_api.api.routes.stubs import IdempotencyKey
from qunxue_api.modules.research_materials import MaterialNotFound, MaterialVersionConflict
from qunxue_api.modules.transcription import (
    TranscriptionError,
    TranscriptionPolicyDenied,
    TranscriptionUnavailable,
    TranscriptVersionConflict,
    UnsupportedTranscriptImport,
)

router = APIRouter(
    prefix="/api/research-tasks/{task_id}/materials/{material_id}/transcription",
    tags=["transcription"],
    responses={422: {"model": ErrorResponse}},
)

MAX_TRANSCRIPT_BYTES = 10 * 1024 * 1024


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    try:
        public_code = ErrorCode(code)
    except ValueError:
        public_code = ErrorCode.VALIDATION_ERROR
    body = ErrorResponse(
        error=ErrorDetail(code=public_code, message=message, trace_id=str(uuid4()))
    )
    payload = body.model_dump(mode="json")
    if public_code is ErrorCode.VALIDATION_ERROR:
        payload["error"]["code"] = code
    return JSONResponse(status_code=status_code, content=payload)


@router.get(
    "",
    operation_id="get_material_transcription",
    response_model=TranscriptionWorkspaceResponse,
)
def get_material_transcription(
    task_id: UUID,
    material_id: UUID,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: TranscriptionApplicationDependency,
) -> TranscriptionWorkspaceResponse | JSONResponse:
    try:
        value = application.workspace(
            user_id=current.user.user_id,
            task_id=task_id,
            material_id=material_id,
        )
    except MaterialNotFound:
        return _error(404, "research_material_not_found", "媒体材料不存在或无权访问。")
    return TranscriptionWorkspaceResponse.from_domain(value)


@router.post(
    "/imports",
    operation_id="import_material_transcript",
    response_model=TranscriptVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_material_transcript(
    task_id: UUID,
    material_id: UUID,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: TranscriptionApplicationDependency,
    idempotency_key: IdempotencyKey,
    file: Annotated[UploadFile, File()],
) -> TranscriptVersionResponse | JSONResponse:
    content = await file.read(MAX_TRANSCRIPT_BYTES + 1)
    await file.close()
    if not content or len(content) > MAX_TRANSCRIPT_BYTES:
        return _error(422, "invalid_transcript_import", "转录稿为空或超过 10 MB。")
    try:
        value = application.import_transcript(
            user_id=current.user.user_id,
            task_id=task_id,
            material_id=material_id,
            idempotency_key=idempotency_key,
            filename=file.filename or "",
            media_type=file.content_type,
            content=content,
        )
    except MaterialNotFound:
        return _error(404, "research_material_not_found", "媒体材料不存在或无权访问。")
    except TranscriptionPolicyDenied as error:
        return _error(403, error.code, "当前材料授权范围不允许读取或校订转录。")
    except UnsupportedTranscriptImport as error:
        return _error(422, error.code, str(error))
    except (TranscriptVersionConflict, MaterialVersionConflict) as error:
        return _error(409, "transcript_version_conflict", str(error))
    return TranscriptVersionResponse.from_domain(value)


@router.post(
    "/versions",
    operation_id="create_corrected_transcript_version",
    response_model=TranscriptVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_corrected_transcript_version(
    task_id: UUID,
    material_id: UUID,
    payload: CreateTranscriptVersionRequest,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: TranscriptionApplicationDependency,
    idempotency_key: IdempotencyKey,
) -> TranscriptVersionResponse | JSONResponse:
    try:
        value = application.revise(
            user_id=current.user.user_id,
            task_id=task_id,
            material_id=material_id,
            idempotency_key=idempotency_key,
            base_version_id=payload.base_version_id,
            segments=tuple(item.to_domain() for item in payload.segments),
        )
    except MaterialNotFound:
        return _error(404, "research_material_not_found", "媒体或转录版本不存在。")
    except TranscriptionPolicyDenied as error:
        return _error(403, error.code, "当前材料授权范围不允许校订转录。")
    except (TranscriptVersionConflict, MaterialVersionConflict) as error:
        return _error(409, "transcript_version_conflict", str(error))
    return TranscriptVersionResponse.from_domain(value)


@router.post(
    "/runs",
    operation_id="start_material_transcription",
    response_model=TranscriptVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_material_transcription(
    task_id: UUID,
    material_id: UUID,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: TranscriptionApplicationDependency,
    idempotency_key: IdempotencyKey,
) -> TranscriptVersionResponse | JSONResponse:
    try:
        value = application.transcribe(
            user_id=current.user.user_id,
            task_id=task_id,
            material_id=material_id,
            idempotency_key=idempotency_key,
        )
    except MaterialNotFound:
        return _error(404, "research_material_not_found", "媒体材料不存在或无权访问。")
    except TranscriptionUnavailable as error:
        return _error(503, error.code, "自动转写服务未配置，请导入现成转录稿。")
    except TranscriptionPolicyDenied as error:
        return _error(403, error.code, "当前材料处理范围不允许调用该转写服务。")
    except TranscriptionError:
        return _error(502, "transcription_provider_failed", "自动转写服务失败，原始媒体已保留。")
    except (TranscriptVersionConflict, MaterialVersionConflict) as error:
        return _error(409, "transcript_version_conflict", str(error))
    return TranscriptVersionResponse.from_domain(value)
