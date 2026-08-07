from datetime import UTC, datetime
from itertools import count
from uuid import UUID

import pytest

from qunxue_api.adapters.model import (
    BuiltInCaseCatalog,
    InMemoryModelInvocationRecorder,
    ModelCapabilityName,
    ModelGateway,
    ModelScenario,
    SqliteModelInvocationRecorder,
    create_deterministic_mock_provider,
)
from qunxue_api.adapters.sqlite import Base
from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.modules.knowledge_catalog import (
    KnowledgeReleaseLevel,
    KnowledgeReleaseRef,
    KnowledgeReviewStatus,
    SourceRecordSnapshot,
    SourceVerificationStatus,
    TheoryProfileSnapshot,
)
from qunxue_api.modules.research_framework import (
    AuditOverallStatus,
    FrameworkVersionSnapshot,
    MethodIntentSnapshot,
    ResearchFrameworkDraft,
    ResearchFrameworkDraftInput,
)
from qunxue_api.modules.research_intake import ConfirmedPhenomenonSnapshot
from qunxue_api.modules.theory_matching import (
    CandidateJudgementRunStatus,
    CandidateOrigin,
    ConfirmedTheoryPlanSnapshot,
    EvidenceBundleSnapshot,
    EvidenceItemSnapshot,
    MatchCompletionBasis,
    TheoryCandidateContentSnapshot,
    TheoryCandidateSnapshot,
    TheoryDecisionAction,
    TheoryDecisionRecord,
    TheoryJudgementBatchInput,
    TheoryJudgementBatchItem,
    TheoryJudgementDraft,
    TheoryJudgementInput,
    TheoryJudgementVerdict,
    TheoryUseAssignment,
)

NOW = datetime(2026, 8, 7, 9, 30, tzinfo=UTC)
RELEASE = KnowledgeReleaseRef(
    knowledge_release_id="knowledge-demo-v1",
    level=KnowledgeReleaseLevel.PREVIEW,
    content_hash="sha256:demo-release",
)


def _ids() -> object:
    values = count(1)
    return lambda: UUID(int=next(values))


def _model_inputs(
    phenomenon_text: str,
) -> tuple[TheoryJudgementInput, ResearchFrameworkDraftInput, FrameworkVersionSnapshot]:
    phenomenon = ConfirmedPhenomenonSnapshot(
        task_id=UUID(int=101),
        phenomenon_query_id=UUID(int=102),
        version=1,
        phenomenon=phenomenon_text,
        research_intent="比较制度规范与关系网络的解释",
        context="由后端演示案例提供的去标识化情境",
    )
    source = SourceRecordSnapshot(
        source_id="source-demo-1",
        source_type="review_note",
        title="演示知识来源说明",
        authors_or_institution=("群学致知项目组",),
        year=2026,
        publication=None,
        locator="demo:1",
        url=None,
        verification_status=SourceVerificationStatus.SYSTEM_SUMMARY,
        use_boundary="仅用于演示流程，不作为正式学术证据",
    )
    profile = TheoryProfileSnapshot(
        theory_id="theory-social-capital",
        related_knowledge_ids=("knowledge-social-capital",),
        title="社会资本理论",
        core_propositions=("持续互动有助于形成互惠规范",),
        applicable_phenomena=("社区互助",),
        analysis_levels=("关系网络",),
        prerequisites=("存在可识别的重复互动",),
        exclusion_signals=("成员之间从不重复互动",),
        observable_evidence=("互助频率与关系持续时间",),
        competing_or_complementary_theory_ids=(),
        source_ids=(source.source_id,),
        content_version=1,
        review_status=KnowledgeReviewStatus.REVIEWED,
        match_eligible=True,
    )
    evidence = EvidenceItemSnapshot(
        evidence_ref_id="evidence-demo-1",
        claim="成员流动可能削弱重复互动",
        excerpt="该内容为演示性系统摘要。",
        locator=source.locator,
        source=source,
        verification_status=source.verification_status,
        use_boundary=source.use_boundary,
    )
    content = TheoryCandidateContentSnapshot(
        theory_id=profile.theory_id,
        title=profile.title,
        origin=CandidateOrigin.REVIEWED_KNOWLEDGE,
        problem_focus="关系持续性如何影响社区互助",
        core_claims=profile.core_propositions,
        analysis_levels=profile.analysis_levels,
        source_ids=profile.source_ids,
        reviewed_profile=profile,
        formal_adoption_eligible=True,
        adoption_blockers=(),
        knowledge_id="knowledge-social-capital",
    )
    judgement_input = TheoryJudgementInput(
        phenomenon=phenomenon,
        candidate=content,
        comparison_candidates=(),
        evidence_items=(evidence,),
    )
    previous_judgement = TheoryJudgementDraft(
        verdict=TheoryJudgementVerdict.CONDITIONAL,
        match_rationale="演示用旧判断",
        applicable_conditions=(),
        limitations=(),
        material_requirements=(),
        evidence_gaps=(),
        alternative_explanations=(),
        evidence_ref_ids=(evidence.evidence_ref_id,),
    )
    candidate = TheoryCandidateSnapshot(
        candidate_id=UUID(int=103),
        candidate_version=1,
        content=content,
        judgement=previous_judgement,
        trace_id=UUID(int=104),
        request_id=UUID(int=105),
        contract_version="theory-judgement.v1",
    )
    bundle = EvidenceBundleSnapshot(
        evidence_bundle_id="bundle-demo-1",
        version=1,
        content_hash="sha256:demo-bundle",
        release=RELEASE,
        theory_profiles=(profile,),
        evidence_items=(evidence,),
    )
    decision = TheoryDecisionRecord(
        decision_id=UUID(int=106),
        candidate_id=candidate.candidate_id,
        candidate_version=1,
        action=TheoryDecisionAction.ADOPT,
        reason="演示案例采用该理论",
        related_source_ids=(source.source_id,),
        revised_applicability=None,
        recorded_at=NOW,
    )
    theory_plan = ConfirmedTheoryPlanSnapshot(
        theory_plan_id=UUID(int=107),
        task_id=phenomenon.task_id,
        match_run_id=UUID(int=108),
        decision_set_id=UUID(int=109),
        version=1,
        phenomenon=phenomenon,
        knowledge_release=RELEASE,
        evidence_bundle=bundle,
        candidates=(candidate,),
        decisions=(decision,),
        use_assignments=(
            TheoryUseAssignment(
                candidate_id=candidate.candidate_id,
                role_code="primary",
                responsibility="解释关系持续性与互助规范",
            ),
        ),
        relations=(),
        confirmed_at=NOW,
    )
    framework_input = ResearchFrameworkDraftInput(
        theory_plan=theory_plan,
        original_research_question="社区互助为什么减少？",
        confirmed_research_question="成员流动如何影响社区互助？",
        question_adjustment_reason="将问题收敛到可观察机制",
        research_object="社区成员",
        analysis_unit="成员关系",
        context=phenomenon.context,
        method_intent=MethodIntentSnapshot(
            method_kind=None,
            constraints=("不得使用未获授权的真实材料",),
            source="user_confirmed",
        ),
    )
    placeholder_framework = FrameworkVersionSnapshot(
        framework_id=UUID(int=110),
        task_id=phenomenon.task_id,
        version=1,
        input=framework_input,
        draft=ResearchFrameworkDraft(
            concept_mappings=(),
            evidence_requirements=(),
            inference_links=(),
            alternative_explanations=(),
            method_plan=None,
            scope_and_limitations=(),
            unresolved_items=("需要用户确认取样范围",),
            next_actions=(),
        ),
        revision_id=UUID(int=111),
    )
    return judgement_input, framework_input, placeholder_framework


