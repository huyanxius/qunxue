"""Preview a retrieval model switch without calling providers or changing configuration."""

import argparse
import json
import sqlite3
from pathlib import Path

from pydantic_settings import SettingsError

from qunxue_api.settings import (
    SILICONFLOW_EMBEDDING_MODELS,
    SILICONFLOW_RERANKER_MODELS,
    Settings,
)


def inspect_switch(
    settings: Settings,
    *,
    embedding_model: str = "BAAI/bge-m3",
    reranker_model: str = "BAAI/bge-reranker-v2-m3",
) -> dict:
    candidate = settings.model_copy(
        update={"embedding_model": embedding_model, "reranker_model": reranker_model}
    )
    try:
        config = candidate.require_retrieval_config()
    except ValueError:
        return {"status": "configuration_invalid", "provider_verification": "not_performed"}
    report = {
        "status": "configuration_valid",
        "embedding_model": config.embedding_model,
        "reranker_model": config.reranker_model,
        "provider_verification": "not_performed",
        "vector_dimension_verification": "not_performed",
        "index_file_present": config.index_path.is_file(),
        "ready_target_indexes": 0,
        "ready_other_indexes": 0,
        "target_vector_dimensions": [],
    }
    if not report["index_file_present"]:
        return report
    try:
        connection = sqlite3.connect(config.index_path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            connection.execute("PRAGMA query_only=ON")
            rows = connection.execute(
                "SELECT vector_dimension, count(*) FROM retrieval_indexes "
                "WHERE embedding_model=? AND status='ready' GROUP BY vector_dimension",
                (config.embedding_model,),
            ).fetchall()
            if any(type(row[0]) is not int or row[0] < 1 for row in rows):
                report["status"] = "index_inspection_failed"
                return report
            report["ready_target_indexes"] = sum(row[1] for row in rows)
            report["target_vector_dimensions"] = sorted({row[0] for row in rows})
            report["ready_other_indexes"] = connection.execute(
                "SELECT count(*) FROM retrieval_indexes "
                "WHERE embedding_model!=? AND status='ready'",
                (config.embedding_model,),
            ).fetchone()[0]
        finally:
            connection.close()
    except (OSError, sqlite3.Error):
        report["status"] = "index_inspection_failed"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file", type=Path, help="Explicit private env file; otherwise process env"
    )
    parser.add_argument(
        "--embedding-model", choices=SILICONFLOW_EMBEDDING_MODELS, default="BAAI/bge-m3"
    )
    parser.add_argument(
        "--reranker-model", choices=SILICONFLOW_RERANKER_MODELS, default="BAAI/bge-reranker-v2-m3"
    )
    args = parser.parse_args()
    try:
        if args.env_file is not None and not args.env_file.is_file():
            raise ValueError("env file unavailable")
        report = inspect_switch(
            Settings(_env_file=args.env_file),
            embedding_model=args.embedding_model,
            reranker_model=args.reranker_model,
        )
    except (OSError, UnicodeError, ValueError, SettingsError):
        # Validation and source errors may contain private env values; never echo them.
        report = {"status": "configuration_invalid", "provider_verification": "not_performed"}
    print(json.dumps(report))
    return 0 if report["status"] == "configuration_valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
