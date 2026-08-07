import base64
import binascii
from dataclasses import replace
from datetime import datetime
from io import BytesIO
from uuid import UUID, uuid4
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from qunxue_api.api.contracts.common import (
    ErrorResponse,
    ModelCapability,
    ModelMetadata,
    TraceMetadata,
)
from qunxue_api.api.contracts.phenomena import (
    ConfirmPhenomenonCandidateRequest,
    DirectInputRequest,
    EntryInputResponse,
    ExtractPhenomenonCandidatesRequest,
    MaterialInputRequest,
    MaterialIntakeRequest,
    MaterialIntakeRunResponse,
    PhenomenonCandidateAction,
    PhenomenonCandidatePageResponse,
    PhenomenonCandidateResponse,
    PhenomenonEvidenceReferenceResponse,
    PhenomenonExamplePageResponse,
    PhenomenonExampleResponse,
    PhenomenonSnapshotAction,
    PhenomenonSnapshotPageResponse,
    PhenomenonSnapshotResponse,
    UpdatePhenomenonCandidateRequest,
)
from qunxue_api.api.dependencies import (
    CurrentSessionDependency,
    OwnedResearchTaskDependency,
    PhenomenonServiceDependency,
    get_owned_research_task,
)
from qunxue_api.api.routes.stubs import IdempotencyKey, not_implemented_response
from qunxue_api.modules.research_intake import (
    ConfirmedPhenomenonSnapshot,
    EntryInputType,
    MaterialIntakeRun,
    PhenomenonCandidate,
    PhenomenonCandidateStatus,
    PhenomenonEvidenceRefSnapshot,
    PhenomenonEvidenceVerificationStatus,
    PhenomenonModelSnapshot,
)

router = APIRouter(
    prefix="/api/research-tasks/{task_id}",
    tags=["phenomena"],
    responses={422: {"model": ErrorResponse}},
    dependencies=[Depends(get_owned_research_task)],
)
example_router = APIRouter(tags=["phenomena"])
material_router = APIRouter(tags=["phenomena"])


@example_router.get(
    "/api/phenomenon-examples",
    operation_id="list_phenomenon_examples",
    response_model=PhenomenonExamplePageResponse,
)
def list_phenomenon_examples(
    service: PhenomenonServiceDependency,
) -> PhenomenonExamplePageResponse:
    return PhenomenonExamplePageResponse(
        items=[
            PhenomenonExampleResponse(
                example_id=item.example_id,
                title=item.title,
                phenomenon=item.phenomenon,
                research_intent=item.research_intent,
                context=item.context,
            )
            for item in service.list_examples()
        ]
    )