def _batch_input(input: TheoryJudgementInput) -> TheoryJudgementBatchInput:
    candidate_id = UUID(int=103)
    return TheoryJudgementBatchInput(
        items=(
            TheoryJudgementBatchItem(
                candidate_id=candidate_id,
                candidate_version=1,
                judgement_input=input,
            ),
        ),
        target_candidate_ids=(candidate_id,),
    )


def test_one_gateway_serves_four_capabilities_and_records_truthful_traces() -> None:
    catalog = BuiltInCaseCatalog.default()
    success = catalog.get("success")
    recorder = InMemoryModelInvocationRecorder()
    gateway = ModelGateway(
        provider=create_deterministic_mock_provider(catalog=catalog),
        recorder=recorder,
        id_factory=_ids(),
        clock=lambda: NOW,
        contract_version="model-gateway.v1",
    )
    judgement_input, framework_input, framework = _model_inputs(success.phenomenon)

    phenomenon = gateway.build(
        task_id=UUID(int=200),
        raw_input=success.phenomenon,
        research_intent=success.research_intent,
        context=success.context,
    )
    judgement = gateway.judge_and_rerank(input=_batch_input(judgement_input))
    draft = gateway.draft(input=framework_input)
    audit = gateway.audit(framework=framework)

    assert phenomenon.phenomenon == success.phenomenon
    assert judgement.results[0].judgement is not None
    assert judgement.results[0].judgement.verdict is TheoryJudgementVerdict.CONDITIONAL
    assert judgement.results[0].status is CandidateJudgementRunStatus.SUCCEEDED
    assert judgement.input_candidate_order == (UUID(int=103),)
    assert judgement.ranked_candidate_order == (UUID(int=103),)
    assert judgement.completion_basis is MatchCompletionBasis.COMPLETE
    assert judgement.retryable_candidate_ids == ()
    assert draft.concept_mappings[0].candidate_id == UUID(int=103)
    assert audit.overall_status is AuditOverallStatus.REVISE

    records = recorder.list_all()
    assert [record.capability for record in records] == [
        ModelCapabilityName.PHENOMENON_EXTRACTION,
        ModelCapabilityName.CANDIDATE_JUDGEMENT_AND_RERANK,
        ModelCapabilityName.FRAMEWORK_DRAFT,
        ModelCapabilityName.FRAMEWORK_AUDIT,
    ]
    assert all(record.provider == "deterministic-mock" for record in records)
    assert all(record.model_version == "mock-sociology-v1" for record in records)
    assert all(record.capability_tier == "mock" for record in records)
    assert all(record.demonstration is True for record in records)
    assert all(record.output is not None for record in records)
    assert all(record.trace_id and record.request_id for record in records)
    assert records[0].knowledge_release_id is None
    assert records[0].task_id == UUID(int=200)
    assert all(record.task_id == UUID(int=101) for record in records[1:])
    assert [record.knowledge_release_id for record in records[1:]] == [
        RELEASE.knowledge_release_id,
        RELEASE.knowledge_release_id,
        RELEASE.knowledge_release_id,
    ]
    assert records[0].input_evidence["raw_input_sha256"].startswith("sha256:")
    assert "raw_input" not in records[0].input_evidence
    assert records[1].input_evidence["evidence_ref_ids"] == ["evidence-demo-1"]
    assert records[1].trace_id == judgement.results[0].trace_id
    assert records[1].request_id == judgement.results[0].request_id
    assert len(recorder.list_for_task(UUID(int=101))) == 3


