"""Validated, serialisable research-map patches emitted by the Agent.

The map is an argument structure, not a transcript projection.  Keeping the
schema here gives the model tool, persistence adapter, SSE route, and browser
one narrow contract to share.
"""

import hashlib
from collections.abc import Mapping, Sequence

RESEARCH_MAP_SCHEMA_VERSION = 1
RESEARCH_NODE_KINDS = frozenset({"question", "theory", "claim", "evidence", "gap", "synthesis"})
RESEARCH_NODE_STATUSES = frozenset(
    {"developing", "grounded", "open", "verified", "challenged", "complete"}
)
RESEARCH_RELATIONS = frozenset({"explains", "supports", "challenges", "derives", "refines"})


def empty_research_map() -> dict[str, object]:
    return {"schema_version": RESEARCH_MAP_SCHEMA_VERSION, "nodes": [], "relations": []}


def normalize_research_map_patch(
    *,
    nodes: Sequence[Mapping[str, object]] | None = None,
    relations: Sequence[Mapping[str, object]] | None = None,
    remove_node_ids: Sequence[str] | None = None,
    remove_relation_ids: Sequence[str] | None = None,
    known_node_ids: set[str] | None = None,
    evidence_ids: set[str] | None = None,
) -> dict[str, object]:
    """Validate and canonicalise one additive/removal patch from the model."""

    normalized_nodes: list[dict[str, object]] = []
    node_ids: set[str] = set()
    for raw in nodes or ():
        if not isinstance(raw, Mapping):
            raise ValueError("research map node must be an object")
        node_id = _required_text_alias(raw, ("id", "node_id"), max_length=120)
        if node_id in node_ids:
            raise ValueError(f"duplicate research map node id: {node_id}")
        node_ids.add(node_id)
        kind = _required_text_alias(raw, ("kind", "node_kind"), max_length=24)
        kind = {
            "argument": "claim",
            "assertion": "claim",
            "source": "evidence",
            "synthesis_claim": "synthesis",
        }.get(kind, kind)
        if kind not in RESEARCH_NODE_KINDS:
            raise ValueError(f"invalid research map node kind: {kind}")
        title = _required_text_alias(raw, ("title", "label", "name", "content"), max_length=240)
        summary = _optional_text(
            raw.get("summary")
            if raw.get("summary") is not None
            else raw.get("description", raw.get("excerpt")),
            max_length=1200,
        )
        status = _optional_text(raw.get("status", raw.get("state")), max_length=24) or "developing"
        status = {
            "proposed": "developing",
            "draft": "developing",
            "established": "grounded",
            "supported": "grounded",
            "missing": "open",
            "disputed": "challenged",
        }.get(status, status)
        if status not in RESEARCH_NODE_STATUSES:
            raise ValueError(f"invalid research map node status: {status}")
        citations = _citation_list(
            raw.get("citation_ids", raw.get("citations", raw.get("evidence_ids")))
        )
        if evidence_ids is not None:
            canonical_citations: list[str] = []
            for citation in citations:
                if citation in evidence_ids:
                    canonical_citations.append(citation)
                    continue
                aliases = [item for item in evidence_ids if item.endswith(f":{citation}")]
                if len(aliases) == 1:
                    canonical_citations.append(aliases[0])
                    continue
                unknown = citation
                raise ValueError(f"research map citation is not current evidence: {unknown}")
            citations = canonical_citations
        normalized_nodes.append(
            {
                "id": node_id,
                "kind": kind,
                "title": title,
                "summary": summary,
                "status": status,
                "citation_ids": citations,
            }
        )

    known = set(known_node_ids or ()) | node_ids
    normalized_relations: list[dict[str, object]] = []
    relation_ids: set[str] = set()
    for raw in relations or ():
        if not isinstance(raw, Mapping):
            raise ValueError("research map relation must be an object")
        relation_id = _optional_text_alias(raw, ("id", "relation_id", "edge_id"), max_length=160)
        source = _required_text_alias(raw, ("source", "from", "source_id"), max_length=120)
        target = _required_text_alias(raw, ("target", "to", "target_id"), max_length=120)
        if source not in known:
            raise ValueError(f"research map relation source is unknown: {source}")
        if target not in known:
            raise ValueError(f"research map relation target is unknown: {target}")
        relation = _required_text_alias(raw, ("relation", "type", "kind"), max_length=24)
        relation = {"explains_mechanism": "explains", "refines_question": "refines"}.get(
            relation, relation
        )
        if relation not in RESEARCH_RELATIONS:
            raise ValueError(f"invalid research map relation: {relation}")
        if relation_id is None:
            relation_id = _generated_relation_id(source=source, target=target, relation=relation)
        if relation_id in relation_ids:
            raise ValueError(f"duplicate research map relation id: {relation_id}")
        relation_ids.add(relation_id)
        label = _optional_text(raw.get("label", raw.get("description")), max_length=120)
        normalized_relations.append(
            {
                "id": relation_id,
                "source": source,
                "target": target,
                "relation": relation,
                "label": label,
            }
        )

    remove_nodes = _string_list(remove_node_ids, "remove_node_ids", max_items=120)
    remove_relations = _string_list(remove_relation_ids, "remove_relation_ids", max_items=240)
    return {
        "schema_version": RESEARCH_MAP_SCHEMA_VERSION,
        "nodes": normalized_nodes,
        "relations": normalized_relations,
        "remove_node_ids": remove_nodes,
        "remove_relation_ids": remove_relations,
    }