@material_router.get(
    "/api/material-intake-runs/{run_id}",
    operation_id="get_material_intake_run",
    response_model=MaterialIntakeRunResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_material_intake_run(
    run_id: UUID,
    current: CurrentSessionDependency,
    service: PhenomenonServiceDependency,
) -> MaterialIntakeRunResponse:
    run = service.get_material_run(run_id, user_id=current.user.user_id)
    if run is None:
        raise HTTPException(status_code=404)
    return _material_run_response(run)


@router.post(
    "/inputs/direct",
    operation_id="submit_direct_input",
    response_model=EntryInputResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def submit_direct_input(
    task_id: UUID,
    payload: DirectInputRequest,
    _idempotency_key: IdempotencyKey,
    service: PhenomenonServiceDependency,
) -> EntryInputResponse:
    direct = service.submit_direct(
        task_id=task_id,
        phenomenon=payload.phenomenon,
        research_intent=payload.research_intent,
        context=payload.context,
    )
    return EntryInputResponse(
        input_id=direct.input_id,
        task_id=direct.task_id,
        entry_type=EntryInputType.DIRECT_INPUT,
        version=direct.version,
        allowed_actions=["extract_phenomenon_candidates"],
        source_ref_ids=list(direct.source_ref_ids),
        accepted_at=direct.accepted_at,
    )


@router.post(
    "/inputs/material",
    operation_id="submit_material_input",
    response_model=EntryInputResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def submit_material_input(
    task_id: UUID,
    payload: MaterialInputRequest,
    _idempotency_key: IdempotencyKey,
) -> JSONResponse:
    return not_implemented_response()


@router.post(
    "/material-intakes",
    operation_id="submit_material_intake",
    response_model=MaterialIntakeRunResponse,
    status_code=201,
    responses={404: {"model": ErrorResponse}},
)
def submit_material_intake(
    task_id: UUID,
    payload: MaterialIntakeRequest,
    idempotency_key: IdempotencyKey,
    request: Request,
    service: PhenomenonServiceDependency,
) -> MaterialIntakeRunResponse:
    run = service.submit_material(
        task_id=task_id,
        idempotency_key=idempotency_key,
        filename=payload.filename,
        media_type=payload.media_type,
        text=_material_text(payload),
        research_intent=payload.research_intent,
        context=payload.context,
        processing_policy_version=payload.processing_policy_version,
        model=PhenomenonModelSnapshot(
            provider="deterministic-material-parser",
            model_version="1",
            capability="mock",
            degraded=False,
            knowledge_release_id=None,
            trace_id=uuid4(),
            request_id=uuid4(),
            contract_version=request.app.state.settings.contract_version,
        ),
    )
    return _material_run_response(run)


@router.post(
    "/phenomenon-candidates",
    operation_id="extract_phenomenon_candidates",
    response_model=PhenomenonCandidatePageResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def extract_phenomenon_candidates(
    task_id: UUID,
    payload: ExtractPhenomenonCandidatesRequest,
    _idempotency_key: IdempotencyKey,
    request: Request,
    service: PhenomenonServiceDependency,
) -> PhenomenonCandidatePageResponse:
    direct = service.input_for_task(task_id)
    if direct is None:
        raise HTTPException(status_code=409)
    existing = service.progress(task_id).candidate
    if existing is None:
        draft = request.app.state.model_gateway.build(
            task_id=task_id,
            raw_input=direct.phenomenon,
            research_intent=direct.research_intent,
            context=direct.context,
        )
        draft = replace(
            draft,
            source_ref_ids=tuple(
                dict.fromkeys((*draft.source_ref_ids, "input:direct"))
            ),
        )
        invocation = request.app.state.model_invocation_recorder.list_for_task(task_id)[-1]
        evidence = PhenomenonEvidenceRefSnapshot(
            evidence_ref_id="input:direct",
            excerpt=direct.phenomenon,
            source_ref_id="input:direct",
            source_description="用户直接输入",
            locator=None,
            verification_status=PhenomenonEvidenceVerificationStatus.USER_ATTESTED,
            use_boundary="仅代表用户陈述，尚未经外部来源核验。",
        )
        existing = service.save_candidate(
            task_id=task_id,
            draft=draft,
            evidence_refs=(evidence,),
            model=PhenomenonModelSnapshot(
                provider=invocation.provider,
                model_version=invocation.model_version,
                capability=invocation.capability_tier,
                degraded=invocation.degraded,
                knowledge_release_id=invocation.knowledge_release_id,
                trace_id=invocation.trace_id,
                request_id=invocation.request_id,
                contract_version=invocation.contract_version,
            ),
        )
    response = _candidate_response(existing)
    return PhenomenonCandidatePageResponse(
        task_id=task_id,
        version=existing.version,
        allowed_actions=list(response.allowed_actions),
        candidates=[response],
        stable_order=[existing.candidate_id],
        next_cursor=None,
        model=response.model,
    )


@router.get(
    "/phenomenon-candidates/{candidate_id}",
    operation_id="get_phenomenon_candidate",
    response_model=PhenomenonCandidateResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def get_phenomenon_candidate(
    task_id: UUID,
    candidate_id: UUID,
    service: PhenomenonServiceDependency,
    version: int | None = Query(default=None, ge=1),
) -> PhenomenonCandidateResponse:
    candidate = service.get_candidate(task_id, candidate_id, version)
    if candidate is None:
        raise HTTPException(status_code=404)
    return _candidate_response(candidate)


@router.patch(
    "/phenomenon-candidates/{candidate_id}",
    operation_id="update_phenomenon_candidate",
    response_model=PhenomenonCandidateResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def update_phenomenon_candidate(
    task_id: UUID,
    candidate_id: UUID,
    payload: UpdatePhenomenonCandidateRequest,
    _idempotency_key: IdempotencyKey,
    service: PhenomenonServiceDependency,
) -> PhenomenonCandidateResponse:
    candidate = service.update_candidate(
        task_id=task_id,
        candidate_id=candidate_id,
        expected_version=payload.expected_version,
        phenomenon=payload.phenomenon,
        research_intent=payload.research_intent,
        context=payload.context,
    )
    if candidate is None:
        raise HTTPException(status_code=409)
    return _candidate_response(candidate)


@router.post(
    "/phenomenon-candidates/{candidate_id}/confirm",
    operation_id="confirm_phenomenon_candidate",
    response_model=PhenomenonSnapshotResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def confirm_phenomenon_candidate(
    task_id: UUID,
    candidate_id: UUID,
    payload: ConfirmPhenomenonCandidateRequest,
    _idempotency_key: IdempotencyKey,
    service: PhenomenonServiceDependency,
    owned_task: OwnedResearchTaskDependency,
) -> PhenomenonSnapshotResponse:
    result = service.confirm_candidate(
        task_id=task_id,
        candidate_id=candidate_id,
        expected_version=payload.expected_version,
        task=owned_task,
    )
    if result is None:
        raise HTTPException(status_code=409)
    snapshot, confirmed_at = result
    candidate = service.get_candidate(task_id, candidate_id)
    assert candidate is not None
    return _snapshot_response(snapshot, candidate, confirmed_at)


@router.get(
    "/phenomenon-snapshots",
    operation_id="list_phenomenon_snapshots",
    response_model=PhenomenonSnapshotPageResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def list_phenomenon_snapshots(
    task_id: UUID,
    service: PhenomenonServiceDependency,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> PhenomenonSnapshotPageResponse:
    progress = service.progress(task_id)
    snapshots = []
    if progress.confirmed is not None and progress.confirmed_at is not None:
        assert progress.candidate is not None
        snapshots.append(
            _snapshot_response(
                progress.confirmed,
                progress.candidate,
                progress.confirmed_at,
            )
        )
    return PhenomenonSnapshotPageResponse(
        task_id=task_id,
        version=progress.candidate.version if progress.candidate else 1,
        allowed_actions=[PhenomenonSnapshotAction.START_MATCHING] if snapshots else [],
        snapshots=snapshots,
        next_cursor=None,
    )


def _evidence_response(
    evidence: PhenomenonEvidenceRefSnapshot,
) -> PhenomenonEvidenceReferenceResponse:
    return PhenomenonEvidenceReferenceResponse(**{
        "evidence_ref_id": evidence.evidence_ref_id,
        "excerpt": evidence.excerpt,
        "source_ref_id": evidence.source_ref_id,
        "source_description": evidence.source_description,
        "locator": evidence.locator,
        "verification_status": evidence.verification_status,
        "use_boundary": evidence.use_boundary,
    })


def _model_response(model: PhenomenonModelSnapshot) -> ModelMetadata:
    return ModelMetadata(
        provider=model.provider,
        model_version=model.model_version,
        capability=ModelCapability(model.capability),
        degraded=model.degraded,
        knowledge_release_id=model.knowledge_release_id,
        trace=TraceMetadata(
            trace_id=model.trace_id,
            request_id=model.request_id,
            contract_version=model.contract_version,
        ),
    )


def _candidate_response(candidate: PhenomenonCandidate) -> PhenomenonCandidateResponse:
    actions = [] if candidate.status is PhenomenonCandidateStatus.CONFIRMED else [
        PhenomenonCandidateAction.UPDATE,
        PhenomenonCandidateAction.CONFIRM,
    ]
    return PhenomenonCandidateResponse(
        candidate_id=candidate.candidate_id,
        task_id=candidate.task_id,
        version=candidate.version,
        status=candidate.status.value,
        allowed_actions=actions,
        phenomenon=candidate.phenomenon,
        research_intent=candidate.research_intent,
        context=candidate.context,
        source_ref_ids=list(candidate.source_ref_ids),
        evidence_refs=[_evidence_response(item) for item in candidate.evidence_refs],
        missing_information=list(candidate.missing_information),
        source_traceability=candidate.source_traceability,
        model=_model_response(candidate.model),
    )


def _material_run_response(run: MaterialIntakeRun) -> MaterialIntakeRunResponse:
    return MaterialIntakeRunResponse(
        run_id=run.run_id,
        task_id=run.task_id,
        status="completed",
        filename=run.filename,
        media_type=run.media_type,
        processing_policy_version=run.processing_policy_version,
        candidates=[_candidate_response(item) for item in run.candidates],
        accepted_at=run.accepted_at,
    )


def _material_text(payload: MaterialIntakeRequest) -> str:
    if payload.pasted_text is not None:
        return payload.pasted_text.strip()
    assert payload.content_base64 is not None
    try:
        content = base64.b64decode(payload.content_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(status_code=422) from error
    if len(content) > 2_000_000:
        raise HTTPException(status_code=422)
    if payload.media_type == "text/plain":
        try:
            return content.decode("utf-8").strip()
        except UnicodeDecodeError as error:
            raise HTTPException(status_code=422) from error
    try:
        with ZipFile(BytesIO(content)) as archive:
            document_xml = archive.read("word/document.xml")
        root = ElementTree.fromstring(document_xml)
    except (BadZipFile, KeyError, ElementTree.ParseError) as error:
        raise HTTPException(status_code=422) from error
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = []
    for paragraph in root.iter(f"{namespace}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{namespace}t"))
        if text.strip():
            paragraphs.append(text.strip())
    if not paragraphs:
        raise HTTPException(status_code=422)
    return "\n\n".join(paragraphs)


def _snapshot_response(
    snapshot: ConfirmedPhenomenonSnapshot,
    candidate: PhenomenonCandidate,
    confirmed_at: datetime,
) -> PhenomenonSnapshotResponse:
    return PhenomenonSnapshotResponse(
        phenomenon_query_id=snapshot.phenomenon_query_id,
        task_id=snapshot.task_id,
        version=snapshot.version,
        status="confirmed",
        allowed_actions=[PhenomenonSnapshotAction.START_MATCHING],
        phenomenon=snapshot.phenomenon,
        research_intent=snapshot.research_intent,
        context=snapshot.context,
        content_hash=snapshot.content_hash,
        source_ref_ids=list(candidate.source_ref_ids),
        evidence_refs=[_evidence_response(item) for item in snapshot.evidence_refs],
        confirmed_at=confirmed_at,
    )
