from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from qunxue_api.adapters.sqlite.theory_matching import SqliteMatchRunRepository
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
    MatchRunModelSnapshot,
    MatchRunSnapshot,
    MatchRunStatus,
    TheoryCandidateContentSnapshot,
    TheoryCandidateSnapshot,
    TheoryJudgementDraft,
    TheoryJudgementVerdict,
)


def _persistable_run(task_id: UUID) -> MatchRunSnapshot:
    release = KnowledgeReleaseRef(
        knowledge_release_id="release-reviewed-v1",
        level=KnowledgeReleaseLevel.PREVIEW,
        content_hash="sha256:reviewed-release",
    )
    phenomenon = ConfirmedPhenomenonSnapshot(
        task_id=task_id,
        phenomenon_query_id=UUID(int=2),
        version=2,
        phenomenon="社区互助为何随成员流动减少？",
        research_intent="比较解释边界",
        context="社区成员持续流动",
        content_hash="phenomenon-hash",
    )
    source = SourceRecordSnapshot(
        source_id="source-1",
        source_type="reviewed_publication",
        title="理论来源",
        authors_or_institution=("作者",),
        year=2025,
        publication="社会学期刊",
        locator="p.1",
        url="https://example.com/source",
        verification_status=SourceVerificationStatus.VERIFIED,
        use_boundary="仅支持档案中列出的命题。",
    )
    profile = TheoryProfileSnapshot(
        theory_id="theory-1",
        related_knowledge_ids=("D2:P001",),
        title="理论 1",
        core_propositions=("已审核命题",),
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
    evidence = EvidenceItemSnapshot(
        evidence_ref_id="evidence-1",
        claim="已审核命题",
        excerpt=None,
        locator=source.locator,
        source=source,
        verification_status=source.verification_status,
        use_boundary=source.use_boundary,
    )
    content = TheoryCandidateContentSnapshot(
        theory_id=profile.theory_id,
        title=profile.title,
        origin=CandidateOrigin.REVIEWED_KNOWLEDGE,
        problem_focus="社区互动",
        core_claims=profile.core_propositions,
        analysis_levels=profile.analysis_levels,
        source_ids=profile.source_ids,
        reviewed_profile=profile,
        formal_adoption_eligible=True,
        adoption_blockers=(),
        knowledge_id="D2:P001",
        content_status=CandidateContentStatus.REVIEWED,
    )
    judgement = TheoryJudgementDraft(
        verdict=TheoryJudgementVerdict.CONDITIONAL,
        match_rationale="能够解释部分机制。",
        applicable_conditions=("存在持续互动",),
        limitations=("仍需核对材料",),
        material_requirements=("互动记录",),
        evidence_gaps=("缺少时间顺序",),
        alternative_explanations=("资源变化",),
        evidence_ref_ids=(evidence.evidence_ref_id,),
    )
    candidate = TheoryCandidateSnapshot(
        candidate_id=UUID(int=3),
        candidate_version=1,
        content=content,
        judgement=judgement,
        trace_id=UUID(int=4),
        request_id=UUID(int=5),
        contract_version="matching.v1",
        judgement_run_status=CandidateJudgementRunStatus.SUCCEEDED,
    )
    return MatchRunSnapshot(
        match_run_id=UUID(int=1),
        task_id=task_id,
        version=1,
        status=MatchRunStatus.AWAITING_DECISION,
        phenomenon=phenomenon,
        knowledge_release=release,
        evidence_bundle=EvidenceBundleSnapshot(
            evidence_bundle_id="bundle-1",
            version=1,
            content_hash="sha256:bundle-1",
            release=release,
            theory_profiles=(profile,),
            evidence_items=(evidence,),
        ),
        candidates=(candidate,),
        stable_candidate_order=(candidate.candidate_id,),
        model=MatchRunModelSnapshot(
            provider="deterministic-mock",
            model_version="mock-sociology-v1",
            capability="mock",
            degraded=False,
            knowledge_release_id=release.knowledge_release_id,
            trace_id=candidate.trace_id,
            request_id=candidate.request_id,
            contract_version=candidate.contract_version,
        ),
    )


def test_repository_restores_the_complete_match_run_in_a_new_session(
    client: TestClient,
) -> None:
    registered = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": "matching-restart@example.com", "password": "research-passphrase"},
    )
    assert registered.status_code == 201
    created = client.post(
        "/api/research-tasks",
        headers={"Idempotency-Key": str(uuid4())},
        json={"entry_type": "direct_input"},
    )
    assert created.status_code == 201
    snapshot = _persistable_run(UUID(created.json()["task_id"]))

    with client.app.state.database.session() as session:
        SqliteMatchRunRepository(session).add(snapshot)

    with client.app.state.database.session() as session:
        restored = SqliteMatchRunRepository(session).get(snapshot.match_run_id)

    assert restored == snapshot


def test_repository_does_not_overwrite_a_concurrent_match_run_update(
    client: TestClient,
) -> None:
    registered = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={"email": "matching-cas@example.com", "password": "research-passphrase"},
    )
    assert registered.status_code == 201
    created = client.post(
        "/api/research-tasks",
        headers={"Idempotency-Key": str(uuid4())},
        json={"entry_type": "direct_input"},
    )
    assert created.status_code == 201
    base = replace(
        _persistable_run(UUID(created.json()["task_id"])),
        status=MatchRunStatus.PARTIAL_FAILURE,
        completion_basis=MatchCompletionBasis.PARTIAL,
        partial_completion_acknowledged=False,
    )
    now = datetime.now(UTC)
    first = replace(
        base,
        version=2,
        status=MatchRunStatus.AWAITING_DECISION,
        completion_basis=MatchCompletionBasis.PARTIAL_WITH_USER_ACK,
        partial_completion_acknowledged=True,
        partial_completion_acknowledgement_reason="first acknowledgement",
        partial_completion_acknowledged_at=now,
        partial_completion_idempotency_key="first-key",
        partial_completion_request_hash="sha256:first",
    )
    stale_second = replace(
        first,
        partial_completion_acknowledgement_reason="stale acknowledgement",
        partial_completion_idempotency_key="second-key",
        partial_completion_request_hash="sha256:second",
    )

    with client.app.state.database.session() as session:
        SqliteMatchRunRepository(session).add(base)
    with client.app.state.database.session() as session:
        assert SqliteMatchRunRepository(session).save(first) == first
    with client.app.state.database.session() as session:
        persisted = SqliteMatchRunRepository(session).save(stale_second)

    assert persisted == first
    with client.app.state.database.session() as session:
        assert SqliteMatchRunRepository(session).get(base.match_run_id) == first
