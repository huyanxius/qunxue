from uuid import UUID

import qunxue_api.modules.theory_matching as matching
from qunxue_api.modules.knowledge_catalog import (
    KnowledgeReleaseLevel,
    KnowledgeReleaseRef,
)
from qunxue_api.modules.research_intake import ConfirmedPhenomenonSnapshot


def test_batch_judgement_preserves_identity_order_partial_failure_and_retry_targets() -> None:
    item_type = getattr(matching, "TheoryJudgementBatchItem", None)
    input_type = getattr(matching, "TheoryJudgementBatchInput", None)
    item_result_type = getattr(matching, "TheoryJudgementBatchItemResult", None)
    result_type = getattr(matching, "TheoryJudgementBatchResult", None)

    assert item_type is not None
    assert input_type is not None
    assert item_result_type is not None
    assert result_type is not None

    candidate_a_id = UUID(int=101)
    candidate_b_id = UUID(int=102)
    phenomenon = ConfirmedPhenomenonSnapshot(
        task_id=UUID(int=1),
        phenomenon_query_id=UUID(int=2),
        version=1,
        phenomenon="社区互助网络在成员流动后发生变化",
        research_intent="比较规范与资源机制",
        context=None,
    )
    candidate = matching.TheoryCandidateContentSnapshot(
        theory_id=None,
        title="候选理论",
        origin=matching.CandidateOrigin.MODEL_EXPLORATION,
        problem_focus="解释互助网络变化",
        core_claims=("互动结构影响规范维持",),
        analysis_levels=("关系",),
        source_ids=(),
        reviewed_profile=None,
        formal_adoption_eligible=False,
        adoption_blockers=("来源待核验",),
    )
    judgement_input = matching.TheoryJudgementInput(
        knowledge_release=KnowledgeReleaseRef(
            knowledge_release_id="knowledge-test-v1",
            level=KnowledgeReleaseLevel.PREVIEW,
            content_hash="sha256:knowledge-test-v1",
        ),
        phenomenon=phenomenon,
        candidate=candidate,
        comparison_candidates=(candidate,),
        evidence_items=(),
    )
    batch_input = input_type(
        items=(
            item_type(candidate_a_id, 1, judgement_input),
            item_type(candidate_b_id, 1, judgement_input),
        ),
        target_candidate_ids=(candidate_b_id,),
    )
    judgement = matching.TheoryJudgementDraft(
        verdict=matching.TheoryJudgementVerdict.CONDITIONAL,
        match_rationale="机制相关但仍需来源核验",
        applicable_conditions=("存在持续互动",),
        limitations=(),
        material_requirements=(),
        evidence_gaps=("缺少时间序列材料",),
        alternative_explanations=("资源供给变化",),
        evidence_ref_ids=(),
    )
    batch_result = result_type(
        results=(
            item_result_type(
                candidate_id=candidate_a_id,
                candidate_version=1,
                status=matching.CandidateJudgementRunStatus.SUCCEEDED,
                judgement=judgement,
                failure_code=None,
                trace_id=UUID(int=201),
                request_id=UUID(int=202),
                contract_version="theory-judgement.v1",
            ),
            item_result_type(
                candidate_id=candidate_b_id,
                candidate_version=1,
                status=matching.CandidateJudgementRunStatus.TIMED_OUT,
                judgement=None,
                failure_code="model_timeout",
                trace_id=UUID(int=203),
                request_id=UUID(int=204),
                contract_version="theory-judgement.v1",
            ),
        ),
        input_candidate_order=(candidate_a_id, candidate_b_id),
        ranked_candidate_order=(candidate_a_id, candidate_b_id),
        completion_basis=matching.MatchCompletionBasis.PARTIAL,
        retryable_candidate_ids=(candidate_b_id,),
    )

    assert batch_input.target_candidate_ids == (candidate_b_id,)
    assert batch_result.input_candidate_order == (candidate_a_id, candidate_b_id)
    assert batch_result.ranked_candidate_order == (candidate_a_id, candidate_b_id)
    assert batch_result.retryable_candidate_ids == (candidate_b_id,)
    assert batch_result.results[1].candidate_id == candidate_b_id
    assert batch_result.results[0].trace_id == UUID(int=201)
    assert batch_result.results[0].request_id == UUID(int=202)
    assert batch_result.results[0].contract_version == "theory-judgement.v1"
    assert hasattr(matching.TheoryCandidateJudge, "judge_and_rerank")
