import asyncio
import logging
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager, suppress
from datetime import UTC, datetime, timedelta
from inspect import Parameter, signature
from threading import Lock
from time import sleep
from uuid import UUID, uuid4

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from qunxue_api.account_extension import install_account_management
from qunxue_api.adapters.email import ResendEmailProvider
from qunxue_api.adapters.model import (
    BuiltInCaseCatalog,
    ModelEndpoint,
    ModelGateway,
    ModelInvocationError,
    ModelProvider,
    ModelRouteExecutor,
    OpenAICompatibleModelProvider,
    RoutedModelProvider,
    SqliteModelAttemptRecorder,
    SqliteModelInvocationRecorder,
    create_deterministic_mock_provider,
)
from qunxue_api.adapters.research_agent import (
    DeterministicKnowledgeRunner,
    OpenAICompatibleEmbeddingProvider,
    OpenWebResearchClient,
    PydanticAIKnowledgeRunner,
    ResearchDocumentToolRegistry,
    SiliconFlowRerankerProvider,
)
from qunxue_api.adapters.research_exchange import map_published_qunxue_project
from qunxue_api.adapters.research_materials import parse_material
from qunxue_api.adapters.research_materials.doi import CrossrefDoiMetadataResolver
from qunxue_api.adapters.retrieval import (
    RETRIEVAL_CORPUS_SCHEMA_VERSION,
    HybridRetriever,
    SqliteRetrievalIndex,
)
from qunxue_api.adapters.security import Argon2PasswordHasher
from qunxue_api.adapters.sqlite.agent_conversation_repository import SqliteConversationRepository
from qunxue_api.adapters.sqlite.billing_repository import SqliteCreditRepository
from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.adapters.sqlite.identity_repository import SqliteIdentityRepository
from qunxue_api.adapters.sqlite.knowledge_catalog import SqliteKnowledgeCatalog
from qunxue_api.adapters.sqlite.phenomenon_repository import SqlitePhenomenonRepository
from qunxue_api.adapters.sqlite.professional_material_repository import (
    SqliteProfessionalMaterialRepository,
)
from qunxue_api.adapters.sqlite.research_analysis_repository import (
    SqliteResearchAnalysisRepository,
)
from qunxue_api.adapters.sqlite.research_cycle_repository import SqliteResearchCycleRepository
from qunxue_api.adapters.sqlite.research_document import (
    SqliteResearchDocumentRepository,
)
from qunxue_api.adapters.sqlite.research_document_mutation import (
    SqliteResearchDocumentMutationRepository,
)
from qunxue_api.adapters.sqlite.research_document_proposal import (
    SqliteResearchDocumentProposalRepository,
)
from qunxue_api.adapters.sqlite.research_material_repository import (
    SqliteResearchMaterialRepository,
)
from qunxue_api.adapters.sqlite.research_material_search import (
    SqliteResearchMaterialSearchRepository,
)
from qunxue_api.adapters.sqlite.research_method_repository import SqliteMethodPlanRepository
from qunxue_api.adapters.sqlite.research_project_audit import (
    SqliteResearchProjectAuditRepository,
)
from qunxue_api.adapters.sqlite.research_start_proposal import (
    SqliteResearchStartProposalRepository,
)
from qunxue_api.adapters.sqlite.research_task_repository import (
    SqliteResearchTaskRepository,
)
from qunxue_api.adapters.sqlite.theory_matching import (
    SqliteMatchingRequestRepository,
    SqliteMatchRunRepository,
)
from qunxue_api.adapters.theory_evidence import (
    CatalogTheoryEvidenceSource,
    CatalogTheoryLexicalRetriever,
)
from qunxue_api.adapters.transcription import (
    DashScopeTranscriptionProvider,
    OpenAICompatibleTranscriptionProvider,
    parse_imported_transcript,
)
from qunxue_api.api.contracts.common import ErrorCode, ErrorDetail, ErrorResponse
from qunxue_api.api.routes.agent import router as agent_router
from qunxue_api.api.routes.frameworks import router as frameworks_router
from qunxue_api.api.routes.health import router as health_router
from qunxue_api.api.routes.knowledge import router as knowledge_router
from qunxue_api.api.routes.matching import router as matching_router
from qunxue_api.api.routes.phenomena import example_router as phenomenon_examples_router
from qunxue_api.api.routes.phenomena import material_router as material_intakes_router
from qunxue_api.api.routes.phenomena import router as phenomena_router
from qunxue_api.api.routes.professional_materials import (
    router as professional_materials_router,
)
from qunxue_api.api.routes.research_analysis import router as research_analysis_router
from qunxue_api.api.routes.research_batch_coding import router as research_batch_coding_router
from qunxue_api.api.routes.research_cycle import router as research_cycle_router
from qunxue_api.api.routes.research_documents import router as research_documents_router
from qunxue_api.api.routes.research_exchange import router as research_exchange_router
from qunxue_api.api.routes.research_materials import router as research_materials_router
from qunxue_api.api.routes.research_method import router as research_method_router
from qunxue_api.api.routes.research_tasks import router as research_tasks_router
from qunxue_api.api.routes.session import router as session_router
from qunxue_api.api.routes.transcription import router as transcription_router
from qunxue_api.application import (
    DisciplinaryAgentApplication,
    ProfessionalMaterialsApplication,
    ResearchAnalysisApplication,
    ResearchBatchCodingApplication,
    ResearchCycleApplication,
    ResearchDocumentApplication,
    ResearchDocumentProposalApplication,
    ResearchJourney,
    ResearchJourneyDependencies,
    ResearchMaterialApplication,
    ResearchMethodPlanApplication,
    ResearchProjectExchangeApplication,
    ResearchStartApplication,
    TheoryMatchingApplication,
    TranscriptionApplication,
)
from qunxue_api.application.agent_research_workflow import AgentResearchWorkflow
from qunxue_api.modules.agent_conversation import ConversationNotFound, ConversationService
from qunxue_api.modules.billing import CreditService
from qunxue_api.modules.identity import (
    EmailAlreadyRegistered,
    EmailDeliveryUnavailable,
    IdentityError,
    IdentityService,
    InvalidEmail,
    InvalidVerificationCode,
    Unauthenticated,
    VerificationCodeRateLimited,
)
from qunxue_api.modules.research_analysis import ResearchAnalysisService
from qunxue_api.modules.research_framework import (
    ResearchDocumentProposalService,
    ResearchDocumentService,
)
from qunxue_api.modules.research_intake import (
    PhenomenonService,
    ResearchStartIdempotencyConflict,
    ResearchStartProposalConflict,
    ResearchStartProposalNotFound,
    ResearchStartSourceIncomplete,
    ResearchTaskNotFound,
    ResearchTaskService,
)
from qunxue_api.modules.research_materials import (
    MaterialIngestionStatus,
    MaterialParseError,
)
from qunxue_api.modules.research_method import MethodPlanService
from qunxue_api.modules.theory_matching import TheoryMatchingService
from qunxue_api.modules.transcription import (
    ProcessingLocation,
    TranscriptionProvider,
    UnavailableTranscriptionProvider,
)
from qunxue_api.settings import (
    KNOWLEDGE_ROOT,
    Settings,
    get_settings,
)

