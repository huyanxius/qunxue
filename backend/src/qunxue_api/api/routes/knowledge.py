from fastapi import APIRouter, HTTPException, Query, Request, status

from qunxue_api.api.contracts.common import ErrorResponse
from qunxue_api.api.contracts.knowledge import (
    BuiltInCasePageResponse,
    BuiltInCaseResponse,
    KnowledgeDirectoryNodeResponse,
    KnowledgeEntryDetailResponse,
    KnowledgeEntryPageResponse,
    KnowledgeEntrySummaryResponse,
    KnowledgeRelationPageResponse,
    KnowledgeRelationResponse,
    KnowledgeReleaseResponse,
    KnowledgeUseEligibilityResponse,
    RelationCandidatePageResponse,
    RelationCandidateResponse,
    SourceRecordResponse,
    StructuralConnectionPageResponse,
    StructuralConnectionResponse,
    TheoryProfileResponse,
)
from qunxue_api.modules.knowledge_catalog import KnowledgeUsePurpose

router = APIRouter(
    prefix="/api/knowledge",
    tags=["knowledge"],
    responses={422: {"model": ErrorResponse}},
)


@router.get(
    "/releases/current",
    operation_id="get_current_knowledge_release",
    response_model=KnowledgeReleaseResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_current_knowledge_release(request: Request) -> KnowledgeReleaseResponse:
    release = request.app.state.knowledge_catalog.current_release(
        purpose=KnowledgeUsePurpose.BROWSE
    )
    return KnowledgeReleaseResponse(
        knowledge_release_id=release.knowledge_release_id,
        level=release.level,
        content_hash=release.content_hash,
    )


@router.get(
    "/connections",
    operation_id="list_knowledge_connections",
    response_model=StructuralConnectionPageResponse,
    responses={404: {"model": ErrorResponse}},
)
def list_knowledge_connections(
    request: Request,
    knowledge_release_id: str | None = None,
    source_node_id: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
) -> StructuralConnectionPageResponse:
    catalog = request.app.state.knowledge_catalog
    release_id = knowledge_release_id or catalog.current_release(
        purpose=KnowledgeUsePurpose.BROWSE
    ).knowledge_release_id
    try:
        page = catalog.list_connections(
            release_id=release_id,
            source_node_id=source_node_id,
            cursor=cursor,
            limit=limit,
        )
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT) from error
    return StructuralConnectionPageResponse(
        knowledge_release_id=page.release.knowledge_release_id,
        connections=[
            StructuralConnectionResponse(
                connection_kind="structure",
                connection_id=item.connection_id,
                source_node_id=item.source_node_id,
                source_node_type=item.source_node_type,
                source_title=item.source_title,
                target_node_id=item.target_node_id,
                target_node_type=item.target_node_type,
                target_title=item.target_title,
                connection_type="contains",
                direction="outbound",
            )
            for item in page.connections
        ],
        stable_order=[item.connection_id for item in page.connections],
        total_count=page.total_count,
        next_cursor=page.next_cursor,
    )


@router.get(
    "/relation-candidates",
    operation_id="list_knowledge_relation_candidates",
    response_model=RelationCandidatePageResponse,
    responses={404: {"model": ErrorResponse}},
)
def list_knowledge_relation_candidates(
    request: Request,
    knowledge_release_id: str | None = None,
    knowledge_id: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
) -> RelationCandidatePageResponse:
    catalog = request.app.state.knowledge_catalog
    release_id = knowledge_release_id or catalog.current_release(
        purpose=KnowledgeUsePurpose.BROWSE
    ).knowledge_release_id
    try:
        page = catalog.list_relation_candidates(
            release_id=release_id,
            knowledge_id=knowledge_id,
            cursor=cursor,
            limit=limit,
        )
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT) from error
    return RelationCandidatePageResponse(
        knowledge_release_id=page.release.knowledge_release_id,
        candidates=[
            RelationCandidateResponse(
                candidate_id=item.candidate_id,
                source_knowledge_id=item.source_knowledge_id,
                target_knowledge_id=item.target_knowledge_id,
                suggested_relation_type=item.suggested_relation_type,
                direction=item.direction,
                evidence_excerpt=item.evidence_excerpt,
                evidence_locator=item.evidence_locator,
                evidence_source_id=item.evidence_source_id,
                source_content_version=item.source_content_version,
                target_content_version=item.target_content_version,
                producer=item.producer,
                producer_config_version=item.producer_config_version,
                score=item.score,
                trigger_reason=item.trigger_reason,
                review_status=item.review_status,
                review_record_id=item.review_record_id,
            )
            for item in page.candidates
        ],
        stable_order=[item.candidate_id for item in page.candidates],
        total_count=page.total_count,
        next_cursor=page.next_cursor,
    )


