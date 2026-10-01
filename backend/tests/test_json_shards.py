import json
import shutil
from pathlib import Path

import pytest

from qunxue_api.json_shards import load_json


@pytest.fixture
def packaged(tmp_path):
    data = Path(__file__).parents[1] / "data"
    shutil.copy(data / "frontier-corpus.json", tmp_path)
    shutil.copytree(data / "frontier-corpus.parts", tmp_path / "frontier-corpus.parts")
    return tmp_path / "frontier-corpus.json"


def test_complete_corpus(packaged):
    value = load_json(packaged)
    assert len(value["records"]) == 276
    assert sum(r["stream"] == "research" for r in value["records"]) == 273


@pytest.mark.parametrize(
    "mutation", ["missing", "changed", "count", "duplicate", "escape", "absolute", "symlink"]
)
def test_reject_bad_shards(packaged, mutation):
    manifest = json.loads(packaged.read_text())
    part = manifest["parts"][0]
    shard = packaged.parent / part["path"]
    if mutation == "missing":
        shard.unlink()
    elif mutation == "changed":
        shard.write_bytes(shard.read_bytes() + b"\n")
    elif mutation == "count":
        part["count"] += 1
    elif mutation == "duplicate":
        manifest["parts"].append(part)
    elif mutation == "escape":
        part["path"] = "../outside.json"
    elif mutation == "absolute":
        part["path"] = str(shard)
    else:
        outside = packaged.parent.parent / "outside.json"
        outside.write_bytes(shard.read_bytes())
        shard.unlink()
        shard.symlink_to(outside)
    packaged.write_text(json.dumps(manifest))
    with pytest.raises((ValueError, FileNotFoundError)):
        load_json(packaged)


def test_plain_json(tmp_path):
    path = tmp_path / "plain.json"
    path.write_text('{"records": [1]}')
    assert load_json(path) == {"records": [1]}
