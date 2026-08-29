class ResearchAnalysisNotFound(LookupError):
    """An analysis record or source is absent from the authenticated task."""


class ResearchAnalysisVersionConflict(ValueError):
    """A concurrent analysis decision won before this request."""


class ResearchAnalysisIdempotencyConflict(ValueError):
    """An idempotency identity was reused for a different analysis write."""