@router.get(
    "/relations",
    operation_id="list_knowledge_relations",
    response_model=KnowledgeRelationPageResponse,
    responses={404: {"model": ErrorResponse}},
)
def list_knowledge_relations(
    request: Request,
    knowledge_release_id: str | None = None,
    knowledge_id: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
) -> KnowledgeRelationPageResponse:
    catalog = request.app.state.knowledge_catalog
    release_id = knowledge_release_id or catalog.current_release(
        purpose=KnowledgeUsePurpose.BROWSE
    ).knowledge_release_id
    try:
        page = catalog.list_relations(
            release_id=release_id,
            knowledge_id=knowledge_id,
            cursor=cursor,
            limit=limit,
        )
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT) from error
    return KnowledgeRelationPageResponse(
        knowledge_release_id=page.release.knowledge_release_id,
        relations=[_relation_response(item) for item in page.relations],
        stable_order=[item.relation_id for item in page.relations],
        total_count=page.total_count,
        next_cursor=page.next_cursor,
    )


@router.get(
    "/entries",
    operation_id="list_knowledge_entries",
    response_model=KnowledgeEntryPageResponse,
    responses={404: {"model": ErrorResponse}},
)
def list_knowledge_entries(
    request: Request,
    knowledge_release_id: str | None = None,
    query: str | None = None,
    category: str | None = None,
    category_id: str | None = None,
    dimension_id: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> KnowledgeEntryPageResponse:
    catalog = request.app.state.knowledge_catalog
    release_id = knowledge_release_id or catalog.current_release(
        purpose=KnowledgeUsePurpose.BROWSE
    ).knowledge_release_id
    try:
        page = catalog.browse(
            release_id=release_id,
            query=query,
            category=category,
            category_id=category_id,
            dimension_id=dimension_id,
            cursor=cursor,
            limit=limit,
        )
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT) from error
    return KnowledgeEntryPageResponse(
        knowledge_release_id=page.release.knowledge_release_id,
        entries=[_entry_summary_response(entry) for entry in page.entries],
        stable_order=[entry.knowledge_id for entry in page.entries],
        next_cursor=page.next_cursor,
    )


