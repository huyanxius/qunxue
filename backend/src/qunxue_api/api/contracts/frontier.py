"""Versioned frontier HTTP contract. Raw provenance extras are preserved in the detail."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FrontierEligibilityResponse(BaseModel):
    browse: bool
    rag: bool
    training_candidate: bool
    match: bool


class FrontierEvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    block_id: str
    snippet: str | None = None
    locator: str
    url: str
    supports: list[str] = Field(default_factory=list)


class FrontierPaperAnalysisEvidenceResponse(BaseModel):
    field: str
    statement: str
    evidence_indexes: list[int]


class FrontierMediaResponse(BaseModel):
    url: str
    caption: str
    source_url: str
    kind: Literal["figure", "chart", "article_photo", "illustration"]
    alt: str | None = None


class FrontierRecordResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    source_id: str
    item_id: str
    snapshot_id: str
    canonical_study_id: str
    content_hash: str
    version: int
    title: str
    authors: list[str] | None = None
    source_name: str
    source_publisher: str
    source_published_at: str | None = None
    source_date_label: str | None = None
    published_at: str | None = None
    published_at_precision: str | None = None
    published_at_display: str
    publication_year: int | None = None
    publication_issue: int | None = None
    url: str
    summary: str | None = None
    topics: list[str]
    material_type: str
    verification_status: Literal[
        "lead_only", "practice_signal", "verified_frontier", "review_queue"
    ]
    verification_note: str
    editorial_caveat: str | None = None
    why_read: str | None = None
    summary_method: str | None = None
    analysis_scope: Literal["abstract", "full_text", "practice_body", "metadata"] | None = None
    analysis_evidence: list[FrontierPaperAnalysisEvidenceResponse] = Field(default_factory=list)
    issue_id: str | None = None
    media: list[FrontierMediaResponse] = Field(default_factory=list)
    research_question: str | None = None
    methods: str | list[str] | None = None
    data: str | None = None
    sample: str | dict[str, object] | None = None
    findings: list[str] | None = None
    limitations: str | list[str] | None = None
    missing_reasons: dict[str, str] = Field(default_factory=dict)
    evidence: list[FrontierEvidenceResponse]
    eligibility: FrontierEligibilityResponse
    extraction_method: str
    snapshot_scope: str
    full_text_retained: bool
    within_preferred_window: bool | None = None


class FrontierRecordSummaryResponse(BaseModel):
    id: str
    title: str
    authors: list[str] | None = None
    source_id: str
    source_name: str
    source_publisher: str
    source_published_at: str | None = None
    published_at: str | None = None
    published_at_display: str
    publication_year: int | None = None
    publication_issue: int | None = None
    url: str
    summary: str
    topics: list[str]
    material_type: str
    verification_status: str
    has_media: bool = False
    research_question: str | None = None
    findings: list[str] = Field(default_factory=list)
    within_preferred_window: bool | None = None


class FrontierRecordPageResponse(BaseModel):
    items: list[FrontierRecordResponse]
    total: int
    offset: int
    limit: int
    next_offset: int | None
    as_of: str
    search_mode: str
    sort_basis: str
    date_filter_basis: str


class FrontierRecordSummaryPageResponse(FrontierRecordPageResponse):
    items: list[FrontierRecordSummaryResponse]


class FrontierTopicCountsResponse(BaseModel):
    total: int
    dated: int
    undated: int
    future_dated: int
    days_30: int
    days_90: int
    days_180: int
    previous_90: int
    prior_90_for_growth: int
    prior_90_for_persistence: int


class FrontierTopicEvidenceResponse(BaseModel):
    record_id: str
    canonical_study_id: str
    source_id: str
    published_at: str | None
    published_at_precision: str | None
    counted_published_at: str | None
    date_status: str
    url: str


class FrontierTimeWindowResponse(BaseModel):
    start: str
    end: str


class FrontierEditorialBriefResponse(BaseModel):
    topic_key: str
    stream: Literal["research", "practice"]
    title: str
    summary: str
    why_it_matters: str
    evidence_record_ids: list[str]
    generated_by: str
    basis_content_hash: str
    updated_at: str


class FrontierEvidenceStatementResponse(BaseModel):
    text: str
    evidence_record_ids: list[str]


class FrontierPriorityReadResponse(BaseModel):
    record_id: str
    reason: str


class FrontierResearchBriefResponse(BaseModel):
    headline: str
    development: FrontierEvidenceStatementResponse | None = None
    consensus: list[FrontierEvidenceStatementResponse] = Field(default_factory=list)
    differences: list[FrontierEvidenceStatementResponse] = Field(default_factory=list)
    methods: list[FrontierEvidenceStatementResponse] = Field(default_factory=list)
    research_implication: FrontierEvidenceStatementResponse | None = None
    priority_reads: list[FrontierPriorityReadResponse] = Field(default_factory=list)
    evidence_record_ids: list[str]
    generated_by: str
    basis_content_hash: str
    updated_at: str


class FrontierMonthlyPointResponse(BaseModel):
    month: str
    record_count: int
    dated_record_ids: list[str]
    denominator: int
    denominator_record_ids: list[str]
    source_ids: list[str]
    denominator_source_ids: list[str]
    sample_share: float | None
    normalized_share: float | None
    coverage_complete: bool
    is_partial_month: bool
    observation_basis: str


class FrontierIssuePointResponse(BaseModel):
    issue_id: str
    label: str
    source_id: str
    publication_month: str
    candidate_count: int
    readable_count: int
    included_count: int
    denominator: int
    topic_record_count: int
    analyzed_count: int = 0
    share: float | None
    coverage_complete: bool
    evidence_record_ids: list[str]
    denominator_record_ids: list[str]
    issue_url: str
    comparison_group: str


class FrontierSeriesMetadataResponse(BaseModel):
    date_basis: str
    unit: str
    comparison_status: str
    comparable_source_ids: list[str]
    topic_membership_overlaps: bool
    coverage_note: str


class FrontierTopicResponse(BaseModel):
    id: str
    topic_key: str
    title: str
    stream: Literal["research", "practice"]
    record_ids: list[str]
    source_ids: list[str]
    source_distribution: dict[str, int]
    summary: str
    summary_method: str
    method: str
    counts: FrontierTopicCountsResponse
    trend_status: Literal["insufficient_evidence", "supported"]
    trend_signals: list[str]
    growth_baseline: float | None
    reasons: list[str]
    evidence: list[FrontierTopicEvidenceResponse]
    editorial_brief: FrontierEditorialBriefResponse | None = None
    research_brief: FrontierResearchBriefResponse | None = None
    monthly_series: list[FrontierMonthlyPointResponse] = Field(default_factory=list)
    issue_series: list[FrontierIssuePointResponse] = Field(default_factory=list)
    series_metadata: FrontierSeriesMetadataResponse | None = None
    novelty_status: str
    time_windows: dict[str, FrontierTimeWindowResponse]


class FrontierTopicPageResponse(BaseModel):
    items: list[FrontierTopicResponse]
    as_of: str
    window: int | None = None
    method: str = "curated_topic_dictionary_v1"


class FrontierSourceResponse(BaseModel):
    source_id: str
    name: str
    adapter_type: str
    base_url: str
    schedule_hours: int
    enabled: bool
    status: str
    cursor: str | None
    last_success_at: str | None
    last_error: str | None
    record_count: int
    reason: str
    coverage_start: str | None
    coverage_end: str | None = None
    automatic_collection: bool
    coverage_complete: bool = False
    sampling_strategy: str = "unknown"


class FrontierSourcePageResponse(BaseModel):
    items: list[FrontierSourceResponse]


class FrontierStatusResponse(BaseModel):
    as_of: str
    record_count: int
    research_count: int
    practice_count: int
    verified_research_count: int
    source_count: int
    registered_source_count: int
    exact_dated_research_count: int
    extractor_status: str
    verifier_status: str
    embedding_status: str
    automatic_collection: bool
    processing_mode: str
    pending_jobs: int
    blocked_jobs: int
    baseline_status: str
    limitations: list[str]


class FrontierDistributionResponse(BaseModel):
    key: str
    label: str
    count: int
    record_ids: list[str]


class FrontierCorpusStatisticsResponse(BaseModel):
    research_count: int
    practice_count: int
    source_distribution: list[FrontierDistributionResponse]
    year_distribution: list[FrontierDistributionResponse]
    topic_distribution: list[FrontierDistributionResponse]
    method_distribution: list[FrontierDistributionResponse]
    data_distribution: list[FrontierDistributionResponse]
    classification_method: str
    overlapping_categories: bool


class FrontierOverviewSectionResponse(BaseModel):
    id: Literal["shared_focus", "change", "methods", "differences", "research_opportunities"]
    title: str
    statements: list[FrontierEvidenceStatementResponse]


class FrontierOverviewScopeResponse(BaseModel):
    stream: Literal["research"]
    coverage_record_ids: list[str]
    analyzed_record_count: int
    source_count: int
    systematic_review_method: str


class FrontierSourceHashResponse(BaseModel):
    record_id: str
    content_hash: str


class FrontierCorpusOverviewResponse(BaseModel):
    headline: str
    summary: str
    sections: list[FrontierOverviewSectionResponse]
    scope: FrontierOverviewScopeResponse
    evidence_record_ids: list[str]
    generated_by: Literal["assistant_evidence_synthesis"]
    basis_content_hash: str
    source_hashes: list[FrontierSourceHashResponse]
    updated_at: str


class FrontierOverviewResponse(BaseModel):
    as_of: str
    overview: FrontierCorpusOverviewResponse | None
    statistics: FrontierCorpusStatisticsResponse
    status: Literal["ready", "not_configured", "stale"]


class FrontierCalendarDayResponse(BaseModel):
    date: str
    count: int
    record_ids: list[str]


class FrontierCalendarMonthResponse(BaseModel):
    month: str
    count: int
    record_ids: list[str]


class FrontierCalendarIssueResponse(BaseModel):
    source_id: str
    issue_id: str
    publication_year: int
    count: int
    record_ids: list[str]


class FrontierCalendarResponse(BaseModel):
    year: int
    as_of: str
    timezone: Literal["Asia/Shanghai"]
    days: list[FrontierCalendarDayResponse]
    month_precision: list[FrontierCalendarMonthResponse]
    issue_precision: list[FrontierCalendarIssueResponse]
    undated_record_ids: list[str]
    conflicting_record_ids: list[str]
    future_record_ids: list[str]


class FrontierKnowledgeLinkResponse(BaseModel):
    knowledge_id: str
    title: str
    content_version: int
    matched_topics: list[str]


class FrontierKnowledgeLinksResponse(BaseModel):
    record_id: str
    record_version: int
    record_content_hash: str
    knowledge_release_id: str | None
    knowledge_release_hash: str | None
    knowledge_release_level: Literal["preview", "final", "working"] | None
    status: Literal["ready", "no_release", "no_topics", "no_matches", "low_evidence"]
    limitations: list[str]
    matches: list[FrontierKnowledgeLinkResponse]
    match_basis: Literal["topic_lexical_retrieval"]
    relationship: Literal["reading_lead"]


class FrontierClassificationCountsResponse(BaseModel):
    denominator: int
    classified: int
    uncategorized: int
    title_available: int
    publisher_keywords_available: int


class FrontierClassificationCoverageResponse(BaseModel):
    previous: FrontierClassificationCountsResponse
    current: FrontierClassificationCountsResponse


class FrontierPeriodReportResponse(BaseModel):
    measurement_method: str
    measurement_version: str
    classification_coverage: FrontierClassificationCoverageResponse
    coverage_scope: str
    previous_window: FrontierTimeWindowResponse
    current_window: FrontierTimeWindowResponse
    comparison_issue_keys: list[str]
    share_basis: str
    coverage_evidence_refs: list[str]
    previous_denominator: int
    current_denominator: int
    cohort_previous_count: int
    cohort_current_count: int
    as_of: str
    timezone: str
    date_basis: str
    semantic_status: str
    method_version: str
    comparability: str
    direction: str | None
    previous_share: float | None
    current_share: float | None
    delta_pp: float | None
    previous_count: int
    current_count: int
    cohort_source_ids: list[str]
    evidence_record_ids: list[str]
    hotspot_allowed: bool
    decline_allowed: bool
    emerging_allowed: bool
    persistent_allowed: bool


class FrontierRatingEvidenceResponse(BaseModel):
    record_id: str
    version: int
    snapshot_hash: str
    locator: str
    reviewed_by: str


class FrontierCriterionRatingResponse(BaseModel):
    weight: int
    score: int | None
    rationale: str | None
    evidence: list[FrontierRatingEvidenceResponse]
    missing_reason: str | None


class FrontierScoreBoundsResponse(BaseModel):
    lower: float
    upper: float


class FrontierValueAssessmentResponse(BaseModel):
    rule_version: str
    track: Literal["empirical", "theoretical", "policy_practice"] | None
    status: Literal["unassessed", "partial", "assessed"]
    ratings: dict[str, int | None]
    criteria: dict[str, FrontierCriterionRatingResponse]
    academic_value: float | None
    score_bounds: FrontierScoreBoundsResponse
    missing_reasons: dict[str, str]
    evidence_readiness: str
    priority: Literal["priority_review", "candidate", "not_yet_for_update"] | None
    authorizes_publication: Literal[False]


class FrontierReadingBasisResponse(BaseModel):
    basis_type: Literal["located_source_excerpt", "assistant_abstract_reading"]
    source_content_hash: str
    block_id: str
    locator: str
    url: str
    snippet: str
    fields: list[str]


class FrontierReadingPriorityResponse(BaseModel):
    record_id: str
    title: str
    version: int
    content_hash: str
    reading_rule_version: str
    reading_priority: Literal["passage_supported", "abstract_supported", "metadata_only"]
    evidence_readiness: str
    supported_fields: list[str]
    missing_fields: dict[str, str]
    basis: list[FrontierReadingBasisResponse]
    assessment: FrontierValueAssessmentResponse
    limitations: list[str]


class FrontierReadingPriorityPageResponse(BaseModel):
    items: list[FrontierReadingPriorityResponse]
    total: int
    offset: int
    limit: int
    next_offset: int | None
    as_of: str
    sort_basis: str
