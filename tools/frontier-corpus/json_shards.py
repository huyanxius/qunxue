"""Load plain JSON or integrity-checked local JSON shards (no network)."""

import hashlib
import json
from pathlib import Path


def load_json(path):
    path = Path(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("$format") != "qunxue-json-shards-v1":
        return value
    kind = value["kind"]
    if kind not in ("array", "mapping", "records"):
        raise ValueError("Unknown JSON shard kind")
    items = []
    seen = set()
    for part in value["parts"]:
        relative = Path(part["path"])
        resolved = (path.parent / relative).resolve()
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or not resolved.is_relative_to(path.parent.resolve())
        ):
            raise ValueError("JSON shard path must stay inside its manifest directory")
        if resolved in seen:
            raise ValueError("Duplicate JSON shard")
        seen.add(resolved)
        raw = resolved.read_bytes()
        if hashlib.sha256(raw).hexdigest() != part["sha256"]:
            raise ValueError("Changed JSON shard: " + part["path"])
        rows = json.loads(raw)
        if not isinstance(rows, list) or len(rows) != part["count"]:
            raise ValueError("Invalid JSON shard count")
        items.extend(rows)
    if len(items) != value["count"]:
        raise ValueError("Invalid JSON manifest count")
    if kind == "records":
        result = dict(value["metadata"])
        result["records"] = items
    elif kind == "mapping":
        result = dict(items)
        if len(result) != len(items):
            raise ValueError("Duplicate JSON mapping keys")
    else:
        result = items
    canonical = json.dumps(
        result, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    if hashlib.sha256(canonical).hexdigest() != value["canonical_sha256"]:
        raise ValueError("Changed assembled JSON data")
    return result
