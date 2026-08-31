"""Task-owned HTTP routes for professional material archive metadata."""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from fastapi.responses import JSONResponse, Response

from qunxue_api.api.contracts.common import ErrorCode, ErrorDetail, ErrorResponse
from qunxue_api.api.contracts.professional_materials import (
    BatchUploadItemResponse,
    BatchUploadResponse,
    CreateLiteratureEntryRequest,
    CreateMaterialBatchRequest,
    CreateMaterialCollectionRequest,
    CreateMaterialRelationRequest,
    CreateResearchCaseRequest,
    DoiMetadataCandidateResponse,
    LiteratureEntryResponse,
    MaterialArchiveProfileResponse,
    MaterialBatchResponse,
    MaterialCollectionResponse,
    MaterialRelationResponse,
    ProfessionalMaterialArchiveResponse,
    ResearchCaseResponse,
    UpdateMaterialArchiveProfileRequest,
)
from qunxue_api.api.dependencies import (
    CurrentSessionDependency,
    OwnedResearchTaskDependency,
    ProfessionalMaterialsApplicationDependency,
    ResearchMaterialApplicationDependency,
)
from qunxue_api.api.routes.research_materials import MAX_MATERIAL_BYTES
from qunxue_api.api.routes.stubs import IdempotencyKey
from qunxue_api.modules.research_materials import (
    DoiMetadataUnavailable,
    LiteratureExchangeFormat,
    MaterialKind,
    ResearchMaterialError,
)

router = APIRouter(
    prefix="/api/research-tasks/{task_id}/material-archive",
    tags=["professional-materials"],
)


@router.get(
    "/doi",
    operation_id="resolve_doi_metadata",
    response_model=DoiMetadataCandidateResponse,
    responses={503: {"model": ErrorResponse}},
)
def resolve_doi_metadata(
    task_id: UUID,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ProfessionalMaterialsApplicationDependency,
    doi: Annotated[str, Query(min_length=6, max_length=300)],
) -> DoiMetadataCandidateResponse | JSONResponse:
    try:
        return DoiMetadataCandidateResponse.from_domain(
            application.resolve_doi(
                user_id=current.user.user_id,
                task_id=task_id,
                doi=doi,
            )
        )
    except DoiMetadataUnavailable as error:
        body = ErrorResponse(
            error=ErrorDetail(
                code=ErrorCode.DOI_METADATA_UNAVAILABLE,
                message=str(error),
                trace_id=str(uuid4()),
            )
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=body.model_dump(mode="json"),
        )


@router.get(
    "",
    operation_id="get_professional_material_archive",
    response_model=ProfessionalMaterialArchiveResponse,
)
def get_professional_material_archive(
    task_id: UUID,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ProfessionalMaterialsApplicationDependency,
) -> ProfessionalMaterialArchiveResponse:
    return ProfessionalMaterialArchiveResponse.from_domain(
        task_id,
        application.get_archive(user_id=current.user.user_id, task_id=task_id),
    )


@router.patch(
    "/materials/{material_id}",
    operation_id="update_professional_material_profile",
    response_model=MaterialArchiveProfileResponse,
)
def update_professional_material_profile(
    task_id: UUID,
    material_id: UUID,
    payload: UpdateMaterialArchiveProfileRequest,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ProfessionalMaterialsApplicationDependency,
) -> MaterialArchiveProfileResponse:
    return MaterialArchiveProfileResponse.from_domain(
        application.update_profile(
            user_id=current.user.user_id,
            task_id=task_id,
            material_id=material_id,
            research_role=payload.research_role,
            specific_type=payload.specific_type,
            stage=payload.stage,
            batch_id=payload.batch_id,
            tags=tuple(payload.tags),
            collection_ids=tuple(payload.collection_ids),
            sensitivity=payload.sensitivity,
            consent_scope=payload.consent_scope,
            deidentification_status=payload.deidentification_status,
            model_processing_scope=payload.model_processing_scope,
        )
    )


