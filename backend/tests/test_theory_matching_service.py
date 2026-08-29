from itertools import count
from uuid import UUID

from qunxue_api.adapters.model import (
    BuiltInCaseCatalog,
    InMemoryModelInvocationRecorder,
    ModelGateway,
    create_deterministic_mock_provider,
)
from qunxue_api.modules.knowledge_catalog import (
    KnowledgeReleaseLevel,
    KnowledgeReleaseRef,
    KnowledgeReviewStatus,
    SourceRecordSnapshot,
    SourceVerificationStatus,
    TheoryProfileSnapshot,
)
from qunxue_api.modules.research_intake import ConfirmedPhenomenonSnapshot
from qunxue_api.modules.theory_matching import (
    CandidateContentStatus,
    CandidateJudgementRunStatus,
    CandidateOrigin,
    EvidenceBundleSnapshot,
    EvidenceItemSnapshot,
    MatchCompletionBasis,
    MatchRunStatus,
    TheoryJudgementBatchItemResult,
    TheoryJudgementBatchResult,
    TheoryJudgementDraft,
    TheoryJudgementVerdict,
    TheoryMatchingService,
)

RELEASE = KnowledgeReleaseRef(
    knowledge_release_id="release-pre-reviewed-v1",
    level=KnowledgeReleaseLevel.PREVIEW,
    content_hash="sha256:pre-reviewed-release",
)
PHENOMENON = ConfirmedPhenomenonSnapshot(
    task_id=UUID(int=100),
    phenomenon_query_id=UUID(int=101),
    version=2,
    phenomenon="社区互助为何随成员流动减少？",
    research_intent="比较理论解释边界",
    context="社区成员持续流动",
    content_hash="phenomenon-hash",
)


class _EvidenceSource:
    def __init__(self, bundle: EvidenceBundleSnapshot) -> None:
        self._bundle = bundle
        self.user_ids: list[UUID | None] = []

    def retrieve(
        self,
        *,
        user_id: UUID | None = None,
        phenomenon: ConfirmedPhenomenonSnapshot,
        release: KnowledgeReleaseRef,
    ) -> EvidenceBundleSnapshot:
        self.user_ids.append(user_id)
        assert phenomenon == PHENOMENON
        assert release == RELEASE
        return self._bundle


class _MatchRunRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, object] = {}

    def add(self, snapshot: object) -> object:
        self.items[snapshot.match_run_id] = snapshot
        return snapshot

    def get(self, match_run_id: UUID) -> object | None:
        return self.items.get(match_run_id)

    def save(self, snapshot: object) -> object:
        self.items[snapshot.match_run_id] = snapshot
        return snapshot


def _ids(start: int = 1):
    values = count(start)
    return lambda: UUID(int=next(values))


def _bundle(profile_count: int) -> EvidenceBundleSnapshot:
    profiles = []
    evidence = []
    for index in range(1, profile_count + 1):
        source = SourceRecordSnapshot(
            source_id=f"source-{index}",
            source_type="pre_reviewed_publication",
            title=f"理论 {index} 来源",
            authors_or_institution=("作者",),
            year=2020 + index,
            publication="社会学期刊",
            locator=f"p.{index}",
            url=f"https://example.com/{index}",
            verification_status=SourceVerificationStatus.VERIFIED,
            use_boundary="仅支持档案中列出的命题。",
        )
        profile = TheoryProfileSnapshot(
            theory_id=f"theory-{index}",
            related_knowledge_ids=(f"D2:P{index:03d}",),
            title=f"理论 {index}",
            core_propositions=(f"理论 {index} 的已审核命题",),
            applicable_phenomena=("社区互动",),
            analysis_levels=("关系",),
            prerequisites=("存在持续互动",),
            exclusion_signals=("没有互动记录",),
            observable_evidence=("互动频率",),
            competing_or_complementary_theory_ids=(),
            source_ids=(source.source_id,),
            content_version=1,
            review_status=KnowledgeReviewStatus.PRE_REVIEW_COMPLETED,
            match_eligible=True,
        )
        profiles.append(profile)
        evidence.append(
            EvidenceItemSnapshot(
                evidence_ref_id=f"evidence-{index}",
                claim=profile.core_propositions[0],
                excerpt=None,
                locator=source.locator,
                source=source,
                verification_status=source.verification_status,
                use_boundary=source.use_boundary,
            )
        )
    return EvidenceBundleSnapshot(
        evidence_bundle_id=f"bundle-{profile_count}",
        version=1,
        content_hash=f"sha256:bundle-{profile_count}",
        release=RELEASE,
        theory_profiles=tuple(profiles),
        evidence_items=tuple(evidence),
    )


