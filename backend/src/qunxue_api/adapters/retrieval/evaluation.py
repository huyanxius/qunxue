"""Frozen retrieval-suite parsing and provider-independent metric calculation."""

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from .hybrid import HybridRetrievalTrace
from .sqlite_index import RetrievalChunk


@dataclass(frozen=True, slots=True)
class RetrievalEvaluationParameters:
    top_k: int
    rrf_rank_constant: int
    recall_limit: int
    min_lexical_score: float
    min_rerank_score: float
    max_provider_calls_per_query: int
    max_rerank_documents: int
    embedding_batch_size: int
    rerank_query_expansion_min_lexical_score: float | None = None


@dataclass(frozen=True, slots=True)
class RetrievalEvaluationAcceptance:
    min_final_top1_accuracy: float
    min_negative_rejection_rate: float
    max_p95_latency_ms: float
    min_required_nonempty_rate: float = 1.0


@dataclass(frozen=True, slots=True)
class RetrievalEvaluationCase:
    case_id: str
    split: Literal["calibration", "test"]
    query: str
    expected_theory_id: str | None
    expect_results: bool


@dataclass(frozen=True, slots=True)
class RetrievalEvaluationSuite:
    suite_version: str
    frozen_at: str
    knowledge_release_id: str
    release_content_hash: str
    chunk_schema_version: str
    embedding_model: str
    reranker_model: str
    parameters: RetrievalEvaluationParameters
    acceptance: RetrievalEvaluationAcceptance
    queries: tuple[RetrievalEvaluationCase, ...]


@dataclass(frozen=True, slots=True)
class RetrievalEvaluationCaseResult:
    case_id: str
    split: str
    query: str
    expected_theory_id: str | None
    expect_results: bool
    lexical_theory_ids: tuple[str, ...]
    semantic_theory_ids: tuple[str, ...]
    hybrid_theory_ids: tuple[str, ...]
    reranked_theory_ids: tuple[str, ...]
    final_theory_ids: tuple[str, ...]
    final_rerank_scores: tuple[float, ...]
    rerank_query: str
    latency_ms: float
    provider_calls: int
    rerank_documents: int
    passed: bool


def load_retrieval_evaluation_suite(path: Path) -> RetrievalEvaluationSuite:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("retrieval evaluation suite must be a JSON object")
    parameters = RetrievalEvaluationParameters(**_required_mapping(payload, "parameters"))
    acceptance = RetrievalEvaluationAcceptance(**_required_mapping(payload, "acceptance"))
    raw_queries = payload.get("queries")
    if not isinstance(raw_queries, list) or not raw_queries:
        raise ValueError("retrieval evaluation suite requires queries")
    parsed_queries = []
    for item in raw_queries:
        if not isinstance(item, dict):
            continue
        expected_theory_id = _optional_text(item.get("expected_theory_id"))
        expect_results = item.get("expect_results", expected_theory_id is not None)
        if not isinstance(expect_results, bool):
            raise ValueError("expect_results must be boolean")
        if expected_theory_id is not None and not expect_results:
            raise ValueError("a labeled theory case must expect retrieval results")
        parsed_queries.append(
            RetrievalEvaluationCase(
                case_id=_required_text(item, "case_id"),
                split=_split(item.get("split")),
                query=_required_text(item, "query"),
                expected_theory_id=expected_theory_id,
                expect_results=expect_results,
            )
        )
    queries = tuple(parsed_queries)
    if len(queries) != len(raw_queries):
        raise ValueError("retrieval evaluation query must be an object")
    case_ids = [item.case_id for item in queries]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("retrieval evaluation case IDs must be unique")
    if {item.split for item in queries} != {"calibration", "test"}:
        raise ValueError("retrieval evaluation requires calibration and test splits")
    _validate_parameters(parameters, acceptance)
    return RetrievalEvaluationSuite(
        suite_version=_required_text(payload, "suite_version"),
        frozen_at=_required_text(payload, "frozen_at"),
        knowledge_release_id=_required_text(payload, "knowledge_release_id"),
        release_content_hash=_required_text(payload, "release_content_hash"),
        chunk_schema_version=_required_text(payload, "chunk_schema_version"),
        embedding_model=_required_text(payload, "embedding_model"),
        reranker_model=_required_text(payload, "reranker_model"),
        parameters=parameters,
        acceptance=acceptance,
        queries=queries,
    )


