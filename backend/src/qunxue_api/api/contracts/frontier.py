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
