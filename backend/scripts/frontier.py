"""Explicit offline import and worker operations. Does not initiate source crawling."""

import argparse
import json
from pathlib import Path

from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.adapters.sqlite.frontier_repository import SqliteFrontierStore
from qunxue_api.bootstrap import create_frontier_worker
from qunxue_api.json_shards import load_json
from qunxue_api.settings import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    importer = commands.add_parser("import")
    importer.add_argument("path", type=Path)
    briefs = commands.add_parser("briefs")
    briefs.add_argument("path", type=Path)
    overview = commands.add_parser("overview")
    overview.add_argument("path", type=Path)
    queue = commands.add_parser("enqueue")
    queue.add_argument(
        "stage", choices=["DISCOVER", "FETCH", "PARSE", "EXTRACT", "VERIFY", "INDEX", "TREND"]
    )
    queue.add_argument("object_id")
    queue.add_argument("--key", required=True)
    replay = commands.add_parser("replay")
    replay.add_argument("path", type=Path)
    commands.add_parser("schedule")
    withdrawal = commands.add_parser("withdraw")
    withdrawal.add_argument("record_id")
    commands.add_parser("status")
    commands.add_parser("resume-blocked")
    worker = commands.add_parser("worker")
    worker.add_argument("--max-jobs", type=int, default=100)
    args = parser.parse_args()
    settings = Settings()
    database = Database(settings.database_url)
    store = SqliteFrontierStore(database)
    try:
        if args.command == "import":
            result = store.import_seed(load_json(args.path))
        elif args.command == "briefs":
            result = {"saved": store.import_briefs(load_json(args.path)["briefs"])}
        elif args.command == "overview":
            result = store.import_corpus_overview(load_json(args.path))
        elif args.command == "enqueue":
            result = {"job_id": store.enqueue(args.stage, args.object_id, args.key)}
        elif args.command == "resume-blocked":
            result = {"resumed": store.resume_blocked()}
        elif args.command == "withdraw":
            result = {"withdrawn": store.withdraw(args.record_id)}
        elif args.command == "schedule":
            from time import time

            result = {"enqueued": store.schedule_sources(now=time())}
        elif args.command == "replay":
            from qunxue_api.modules.frontier_knowledge import content_hash

            corpus = load_json(args.path)
            store.configure_sources()
            worker_instance = create_frontier_worker(settings, store, corpus)
            for source in store.list_sources():
                store.enqueue(
                    "DISCOVER",
                    source["source_id"],
                    f"replay:{source['source_id']}:{content_hash(corpus)}",
                    {"cursor": source["cursor"]},
                )
            count = 0
            while count < 10000 and worker_instance.run_once():
                count += 1
            result = {
                "processed": count,
                "records": len(store.list_records()),
                "jobs": store.list_jobs(),
            }
        elif args.command == "worker":
            if not 1 <= args.max_jobs <= 10000:
                parser.error("--max-jobs must be 1..10000")
            worker_instance = create_frontier_worker(settings, store)
            count = 0
            while count < args.max_jobs and worker_instance.run_once():
                count += 1
            result = {"processed": count, "jobs": store.list_jobs()}
        else:
            result = {
                "sources": store.list_sources(),
                "jobs": store.list_jobs(),
                "reviews": store.list_reviews(),
                "records": len(store.list_records()),
            }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        database.engine.dispose()


if __name__ == "__main__":
    main()
