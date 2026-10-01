"""Explicit offline SQLite import with consistent backup; never consults production Settings."""

import argparse
import json
import sqlite3
from pathlib import Path

from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.adapters.sqlite.frontier_repository import SqliteFrontierStore
from qunxue_api.json_shards import load_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--backup", required=True, type=Path)
    args = parser.parse_args()
    target = args.database.resolve()
    backup = args.backup.resolve()
    if not target.is_file():
        parser.error("Migrate a designated SQLite file first; importer never creates schema")
    if target == backup or backup.exists():
        parser.error("Backup must be a fresh distinct path")
    backup.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target) as src, sqlite3.connect(backup) as dst:
        src.backup(dst)
    db = Database("sqlite:///" + str(target))
    store = SqliteFrontierStore(db)
    try:
        result = store.import_seed(load_json(args.corpus))
        # Pending metadata remains an inert review task, never a published frontier record.
        pending = []
        if args.audit:
            pending = json.loads(args.audit.read_text()).get("pending", [])
            for entry in pending:
                raw = entry["original_source_record"]
                identity = raw.get("id") or raw.get("url")
                store.queue_manual_review(identity, "closeout-review:" + identity, entry)
        records = store.list_records()
        print(
            json.dumps(
                {
                    "import": result,
                    "research_unique": len(
                        {
                            r["canonical_study_id"]
                            for r in records
                            if r["material_type"] != "official_practice"
                        }
                    ),
                    "practice_records": sum(
                        r["material_type"] == "official_practice" for r in records
                    ),
                    "pending_manual_reviews": len(pending),
                    "database": str(target),
                    "backup": str(backup),
                },
                ensure_ascii=False,
            )
        )
    finally:
        db.engine.dispose()


if __name__ == "__main__":
    main()