def _service(
    bundle: EvidenceBundleSnapshot,
) -> tuple[TheoryMatchingService, InMemoryModelInvocationRecorder]:
    recorder = InMemoryModelInvocationRecorder()
    gateway = ModelGateway(
        provider=create_deterministic_mock_provider(catalog=BuiltInCaseCatalog.default()),
        recorder=recorder,
        contract_version="matching.v1",
        id_factory=_ids(1000),
    )
    service = TheoryMatchingService(
        evidence_source=_EvidenceSource(bundle),
        judge=gateway,
        repository=_MatchRunRepository(),
        provider="deterministic-mock",
        model_version="mock-sociology-v1",
        capability="mock",
        contract_version="matching.v1",
        id_factory=_ids(),
    )
    return service, recorder


def test_three_pre_reviewed_profiles_become_stably_ordered_judged_candidates() -> None:
    service, recorder = _service(_bundle(3))

    run = service.start(phenomenon=PHENOMENON, release=RELEASE)

    assert run.status is MatchRunStatus.AWAITING_DECISION
    assert [candidate.content.theory_id for candidate in run.candidates] == [
        "theory-1",
        "theory-2",
        "theory-3",
    ]
    assert run.stable_candidate_order == tuple(
        candidate.candidate_id for candidate in run.candidates
    )
    assert all(
        candidate.content.origin is CandidateOrigin.PRE_REVIEWED_KNOWLEDGE
        and candidate.content.content_status
        is CandidateContentStatus.PRE_REVIEW_COMPLETED
        and candidate.content.formal_adoption_eligible
        for candidate in run.candidates
    )
    assert [record.task_id for record in recorder.list_all()] == [PHENOMENON.task_id] * 3
    assert [record.knowledge_release_id for record in recorder.list_all()] == [
        RELEASE.knowledge_release_id
    ] * 3
    assert run.model is not None
    assert run.model.degraded is False
    assert run.model.trace_id == run.candidates[0].trace_id


def test_fewer_than_three_profiles_persist_empty_without_invoking_the_judge() -> None:
    service, recorder = _service(_bundle(2))

    run = service.start(phenomenon=PHENOMENON, release=RELEASE)

    assert run.status is MatchRunStatus.NO_RELIABLE_CANDIDATE
    assert run.candidates == ()
    assert run.stable_candidate_order == ()
    assert run.model is None
    assert recorder.list_all() == ()


def test_matching_passes_the_authenticated_owner_to_personal_evidence_retrieval() -> None:
    source = _EvidenceSource(_bundle(2))
    service = TheoryMatchingService(
        evidence_source=source,
        judge=create_deterministic_mock_provider(),
        repository=_MatchRunRepository(),
        provider="deterministic-mock",
        model_version="mock-sociology-v1",
        capability="mock",
        contract_version="matching.v1",
        id_factory=_ids(),
    )
    owner_id = UUID(int=909)

    service.start(user_id=owner_id, phenomenon=PHENOMENON, release=RELEASE)

    assert source.user_ids == [owner_id]


