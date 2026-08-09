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
    CandidateOrigin,
    EvidenceBundleSnapshot,
    EvidenceItemSnapshot,
    MatchRunStatus,
    TheoryMatchingService,
)

RELEASE = KnowledgeReleaseRef(
    knowledge_release_id="release-reviewed-v1",
    level=KnowledgeReleaseLevel.PREVIEW,
    content_hash="sha256:reviewed-release",
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

    def retrieve(
        self,
        *,
        phenomenon: ConfirmedPhenomenonSnapshot,
        release: KnowledgeReleaseRef,
    ) -> EvidenceBundleSnapshot:
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


def _ids(start: int = 1):
    values = count(start)
    return lambda: UUID(int=next(values))


def _bundle(profile_count: int) -> EvidenceBundleSnapshot:
    profiles = []
    evidence = []
    for index in range(1, profile_count + 1):
        source = SourceRecordSnapshot(
            source_id=f"source-{index}",
            source_type="reviewed_publication",
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
            review_status=KnowledgeReviewStatus.REVIEWED,
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


def test_three_reviewed_profiles_become_stably_ordered_judged_candidates() -> None:
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
        candidate.content.origin is CandidateOrigin.REVIEWED_KNOWLEDGE
        and candidate.content.content_status is CandidateContentStatus.REVIEWED
        and candidate.content.formal_adoption_eligible
        for candidate in run.candidates
    )
    assert [record.task_id for record in recorder.list_all()] == [PHENOMENON.task_id] * 3
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
