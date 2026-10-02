"""Public frontier boundary, separate from immutable stable knowledge releases."""

from .analysis import aggregate_topics
from .briefs import (
    SYNTHESIS_METHODS,
    validate_media,
    validate_paper_analysis,
    validate_research_brief,
)
from .domain import (
    RULE_VERSION,
    SCHEMA_VERSION,
    Candidate,
    FrontierJob,
    FrontierRecord,
    JobStage,
    SourceBlock,
    SourceSnapshot,
    VerificationStatus,
    content_hash,
    eligibility,
    frontier_today,
    normalize_doi,
    normalize_title_author,
    qualify_record,
    safe_public_url,
    validate_import,
)
from .overview import overview_basis, validate_corpus_overview
from .overview_stats import corpus_statistics, visible_corpus_records
from .ports import (
    FrontierExtractorPort,
    FrontierSourceAdapter,
    FrontierStore,
    FrontierVerifierPort,
)
from .read_projection import build_read_projection, record_summary
from .series import topic_series
from .service import FrontierService
from .value import assess_record_value, reading_basis

__all__ = [
    "RULE_VERSION",
    "SCHEMA_VERSION",
    "Candidate",
    "FrontierJob",
    "FrontierRecord",
    "JobStage",
    "SourceBlock",
    "SourceSnapshot",
    "VerificationStatus",
    "content_hash",
    "eligibility",
    "normalize_doi",
    "normalize_title_author",
    "qualify_record",
    "validate_import",
    "FrontierExtractorPort",
    "FrontierSourceAdapter",
    "FrontierStore",
    "FrontierVerifierPort",
]


__all__ += ["aggregate_topics", "FrontierService"]

__all__ += ["frontier_today"]


__all__ += ["SYNTHESIS_METHODS", "validate_paper_analysis", "validate_research_brief"]


__all__ += ["topic_series"]

__all__ += ["safe_public_url"]

__all__ += ["validate_media"]
__all__ += [
    "overview_basis",
    "validate_corpus_overview",
    "corpus_statistics",
    "visible_corpus_records",
]

__all__ += ["assess_record_value", "reading_basis"]


__all__ += ["build_read_projection", "record_summary"]