class _JudgeThatOmitsOneCandidate:
    def judge_and_rerank(self, *, input):
        first = input.items[0]
        input_ids = tuple(item.candidate_id for item in input.items)
        return TheoryJudgementBatchResult(
            results=(
                TheoryJudgementBatchItemResult(
                    candidate_id=first.candidate_id,
                    candidate_version=first.candidate_version,
                    status=CandidateJudgementRunStatus.FAILED,
                    judgement=None,
                    failure_code="model_timeout",
                    trace_id=UUID(int=900),
                    request_id=UUID(int=901),
                    contract_version="matching.v1",
                ),
            ),
            input_candidate_order=input_ids,
            ranked_candidate_order=(first.candidate_id,),
            completion_basis=MatchCompletionBasis.PARTIAL,
            retryable_candidate_ids=(first.candidate_id,),
        )


def test_all_missing_or_failed_results_do_not_enter_partial_decision() -> None:
    repository = _MatchRunRepository()
    service = TheoryMatchingService(
        evidence_source=_EvidenceSource(_bundle(3)),
        judge=_JudgeThatOmitsOneCandidate(),
        repository=repository,
        provider="test",
        model_version="test",
        capability="base",
        contract_version="matching.v1",
        id_factory=_ids(),
    )

    run = service.start(phenomenon=PHENOMENON, release=RELEASE)

    assert run.status is MatchRunStatus.FAILED
    assert len(run.failed_candidate_ids) == 3
    assert len(run.candidate_failures) == 3


def _judgement(title: str) -> TheoryJudgementDraft:
    return TheoryJudgementDraft(
        verdict=TheoryJudgementVerdict.CONDITIONAL,
        match_rationale=f"{title} 有条件适用",
        applicable_conditions=("存在持续互动",),
        limitations=("仍需比较材料",),
        material_requirements=("互动记录",),
        evidence_gaps=("缺少时间顺序",),
        alternative_explanations=("资源供给变化",),
        evidence_ref_ids=(),
    )


class _OneFailureThenSuccessJudge:
    def __init__(self) -> None:
        self.calls = 0

    def judge_and_rerank(self, *, input):
        self.calls += 1
        if self.calls == 1:
            results = []
            failed_id = input.items[-1].candidate_id
            for item in input.items:
                failed = item.candidate_id == failed_id
                results.append(
                    TheoryJudgementBatchItemResult(
                        candidate_id=item.candidate_id,
                        candidate_version=item.candidate_version,
                        status=(
                            CandidateJudgementRunStatus.TIMED_OUT
                            if failed
                            else CandidateJudgementRunStatus.SUCCEEDED
                        ),
                        judgement=(
                            None
                            if failed
                            else _judgement(item.judgement_input.candidate.title)
                        ),
                        failure_code="model_timeout" if failed else None,
                        trace_id=UUID(int=700 + len(results)),
                        request_id=UUID(int=800 + len(results)),
                        contract_version="matching.v1",
                    )
                )
            return TheoryJudgementBatchResult(
                results=tuple(results),
                input_candidate_order=tuple(item.candidate_id for item in input.items),
                ranked_candidate_order=tuple(item.candidate_id for item in input.items),
                completion_basis=MatchCompletionBasis.PARTIAL,
                retryable_candidate_ids=(failed_id,),
            )

        item = next(
            item for item in input.items if item.candidate_id in input.target_candidate_ids
        )
        return TheoryJudgementBatchResult(
            results=(
                TheoryJudgementBatchItemResult(
                    candidate_id=item.candidate_id,
                    candidate_version=item.candidate_version,
                    status=CandidateJudgementRunStatus.SUCCEEDED,
                    judgement=_judgement(item.judgement_input.candidate.title),
                    failure_code=None,
                    trace_id=UUID(int=900),
                    request_id=UUID(int=901),
                    contract_version="matching.v1",
                ),
            ),
            input_candidate_order=tuple(value.candidate_id for value in input.items),
            ranked_candidate_order=tuple(value.candidate_id for value in input.items),
            completion_basis=MatchCompletionBasis.COMPLETE,
            retryable_candidate_ids=(),
        )


