from collections.abc import Mapping

from .errors import AgentConversationError, ConversationNotFound


class CanvasEditConflict(AgentConversationError):
    """A researcher is editing an older card snapshot."""


def apply_canvas_edits(research_map: dict, edits: Mapping[str, dict]) -> dict:
    # 用户文字优先；只有明确核对过同一版本文字的 Agent 才能更新证据状态。
    nodes = {node["id"]: node for node in research_map.get("nodes", [])}
    relations = {edge["id"]: edge for edge in research_map.get("relations", [])}
    for node_id, edit in edits.items():
        current = nodes.get(node_id)
        snapshot = {key: value for key, value in edit.items() if not key.startswith("_")}
        if current is None:
            for edge in edit.get("_relations", []):
                relations.setdefault(edge["id"], edge)
        elif (
            current.get("reviewed_user_version") == edit.get("user_edit_version")
            and current.get("reviewed_user_title") == edit["title"]
            and (current.get("reviewed_user_summary") or "") == (edit.get("summary") or "")
        ):
            snapshot.update({key: current[key] for key in ("citation_ids", "status")})
        nodes[node_id] = {**snapshot, "user_edited": True}
    return {
        **research_map,
        "nodes": list(nodes.values()),
        "relations": [
            edge
            for edge in relations.values()
            if edge["source"] in nodes and edge["target"] in nodes
        ],
    }


def prepare_canvas_edit(
    research_map: dict,
    *,
    node_id: str,
    title: str,
    summary: str,
    expected_title: str,
    expected_summary: str | None,
) -> dict:
    node = next((node for node in research_map.get("nodes", []) if node["id"] == node_id), None)
    if node is None:
        raise ConversationNotFound(node_id)
    if node["title"] != expected_title or (node.get("summary") or "") != (expected_summary or ""):
        raise CanvasEditConflict("卡片已经更新，请重新载入后再保存。")
    if not title.strip() or len(title.strip()) > 240 or len(summary.strip()) > 1200:
        raise ValueError("卡片标题需为 1–240 字，说明不能超过 1200 字。")
    return {
        **{key: value for key, value in node.items() if not key.startswith("reviewed_user_")},
        "_patch_count": research_map.get("_patch_count", 0),
        "_relations": [
            edge
            for edge in research_map.get("relations", [])
            if node_id in (edge["source"], edge["target"])
        ],
        "title": title.strip(),
        "summary": summary.strip(),
        "status": "open" if node["kind"] == "gap" else "developing",
    }
