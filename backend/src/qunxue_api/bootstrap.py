from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from threading import Lock
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from qunxue_api.account_extension import install_account_management
from qunxue_api.adapters.model import (
    BuiltInCaseCatalog,
    ModelGateway,
    ModelInvocationError,
    ModelProvider,
    OpenAICompatibleModelProvider,
    SqliteModelInvocationRecorder,
    create_deterministic_mock_provider,
)
from qunxue_api.adapters.research_agent import (
    DeterministicKnowledgeRunner,
    OpenAICompatibleEmbeddingProvider,
    PydanticAIKnowledgeRunner,
    ResearchDocumentToolRegistry,
    SiliconFlowRerankerProvider,
)
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
from qunxue_api.adapters.sqlite.research_document import (
    SqliteResearchDocumentRepository,
)
from qunxue_api.adapters.sqlite.research_document_mutation import (
    SqliteResearchDocumentMutationRepository,
)
from qunxue_api.adapters.sqlite.research_document_proposal import (
    SqliteResearchDocumentProposalRepository,
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
from qunxue_api.adapters.theory_evidence import CatalogTheoryEvidenceSource
from qunxue_api.api.contracts.common import ErrorCode, ErrorDetail, ErrorResponse
from qunxue_api.api.routes.agent import router as agent_router
from qunxue_api.api.routes.frameworks import router as frameworks_router
from qunxue_api.api.routes.health import router as health_router
from qunxue_api.api.routes.knowledge import router as knowledge_router
from qunxue_api.api.routes.matching import router as matching_router
from qunxue_api.api.routes.phenomena import example_router as phenomenon_examples_router
from qunxue_api.api.routes.phenomena import material_router as material_intakes_router
from qunxue_api.api.routes.phenomena import router as phenomena_router
from qunxue_api.api.routes.research_documents import router as research_documents_router
from qunxue_api.api.routes.research_tasks import router as research_tasks_router
from qunxue_api.api.routes.session import router as session_router
from qunxue_api.application import (
    DisciplinaryAgentApplication,
    ResearchDocumentApplication,
    ResearchDocumentProposalApplication,
    ResearchJourney,
    ResearchJourneyDependencies,
    ResearchStartApplication,
    TheoryMatchingApplication,
)
from qunxue_api.application.agent_research_workflow import AgentResearchWorkflow
from qunxue_api.modules.agent_conversation import ConversationNotFound, ConversationService
from qunxue_api.modules.billing import CreditService
from qunxue_api.modules.identity import (
    EmailAlreadyRegistered,
    IdentityError,
    IdentityService,
    InvalidEmail,
    Unauthenticated,
)
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
from qunxue_api.modules.theory_matching import TheoryMatchingService
from qunxue_api.settings import KNOWLEDGE_ROOT, Settings, get_settings


def create_app(
    *,
    settings: Settings | None = None,
    database: Database | None = None,
    journey_dependencies: ResearchJourneyDependencies | None = None,
    model_provider: ModelProvider | None = None,
    knowledge_retriever: HybridRetriever | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    resolved_database = database or Database(resolved_settings.database_url)

    app = FastAPI(
        title=resolved_settings.app_name,
        version="0.1.0",
        description="群学致知前后端架构基线 API。",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "Idempotency-Key"],
    )
    app.state.settings = resolved_settings
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
    app.state.knowledge_retriever = resolved_knowledge_retriever
    builtin_case_catalog = BuiltInCaseCatalog.default()
    resolved_model_provider = model_provider or _model_provider_from_settings(
        settings=resolved_settings,
        builtin_case_catalog=builtin_case_catalog,
    )
    model_invocation_recorder = SqliteModelInvocationRecorder(resolved_database)
    app.state.builtin_case_catalog = builtin_case_catalog
    app.state.model_invocation_recorder = model_invocation_recorder
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

    @contextmanager
    def theory_matching_application_scope() -> Iterator[TheoryMatchingApplication]:
        # Hold the process lock until the transaction commits. Cross-process
        # writers are rejected by the task repository's version CAS.
        with app.state.matching_start_lock, resolved_database.session() as session:
            descriptor = app.state.model_gateway.descriptor
            matching = TheoryMatchingService(
                evidence_source=CatalogTheoryEvidenceSource(
                    app.state.knowledge_catalog,
                    retriever=app.state.knowledge_retriever,
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
            )

    app.state.research_task_service_scope = research_task_service_scope
    app.state.phenomenon_service_scope = phenomenon_service_scope
    app.state.theory_matching_application_scope = theory_matching_application_scope

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
            matching_requests = SqliteMatchingRequestRepository(session)
            proposals = SqliteResearchDocumentProposalRepository(session)
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
            matching_requests = SqliteMatchingRequestRepository(session)
            proposal_repository = SqliteResearchDocumentProposalRepository(session)
            document_application = ResearchDocumentApplication(
                documents=documents,
                research_tasks=SqliteResearchTaskRepository(session),
                mutations=SqliteResearchDocumentMutationRepository(session),
                get_theory_plan=match_runs.get_confirmed_plan,
                get_match_run=match_runs.get,
                list_proposals_for_task=proposal_repository.list_for_task,
                list_actionable_proposals_for_task=(proposal_repository.list_actionable_for_task),
                owns_match_run=matching_requests.owns,
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
            matching_requests = SqliteMatchingRequestRepository(session)
            proposal_repository = SqliteResearchDocumentProposalRepository(session)
            descriptor = app.state.model_gateway.descriptor
            matching_service = TheoryMatchingService(
                evidence_source=CatalogTheoryEvidenceSource(
                    app.state.knowledge_catalog,
                    retriever=app.state.knowledge_retriever,
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
            use_real_agent = (
                resolved_settings.runtime_mode != "mock" or resolved_settings.has_model_api_key
            )
            model_base_url = resolved_settings.model_base_url or (
                "https://api.deepseek.com" if resolved_settings.has_model_api_key else None
            )
            model_name = resolved_settings.model_name or (
                "deepseek-v4-flash" if resolved_settings.has_model_api_key else None
            )
            if not use_real_agent:
                runner = DeterministicKnowledgeRunner()
            else:
                if model_base_url is None or model_name is None:
                    raise ValueError(
                        "QUNXUE_MODEL_BASE_URL and QUNXUE_MODEL_NAME are required for Agent runtime"
                    )
                runner = PydanticAIKnowledgeRunner(
                    base_url=model_base_url,
                    api_key=(
                        resolved_settings.model_api_key.get_secret_value()
                        if resolved_settings.has_model_api_key
                        else None
                    ),
                    model=model_name,
                    timeout_seconds=resolved_settings.model_timeout_seconds,
                    extra_headers=_model_headers_from_settings(resolved_settings),
                    reasoning_effort=resolved_settings.model_reasoning_effort,
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
                    tools_factory=lambda: ResearchDocumentToolRegistry(
                        catalog=app.state.knowledge_catalog,
                        retriever=app.state.knowledge_retriever,
                        documents=document_application,
                        proposals=proposal_service,
                        workflow=agent_research_workflow,
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
        if isinstance(error, EmailAlreadyRegistered):
            status_code = status.HTTP_409_CONFLICT
        elif isinstance(error, InvalidEmail):
            status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
        else:
            status_code = status.HTTP_401_UNAUTHORIZED
        code = (
            ErrorCode.UNAUTHENTICATED
            if status_code == status.HTTP_401_UNAUTHORIZED
            else ErrorCode.VALIDATION_ERROR
        )
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
    if settings.runtime_mode == "mock" and not has_partial_configuration:
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
) -> ModelProvider:
    if settings.runtime_mode == "mock":
        return create_deterministic_mock_provider(catalog=builtin_case_catalog)
    if settings.model_base_url is None or settings.model_name is None:
        raise ValueError(
            "QUNXUE_MODEL_BASE_URL (model_base_url) and "
            "QUNXUE_MODEL_NAME (model_name) are required outside mock mode"
        )

    headers = _model_headers_from_settings(settings)

    return OpenAICompatibleModelProvider(
        base_url=settings.model_base_url,
        api_key=(
            settings.model_api_key.get_secret_value()
            if settings.model_api_key is not None
            else None
        ),
        model=settings.model_name,
        timeout_seconds=settings.model_timeout_seconds,
        capability_tier=settings.runtime_mode,
        extra_headers=headers,
    )


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
