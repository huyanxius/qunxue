"""Run the frozen release-bound retrieval comparison with real providers."""

import argparse
import json
import math
import time
from collections.abc import Sequence
from pathlib import Path

from qunxue_api.adapters.research_agent.embedding import (
    OpenAICompatibleEmbeddingProvider,
)
from qunxue_api.adapters.research_agent.reranker import SiliconFlowRerankerProvider
from qunxue_api.adapters.retrieval import (
    HybridRetriever,
    SqliteRetrievalIndex,
)
from qunxue_api.adapters.retrieval.evaluation import (
    evaluate_retrieval_trace,
    load_retrieval_evaluation_suite,
    summarize_retrieval_evaluation,
)
from qunxue_api.settings import Settings

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUITE = BACKEND_ROOT / "evals" / "retrieval_v3.json"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare lexical, vector, hybrid, and reranked rankings on a frozen "
            "KnowledgeRelease. Production retrieval remains hybrid plus mandatory reranking."
        )
    )
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument(
        "--split",
        choices=("calibration", "test", "all"),
        default="test",
    )
    parser.add_argument(
        "--no-enforce",
        action="store_true",
        help="Print results without failing the process when an acceptance gate misses.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        suite = load_retrieval_evaluation_suite(arguments.suite.resolve())
        settings = Settings()
        config = settings.require_retrieval_config()
        _require_frozen_configuration(suite=suite, config=config)
        index = SqliteRetrievalIndex(config.index_path)
        manifest = index.find_ready_manifest(
            knowledge_release_id=suite.knowledge_release_id,
            release_content_hash=suite.release_content_hash,
            embedding_model=suite.embedding_model,
            chunk_schema_version=suite.chunk_schema_version,
        )
        chunks = index.list_chunks(
            retrieval_index_id=manifest.retrieval_index_id,
            knowledge_release_id=suite.knowledge_release_id,
            document_kind="theory_profile",
        )
        chunks_by_id = {item.chunk_id: item for item in chunks}
        retriever = HybridRetriever(
            index=index,
            embedder=OpenAICompatibleEmbeddingProvider(
                base_url=config.embedding_base_url,
                api_key=config.embedding_api_key.get_secret_value(),
                model=config.embedding_model,
                timeout_seconds=config.embedding_timeout_seconds,
            ),
            embedding_model=config.embedding_model,
            chunk_schema_version=suite.chunk_schema_version,
            reranker=SiliconFlowRerankerProvider(
                base_url=config.reranker_base_url,
                api_key=config.reranker_api_key.get_secret_value(),
                model=config.reranker_model,
                timeout_seconds=config.reranker_timeout_seconds,
            ),
            reranker_model=config.reranker_model,
            min_rerank_score=config.min_rerank_score,
            min_lexical_score=config.min_lexical_score,
            recall_limit=config.recall_limit,
        )
        selected = tuple(
            item
            for item in suite.queries
            if arguments.split == "all" or item.split == arguments.split
        )
        results = []
        for case in selected:
            started = time.perf_counter()
            trace = retriever.search_with_trace(
                query=case.query,
                knowledge_release_id=suite.knowledge_release_id,
                release_content_hash=suite.release_content_hash,
                document_kind="theory_profile",
                limit=suite.parameters.top_k,
            )
            results.append(
                evaluate_retrieval_trace(
                    case=case,
                    trace=trace,
                    chunks_by_id=chunks_by_id,
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
            )
        report = summarize_retrieval_evaluation(
            suite=suite,
            split=arguments.split,
            retrieval_index_id=manifest.retrieval_index_id,
            results=tuple(results),
        )
    except (OSError, TypeError, ValueError) as error:
        parser.error(str(error))

    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if arguments.no_enforce or report["passed"] else 1


def _require_frozen_configuration(*, suite, config) -> None:
    mismatches = []
    for field, actual, expected in (
        ("embedding_model", config.embedding_model, suite.embedding_model),
        ("reranker_model", config.reranker_model, suite.reranker_model),
        (
            "embedding_batch_size",
            config.embedding_batch_size,
            suite.parameters.embedding_batch_size,
        ),
        ("recall_limit", config.recall_limit, suite.parameters.recall_limit),
    ):
        if actual != expected:
            mismatches.append(f"{field}={actual!r}, expected {expected!r}")
    for field, actual, expected in (
        ("min_lexical_score", config.min_lexical_score, suite.parameters.min_lexical_score),
        ("min_rerank_score", config.min_rerank_score, suite.parameters.min_rerank_score),
    ):
        if not math.isclose(actual, expected, rel_tol=0, abs_tol=1e-12):
            mismatches.append(f"{field}={actual!r}, expected {expected!r}")
    if suite.parameters.rrf_rank_constant != 60:
        mismatches.append("rrf_rank_constant must match the production value 60")
    if mismatches:
        raise ValueError("frozen retrieval configuration mismatch: " + "; ".join(mismatches))


if __name__ == "__main__":
    raise SystemExit(main())