logger = logging.getLogger(__name__)


def _build_transcription_provider(settings: Settings) -> TranscriptionProvider:
    if not settings.has_transcription_provider:
        return UnavailableTranscriptionProvider()
    provider_type = (
        DashScopeTranscriptionProvider
        if "dashscope" in (settings.transcription_base_url or "")
        and (settings.transcription_model or "").endswith("filetrans")
        else OpenAICompatibleTranscriptionProvider
    )
    return provider_type(
        base_url=settings.transcription_base_url or "",
        api_key=(
            settings.transcription_api_key.get_secret_value()
            if settings.transcription_api_key
            else ""
        ),
        model=settings.transcription_model or "",
        processing_location=ProcessingLocation(settings.transcription_processing_location),
        timeout_seconds=settings.transcription_timeout_seconds,
    )


def create_app(
    *,
    settings: Settings | None = None,
    database: Database | None = None,
    journey_dependencies: ResearchJourneyDependencies | None = None,
    model_provider: ModelProvider | None = None,
    knowledge_retriever: HybridRetriever | None = None,
    require_email_verification: bool = True,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    resolved_database = database or Database(resolved_settings.database_url)

    async def run_model_probe_loop(app: FastAPI) -> None:
        while True:
            try:
                await asyncio.to_thread(app.state.model_provider.probe)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("Model health probe failed.")
            await asyncio.sleep(resolved_settings.model_probe_interval_seconds)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        probe_task = None
        if app.state.model_router is not None:
            probe_task = asyncio.create_task(
                run_model_probe_loop(app),
                name="qunxue-model-health-probe",
            )
        app.state.model_probe_task = probe_task
        try:
            yield
        finally:
            if probe_task is not None:
                probe_task.cancel()
                with suppress(asyncio.CancelledError):
                    await probe_task

    def build_catalog_evidence_source(
        *,
        analysis_application: ResearchAnalysisApplication,
    ) -> CatalogTheoryEvidenceSource:
        """Build the release-bound source while tolerating older test doubles.

        The comparison projection is an optional extension of the adapter
        constructor.  Keeping the capability check at this composition point
        lets narrow bootstrap tests replace the adapter with a legacy-shaped
        double without weakening the production wiring.
        """
        kwargs: dict[str, object] = {"retriever": app.state.knowledge_retriever}
        try:
            parameters = signature(CatalogTheoryEvidenceSource).parameters
        except (TypeError, ValueError):
            parameters = {}
        accepts_analysis = "get_confirmed_analysis_evidence" in parameters or any(
            parameter.kind is Parameter.VAR_KEYWORD for parameter in parameters.values()
        )
        if accepts_analysis:
            kwargs["get_confirmed_analysis_evidence"] = (
                analysis_application.confirmed_cycle_evidence
            )
        elif "get_confirmed_comparison_projection" in parameters:
            kwargs["get_confirmed_comparison_projection"] = (
                analysis_application.get_confirmed_comparison_projection
            )
        return CatalogTheoryEvidenceSource(app.state.knowledge_catalog, **kwargs)

    app = FastAPI(
        title=resolved_settings.app_name,
        version="0.1.0",
        description="群学致知前后端架构基线 API。",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "Idempotency-Key"],
    )
    app.state.settings = resolved_settings
    app.state.require_email_verification = require_email_verification
    app.state.email_provider = (
        ResendEmailProvider(
            api_key=resolved_settings.resend_api_key.get_secret_value(),
            from_email=resolved_settings.email_from,
        )
        if resolved_settings.has_resend_api_key
        else None
    )
    app.state.matching_start_lock = Lock()
    app.state.research_start_lock = Lock()
    app.state.database = resolved_database
    app.state.knowledge_catalog = SqliteKnowledgeCatalog(
        resolved_database,
        knowledge_root=KNOWLEDGE_ROOT,
    )
    resolved_knowledge_retriever = knowledge_retriever or _retriever_from_settings(
        resolved_settings
    )
    if resolved_knowledge_retriever is None and resolved_settings.has_model_api_key:
        resolved_knowledge_retriever = CatalogTheoryLexicalRetriever(app.state.knowledge_catalog)
    app.state.knowledge_retriever = resolved_knowledge_retriever
    builtin_case_catalog = BuiltInCaseCatalog.default()
    model_endpoints = (
        _model_endpoints_from_settings(resolved_settings)
        if _effective_model_runtime_mode(resolved_settings) != "mock"
        else ()
    )
    if model_provider is None:
        (
            resolved_model_provider,
            model_router,
            model_attempt_recorder,
        ) = _model_provider_from_settings(
            settings=resolved_settings,
            builtin_case_catalog=builtin_case_catalog,
            database=resolved_database,
            endpoints=model_endpoints,
        )
    else:
        resolved_model_provider = model_provider
        model_router = None
        model_attempt_recorder = None
    model_invocation_recorder = SqliteModelInvocationRecorder(resolved_database)
    app.state.builtin_case_catalog = builtin_case_catalog
    app.state.model_invocation_recorder = model_invocation_recorder
    app.state.model_endpoints = model_endpoints
    app.state.model_router = model_router
    app.state.model_attempt_recorder = model_attempt_recorder
    app.state.model_provider = resolved_model_provider
    app.state.model_gateway = ModelGateway(
        provider=resolved_model_provider,
        recorder=model_invocation_recorder,
        contract_version=resolved_settings.contract_version,
    )
    app.state.research_journey = (
        ResearchJourney(journey_dependencies) if journey_dependencies is not None else None
    )
    password_hasher = Argon2PasswordHasher()
    invalid_password_hash = password_hasher.hash("invalid-account-password")

    @contextmanager
    def identity_service_scope() -> Iterator[IdentityService]:
        with resolved_database.session() as session:
            yield IdentityService(
                SqliteIdentityRepository(session),
                password_hasher,
                invalid_password_hash=invalid_password_hash,
                session_ttl=timedelta(seconds=resolved_settings.session_ttl_seconds),
                email_provider=app.state.email_provider,
                require_email_verification=app.state.require_email_verification,
            )

    @contextmanager
    def research_task_service_scope() -> Iterator[ResearchTaskService]:
        with resolved_database.session() as session:
            yield ResearchTaskService(SqliteResearchTaskRepository(session))

    @contextmanager
    def phenomenon_service_scope() -> Iterator[PhenomenonService]:
        with resolved_database.session() as session:
            yield PhenomenonService(
                SqlitePhenomenonRepository(session),
                SqliteResearchTaskRepository(session),
            )

    def build_research_analysis_application(
        session,
        *,
        task_repository: SqliteResearchTaskRepository | None = None,
    ) -> ResearchAnalysisApplication:
        return ResearchAnalysisApplication(
            analysis=ResearchAnalysisService(SqliteResearchAnalysisRepository(session)),
            materials=SqliteResearchMaterialRepository(session),
            research_tasks=task_repository or SqliteResearchTaskRepository(session),
            commit=session.commit,
        )

    @contextmanager
    def theory_matching_application_scope() -> Iterator[TheoryMatchingApplication]:
        # Hold the process lock until the transaction commits. Cross-process
        # writers are rejected by the task repository's version CAS.
        with app.state.matching_start_lock, resolved_database.session() as session:
            descriptor = app.state.model_gateway.descriptor
            analysis_application = build_research_analysis_application(session)
            method_plan_service = MethodPlanService(SqliteMethodPlanRepository(session))
            matching = TheoryMatchingService(
                evidence_source=build_catalog_evidence_source(
                    analysis_application=analysis_application,
                ),
                judge=app.state.model_gateway,
                repository=SqliteMatchRunRepository(session),
                provider=descriptor.provider,
                model_version=descriptor.model_version,
                capability=descriptor.capability_tier,
                contract_version=resolved_settings.contract_version,
            )
            yield TheoryMatchingApplication(
                catalog=app.state.knowledge_catalog,
                matching=matching,
                matching_requests=SqliteMatchingRequestRepository(session),
                research_tasks=SqliteResearchTaskRepository(session),
                rollback=session.rollback,
                invalidate_method_plan=(
                    lambda task_id, reason: method_plan_service.mark_stale_for_task(
                        task_id=task_id, reason=reason
                    )
                ),
            )

    app.state.research_task_service_scope = research_task_service_scope
    app.state.phenomenon_service_scope = phenomenon_service_scope
    app.state.theory_matching_application_scope = theory_matching_application_scope

    @contextmanager
    def research_material_application_scope() -> Iterator[ResearchMaterialApplication]:
        with resolved_database.session() as session:
            yield ResearchMaterialApplication(
                materials=SqliteResearchMaterialRepository(session),
                research_tasks=SqliteResearchTaskRepository(session),
                parser=parse_material,
                search=SqliteResearchMaterialSearchRepository(session),
                transcription_available=resolved_settings.has_transcription_provider,
                commit=session.commit,
                rollback=session.rollback,
            )

    app.state.research_material_application_scope = research_material_application_scope

    ingestion_executor = ThreadPoolExecutor(
        max_workers=2,
        thread_name_prefix="qunxue-material-ingestion",
    )

    def process_research_material_ingestion(job_id: UUID) -> None:
        while True:
            try:
                with research_material_application_scope() as application:
                    job = application.process_ingestion(job_id)
            except MaterialParseError:
                logger.info(
                    "research material ingestion needs user action",
                    extra={"job_id": str(job_id)},
                )
                return
            except Exception:
                logger.exception(
                    "research material ingestion attempt failed",
                    extra={"job_id": str(job_id)},
                )
                with research_material_application_scope() as application:
                    job = application.get_ingestion_job(job_id)
            if (
                job is None
                or job.ingestion_status is not MaterialIngestionStatus.FAILED
                or job.completed_at is not None
                or job.attempt_count >= job.max_attempts
            ):
                return
            delay = max(0.0, (job.available_at - datetime.now(UTC)).total_seconds())
            if delay:
                sleep(delay)

    def schedule_research_material_ingestion(job_id: UUID) -> None:
        ingestion_executor.submit(process_research_material_ingestion, job_id)

    def recover_research_material_ingestions() -> None:
        with research_material_application_scope() as application:
            recoverable = application.recoverable_ingestion_ids()
        for job_id in recoverable:
            schedule_research_material_ingestion(job_id)

    def shutdown_research_material_ingestions() -> None:
        ingestion_executor.shutdown(wait=True, cancel_futures=False)

    app.state.schedule_research_material_ingestion = schedule_research_material_ingestion
    app.router.add_event_handler("startup", recover_research_material_ingestions)
    app.router.add_event_handler("shutdown", shutdown_research_material_ingestions)

    @contextmanager
    def professional_materials_application_scope() -> Iterator[ProfessionalMaterialsApplication]:
        with resolved_database.session() as session:
            yield ProfessionalMaterialsApplication(
                archive=SqliteProfessionalMaterialRepository(session),
                materials=SqliteResearchMaterialRepository(session),
                research_tasks=SqliteResearchTaskRepository(session),
                commit=session.commit,
                doi_resolver=CrossrefDoiMetadataResolver(),
            )

    app.state.professional_materials_application_scope = professional_materials_application_scope
    transcription_provider = _build_transcription_provider(resolved_settings)

    @contextmanager
    def transcription_application_scope() -> Iterator[TranscriptionApplication]:
        with resolved_database.session() as session:
            yield TranscriptionApplication(
                materials=SqliteResearchMaterialRepository(session),
                archive=SqliteProfessionalMaterialRepository(session),
                research_tasks=SqliteResearchTaskRepository(session),
                provider=transcription_provider,
                importer=parse_imported_transcript,
                commit=session.commit,
            )

    app.state.transcription_application_scope = transcription_application_scope

    @contextmanager
    def research_analysis_application_scope() -> Iterator[ResearchAnalysisApplication]:
        with resolved_database.session() as session:
            yield build_research_analysis_application(session)

    app.state.research_analysis_application_scope = research_analysis_application_scope

    @contextmanager
    def research_batch_coding_application_scope() -> Iterator[ResearchBatchCodingApplication]:
        with resolved_database.session() as session:
            materials = SqliteResearchMaterialRepository(session)
            yield ResearchBatchCodingApplication(
                analysis=ResearchAnalysisService(SqliteResearchAnalysisRepository(session)),
                materials=materials,
                research_tasks=SqliteResearchTaskRepository(session),
                batches=SqliteResearchAnalysisRepository(session),
            )

    app.state.research_batch_coding_application_scope = research_batch_coding_application_scope

    @contextmanager
    def research_project_exchange_application_scope() -> Iterator[
        ResearchProjectExchangeApplication
    ]:
        with resolved_database.session() as session:
            yield ResearchProjectExchangeApplication(
                research_tasks=SqliteResearchTaskRepository(session),
                materials=SqliteResearchMaterialRepository(session),
                professional_archive=SqliteProfessionalMaterialRepository(session),
                analysis=SqliteResearchAnalysisRepository(session),
                documents=SqliteResearchDocumentRepository(session),
                cycles=SqliteResearchCycleRepository(session),
                audit=SqliteResearchProjectAuditRepository(session),
                project_mapper=map_published_qunxue_project,
                commit=session.commit,
            )

    app.state.research_project_exchange_application_scope = (
        research_project_exchange_application_scope
    )

    @contextmanager
    def research_method_plan_application_scope() -> Iterator[ResearchMethodPlanApplication]:
        with resolved_database.session() as session:
            documents = SqliteResearchDocumentRepository(session)
            matches = SqliteMatchRunRepository(session)
            task_repository = SqliteResearchTaskRepository(session)
            material_repository = SqliteResearchMaterialRepository(session)
            analysis_application = build_research_analysis_application(
                session,
                task_repository=task_repository,
            )
            professional_application = ProfessionalMaterialsApplication(
                archive=SqliteProfessionalMaterialRepository(session),
                materials=material_repository,
                research_tasks=task_repository,
            )
            cycle_application = ResearchCycleApplication(
                analysis=analysis_application,
                materials=material_repository,
                professional_materials=professional_application,
                get_theory_plan_for_task=matches.get_confirmed_plan_for_task,
                snapshots=SqliteResearchCycleRepository(session),
            )
            yield ResearchMethodPlanApplication(
                plans=MethodPlanService(SqliteMethodPlanRepository(session)),
                research_tasks=task_repository,
                mutations=SqliteResearchDocumentMutationRepository(session),
                get_framework=documents.latest,
                get_theory_plan=matches.get_confirmed_plan,
                get_cycle_snapshot=lambda user_id, task_id: cycle_application.current(
                    user_id=user_id,
                    task_id=task_id,
                ),
            )

    app.state.research_method_plan_application_scope = research_method_plan_application_scope

    @contextmanager
    def research_cycle_application_scope() -> Iterator[ResearchCycleApplication]:
        with resolved_database.session() as session:
            task_repository = SqliteResearchTaskRepository(session)
            material_repository = SqliteResearchMaterialRepository(session)
            yield ResearchCycleApplication(
                analysis=build_research_analysis_application(
                    session,
                    task_repository=task_repository,
                ),
                materials=material_repository,
                professional_materials=ProfessionalMaterialsApplication(
                    archive=SqliteProfessionalMaterialRepository(session),
                    materials=material_repository,
                    research_tasks=task_repository,
                ),
                get_theory_plan_for_task=SqliteMatchRunRepository(
                    session
                ).get_confirmed_plan_for_task,
                snapshots=SqliteResearchCycleRepository(session),
            )

    app.state.research_cycle_application_scope = research_cycle_application_scope

    @contextmanager
    def research_navigation_match_reader_scope() -> Iterator[SqliteMatchRunRepository]:
        with resolved_database.session() as session:
            yield SqliteMatchRunRepository(session)

    app.state.research_navigation_match_reader_scope = research_navigation_match_reader_scope

    @contextmanager
    def research_start_application_scope() -> Iterator[ResearchStartApplication]:
        # Keep the in-process read/create/link sequence contiguous; database
        # uniqueness remains the cross-process duplicate-task backstop.
        with app.state.research_start_lock, resolved_database.session() as session:
            task_repository = SqliteResearchTaskRepository(session)
            yield ResearchStartApplication(
                proposals=SqliteResearchStartProposalRepository(session),
                bindings=SqliteConversationRepository(session),
                tasks=ResearchTaskService(task_repository),
                phenomena=PhenomenonService(SqlitePhenomenonRepository(session), task_repository),
            )

    app.state.research_start_application_scope = research_start_application_scope

    @contextmanager
    def research_document_application_scope() -> Iterator[ResearchDocumentApplication]:
        with resolved_database.session() as session:
            match_runs = SqliteMatchRunRepository(session)
            method_plans = SqliteMethodPlanRepository(session)
            method_plan_service = MethodPlanService(method_plans)
            matching_requests = SqliteMatchingRequestRepository(session)
            proposals = SqliteResearchDocumentProposalRepository(session)
            analysis_application = build_research_analysis_application(session)
            yield ResearchDocumentApplication(
                documents=ResearchDocumentService(
                    repository=SqliteResearchDocumentRepository(session)
                ),
                research_tasks=SqliteResearchTaskRepository(session),
                mutations=SqliteResearchDocumentMutationRepository(session),
                get_theory_plan=match_runs.get_confirmed_plan,
                get_match_run=match_runs.get,
                list_proposals_for_task=proposals.list_for_task,
                list_actionable_proposals_for_task=proposals.list_actionable_for_task,
                owns_match_run=matching_requests.owns,
                formal_analysis_handoff=analysis_application.formal_handoff,
                get_method_plan=method_plans.latest_for_task,
                invalidate_method_plan=(
                    lambda task_id, reason: method_plan_service.mark_stale_for_task(
                        task_id=task_id, reason=reason
                    )
                ),
            )

    app.state.research_document_application_scope = research_document_application_scope

    @contextmanager
    def research_document_proposal_application_scope() -> Iterator[
        ResearchDocumentProposalApplication
    ]:
        with resolved_database.session() as session:
            documents = ResearchDocumentService(
                repository=SqliteResearchDocumentRepository(session)
            )
            match_runs = SqliteMatchRunRepository(session)
            method_plans = SqliteMethodPlanRepository(session)
            method_plan_service = MethodPlanService(method_plans)
            matching_requests = SqliteMatchingRequestRepository(session)
            proposal_repository = SqliteResearchDocumentProposalRepository(session)
            analysis_application = build_research_analysis_application(session)
            document_application = ResearchDocumentApplication(
                documents=documents,
                research_tasks=SqliteResearchTaskRepository(session),
                mutations=SqliteResearchDocumentMutationRepository(session),
                get_theory_plan=match_runs.get_confirmed_plan,
                get_match_run=match_runs.get,
                list_proposals_for_task=proposal_repository.list_for_task,
                list_actionable_proposals_for_task=(proposal_repository.list_actionable_for_task),
                owns_match_run=matching_requests.owns,
                formal_analysis_handoff=analysis_application.formal_handoff,
                get_method_plan=method_plans.latest_for_task,
                invalidate_method_plan=(
                    lambda task_id, reason: method_plan_service.mark_stale_for_task(
                        task_id=task_id, reason=reason
                    )
                ),
            )
            yield ResearchDocumentProposalApplication(
                ResearchDocumentProposalService(
                    repository=proposal_repository,
                    documents=documents,
                    atomic=session.begin_nested,
                    validate_proposal=document_application.validate_proposal,
                ),
                research_tasks=SqliteResearchTaskRepository(session),
                mutations=SqliteResearchDocumentMutationRepository(session),
                invalidate_method_plan=(
                    lambda task_id, reason: method_plan_service.mark_stale_for_task(
                        task_id=task_id, reason=reason
                    )
                ),
            )

    app.state.research_document_proposal_application_scope = (
        research_document_proposal_application_scope
    )

    @contextmanager
    def disciplinary_agent_scope() -> Iterator[DisciplinaryAgentApplication]:
        with resolved_database.session() as session:
            conversation_repository = SqliteConversationRepository(session)
            conversations = ConversationService(conversation_repository)
            task_repository = SqliteResearchTaskRepository(session)
            task_service = ResearchTaskService(task_repository)
            phenomenon_service = PhenomenonService(
                SqlitePhenomenonRepository(session), task_repository
            )
            document_service = ResearchDocumentService(
                repository=SqliteResearchDocumentRepository(session)
            )
            match_runs = SqliteMatchRunRepository(session)
            method_plans = SqliteMethodPlanRepository(session)
            method_plan_service = MethodPlanService(method_plans)
            matching_requests = SqliteMatchingRequestRepository(session)
            proposal_repository = SqliteResearchDocumentProposalRepository(session)
            material_repository = SqliteResearchMaterialRepository(session)
            analysis_application = build_research_analysis_application(
                session,
                task_repository=task_repository,
            )
            descriptor = app.state.model_gateway.descriptor
            matching_service = TheoryMatchingService(
                evidence_source=build_catalog_evidence_source(
                    analysis_application=analysis_application,
                ),
                judge=app.state.model_gateway,
                repository=match_runs,
                provider=descriptor.provider,
                model_version=descriptor.model_version,
                capability=descriptor.capability_tier,
                contract_version=resolved_settings.contract_version,
            )
            matching_application = TheoryMatchingApplication(
                catalog=app.state.knowledge_catalog,
                matching=matching_service,
                matching_requests=matching_requests,
                research_tasks=task_repository,
                rollback=session.rollback,
                invalidate_method_plan=(
                    lambda task_id, reason: method_plan_service.mark_stale_for_task(
                        task_id=task_id, reason=reason
                    )
                ),
            )
            research_start_application = ResearchStartApplication(
                proposals=SqliteResearchStartProposalRepository(session),
                bindings=conversation_repository,
                tasks=task_service,
                phenomena=phenomenon_service,
            )
            agent_research_workflow = AgentResearchWorkflow(
                bindings=conversation_repository,
                tasks=task_service,
                task_repository=task_repository,
                phenomena=phenomenon_service,
                matching=matching_application,
                research_start=research_start_application,
            )
            document_application = ResearchDocumentApplication(
                documents=document_service,
                research_tasks=task_repository,
                mutations=SqliteResearchDocumentMutationRepository(session),
                get_theory_plan=match_runs.get_confirmed_plan,
                get_match_run=match_runs.get,
                list_proposals_for_task=proposal_repository.list_for_task,
                list_actionable_proposals_for_task=(proposal_repository.list_actionable_for_task),
                owns_match_run=matching_requests.owns,
                formal_analysis_handoff=analysis_application.formal_handoff,
                get_method_plan=method_plans.latest_for_task,
                invalidate_method_plan=(
                    lambda task_id, reason: method_plan_service.mark_stale_for_task(
                        task_id=task_id, reason=reason
                    )
                ),
            )
            proposal_service = ResearchDocumentProposalService(
                repository=proposal_repository,
                documents=document_service,
                atomic=session.begin_nested,
                validate_proposal=document_application.validate_proposal,
            )
            # A key in the local .env opts the independent Agent into a real
            # OpenAI-compatible runtime while keeping the deterministic runner
            # as the zero-config development default.
            agent_runtime_mode = _effective_model_runtime_mode(resolved_settings)
            use_real_agent = agent_runtime_mode != "mock"
            if not use_real_agent:
                runner = DeterministicKnowledgeRunner()
            else:
                agent_endpoints = app.state.model_endpoints
                if not agent_endpoints:
                    raise ValueError(
                        "QUNXUE_MODEL_BASE_URL and QUNXUE_MODEL_NAME are required for Agent runtime"
                    )
                primary_endpoint = agent_endpoints[0]
                runner = PydanticAIKnowledgeRunner(
                    base_url=primary_endpoint.base_url,
                    api_key=primary_endpoint.api_key,
                    model=primary_endpoint.model,
                    fallback_endpoints=tuple(
                        (endpoint.base_url, endpoint.api_key, endpoint.model)
                        for endpoint in agent_endpoints[1:]
                    ),
                    timeout_seconds=resolved_settings.model_timeout_seconds,
                    extra_headers=primary_endpoint.extra_headers,
                    reasoning_effort=resolved_settings.model_reasoning_effort,
                    route_executor=app.state.model_router,
                )
            try:
                yield DisciplinaryAgentApplication(
                    conversations=conversations,
                    runner=runner,
                    credits=CreditService(
                        SqliteCreditRepository(session),
                        exempt_user_ids=getattr(
                            app.state,
                            "credit_exempt_user_ids",
                            (),
                        ),
                    ),
                    atomic=session.begin_nested,
                    ensure_research_draft=(
                        lambda **payload: (
                            research_start_application.ensure_draft_project(**payload).task_id
                        )
                    ),
                    bind_research_draft=(
                        lambda **payload: (
                            research_start_application.bind_material_first_draft(**payload).task_id
                        )
                    ),
                    tools_factory=lambda: ResearchDocumentToolRegistry(
                        catalog=app.state.knowledge_catalog,
                        retriever=app.state.knowledge_retriever,
                        web_research=OpenWebResearchClient(
                            search_provider=resolved_settings.web_search_provider,
                            search_api_key=(
                                resolved_settings.web_search_api_key.get_secret_value()
                                if resolved_settings.web_search_api_key
                                else None
                            ),
                            search_base_url=resolved_settings.web_search_base_url,
                            profile=resolved_settings.web_search_profile,
                            allowed_domains=resolved_settings.web_search_allowed_domains,
                            search_timeout_seconds=(resolved_settings.web_search_timeout_seconds),
                            reranker=app.state.knowledge_retriever,
                        ),
                        documents=document_application,
                        proposals=proposal_service,
                        workflow=agent_research_workflow,
                        materials=material_repository,
                        material_search=SqliteResearchMaterialSearchRepository(session),
                        analysis=analysis_application,
                    ),
                )
            except Exception:
                # A failed model turn is an auditable run that must survive the
                # request rollback so the same idempotency key can retry safely.
                session.commit()
                raise

    app.state.disciplinary_agent_scope = disciplinary_agent_scope
    app.state.identity_service_scope = identity_service_scope
    app.include_router(health_router)
    app.include_router(session_router)
    app.include_router(research_tasks_router)
    app.include_router(research_documents_router)
    app.include_router(research_materials_router)
    app.include_router(transcription_router)
    app.include_router(professional_materials_router)
    app.include_router(research_method_router)
    app.include_router(research_analysis_router)
    app.include_router(research_batch_coding_router)
    app.include_router(research_cycle_router)
    app.include_router(research_exchange_router)
    app.include_router(phenomena_router)
    app.include_router(phenomenon_examples_router)
    app.include_router(material_intakes_router)
    app.include_router(knowledge_router)
    app.include_router(matching_router)
    app.include_router(frameworks_router)
    app.include_router(agent_router)

    @app.exception_handler(ResearchTaskNotFound)
    async def handle_research_task_not_found(
        _request: Request,
        error: ResearchTaskNotFound,
    ) -> JSONResponse:
        body = ErrorResponse(
            error=ErrorDetail(
                code=error.code,
                message=str(error),
                trace_id=str(uuid4()),
            )
        )
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=body.model_dump(mode="json"),
        )

    @app.exception_handler(ResearchStartProposalNotFound)
    async def handle_research_start_proposal_not_found(
        _request: Request,
        error: ResearchStartProposalNotFound,
    ) -> JSONResponse:
        body = ErrorResponse(
            error=ErrorDetail(
                code=ErrorCode.RESEARCH_START_PROPOSAL_NOT_FOUND,
                message=str(error),
                trace_id=str(uuid4()),
            )
        )
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=body.model_dump(mode="json"),
        )

    @app.exception_handler(ResearchStartIdempotencyConflict)
    @app.exception_handler(ResearchStartProposalConflict)
    @app.exception_handler(ResearchStartSourceIncomplete)
    async def handle_research_start_conflict(
        _request: Request,
        error: Exception,
    ) -> JSONResponse:
        code = {
            ResearchStartIdempotencyConflict: ErrorCode.RESEARCH_START_IDEMPOTENCY_CONFLICT,
            ResearchStartProposalConflict: ErrorCode.RESEARCH_START_PROPOSAL_CONFLICT,
            ResearchStartSourceIncomplete: ErrorCode.RESEARCH_START_SOURCE_INCOMPLETE,
        }[type(error)]
        body = ErrorResponse(
            error=ErrorDetail(code=code, message=str(error), trace_id=str(uuid4()))
        )
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=body.model_dump(mode="json"),
        )

    @app.exception_handler(ConversationNotFound)
    async def handle_agent_conversation_not_found(
        _request: Request,
        _error: ConversationNotFound,
    ) -> JSONResponse:
        body = ErrorResponse(
            error=ErrorDetail(
                code=ErrorCode.NOT_FOUND,
                message="对话不存在或无权访问。",
                trace_id=str(uuid4()),
            )
        )
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=body.model_dump(mode="json"),
        )

    @app.exception_handler(IdentityError)
    async def handle_identity_error(
        _request: Request,
        error: IdentityError,
    ) -> JSONResponse:
        if isinstance(error, VerificationCodeRateLimited):
            status_code = status.HTTP_429_TOO_MANY_REQUESTS
        elif isinstance(error, EmailDeliveryUnavailable):
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        elif isinstance(error, EmailAlreadyRegistered):
            status_code = status.HTTP_409_CONFLICT
        elif isinstance(error, (InvalidEmail, InvalidVerificationCode)):
            status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
        else:
            status_code = status.HTTP_401_UNAUTHORIZED
        code = {
            status.HTTP_401_UNAUTHORIZED: ErrorCode.UNAUTHENTICATED,
            status.HTTP_429_TOO_MANY_REQUESTS: ErrorCode.EMAIL_VERIFICATION_RATE_LIMITED,
            status.HTTP_503_SERVICE_UNAVAILABLE: ErrorCode.EMAIL_DELIVERY_UNAVAILABLE,
        }.get(status_code, ErrorCode.VALIDATION_ERROR)
        body = ErrorResponse(
            error=ErrorDetail(
                code=code,
                message=str(error),
                trace_id=str(uuid4()),
            )
        )
        response = JSONResponse(
            status_code=status_code,
            content=body.model_dump(mode="json"),
        )
        if isinstance(error, VerificationCodeRateLimited):
            response.headers["Retry-After"] = str(error.retry_after_seconds)
        if isinstance(error, Unauthenticated):
            response.delete_cookie(
                resolved_settings.session_cookie_name,
                path="/",
                secure=resolved_settings.session_cookie_secure,
                httponly=True,
                samesite=resolved_settings.session_cookie_samesite,
            )
        return response

    @app.exception_handler(ModelInvocationError)
    async def handle_model_invocation_error(
        _request: Request,
        error: ModelInvocationError,
    ) -> JSONResponse:
        public_code, response_status = {
            "model_timeout": (
                ErrorCode.MODEL_TIMEOUT,
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ),
            "model_unavailable": (
                ErrorCode.MODEL_TIMEOUT,
                status.HTTP_503_SERVICE_UNAVAILABLE,
            ),
            "model_rate_limited": (
                ErrorCode.MODEL_TIMEOUT,
                status.HTTP_429_TOO_MANY_REQUESTS,
            ),
            "model_invalid_output": (
                ErrorCode.INTERNAL_SERVER_ERROR,
                status.HTTP_502_BAD_GATEWAY,
            ),
            "model_request_rejected": (
                ErrorCode.INTERNAL_SERVER_ERROR,
                status.HTTP_502_BAD_GATEWAY,
            ),
            "no_reliable_candidate": (
                ErrorCode.NO_RELIABLE_CANDIDATE,
                status.HTTP_409_CONFLICT,
            ),
            "insufficient_sources": (
                ErrorCode.INSUFFICIENT_SOURCES,
                status.HTTP_409_CONFLICT,
            ),
        }[error.code]
        body = ErrorResponse(
            error=ErrorDetail(
                code=public_code,
                message=str(error),
                trace_id=str(error.trace_id),
            )
        )
        return JSONResponse(
            status_code=response_status,
            content=body.model_dump(mode="json"),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        _request: Request,
        _error: RequestValidationError,
    ) -> JSONResponse:
        body = ErrorResponse(
            error=ErrorDetail(
                code="validation_error",
                message="Request validation failed.",
                trace_id=str(uuid4()),
            )
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=body.model_dump(mode="json"),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        _request: Request,
        error: StarletteHTTPException,
    ) -> JSONResponse:
        code, message = {
            status.HTTP_401_UNAUTHORIZED: (
                ErrorCode.UNAUTHENTICATED,
                "Authentication required.",
            ),
            status.HTTP_404_NOT_FOUND: (
                ErrorCode.NOT_FOUND,
                "Resource not found.",
            ),
            status.HTTP_405_METHOD_NOT_ALLOWED: (
                ErrorCode.METHOD_NOT_ALLOWED,
                "Method not allowed.",
            ),
        }.get(
            error.status_code,
            (
                ErrorCode.VALIDATION_ERROR
                if error.status_code < 500
                else ErrorCode.INTERNAL_SERVER_ERROR,
                "Request failed." if error.status_code < 500 else "Internal server error.",
            ),
        )
        body = ErrorResponse(
            error=ErrorDetail(
                code=code,
                message=message,
                trace_id=str(uuid4()),
            )
        )
        return JSONResponse(
            status_code=error.status_code,
            content=body.model_dump(mode="json"),
        )

    if resolved_settings.account_initial_admin_password is not None:
        install_account_management(
            app,
            database=resolved_database,
            password_hasher=password_hasher,
        )

    return app