@router.get(
    "/entries/{knowledge_id}",
    operation_id="get_knowledge_entry",
    response_model=KnowledgeEntryDetailResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_knowledge_entry(
    request: Request,
    knowledge_id: str,
    knowledge_release_id: str | None = None,
) -> KnowledgeEntryDetailResponse:
    catalog = request.app.state.knowledge_catalog
    release_id = knowledge_release_id or catalog.current_release(
        purpose=KnowledgeUsePurpose.BROWSE
    ).knowledge_release_id
    try:
        entry = catalog.get_entry(knowledge_id=knowledge_id, release_id=release_id)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from error
    return KnowledgeEntryDetailResponse(
        knowledge_release_id=entry.release.knowledge_release_id,
        knowledge_id=entry.summary.knowledge_id,
        content_version=entry.summary.content_version,
        title=entry.summary.title,
        category_id=entry.summary.category_id,
        category=entry.summary.category,
        dimension_id=entry.summary.dimension_id,
        dimension=entry.summary.dimension,
        directory_path=[
            KnowledgeDirectoryNodeResponse(
                node_id=node.node_id,
                node_type=node.node_type,
                title=node.title,
            )
            for node in entry.summary.directory_path
        ],
        review_status=entry.summary.review_status,
        eligibility=_eligibility_response(entry.summary.eligibility),
        aliases=list(entry.aliases),
        content=entry.content,
        sources=[
            SourceRecordResponse(
                source_id=source.source_id,
                source_type=source.source_type,
                title=source.title,
                authors_or_institution=list(source.authors_or_institution),
                year=source.year,
                publication=source.publication,
                locator=source.locator,
                url=source.url,
                verification_status=source.verification_status,
                use_boundary=source.use_boundary,
            )
            for source in entry.sources
        ],
        relations=[
            KnowledgeRelationResponse(
                relation_id=relation.relation_id,
                source_knowledge_id=relation.source_knowledge_id,
                target_knowledge_id=relation.target_knowledge_id,
                relation_type=relation.relation_type,
                direction=relation.direction,
                description=relation.description,
                evidence_source_ids=list(relation.evidence_source_ids),
                evidence_grade=relation.evidence_grade,
                algorithm_weight=relation.algorithm_weight,
                algorithm_config_version=relation.algorithm_config_version,
                content_version=relation.content_version,
                review_status=relation.review_status,
            )
            for relation in entry.relations
        ],
        theory_profile=(
            TheoryProfileResponse(
                theory_id=entry.theory_profile.theory_id,
                related_knowledge_ids=list(entry.theory_profile.related_knowledge_ids),
                title=entry.theory_profile.title,
                core_propositions=list(entry.theory_profile.core_propositions),
                applicable_phenomena=list(entry.theory_profile.applicable_phenomena),
                analysis_levels=list(entry.theory_profile.analysis_levels),
                prerequisites=list(entry.theory_profile.prerequisites),
                exclusion_signals=list(entry.theory_profile.exclusion_signals),
                observable_evidence=list(entry.theory_profile.observable_evidence),
                competing_or_complementary_theory_ids=list(
                    entry.theory_profile.competing_or_complementary_theory_ids
                ),
                source_ids=list(entry.theory_profile.source_ids),
                content_version=entry.theory_profile.content_version,
                review_status=entry.theory_profile.review_status,
                match_eligible=entry.theory_profile.match_eligible,
            )
            if entry.theory_profile is not None
            else None
        ),
    )


def _entry_summary_response(entry: object) -> KnowledgeEntrySummaryResponse:
    return KnowledgeEntrySummaryResponse(
        knowledge_id=entry.knowledge_id,
        content_version=entry.content_version,
        title=entry.title,
        category_id=entry.category_id,
        category=entry.category,
        dimension_id=entry.dimension_id,
        dimension=entry.dimension,
        directory_path=[
            KnowledgeDirectoryNodeResponse(
                node_id=node.node_id,
                node_type=node.node_type,
                title=node.title,
            )
            for node in entry.directory_path
        ],
        review_status=entry.review_status,
        eligibility=_eligibility_response(entry.eligibility),
    )


def _eligibility_response(eligibility: object) -> KnowledgeUseEligibilityResponse:
    return KnowledgeUseEligibilityResponse(
        browse_eligible=eligibility.browse_eligible,
        rag_eligible=eligibility.rag_eligible,
        training_candidate_eligible=eligibility.training_candidate_eligible,
        match_eligible=eligibility.match_eligible,
        review_record_ids=list(eligibility.review_record_ids),
    )


def _relation_response(relation: object) -> KnowledgeRelationResponse:
    return KnowledgeRelationResponse(
        relation_id=relation.relation_id,
        source_knowledge_id=relation.source_knowledge_id,
        target_knowledge_id=relation.target_knowledge_id,
        relation_type=relation.relation_type,
        direction=relation.direction,
        description=relation.description,
        evidence_source_ids=list(relation.evidence_source_ids),
        evidence_grade=relation.evidence_grade,
        algorithm_weight=relation.algorithm_weight,
        algorithm_config_version=relation.algorithm_config_version,
        content_version=relation.content_version,
        review_status=relation.review_status,
    )


@router.get(
    "/cases",
    operation_id="list_builtin_cases",
    response_model=BuiltInCasePageResponse,
    responses={404: {"model": ErrorResponse}, 501: {"model": ErrorResponse}},
)
def list_builtin_cases(
    request: Request,
    knowledge_release_id: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> BuiltInCasePageResponse:
    catalog = request.app.state.builtin_case_catalog
    if (
        knowledge_release_id is not None
        and knowledge_release_id != catalog.knowledge_release_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    try:
        page = catalog.list_page(cursor=cursor, limit=limit)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT
        ) from error
    return BuiltInCasePageResponse(
        knowledge_release_id=catalog.knowledge_release_id,
        cases=[
            BuiltInCaseResponse(
                case_id=item.case_id,
                title=item.title,
                summary=item.summary,
                phenomenon=item.phenomenon,
                research_intent=item.research_intent,
                context=item.context,
                content_status=item.content_status,
            )
            for item in page.items
        ],
        stable_order=[item.case_id for item in page.items],
        next_cursor=page.next_cursor,
    )