@pytest.mark.parametrize(
    ("case_id", "expected_code", "expected_status", "retryable"),
    [
        ("timeout", "model_timeout", CandidateJudgementRunStatus.TIMED_OUT, True),
        (
            "insufficient-sources",
            "insufficient_sources",
            CandidateJudgementRunStatus.INSUFFICIENT_SOURCES,
            True,
        ),
        (
            "no-reliable-candidate",
            "no_reliable_candidate",
            CandidateJudgementRunStatus.FAILED,
            False,
        ),
    ],
)
def test_candidate_failures_are_formal_batch_states_and_are_recorded(
    case_id: str,
    expected_code: str,
    expected_status: CandidateJudgementRunStatus,
    retryable: bool,
) -> None:
    catalog = BuiltInCaseCatalog.default()
    scenario = catalog.get(case_id)
    recorder = InMemoryModelInvocationRecorder()
    gateway = ModelGateway(
        provider=create_deterministic_mock_provider(catalog=catalog),
        recorder=recorder,
        id_factory=_ids(),
        clock=lambda: NOW,
        contract_version="model-gateway.v1",
    )
    judgement_input, _, _ = _model_inputs(scenario.phenomenon)

    result = gateway.judge_and_rerank(input=_batch_input(judgement_input))

    item = result.results[0]
    assert item.status is expected_status
    assert item.judgement is None
    assert item.failure_code == expected_code
    assert item.trace_id == UUID(int=1)
    assert item.request_id == UUID(int=2)
    assert result.completion_basis is MatchCompletionBasis.PARTIAL
    assert result.retryable_candidate_ids == ((UUID(int=103),) if retryable else ())
    record = recorder.list_all()[0]
    assert record.degraded is True
    assert record.error_code == expected_code
    assert record.output is None


def test_shared_backend_catalog_covers_five_deterministic_scenarios() -> None:
    catalog = BuiltInCaseCatalog.default()

    page = catalog.list_page(cursor=None, limit=3)
    second_page = catalog.list_page(cursor=page.next_cursor, limit=3)

    assert tuple(item.scenario for item in catalog.list_all()) == tuple(ModelScenario)
    assert [item.case_id for item in (*page.items, *second_page.items)] == [
        "success",
        "no-reliable-candidate",
        "timeout",
        "insufficient-sources",
        "user-deferred",
    ]
    assert second_page.next_cursor is None
    assert all(item.content_status == "demonstration" for item in catalog.list_all())
    assert all("去标识化" in item.summary for item in catalog.list_all())


def test_sqlite_recorder_persists_complete_model_trace(tmp_path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'model-trace.db'}")
    Base.metadata.create_all(database.engine)
    try:
        recorder = SqliteModelInvocationRecorder(database)
        catalog = BuiltInCaseCatalog.default()
        success = catalog.get("success")
        gateway = ModelGateway(
            provider=create_deterministic_mock_provider(catalog=catalog),
            recorder=recorder,
            id_factory=_ids(),
            clock=lambda: NOW,
            contract_version="model-gateway.v1",
        )

        gateway.build(
            task_id=UUID(int=300),
            raw_input=success.phenomenon,
            research_intent=success.research_intent,
            context=success.context,
        )

        persisted = recorder.get(UUID(int=1))
        assert persisted is not None
        assert persisted.provider == "deterministic-mock"
        assert persisted.task_id == UUID(int=300)
        assert persisted.model_version == "mock-sociology-v1"
        assert persisted.input_evidence["raw_input_length"] == len(success.phenomenon)
        assert persisted.output["phenomenon"] == success.phenomenon
        assert persisted.started_at == NOW
        assert persisted.completed_at == NOW
        assert recorder.list_for_task(UUID(int=300)) == (persisted,)
    finally:
        database.engine.dispose()