def apply_research_map_patch(
    current: Mapping[str, object] | None,
    patch: Mapping[str, object],
) -> dict[str, object]:
    """Apply a validated patch while preserving stable insertion order."""

    state = empty_research_map()
    if isinstance(current, Mapping):
        state["nodes"] = [
            dict(item) for item in current.get("nodes", []) if isinstance(item, Mapping)
        ]
        state["relations"] = [
            dict(item) for item in current.get("relations", []) if isinstance(item, Mapping)
        ]
    nodes = {
        str(item["id"]): item
        for item in state["nodes"]
        if isinstance(item, Mapping) and item.get("id")
    }
    relations = {
        str(item["id"]): item
        for item in state["relations"]
        if isinstance(item, Mapping) and item.get("id")
    }
    for node_id in patch.get("remove_node_ids", []):
        nodes.pop(str(node_id), None)
    for relation_id in patch.get("remove_relation_ids", []):
        relations.pop(str(relation_id), None)
    removed_nodes = {str(item) for item in patch.get("remove_node_ids", [])}
    for raw in patch.get("nodes", []):
        if isinstance(raw, Mapping):
            nodes[str(raw["id"])] = dict(raw)
    for raw in patch.get("relations", []):
        if isinstance(raw, Mapping):
            if str(raw["source"]) in removed_nodes or str(raw["target"]) in removed_nodes:
                continue
            relations[str(raw["id"])] = dict(raw)
    valid_nodes = set(nodes)
    relations = {
        key: value
        for key, value in relations.items()
        if str(value.get("source")) in valid_nodes and str(value.get("target")) in valid_nodes
    }
    return {
        "schema_version": RESEARCH_MAP_SCHEMA_VERSION,
        "nodes": list(nodes.values()),
        "relations": list(relations.values()),
    }


def patches_from_tool_summary(
    summaries: Sequence[Mapping[str, object]] | None,
) -> tuple[dict[str, object], ...]:
    patches: list[dict[str, object]] = []
    for summary in summaries or ():
        if summary.get("tool") != "update_research_map" or summary.get("phase") != "finished":
            continue
        output = summary.get("output")
        if (
            isinstance(output, Mapping)
            and output.get("schema_version") == RESEARCH_MAP_SCHEMA_VERSION
        ):
            patches.append(dict(output))
    return tuple(patches)


def aggregate_research_map(patches: Sequence[Mapping[str, object]] | None) -> dict[str, object]:
    state = empty_research_map()
    for patch in patches or ():
        state = apply_research_map_patch(state, patch)
    return state


def _required_text(raw: Mapping[str, object], key: str, *, max_length: int) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"research map {key} is required")
    value = value.strip()
    if len(value) > max_length:
        raise ValueError(f"research map {key} is too long")
    return value


def _required_text_alias(
    raw: Mapping[str, object], keys: tuple[str, ...], *, max_length: int
) -> str:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            value = value.strip()
            if len(value) > max_length:
                raise ValueError(f"research map {key} is too long")
            return value
    raise ValueError(f"research map {keys[0]} is required")


def _optional_text_alias(
    raw: Mapping[str, object], keys: tuple[str, ...], *, max_length: int
) -> str | None:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            value = value.strip()
            if len(value) > max_length:
                raise ValueError(f"research map {key} is too long")
            return value
    return None


def _generated_relation_id(*, source: str, target: str, relation: str) -> str:
    """Give an id-less model edge a stable identity for incremental updates."""

    digest = hashlib.sha256(f"{source}\0{target}\0{relation}".encode()).hexdigest()[:20]
    return f"relation-{digest}"


def _optional_text(value: object, *, max_length: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("research map text fields must be strings")
    value = value.strip()
    if len(value) > max_length:
        raise ValueError("research map text field is too long")
    return value or None


def _string_list(value: object, key: str, *, max_items: int) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"research map {key} must be a list")
    if len(value) > max_items:
        raise ValueError(f"research map {key} has too many items")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"research map {key} must contain non-empty strings")
        item = item.strip()
        if item not in result:
            result.append(item)
    return result


def _citation_list(value: object) -> list[str]:
    """Accept the common model shapes while returning one canonical ID list."""

    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise ValueError("research map citation_ids must be a list")
    if len(value) > 16:
        raise ValueError("research map citation_ids has too many items")
    result: list[str] = []
    for item in value:
        if isinstance(item, Mapping):
            item = item.get("citation_id", item.get("id", item.get("knowledge_id")))
        if not isinstance(item, str) or not item.strip():
            raise ValueError("research map citation_ids must contain IDs")
        item = item.strip()
        if item not in result:
            result.append(item)
    return result