def evaluate_retrieval_trace(
    *,
    case: RetrievalEvaluationCase,
    trace: HybridRetrievalTrace,
    chunks_by_id: dict[str, RetrievalChunk],
    latency_ms: float,
) -> RetrievalEvaluationCaseResult:
    lexical = _theory_ids(trace.lexical, chunks_by_id)
    semantic = _theory_ids(trace.semantic, chunks_by_id)
    hybrid = _theory_ids(trace.fused, chunks_by_id)
    reranked = _theory_ids(trace.reranked, chunks_by_id)
    final = tuple(
        hit.chunk.theory_id or hit.chunk.knowledge_id or hit.chunk.chunk_id
        for hit in trace.result.hits
    )
    expected = case.expected_theory_id
    passed = (
        final[:1] == (expected,)
        if expected is not None
        else bool(final)
        if case.expect_results
        else not final
    )
    return RetrievalEvaluationCaseResult(
        case_id=case.case_id,
        split=case.split,
        query=case.query,
        expected_theory_id=expected,
        expect_results=case.expect_results,
        lexical_theory_ids=lexical,
        semantic_theory_ids=semantic,
        hybrid_theory_ids=hybrid,
        reranked_theory_ids=reranked,
        final_theory_ids=final,
        final_rerank_scores=tuple(
            round(float(hit.rerank_score), 8)
            for hit in trace.result.hits
            if hit.rerank_score is not None
        ),
        rerank_query=trace.rerank_query,
        latency_ms=round(latency_ms, 1),
        provider_calls=1 + int(bool(trace.fused)),
        rerank_documents=len(trace.fused),
        passed=passed,
    )


def summarize_retrieval_evaluation(
    *,
    suite: RetrievalEvaluationSuite,
    split: str,
    retrieval_index_id: str,
    results: tuple[RetrievalEvaluationCaseResult, ...],
) -> dict[str, object]:
    if not results:
        raise ValueError("retrieval evaluation produced no results")
    positives = tuple(item for item in results if item.expected_theory_id is not None)
    required_nonempty = tuple(
        item for item in results if item.expected_theory_id is None and item.expect_results
    )
    negatives = tuple(item for item in results if not item.expect_results)
    if not positives or not negatives:
        raise ValueError("retrieval evaluation split requires positive and negative cases")
    top_k = suite.parameters.top_k
    stage_recall = {
        "lexical": _recall_at_k(positives, "lexical_theory_ids", top_k),
        "semantic": _recall_at_k(positives, "semantic_theory_ids", top_k),
        "hybrid": _recall_at_k(positives, "hybrid_theory_ids", top_k),
        "reranked": _recall_at_k(positives, "reranked_theory_ids", top_k),
    }
    final_top1_accuracy = _ratio(sum(item.passed for item in positives), len(positives))
    negative_rejection_rate = _ratio(sum(item.passed for item in negatives), len(negatives))
    required_nonempty_rate = (
        _ratio(sum(item.passed for item in required_nonempty), len(required_nonempty))
        if required_nonempty
        else None
    )
    p95_latency_ms = _nearest_rank_percentile(tuple(item.latency_ms for item in results), 0.95)
    max_provider_calls = max(item.provider_calls for item in results)
    max_rerank_documents = max(item.rerank_documents for item in results)
    gates = {
        "final_top1_accuracy": (final_top1_accuracy >= suite.acceptance.min_final_top1_accuracy),
        "negative_rejection_rate": (
            negative_rejection_rate >= suite.acceptance.min_negative_rejection_rate
        ),
        "p95_latency_ms": p95_latency_ms <= suite.acceptance.max_p95_latency_ms,
        "provider_calls_per_query": (
            max_provider_calls <= suite.parameters.max_provider_calls_per_query
        ),
        "rerank_documents": (max_rerank_documents <= suite.parameters.max_rerank_documents),
    }
    if required_nonempty_rate is not None:
        gates["required_nonempty_rate"] = (
            required_nonempty_rate >= suite.acceptance.min_required_nonempty_rate
        )
    return {
        "suite_version": suite.suite_version,
        "frozen_at": suite.frozen_at,
        "split": split,
        "retrieval_index_id": retrieval_index_id,
        "knowledge_release_id": suite.knowledge_release_id,
        "release_content_hash": suite.release_content_hash,
        "embedding_model": suite.embedding_model,
        "reranker_model": suite.reranker_model,
        "parameters": asdict(suite.parameters),
        "metrics": {
            "positive_case_count": len(positives),
            "negative_case_count": len(negatives),
            "required_nonempty_case_count": len(required_nonempty),
            "stage_recall_at_k": stage_recall,
            "final_top1_accuracy": final_top1_accuracy,
            "negative_rejection_rate": negative_rejection_rate,
            "required_nonempty_rate": required_nonempty_rate,
            "p95_latency_ms": p95_latency_ms,
            "max_provider_calls_per_query": max_provider_calls,
            "max_rerank_documents": max_rerank_documents,
        },
        "cost_bounds": {
            "provider_calls_per_query": max_provider_calls,
            "embedding_inputs_per_query": 1,
            "reranker_documents_per_query": max_rerank_documents,
        },
        "gates": gates,
        "passed": all(gates.values()),
        "cases": [asdict(item) for item in results],
    }


