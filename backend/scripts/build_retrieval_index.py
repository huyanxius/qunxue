"""Build one SQLite retrieval index for an explicitly pinned final release."""

import argparse
import json
import sqlite3
from collections.abc import Sequence

from sqlalchemy.exc import SQLAlchemyError

from qunxue_api.adapters.research_agent.embedding import (
    EmbeddingProviderError,
    OpenAICompatibleEmbeddingProvider,
)
from qunxue_api.adapters.retrieval import (
    RETRIEVAL_CORPUS_SCHEMA_VERSION,
    PublishedReleaseCorpusCollector,
    RetrievalIndexBuilder,
    SqliteRetrievalIndex,
)
from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.adapters.sqlite.knowledge_catalog import SqliteKnowledgeCatalog
from qunxue_api.settings import KNOWLEDGE_ROOT, Settings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build the fail-closed hybrid retrieval index for one explicit immutable "
            "knowledge release. The command never selects another release."
        )
    )
    parser.add_argument(
        "release_id",
        help="Exact final knowledge_release_id to collect and index.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    settings = Settings()
    try:
        config = settings.require_retrieval_config()
    except ValueError as error:
        parser.error(str(error))

    database = Database(settings.database_url)
    try:
        catalog = SqliteKnowledgeCatalog(database, knowledge_root=KNOWLEDGE_ROOT)
        corpus = PublishedReleaseCorpusCollector(catalog=catalog).collect(
            release_id=arguments.release_id
        )
        embedder = OpenAICompatibleEmbeddingProvider(
            base_url=config.embedding_base_url,
            api_key=config.embedding_api_key.get_secret_value(),
            model=config.embedding_model,
            timeout_seconds=config.embedding_timeout_seconds,
        )
        manifest = RetrievalIndexBuilder(
            index=SqliteRetrievalIndex(config.index_path),
            embedder=embedder,
            embedding_model=config.embedding_model,
            chunk_schema_version=RETRIEVAL_CORPUS_SCHEMA_VERSION,
            batch_size=config.embedding_batch_size,
        ).build(release=corpus.release, chunks=corpus.chunks)
    except (
        EmbeddingProviderError,
        LookupError,
        OSError,
        SQLAlchemyError,
        sqlite3.Error,
        ValueError,
    ) as error:
        parser.error(str(error))
    finally:
        database.engine.dispose()

    print(
        json.dumps(
            {
                "retrieval_index_id": manifest.retrieval_index_id,
                "knowledge_release_id": manifest.knowledge_release_id,
                "release_content_hash": manifest.release_content_hash,
                "embedding_model": manifest.embedding_model,
                "chunk_schema_version": manifest.chunk_schema_version,
                "vector_dimension": manifest.vector_dimension,
                "point_count": manifest.point_count,
                "manifest_content_hash": manifest.manifest_content_hash,
                "status": manifest.status,
                "knowledge_entry_count": corpus.knowledge_entry_count,
                "theory_profile_count": corpus.theory_profile_count,
                "index_path": str(config.index_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
