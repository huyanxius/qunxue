import json
import os
import subprocess
import sys
from pathlib import Path

from qunxue_api.adapters.retrieval import RetrievalChunk, SqliteRetrievalIndex


def run_preflight(tmp_path, **overrides):
    values = {
        "EMBEDDING_BASE_URL": "https://synthetic.invalid/v1",
        "EMBEDDING_API_KEY": "private-synthetic-embedding",
        "EMBEDDING_MODEL": "Pro/BAAI/bge-m3",
        "RERANKER_BASE_URL": "https://synthetic.invalid/v1",
        "RERANKER_API_KEY": "private-synthetic-reranker",
        "RERANKER_MODEL": "Pro/BAAI/bge-reranker-v2-m3",
        "RETRIEVAL_INDEX_PATH": str(tmp_path / "retrieval.db"),
        **overrides,
    }
    prefix = "QUNXUE"  # Each repository uses its own namespace.
    env_file = tmp_path / "runtime.env"
    env_file.write_text("\n".join(f"{prefix}_{name}={value}" for name, value in values.items()))
    before = env_file.read_bytes()
    result = subprocess.run(
        [sys.executable, "-m", "qunxue_api.retrieval_preflight", "--env-file", str(env_file)],
        env={
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": str(Path(__file__).parents[1] / "src"),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert env_file.read_bytes() == before
    assert "private-synthetic" not in result.stdout + result.stderr
    return result


def test_preflight_previews_free_configuration_without_creating_an_index(tmp_path):
    result = run_preflight(tmp_path)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "configuration_valid"
    assert report["embedding_model"] == "BAAI/bge-m3"
    assert report["reranker_model"] == "BAAI/bge-reranker-v2-m3"
    assert report["provider_verification"] == "not_performed"
    assert report["index_file_present"] is False
    assert not (tmp_path / "retrieval.db").exists()


def test_preflight_does_not_count_a_pro_manifest_as_a_free_manifest(tmp_path):
    path = tmp_path / "retrieval.db"
    index = SqliteRetrievalIndex(path)
    index.rebuild(
        knowledge_release_id="synthetic-release",
        release_content_hash="synthetic-hash",
        embedding_model="Pro/BAAI/bge-m3",
        chunk_schema_version="synthetic-v1",
        chunks=[
            RetrievalChunk(
                "synthetic",
                "personal_material",
                None,
                None,
                1,
                "synthetic-hash",
                "Synthetic",
                "Synthetic text",
                (),
            )
        ],
        vectors=[[1.0, 0.0]],
    )
    before = path.read_bytes()
    result = run_preflight(tmp_path)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["ready_target_indexes"] == 0
    assert report["ready_other_indexes"] == 1
    assert report["target_vector_dimensions"] == []
    assert path.read_bytes() == before


def test_preflight_rejects_missing_credentials_without_leaking_env_values(tmp_path):
    result = run_preflight(tmp_path, RERANKER_API_KEY="")
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "configuration_invalid"


def test_preflight_redacts_settings_validation_errors(tmp_path):
    result = run_preflight(tmp_path, EMBEDDING_TIMEOUT_SECONDS="private-synthetic-malformed")
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "configuration_invalid"


def test_preflight_reports_unreadable_index_without_raw_sqlite_errors(tmp_path):
    path = tmp_path / "retrieval.db"
    path.write_bytes(b"private-synthetic-corrupt-index")
    result = run_preflight(tmp_path)
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "index_inspection_failed"
    assert path.read_bytes() == b"private-synthetic-corrupt-index"


def test_preflight_rejects_invalid_dimension_metadata_without_echoing_it(tmp_path):
    import sqlite3

    path = tmp_path / "retrieval.db"
    index = SqliteRetrievalIndex(path)
    index.rebuild(
        knowledge_release_id="synthetic-release",
        release_content_hash="synthetic-hash",
        embedding_model="BAAI/bge-m3",
        chunk_schema_version="synthetic-v1",
        chunks=[
            RetrievalChunk(
                "synthetic",
                "personal_material",
                None,
                None,
                1,
                "synthetic-hash",
                "Synthetic",
                "Synthetic text",
                (),
            )
        ],
        vectors=[[1.0, 0.0]],
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE retrieval_indexes SET vector_dimension=?", ("private-synthetic-invalid",)
        )
    result = run_preflight(tmp_path)
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "index_inspection_failed"
