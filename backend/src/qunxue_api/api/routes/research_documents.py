from uuid import UUID, uuid4

from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse

from qunxue_api.api.contracts.common import ErrorCode, ErrorDetail, ErrorResponse
from qunxue_api.api.contracts.research_documents import (
    AcceptResearchDocumentProposalRequest,
    ConfirmResearchDocumentRequest,
    CreateResearchDocumentRequest,
    RejectResearchDocumentProposalRequest,
    ResearchDocumentExportResponse,
    ResearchDocumentListResponse,
    ResearchDocumentProposalAcceptanceResponse,
    ResearchDocumentProposalListResponse,
    ResearchDocumentProposalResponse,
    ResearchDocumentResponse,
    ResearchDocumentSectionContract,
    ResearchDocumentVersionListResponse,
    ResearchTaskDocumentProposalListResponse,
    RestoreResearchDocumentRequest,
    UpdateResearchDocumentRequest,
)
from qunxue_api.api.dependencies import (
    CurrentSessionDependency,
    OwnedResearchTaskDependency,
    ResearchDocumentApplicationDependency,
    ResearchDocumentProposalApplicationDependency,
)
from qunxue_api.api.routes.stubs import IdempotencyKey
from qunxue_api.modules.research_framework import (
    ResearchDocumentEvidenceRef,
    ResearchDocumentProposalSnapshot,
    ResearchDocumentProposalStatus,
    ResearchDocumentSection,
    ResearchDocumentSnapshot,
)

router = APIRouter(
    tags=["research-documents"],
    responses={422: {"model": ErrorResponse}},
)