@router.post(
    "/batches",
    operation_id="create_material_batch",
    response_model=MaterialBatchResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_material_batch(
    task_id: UUID,
    payload: CreateMaterialBatchRequest,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ProfessionalMaterialsApplicationDependency,
) -> MaterialBatchResponse:
    return MaterialBatchResponse.from_domain(
        application.create_batch(
            user_id=current.user.user_id, task_id=task_id, name=payload.name
        )
    )


@router.post(
    "/collections",
    operation_id="create_material_collection",
    response_model=MaterialCollectionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_material_collection(
    task_id: UUID,
    payload: CreateMaterialCollectionRequest,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ProfessionalMaterialsApplicationDependency,
) -> MaterialCollectionResponse:
    return MaterialCollectionResponse.from_domain(
        application.create_collection(
            user_id=current.user.user_id,
            task_id=task_id,
            name=payload.name,
            description=payload.description,
            parent_collection_id=payload.parent_collection_id,
        )
    )


@router.post(
    "/literature",
    operation_id="create_literature_entry",
    response_model=LiteratureEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_literature_entry(
    task_id: UUID,
    payload: CreateLiteratureEntryRequest,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ProfessionalMaterialsApplicationDependency,
) -> LiteratureEntryResponse:
    return LiteratureEntryResponse.from_domain(
        application.create_literature(
            user_id=current.user.user_id,
            task_id=task_id,
            item_type=payload.item_type,
            title=payload.title,
            doi=payload.doi,
            csl_data=payload.csl_data,
            attachment_material_ids=tuple(payload.attachment_material_ids),
            collection_ids=tuple(payload.collection_ids),
        )
    )


@router.post(
    "/literature/import",
    operation_id="import_literature_entries",
    response_model=list[LiteratureEntryResponse],
    status_code=status.HTTP_201_CREATED,
)
async def import_literature_entries_route(
    task_id: UUID,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ProfessionalMaterialsApplicationDependency,
    exchange_format: Annotated[LiteratureExchangeFormat, Form()],
    file: Annotated[UploadFile, File()],
) -> list[LiteratureEntryResponse]:
    payload = await file.read(5 * 1024 * 1024 + 1)
    await file.close()
    if len(payload) > 5 * 1024 * 1024:
        raise ValueError("literature exchange file is too large")
    values = application.import_literature(
        user_id=current.user.user_id,
        task_id=task_id,
        exchange_format=exchange_format,
        payload=payload,
    )
    return [LiteratureEntryResponse.from_domain(value) for value in values]


@router.get(
    "/literature/export",
    operation_id="export_literature_entries",
)
def export_literature_entries_route(
    task_id: UUID,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ProfessionalMaterialsApplicationDependency,
    exchange_format: Annotated[LiteratureExchangeFormat, Query()],
) -> Response:
    payload = application.export_literature(
        user_id=current.user.user_id,
        task_id=task_id,
        exchange_format=exchange_format,
    )
    media_type = {
        LiteratureExchangeFormat.CSL_JSON: "application/json",
        LiteratureExchangeFormat.BIBTEX: "application/x-bibtex",
        LiteratureExchangeFormat.RIS: "application/x-research-info-systems",
    }[exchange_format]
    return Response(content=payload, media_type=media_type)


@router.post(
    "/cases",
    operation_id="create_research_case",
    response_model=ResearchCaseResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_research_case(
    task_id: UUID,
    payload: CreateResearchCaseRequest,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ProfessionalMaterialsApplicationDependency,
) -> ResearchCaseResponse:
    return ResearchCaseResponse.from_domain(
        application.create_case(
            user_id=current.user.user_id,
            task_id=task_id,
            name=payload.name,
            description=payload.description,
            attributes=payload.attributes,
            material_ids=tuple(payload.material_ids),
        )
    )


@router.post(
    "/relations",
    operation_id="create_material_relation",
    response_model=MaterialRelationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_material_relation(
    task_id: UUID,
    payload: CreateMaterialRelationRequest,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ProfessionalMaterialsApplicationDependency,
) -> MaterialRelationResponse:
    return MaterialRelationResponse.from_domain(
        application.create_relation(
            user_id=current.user.user_id,
            task_id=task_id,
            source_material_id=payload.source_material_id,
            target_material_id=payload.target_material_id,
            relation_type=payload.relation_type,
            note=payload.note,
        )
    )


@router.post(
    "/batches/{batch_id}/materials",
    operation_id="batch_upload_materials",
    response_model=BatchUploadResponse,
    status_code=status.HTTP_207_MULTI_STATUS,
)
async def batch_upload_materials(
    task_id: UUID,
    batch_id: UUID,
    _task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    materials: ResearchMaterialApplicationDependency,
    archive: ProfessionalMaterialsApplicationDependency,
    idempotency_key: IdempotencyKey,
    files: Annotated[list[UploadFile], File()],
    material_kind: Annotated[MaterialKind, Form()] = MaterialKind.OTHER,
) -> BatchUploadResponse:
    items: list[BatchUploadItemResponse] = []
    for index, file in enumerate(files):
        filename = file.filename or ""
        content = await file.read(MAX_MATERIAL_BYTES + 1)
        await file.close()
        if len(content) > MAX_MATERIAL_BYTES:
            items.append(
                BatchUploadItemResponse(
                    filename=filename,
                    status="failed",
                    error_code="research_material_too_large",
                    message="单份研究材料不能超过 25 MB。",
                )
            )
            continue
        try:
            material = materials.upload(
                user_id=current.user.user_id,
                task_id=task_id,
                idempotency_key=f"{idempotency_key}:{index}",
                filename=filename,
                media_type=file.content_type or "",
                content=content,
                material_kind=material_kind,
            )
            profile = archive.ensure_profile(
                user_id=current.user.user_id,
                task_id=task_id,
                material_id=material.material_id,
            )
            archive.update_profile(
                user_id=current.user.user_id,
                task_id=task_id,
                material_id=material.material_id,
                research_role=profile.research_role,
                specific_type=profile.specific_type,
                stage=profile.stage,
                batch_id=batch_id,
                tags=profile.tags,
                collection_ids=profile.collection_ids,
                sensitivity=profile.sensitivity,
                consent_scope=profile.consent_scope,
                deidentification_status=profile.deidentification_status,
                model_processing_scope=profile.model_processing_scope,
            )
        except (ResearchMaterialError, ValueError) as error:
            items.append(
                BatchUploadItemResponse(
                    filename=filename,
                    status="failed",
                    error_code=str(getattr(error, "code", "validation_error")),
                    message=str(error),
                )
            )
        else:
            items.append(
                BatchUploadItemResponse(
                    filename=filename,
                    status="created",
                    material_id=material.material_id,
                )
            )
    return BatchUploadResponse(batch_id=batch_id, items=items)
