from uuid import UUID

import qunxue_api.modules.research_framework as framework


def test_framework_review_snapshot_preserves_failure_and_retry_lineage() -> None:
    failure_type = getattr(framework, "FrameworkReviewFailureSnapshot", None)
    failure_code = getattr(framework, "FrameworkReviewFailureCode", None)

    assert failure_type is not None
    assert failure_code is not None
    failure = failure_type(
        code=failure_code.INSUFFICIENT_SOURCES,
        message="Two claims still lack a verifiable source.",
        retryable=True,
        requested_source_ids=("source-missing-1",),
    )
    review = framework.FrameworkReviewRunSnapshot(
        review_run_id=UUID(int=1),
        framework_id=UUID(int=2),
        framework_version=3,
        trace_id=UUID(int=4),
        idempotency_key="framework-review-contract",
        version=2,
        status=framework.FrameworkReviewRunStatus.INSUFFICIENT_SOURCES,
        audit=None,
        revision_id=UUID(int=5),
        retry_of_review_run_id=UUID(int=6),
        attempt=2,
        failure=failure,
    )

    assert review.failure == failure
    assert review.retry_of_review_run_id == UUID(int=6)
    assert review.attempt == 2
    assert hasattr(framework.ResearchFrameworkWorkflow, "retry_review")