def _retriever_from_settings(settings: Settings) -> HybridRetriever | None:
    configured_values = (
        settings.embedding_base_url,
        settings.embedding_api_key,
        settings.embedding_model,
        settings.reranker_base_url,
        settings.reranker_api_key,
        settings.reranker_model,
    )
    has_partial_configuration = any(value is not None for value in configured_values)
    if not has_partial_configuration and (
        settings.runtime_mode == "mock" or settings.has_model_api_key
    ):
        return None
    config = settings.require_retrieval_config()
    embedder = OpenAICompatibleEmbeddingProvider(
        base_url=config.embedding_base_url,
        api_key=config.embedding_api_key.get_secret_value(),
        model=config.embedding_model,
        timeout_seconds=config.embedding_timeout_seconds,
    )
    reranker = SiliconFlowRerankerProvider(
        base_url=config.reranker_base_url,
        api_key=config.reranker_api_key.get_secret_value(),
        model=config.reranker_model,
        timeout_seconds=config.reranker_timeout_seconds,
    )
    return HybridRetriever(
        index=SqliteRetrievalIndex(config.index_path),
        embedder=embedder,
        embedding_model=config.embedding_model,
        chunk_schema_version=RETRIEVAL_CORPUS_SCHEMA_VERSION,
        reranker=reranker,
        reranker_model=config.reranker_model,
        min_rerank_score=config.min_rerank_score,
        min_lexical_score=config.min_lexical_score,
        recall_limit=config.recall_limit,
    )


