import json
import os
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from fastapi.testclient import TestClient
from sqlalchemy import update
from test_pre_reviewed_theory_release import _write_bundle

from qunxue_api.adapters.retrieval import SqliteRetrievalIndex
from qunxue_api.adapters.sqlite.knowledge_catalog_model import KnowledgeEntryRevisionRow
from qunxue_api.modules.knowledge_catalog import KnowledgeUsePurpose


def test_cli_builds_the_explicit_release_with_the_real_embedding_http_adapter(
    client: TestClient,
    tmp_path: Path,
) -> None:
    catalog = client.app.state.knowledge_catalog
    preview = catalog.current_release(purpose=KnowledgeUsePurpose.BROWSE)
    first_bundle = _write_bundle(
        tmp_path / "first-pre-reviewed-theories.json",
        base_release_id=preview.knowledge_release_id,
    )
    first_release = catalog.install_pre_reviewed_bundle(first_bundle).release
    second_bundle = tmp_path / "second-pre-reviewed-theories.json"
    second_payload = json.loads(first_bundle.read_text(encoding="utf-8"))
    second_payload["release_key"] = "pre-reviewed-theories-test-v2"
    second_bundle.write_text(
        json.dumps(second_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    second_release = catalog.install_pre_reviewed_bundle(second_bundle).release
    assert second_release != first_release
    assert catalog.current_release(purpose=KnowledgeUsePurpose.MATCH) == second_release
    with client.app.state.database.session() as session:
        session.execute(
            update(KnowledgeEntryRevisionRow)
            .where(
                KnowledgeEntryRevisionRow.knowledge_release_id
                == first_release.knowledge_release_id,
                KnowledgeEntryRevisionRow.knowledge_id == "D1:C001",
            )
            .values(rag_eligible=False)
        )
    published_entry_count = catalog.browse(
        release_id=first_release.knowledge_release_id,
        query=None,
        category=None,
        category_id=None,
        dimension_id=None,
        cursor=None,
        limit=1,
    ).total_count

    index_path = tmp_path / "retrieval.db"
    with _embedding_service() as base_url:
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).parents[1] / "scripts/build_retrieval_index.py"),
                first_release.knowledge_release_id,
            ],
            cwd=Path(__file__).parents[1],
            env={
                **os.environ,
                "QUNXUE_DATABASE_URL": client.app.state.settings.database_url,
                "QUNXUE_RETRIEVAL_INDEX_PATH": str(index_path),
                "QUNXUE_RETRIEVAL_EMBEDDING_BATCH_SIZE": "2",
                "QUNXUE_EMBEDDING_BASE_URL": base_url,
                "QUNXUE_EMBEDDING_API_KEY": "embedding-test-key",
                "QUNXUE_EMBEDDING_MODEL": "Pro/BAAI/bge-m3",
                "QUNXUE_RERANKER_BASE_URL": base_url,
                "QUNXUE_RERANKER_API_KEY": "reranker-test-key",
                "QUNXUE_RERANKER_MODEL": "Pro/BAAI/bge-reranker-v2-m3",
            },
            check=False,
            capture_output=True,
            text=True,
        )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["knowledge_release_id"] == first_release.knowledge_release_id
    assert payload["release_content_hash"] == first_release.content_hash
    assert payload["embedding_model"] == "Pro/BAAI/bge-m3"
    assert payload["chunk_schema_version"] == "retrieval-corpus-v1"
    assert payload["point_count"] >= published_entry_count + 3
    assert payload["knowledge_entry_count"] == published_entry_count
    assert payload["theory_profile_count"] == 3

    index = SqliteRetrievalIndex(index_path)
    chunks = index.list_chunks(
        retrieval_index_id=payload["retrieval_index_id"],
        knowledge_release_id=first_release.knowledge_release_id,
        document_kind=None,
    )
    assert [
        chunk.chunk_id
        for chunk in chunks
        if chunk.document_kind == "knowledge_entry" and chunk.knowledge_id == "D1:C001"
    ] == [
        "knowledge-entry:D1:C001:v1:0",
        "knowledge-entry:D1:C001:v1:1",
    ]
    assert [chunk.theory_id for chunk in chunks if chunk.document_kind == "theory_profile"] == [
        "theory-pre-reviewed-1",
        "theory-pre-reviewed-2",
        "theory-pre-reviewed-3",
    ]


@contextmanager
def _embedding_service() -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if (
                self.path != "/v1/embeddings"
                or self.headers.get("Authorization") != "Bearer embedding-test-key"
                or body.get("model") != "Pro/BAAI/bge-m3"
                or not isinstance(body.get("input"), list)
            ):
                self.send_error(400)
                return
            payload = {
                "data": [
                    {"index": index, "embedding": [float(index + 1), 1.0]}
                    for index, _text in enumerate(body["input"])
                ]
            }
            encoded = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