@router.post(
    "/api/research-tasks/{task_id}/research-documents",
    operation_id="create_research_document",
    response_model=ResearchDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def create_research_document(
    task_id: UUID,
    task: OwnedResearchTaskDependency,
    payload: CreateResearchDocumentRequest,
    idempotency_key: IdempotencyKey,
    current: CurrentSessionDependency,
    application: ResearchDocumentApplicationDependency,
) -> ResearchDocumentResponse | JSONResponse:
    del task_id
    try:
        snapshot = application.create(
            user_id=current.user.user_id,
            task=task,
            theory_plan_id=payload.theory_plan_id,
            title=payload.title,
            sections=tuple(_section(item) for item in payload.sections),
            idempotency_key=idempotency_key,
        )
    except LookupError:
        return _error(
            404, ErrorCode.NOT_FOUND, "Confirmed theory plan was not found for this task."
        )
    except ValueError as error:
        return _error(409, ErrorCode.VALIDATION_ERROR, str(error))
    return _response(snapshot)


@router.get(
    "/api/research-tasks/{task_id}/research-documents",
    operation_id="list_research_documents",
    response_model=ResearchDocumentListResponse,
    responses={404: {"model": ErrorResponse}},
)
def list_research_documents(
    task_id: UUID,
    task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchDocumentApplicationDependency,
) -> ResearchDocumentListResponse | JSONResponse:
    try:
        snapshots = application.list_for_task(user_id=current.user.user_id, task=task)
    except LookupError:
        return _error(404, ErrorCode.NOT_FOUND, "Research task was not found.")
    return ResearchDocumentListResponse(
        task_id=task_id,
        items=[_response(item) for item in snapshots],
    )


@router.get(
    "/api/research-documents/{document_id}",
    operation_id="get_research_document",
    response_model=ResearchDocumentResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_research_document(
    document_id: UUID,
    current: CurrentSessionDependency,
    application: ResearchDocumentApplicationDependency,
    version: int | None = Query(default=None, ge=1),
) -> ResearchDocumentResponse | JSONResponse:
    try:
        return _response(
            application.get(
                user_id=current.user.user_id,
                document_id=document_id,
                version=version,
            )
        )
    except LookupError:
        return _error(404, ErrorCode.NOT_FOUND, "Research document was not found.")


@router.get(
    "/api/research-documents/{document_id}/versions",
    operation_id="list_research_document_versions",
    response_model=ResearchDocumentVersionListResponse,
    responses={404: {"model": ErrorResponse}},
)
def list_research_document_versions(
    document_id: UUID,
    current: CurrentSessionDependency,
    application: ResearchDocumentApplicationDependency,
) -> ResearchDocumentVersionListResponse | JSONResponse:
    try:
        versions = application.list_versions(user_id=current.user.user_id, document_id=document_id)
    except LookupError:
        return _error(404, ErrorCode.NOT_FOUND, "Research document was not found.")
    return ResearchDocumentVersionListResponse(
        document_id=document_id,
        items=[_response(item) for item in versions],
    )


@router.get(
    "/api/research-document-proposals/{proposal_id}",
    operation_id="get_research_document_proposal",
    response_model=ResearchDocumentProposalResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_research_document_proposal(
    proposal_id: UUID,
    current: CurrentSessionDependency,
    application: ResearchDocumentProposalApplicationDependency,
) -> ResearchDocumentProposalResponse | JSONResponse:
    try:
        return _proposal_response(
            application.get(
                user_id=current.user.user_id,
                proposal_id=proposal_id,
            )
        )
    except LookupError:
        return _error(404, ErrorCode.NOT_FOUND, "Research document proposal was not found.")


@router.get(
    "/api/research-documents/{document_id}/proposals",
    operation_id="list_research_document_proposals",
    response_model=ResearchDocumentProposalListResponse,
    responses={404: {"model": ErrorResponse}},
)
def list_research_document_proposals(
    document_id: UUID,
    current: CurrentSessionDependency,
    documents: ResearchDocumentApplicationDependency,
    application: ResearchDocumentProposalApplicationDependency,
) -> ResearchDocumentProposalListResponse | JSONResponse:
    try:
        documents.get(user_id=current.user.user_id, document_id=document_id)
        snapshots = application.list_for_document(
            user_id=current.user.user_id,
            document_id=document_id,
        )
    except LookupError:
        return _error(404, ErrorCode.NOT_FOUND, "Research document was not found.")
    return ResearchDocumentProposalListResponse(
        document_id=document_id,
        items=[_proposal_response(item) for item in snapshots],
    )


@router.get(
    "/api/research-tasks/{task_id}/research-document-proposals",
    operation_id="list_research_task_document_proposals",
    response_model=ResearchTaskDocumentProposalListResponse,
    responses={404: {"model": ErrorResponse}},
)
def list_research_task_document_proposals(
    task_id: UUID,
    task: OwnedResearchTaskDependency,
    current: CurrentSessionDependency,
    application: ResearchDocumentProposalApplicationDependency,
) -> ResearchTaskDocumentProposalListResponse | JSONResponse:
    if task.user_id != current.user.user_id:
        return _error(404, ErrorCode.NOT_FOUND, "Research task was not found.")
    try:
        snapshots = application.list_for_task(
            user_id=current.user.user_id,
            task_id=task_id,
        )
    except LookupError:
        return _error(404, ErrorCode.NOT_FOUND, "Research task was not found.")
    return ResearchTaskDocumentProposalListResponse(
        task_id=task_id,
        items=[_proposal_response(item) for item in snapshots],
    )


@router.post(
    "/api/research-document-proposals/{proposal_id}/accept",
    operation_id="accept_research_document_proposal",
    response_model=ResearchDocumentProposalAcceptanceResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def accept_research_document_proposal(
    proposal_id: UUID,
    payload: AcceptResearchDocumentProposalRequest,
    idempotency_key: IdempotencyKey,
    current: CurrentSessionDependency,
    application: ResearchDocumentProposalApplicationDependency,
) -> ResearchDocumentProposalAcceptanceResponse | JSONResponse:
    try:
        accepted = application.accept(
            user_id=current.user.user_id,
            proposal_id=proposal_id,
            expected_document_version=payload.expected_document_version,
            idempotency_key=idempotency_key,
        )
    except LookupError:
        return _error(404, ErrorCode.NOT_FOUND, "Research document proposal was not found.")
    except ValueError as error:
        return _error(409, ErrorCode.VALIDATION_ERROR, str(error))
    return ResearchDocumentProposalAcceptanceResponse(
        proposal=_proposal_response(accepted.proposal),
        document=_response(accepted.document),
    )


@router.post(
    "/api/research-document-proposals/{proposal_id}/reject",
    operation_id="reject_research_document_proposal",
    response_model=ResearchDocumentProposalResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def reject_research_document_proposal(
    proposal_id: UUID,
    payload: RejectResearchDocumentProposalRequest,
    idempotency_key: IdempotencyKey,
    current: CurrentSessionDependency,
    application: ResearchDocumentProposalApplicationDependency,
) -> ResearchDocumentProposalResponse | JSONResponse:
    try:
        return _proposal_response(
            application.reject(
                user_id=current.user.user_id,
                proposal_id=proposal_id,
                reason=payload.reason,
                idempotency_key=idempotency_key,
            )
        )
    except LookupError:
        return _error(404, ErrorCode.NOT_FOUND, "Research document proposal was not found.")
    except ValueError as error:
        return _error(409, ErrorCode.VALIDATION_ERROR, str(error))


@router.patch(
    "/api/research-documents/{document_id}",
    operation_id="update_research_document",
    response_model=ResearchDocumentResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def update_research_document(
    document_id: UUID,
    payload: UpdateResearchDocumentRequest,
    idempotency_key: IdempotencyKey,
    current: CurrentSessionDependency,
    application: ResearchDocumentApplicationDependency,
) -> ResearchDocumentResponse | JSONResponse:
    try:
        return _response(
            application.revise(
                user_id=current.user.user_id,
                document_id=document_id,
                expected_version=payload.expected_version,
                sections=tuple(_section(item) for item in payload.sections),
                change_summary=payload.change_summary,
                actor="user",
                idempotency_key=idempotency_key,
            )
        )
    except LookupError:
        return _error(404, ErrorCode.NOT_FOUND, "Research document was not found.")
    except ValueError as error:
        return _error(409, ErrorCode.VALIDATION_ERROR, str(error))


@router.post(
    "/api/research-documents/{document_id}/restore",
    operation_id="restore_research_document",
    response_model=ResearchDocumentResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def restore_research_document(
    document_id: UUID,
    payload: RestoreResearchDocumentRequest,
    idempotency_key: IdempotencyKey,
    current: CurrentSessionDependency,
    application: ResearchDocumentApplicationDependency,
) -> ResearchDocumentResponse | JSONResponse:
    try:
        return _response(
            application.restore(
                user_id=current.user.user_id,
                document_id=document_id,
                source_version=payload.source_version,
                expected_version=payload.expected_version,
                reason=payload.reason,
                idempotency_key=idempotency_key,
            )
        )
    except LookupError:
        return _error(
            404, ErrorCode.NOT_FOUND, "Research document or source version was not found."
        )
    except ValueError as error:
        return _error(409, ErrorCode.VALIDATION_ERROR, str(error))


@router.post(
    "/api/research-documents/{document_id}/confirm",
    operation_id="confirm_research_document",
    response_model=ResearchDocumentResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def confirm_research_document(
    document_id: UUID,
    payload: ConfirmResearchDocumentRequest,
    idempotency_key: IdempotencyKey,
    current: CurrentSessionDependency,
    application: ResearchDocumentApplicationDependency,
) -> ResearchDocumentResponse | JSONResponse:
    try:
        return _response(
            application.confirm(
                user_id=current.user.user_id,
                document_id=document_id,
                expected_version=payload.expected_version,
                idempotency_key=idempotency_key,
            )
        )
    except LookupError:
        return _error(404, ErrorCode.NOT_FOUND, "Research document was not found.")
    except ValueError as error:
        return _error(409, ErrorCode.VALIDATION_ERROR, str(error))


@router.get(
    "/api/research-documents/{document_id}/export",
    operation_id="export_research_document",
    response_model=ResearchDocumentExportResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def export_research_document(
    document_id: UUID,
    current: CurrentSessionDependency,
    application: ResearchDocumentApplicationDependency,
    version: int | None = Query(default=None, ge=1),
) -> ResearchDocumentExportResponse | JSONResponse:
    try:
        exported = application.export_markdown(
            user_id=current.user.user_id,
            document_id=document_id,
            version=version,
        )
    except LookupError:
        return _error(404, ErrorCode.NOT_FOUND, "Research document was not found.")
    except ValueError as error:
        return _error(409, ErrorCode.VALIDATION_ERROR, str(error))
    return ResearchDocumentExportResponse(
        document_id=exported.document_id,
        task_id=exported.task_id,
        theory_plan_id=exported.theory_plan_id,
        knowledge_release_id=exported.knowledge_release_id,
        version=exported.version,
        filename=exported.filename,
        media_type="text/markdown",
        markdown=exported.markdown,
    )


def _section(item: ResearchDocumentSectionContract) -> ResearchDocumentSection:
    return ResearchDocumentSection(
        section_id=item.section_id,
        key=item.key,
        title=item.title,
        content=item.content,
        status=item.status,
        evidence_refs=tuple(
            ResearchDocumentEvidenceRef(
                evidence_ref_id=evidence.evidence_ref_id,
                source_id=evidence.source_id,
                knowledge_release_id=evidence.knowledge_release_id,
            )
            for evidence in item.evidence_refs
        ),
    )


def _response(snapshot: ResearchDocumentSnapshot) -> ResearchDocumentResponse:
    return ResearchDocumentResponse(
        document_id=snapshot.document_id,
        task_id=snapshot.task_id,
        theory_plan_id=snapshot.theory_plan_id,
        knowledge_release_id=snapshot.knowledge_release_id,
        revision_id=snapshot.revision_id,
        version=snapshot.version,
        title=snapshot.title,
        sections=[
            ResearchDocumentSectionContract(
                section_id=section.section_id,
                key=section.key,
                title=section.title,
                content=section.content,
                status=section.status,
                evidence_refs=[
                    {
                        "evidence_ref_id": evidence.evidence_ref_id,
                        "source_id": evidence.source_id,
                        "knowledge_release_id": evidence.knowledge_release_id,
                    }
                    for evidence in section.evidence_refs
                ],
            )
            for section in snapshot.sections
        ],
        status=snapshot.status,
        change_summary=snapshot.change_summary,
        actor=snapshot.actor,
        restored_from_version=snapshot.restored_from_version,
        created_at=snapshot.created_at,
        confirmed_at=snapshot.confirmed_at,
    )


def _proposal_response(
    snapshot: ResearchDocumentProposalSnapshot,
) -> ResearchDocumentProposalResponse:
    return ResearchDocumentProposalResponse(
        proposal_id=snapshot.proposal_id,
        kind=snapshot.kind,
        status=snapshot.status,
        user_id=snapshot.user_id,
        conversation_id=snapshot.conversation_id,
        agent_run_id=snapshot.agent_run_id,
        task_id=snapshot.task_id,
        theory_plan_id=snapshot.theory_plan_id,
        knowledge_release_id=snapshot.knowledge_release_id,
        title=snapshot.title,
        proposed_sections=[
            ResearchDocumentSectionContract(
                section_id=section.section_id,
                key=section.key,
                title=section.title,
                content=section.content,
                status=section.status,
                evidence_refs=[
                    {
                        "evidence_ref_id": evidence.evidence_ref_id,
                        "source_id": evidence.source_id,
                        "knowledge_release_id": evidence.knowledge_release_id,
                    }
                    for evidence in section.evidence_refs
                ],
            )
            for section in snapshot.proposed_sections
        ],
        rationale=snapshot.rationale,
        document_id=snapshot.document_id,
        base_document_version=snapshot.base_document_version,
        target_section_id=snapshot.target_section_id,
        decision_reason=snapshot.decision_reason,
        result_document_id=snapshot.result_document_id,
        result_document_version=snapshot.result_document_version,
        requires_user_approval=(snapshot.status is ResearchDocumentProposalStatus.PENDING),
        created_at=snapshot.created_at,
        decided_at=snapshot.decided_at,
    )


def _error(status_code: int, code: ErrorCode, message: str) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message, trace_id=str(uuid4())))
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))