def _model_provider_from_settings(
    *,
    settings: Settings,
    builtin_case_catalog: BuiltInCaseCatalog,
    database: Database,
    endpoints: tuple[ModelEndpoint, ...],
) -> tuple[
    ModelProvider,
    ModelRouteExecutor | None,
    SqliteModelAttemptRecorder | None,
]:
    runtime_mode = _effective_model_runtime_mode(settings)
    if runtime_mode == "mock":
        return create_deterministic_mock_provider(catalog=builtin_case_catalog), None, None
    if not endpoints:
        raise ValueError(
            "QUNXUE_MODEL_BASE_URL (model_base_url) and "
            "QUNXUE_MODEL_NAME (model_name) are required outside mock mode"
        )

    providers: tuple[ModelProvider, ...] = tuple(
        OpenAICompatibleModelProvider(
            base_url=endpoint.base_url,
            api_key=endpoint.api_key,
            model=endpoint.model,
            timeout_seconds=endpoint.timeout_seconds,
            capability_tier=runtime_mode,
            extra_headers=dict(endpoint.extra_headers),
        )
        for endpoint in endpoints
    )
    attempt_recorder = SqliteModelAttemptRecorder(database)
    router = ModelRouteExecutor(endpoints=endpoints, recorder=attempt_recorder)
    return (
        RoutedModelProvider(providers=providers, router=router),
        router,
        attempt_recorder,
    )


