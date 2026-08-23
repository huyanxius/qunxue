"""Install one human pre-reviewed theory bundle as an immutable MATCH release."""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.adapters.sqlite.knowledge_catalog import SqliteKnowledgeCatalog
from qunxue_api.modules.knowledge_catalog import KnowledgeUsePurpose
from qunxue_api.settings import KNOWLEDGE_ROOT, Settings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a pre-reviewed-theory-release/v1 bundle and install its exact "
            "contents as the current immutable final MATCH knowledge release for "
            "internal testing. This does not claim expert final review."
        )
    )
    parser.add_argument(
        "bundle",
        type=Path,
        help="Path to the recorded human pre-review bundle.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    settings = Settings()
    database = Database(settings.database_url)
    try:
        catalog = SqliteKnowledgeCatalog(database, knowledge_root=KNOWLEDGE_ROOT)
        # A clean migrated database has no rows until this deterministic base is built.
        catalog.current_release(purpose=KnowledgeUsePurpose.BROWSE)
        manifest = catalog.install_pre_reviewed_bundle(arguments.bundle.resolve())
    except (OSError, SQLAlchemyError, ValueError) as error:
        parser.error(str(error))
    finally:
        database.engine.dispose()

    print(
        json.dumps(
            {
                "knowledge_release_id": manifest.release.knowledge_release_id,
                "level": manifest.release.level.value,
                "content_hash": manifest.release.content_hash,
                "theory_ids": list(manifest.theory_ids),
                "review_record_ids": list(manifest.review_record_ids),
                "artifact_hashes": dict(manifest.artifact_hashes),
                "built_at": manifest.built_at.isoformat(),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
