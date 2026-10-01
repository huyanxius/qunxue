"""Split a private runtime corpus into public metadata with identity/hash reconciliation."""

import argparse
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

from qunxue_api.api.contracts.frontier import FrontierRecordResponse
from qunxue_api.json_shards import load_json

spec = importlib.util.spec_from_file_location(
    "normalizer", Path(__file__).with_name("normalize_inputs.py")
)
normalizer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(normalizer)
SAFE = set(FrontierRecordResponse.model_fields) | {
    "external_id",
    "source_scope",
    "stream",
    "display_ready",
    "origin_source_id",
    "discovered_at",
    "full_text_verified",
    "human_full_text_reviewed",
    "keywords",
    "topics_source",
    "source_aliases",
    "reading_note_basis_sha256",
    "reading_note_review_type",
    "source_hash_scope",
    "source_content_hash",
    "source_text_hash",
    "source_date_precision",
}


def export(source: Path, audit: Path, private: Path, public: Path):
    payload = load_json(source)
    original_audit = json.loads(audit.read_text())
    normalizer.write_shards(private / "frontier-closeout.json", payload)
    (private / "frontier-closeout-audit.json").write_text(
        json.dumps(original_audit, ensure_ascii=False, indent=2) + "\n"
    )
    safe = deepcopy(payload)
    for row in safe["records"]:
        original = deepcopy(row)
        row.clear()
        row.update({key: value for key, value in original.items() if key in SAFE})
        row["private_source_record_sha256"] = normalizer.sha(
            normalizer.canonical_json(original)
        )
        row["evidence"] = [
            {
                key: value
                for key, value in item.items()
                if key in {"url", "locator", "supports", "block_id"}
            }
            for item in original.get("evidence", [])
        ]
    normalizer.write_shards(public / "frontier-closeout.json", safe)
    public_audit = {
        key: value
        for key, value in original_audit.items()
        if key not in {"pending", "source_inputs"}
    }
    public_audit["pending"] = [
        {key: value for key, value in item.items() if key != "original_source_record"}
        | {
            "source_record_sha256": normalizer.sha(
                normalizer.canonical_json(item["original_source_record"])
            )
        }
        for item in original_audit["pending"]
    ]
    public_audit["source_inputs"] = [
        {key: value for key, value in item.items() if key not in {"path", "file"}}
        for item in original_audit.get("source_inputs", [])
    ]

    def scrub(value):
        if isinstance(value, list):
            return [scrub(item) for item in value]
        if isinstance(value, dict):
            result = {
                key: scrub(item)
                for key, item in value.items()
                if key
                not in {
                    "original_source_record",
                    "internal_source_content",
                    "abstract",
                    "abstract_excerpt",
                    "abstract_en",
                    "raw_response",
                    "path",
                    "file",
                }
            }
            if "original_source_record" in value:
                result["source_record_sha256"] = normalizer.sha(
                    normalizer.canonical_json(value["original_source_record"])
                )
            return result
        return value

    public_audit = scrub(public_audit)
    public_audit["private_runtime_canonical_sha256"] = normalizer.sha(
        normalizer.canonical_json(payload)
    )
    public_audit["canonical_sha256"] = normalizer.sha(normalizer.canonical_json(safe))
    (public / "frontier-closeout-audit.json").write_text(
        json.dumps(public_audit, ensure_ascii=False, indent=2) + "\n"
    )
    identities = lambda value: sorted(
        (r["id"], r["canonical_study_id"], r["source_id"]) for r in value["records"]
    )
    assert identities(payload) == identities(safe)
    proof = {
        "record_variants": len(payload["records"]),
        "research_unique": original_audit["research_unique"],
        "practice_count": original_audit["practice_count"],
        "identity_manifest_sha256": normalizer.sha(
            normalizer.canonical_json(identities(payload))
        ),
        "private_runtime_canonical_sha256": public_audit[
            "private_runtime_canonical_sha256"
        ],
        "public_canonical_sha256": public_audit["canonical_sha256"],
    }
    (private / "reconciliation.json").write_text(json.dumps(proof, indent=2) + "\n")
    (public / "frontier-closeout-reconciliation.json").write_text(
        json.dumps(proof, indent=2) + "\n"
    )
    print(json.dumps(proof))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("audit", type=Path)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--public", type=Path, required=True)
    args = parser.parse_args()
    export(args.source, args.audit, args.private, args.public)
