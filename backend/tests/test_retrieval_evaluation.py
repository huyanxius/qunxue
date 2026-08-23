from dataclasses import replace
from pathlib import Path
from runpy import run_path

from qunxue_api.adapters.retrieval.evaluation import (
    RetrievalEvaluationCaseResult,
    load_retrieval_evaluation_suite,
    summarize_retrieval_evaluation,
)


def _suite():
    return load_retrieval_evaluation_suite(Path(__file__).parents[1] / "evals/retrieval_v3.json")


def test_evaluation_cli_defaults_to_frozen_v3_suite() -> None:
    script = run_path(str(Path(__file__).parents[1] / "scripts/evaluate_retrieval.py"))

    assert Path(script["DEFAULT_SUITE"]).name == "retrieval_v3.json"


def _result(
    case_id: str,
    *,
    expected: str | None,
    lexical: tuple[str, ...],
    semantic: tuple[str, ...],
    hybrid: tuple[str, ...],
    reranked: tuple[str, ...],
    final: tuple[str, ...],
    latency_ms: float,
    expect_results: bool | None = None,
) -> RetrievalEvaluationCaseResult:
    required = expected is not None if expect_results is None else expect_results
    return RetrievalEvaluationCaseResult(
        case_id=case_id,
        split="test",
        query=case_id,
        expected_theory_id=expected,
        expect_results=required,
        lexical_theory_ids=lexical,
        semantic_theory_ids=semantic,
        hybrid_theory_ids=hybrid,
        reranked_theory_ids=reranked,
        final_theory_ids=final,
        final_rerank_scores=(0.9,) if final else (),
        rerank_query=case_id,
        latency_ms=latency_ms,
        provider_calls=2,
        rerank_documents=3,
        passed=(
            final[:1] == (expected,)
            if expected is not None
            else bool(final)
            if required
            else not final
        ),
    )


def test_frozen_retrieval_suite_has_disjoint_calibration_and_test_cases() -> None:
    suite = _suite()

    calibration = {item.case_id for item in suite.queries if item.split == "calibration"}
    test = {item.case_id for item in suite.queries if item.split == "test"}

    assert suite.parameters.min_rerank_score == 0.01
    assert suite.embedding_model == "Pro/BAAI/bge-m3"
    assert suite.reranker_model == "Pro/BAAI/bge-reranker-v2-m3"
    assert calibration
    assert test
    assert calibration.isdisjoint(test)


def test_evaluation_summary_compares_stages_and_enforces_latency_and_cost_bounds() -> None:
    suite = replace(
        _suite(),
        acceptance=replace(_suite().acceptance, max_p95_latency_ms=5000),
    )
    results = (
        _result(
            "positive-a",
            expected="theory-a",
            lexical=("theory-a",),
            semantic=("theory-a",),
            hybrid=("theory-a",),
            reranked=("theory-a",),
            final=("theory-a",),
            latency_ms=3100,
        ),
        _result(
            "positive-b",
            expected="theory-b",
            lexical=(),
            semantic=("theory-b",),
            hybrid=("theory-b",),
            reranked=("theory-b",),
            final=("theory-b",),
            latency_ms=4200,
        ),
        _result(
            "negative-a",
            expected=None,
            lexical=("theory-a",),
            semantic=("theory-a",),
            hybrid=("theory-a",),
            reranked=("theory-a",),
            final=(),
            latency_ms=3900,
        ),
        _result(
            "required-nonempty-a",
            expected=None,
            lexical=(),
            semantic=("theory-a",),
            hybrid=("theory-a",),
            reranked=("theory-a",),
            final=("theory-a",),
            latency_ms=3800,
            expect_results=True,
        ),
    )

    report = summarize_retrieval_evaluation(
        suite=suite,
        split="test",
        retrieval_index_id="retrieval-index:test",
        results=results,
    )

    assert report["metrics"]["stage_recall_at_k"] == {
        "lexical": 0.5,
        "semantic": 1.0,
        "hybrid": 1.0,
        "reranked": 1.0,
    }
    assert report["metrics"]["final_top1_accuracy"] == 1.0
    assert report["metrics"]["negative_rejection_rate"] == 1.0
    assert report["metrics"]["required_nonempty_rate"] == 1.0
    assert report["metrics"]["p95_latency_ms"] == 4200
    assert report["cost_bounds"] == {
        "provider_calls_per_query": 2,
        "embedding_inputs_per_query": 1,
        "reranker_documents_per_query": 3,
    }
    assert report["passed"] is True