def _theory_ids(values, chunks_by_id: dict[str, RetrievalChunk]) -> tuple[str, ...]:
    result = []
    for item in values:
        chunk = chunks_by_id.get(item.chunk_id)
        if chunk is None:
            raise ValueError("retrieval trace references a chunk outside the pinned index")
        identity = chunk.theory_id or chunk.knowledge_id or chunk.chunk_id
        if identity not in result:
            result.append(identity)
    return tuple(result)


def _recall_at_k(
    results: tuple[RetrievalEvaluationCaseResult, ...],
    field: str,
    top_k: int,
) -> float:
    hits = sum(item.expected_theory_id in getattr(item, field)[:top_k] for item in results)
    return _ratio(hits, len(results))


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6)


def _nearest_rank_percentile(values: tuple[float, ...], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 1)


def _required_mapping(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"retrieval evaluation requires {key}")
    return value


def _required_text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"retrieval evaluation requires {key}")
    return value.strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("expected_theory_id must be a non-empty string or null")
    return value.strip()


def _split(value: object) -> Literal["calibration", "test"]:
    if value not in {"calibration", "test"}:
        raise ValueError("retrieval evaluation split must be calibration or test")
    return value


def _validate_parameters(
    parameters: RetrievalEvaluationParameters,
    acceptance: RetrievalEvaluationAcceptance,
) -> None:
    if any(
        value < 1
        for value in (
            parameters.top_k,
            parameters.rrf_rank_constant,
            parameters.recall_limit,
            parameters.max_provider_calls_per_query,
            parameters.max_rerank_documents,
            parameters.embedding_batch_size,
        )
    ):
        raise ValueError("retrieval evaluation integer parameters must be positive")
    if not 0 <= parameters.min_lexical_score <= 1:
        raise ValueError("min_lexical_score must be between zero and one")
    if not 0 <= parameters.min_rerank_score <= 1:
        raise ValueError("min_rerank_score must be between zero and one")
    if (
        parameters.rerank_query_expansion_min_lexical_score is not None
        and not 0 <= parameters.rerank_query_expansion_min_lexical_score <= 1
    ):
        raise ValueError("rerank_query_expansion_min_lexical_score must be between zero and one")
    if not 0 <= acceptance.min_final_top1_accuracy <= 1:
        raise ValueError("min_final_top1_accuracy must be between zero and one")
    if not 0 <= acceptance.min_negative_rejection_rate <= 1:
        raise ValueError("min_negative_rejection_rate must be between zero and one")
    if not 0 <= acceptance.min_required_nonempty_rate <= 1:
        raise ValueError("min_required_nonempty_rate must be between zero and one")
    if acceptance.max_p95_latency_ms <= 0:
        raise ValueError("max_p95_latency_ms must be positive")