def _model_endpoints_from_settings(settings: Settings) -> tuple[ModelEndpoint, ...]:
    headers = _model_headers_from_settings(settings)
    return tuple(
        ModelEndpoint(
            endpoint_id=endpoint.endpoint_id,
            base_url=endpoint.base_url,
            api_key=(
                endpoint.api_key.get_secret_value()
                if endpoint.api_key is not None
                else None
            ),
            model=endpoint.model,
            timeout_seconds=endpoint.timeout_seconds,
            provider="openai-compatible",
            extra_headers=dict(headers),
        )
        for endpoint in settings.resolved_model_endpoints()
    )


def _effective_model_runtime_mode(settings: Settings) -> str:
    """Resolve the runtime selected by the actual model credentials."""

    if settings.runtime_mode == "mock" and settings.has_model_api_key:
        return "base"
    return settings.runtime_mode


def _model_headers_from_settings(settings: Settings) -> dict[str, str]:
    headers = {
        name: value.get_secret_value() for name, value in settings.model_extra_headers.items()
    }
    if settings.runtime_mode == "sft" and settings.model_sft_resource_id is not None:
        header_name = settings.model_sft_resource_header
        if header_name.lower() in {name.lower() for name in headers}:
            raise ValueError("SFT resource header duplicates a model extension header")
        headers[header_name] = settings.model_sft_resource_id.get_secret_value()
    return headers