def test_partial_failure_keeps_reason_and_content_then_retry_recovers() -> None:
    repository = _MatchRunRepository()
    judge = _OneFailureThenSuccessJudge()
    service = TheoryMatchingService(
        evidence_source=_EvidenceSource(_bundle(3)),
        judge=judge,
        repository=repository,
        provider="test",
        model_version="test",
        capability="base",
        contract_version="matching.v1",
        id_factory=_ids(),
    )

    run = service.start(phenomenon=PHENOMENON, release=RELEASE)

    assert run.status is MatchRunStatus.PARTIAL_FAILURE
    assert len(run.candidates) == 2
    assert len(run.candidate_failures) == 1
    failure = run.candidate_failures[0]
    assert failure.content.title == "理论 3"
    assert failure.failure_code == "model_timeout"
    assert failure.retryable is True

    recovered = service.retry_candidate(
        match_run_id=run.match_run_id,
        candidate_id=failure.candidate_id,
        expected_version=run.version,
        expected_candidate_version=failure.candidate_version,
    )

    assert recovered.version == 2
    assert recovered.status is MatchRunStatus.AWAITING_DECISION
    assert recovered.candidate_failures == ()
    assert len(recovered.candidates) == 3
    assert next(
        item for item in recovered.candidates if item.candidate_id == failure.candidate_id
    ).candidate_version == 2


class _AllFailuresJudge:
    def __init__(self, failure_code: str, retryable: bool) -> None:
        self.failure_code = failure_code
        self.retryable = retryable

    def judge_and_rerank(self, *, input):
        results = tuple(
            TheoryJudgementBatchItemResult(
                candidate_id=item.candidate_id,
                candidate_version=item.candidate_version,
                status=CandidateJudgementRunStatus.FAILED,
                judgement=None,
                failure_code=self.failure_code,
                trace_id=UUID(int=950 + index),
                request_id=UUID(int=960 + index),
                contract_version="matching.v1",
            )
            for index, item in enumerate(input.items)
        )
        ids = tuple(item.candidate_id for item in input.items)
        return TheoryJudgementBatchResult(
            results=results,
            input_candidate_order=ids,
            ranked_candidate_order=ids,
            completion_basis=MatchCompletionBasis.PARTIAL,
            retryable_candidate_ids=ids if self.retryable else (),
        )


def test_all_no_reliable_results_have_a_truthful_terminal_state() -> None:
    repository = _MatchRunRepository()
    service = TheoryMatchingService(
        evidence_source=_EvidenceSource(_bundle(3)),
        judge=_AllFailuresJudge("no_reliable_candidate", retryable=False),
        repository=repository,
        provider="test",
        model_version="test",
        capability="base",
        contract_version="matching.v1",
        id_factory=_ids(),
    )

    run = service.start(phenomenon=PHENOMENON, release=RELEASE)

    assert run.status is MatchRunStatus.NO_RELIABLE_CANDIDATE
    assert len(run.candidate_failures) == 3
    assert all(not item.retryable for item in run.candidate_failures)


def test_all_transient_failures_stay_retryable_without_entering_decision() -> None:
    repository = _MatchRunRepository()
    service = TheoryMatchingService(
        evidence_source=_EvidenceSource(_bundle(3)),
        judge=_AllFailuresJudge("model_unavailable", retryable=True),
        repository=repository,
        provider="test",
        model_version="test",
        capability="base",
        contract_version="matching.v1",
        id_factory=_ids(),
    )

    run = service.start(phenomenon=PHENOMENON, release=RELEASE)

    assert run.status is MatchRunStatus.FAILED
    assert run.candidates == ()
    assert len(run.candidate_failures) == 3
    assert all(item.retryable for item in run.candidate_failures)
