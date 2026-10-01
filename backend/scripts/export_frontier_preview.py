"""Export a clearly labeled snapshot from real HTTP contracts and an isolated SQLite DB."""

import argparse
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.adapters.sqlite.frontier_repository import SqliteFrontierStore
from qunxue_api.bootstrap import create_app
from qunxue_api.json_shards import load_json
from qunxue_api.settings import Settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--briefs", type=Path)
    parser.add_argument("--overview", type=Path)
    args = parser.parse_args()
    with TemporaryDirectory(prefix="frontier-preview-") as temporary:
        url = f"sqlite:///{temporary}/preview.db"
        previous = os.environ.get("QUNXUE_DATABASE_URL")
        os.environ["QUNXUE_DATABASE_URL"] = url
        try:
            command.upgrade(Config("alembic.ini"), "head")
            db = Database(url)
            store = SqliteFrontierStore(db)
            imported = store.import_seed(load_json(args.input))
            if args.briefs:
                store.import_briefs(json.loads(args.briefs.read_text())["briefs"])
            if args.overview:
                store.import_corpus_overview(json.loads(args.overview.read_text()))
            settings = Settings(
                _env_file=None,
                database_url=url,
                memory_learning_enabled=False,
                model_api_key=None,
                model_base_url=None,
                model_name=None,
                model_fallbacks=[],
                embedding_api_key=None,
                reranker_api_key=None,
            )
            with TestClient(create_app(settings=settings, database=db)) as client:
                snapshot = {
                    "preview_only": True,
                    "origin": "isolated_sqlite_fastapi_export",
                    "import_result": imported,
                }
                all_records = []
                offset = 0
                while True:
                    response = client.get(
                        "/api/frontier/search", params={"limit": 200, "offset": offset}
                    )
                    response.raise_for_status()
                    page = response.json()
                    all_records.extend(page["items"])
                    offset = page["next_offset"]
                    if offset is None:
                        break
                snapshot["records"] = all_records
                for endpoint in ("topics", "trends", "sources", "status", "overview"):
                    response = client.get(f"/api/frontier/{endpoint}")
                    response.raise_for_status()
                    snapshot[endpoint] = response.json()
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
                print(f"Exported {len(all_records)} real stored records to {args.output}")
            db.engine.dispose()
        finally:
            if previous is None:
                os.environ.pop("QUNXUE_DATABASE_URL", None)
            else:
                os.environ["QUNXUE_DATABASE_URL"] = previous


if __name__ == "__main__":
    main()
