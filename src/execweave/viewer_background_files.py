"""Collapse known Python cache files without deleting or inventing evidence."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any

CACHE_FILES_NODE_ID = "viewer-cluster:python-cache-files"


def file_path(node: dict[str, Any]) -> str:
    attributes = node.get("attributes")
    attributes = attributes if isinstance(attributes, dict) else {}
    value = attributes.get("path")
    if isinstance(value, str) and value:
        return value
    node_id = str(node.get("id") or "")
    if node_id.startswith(("file:", "directory:")):
        return node_id.split(":", 1)[1]
    return str(node.get("name") or "")


def is_python_cache(node: dict[str, Any]) -> bool:
    if node.get("type") not in {"file", "directory"}:
        return False
    path = file_path(node).replace("\\", "/")
    parts = path.lower().split("/")
    return "__pycache__" in parts or parts[-1].endswith((".pyc", ".pyo"))


def collapse_python_cache_files(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]], root_id: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None]:
    members = [node for node in nodes if is_python_cache(node) and isinstance(node.get("id"), str)]
    if len(members) < 3:
        return nodes, edges, None
    ids = {node["id"] for node in members}
    incident = [edge for edge in edges if edge.get("source") in ids or edge.get("target") in ids]
    entries = [{
        "id": n["id"], "type": n.get("type"), "path": file_path(n),
        "first_seen": n.get("first_seen"), "last_seen": n.get("last_seen"),
        "event_count": n.get("event_count", 0),
    } for n in sorted(members, key=lambda item: str(item.get("name") or item["id"]))]
    cluster = {
        "id": CACHE_FILES_NODE_ID, "type": "file_cluster", "name": f"Python cache · {len(members)} files",
        "attributes": {"viewer_only": True, "collapsed": True, "expandable": True,
                       "reason": "python_cache_paths", "member_count": len(members), "entries": entries},
        "first_seen": min((n["first_seen"] for n in members if n.get("first_seen")), default=None),
        "last_seen": max((n["last_seen"] for n in members if n.get("last_seen")), default=None),
        "event_count": sum(int(n.get("event_count") or 0) for n in members),
    }
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    out_edges = []
    for edge in edges:
        source, target = edge.get("source"), edge.get("target")
        if source not in ids and target not in ids:
            out_edges.append(deepcopy(edge))
            continue
        source = CACHE_FILES_NODE_ID if source in ids else source
        target = CACHE_FILES_NODE_ID if target in ids else target
        if source != target:
            grouped[(source, str(edge.get("relation") or ""), target)].append(edge)
    for (source, relation, target), observations in grouped.items():
        value = deepcopy(observations[0])
        value.update({
            "id": f"viewer:{source}--{relation}-->{target}", "source": source, "target": target,
            "viewer_only": True, "count": sum(int(e.get("count") or 0) for e in observations),
            "event_ids": list(dict.fromkeys(i for e in observations for i in (e.get("event_ids") or []))),
            "viewer_occurrences": deepcopy(observations),
            "first_seen": min((e["first_seen"] for e in observations if e.get("first_seen")), default=None),
            "last_seen": max((e["last_seen"] for e in observations if e.get("last_seen")), default=None),
        })
        # A display aggregate must not promote a mixed evidence set to certainty.
        for field in ("causal", "inferred", "identity_exact"):
            values = {e.get(field) for e in observations}
            value[field] = next(iter(values)) if len(values) == 1 else None
        out_edges.append(value)
    display_edge = None
    if not grouped and root_id:
        display_edge = f"viewer:{root_id}--OBSERVED_FILES-->{CACHE_FILES_NODE_ID}"
        out_edges.append({"id": display_edge, "source": root_id, "target": CACHE_FILES_NODE_ID,
                          "relation": "OBSERVED_FILES", "viewer_only": True,
                          "causal": False, "inferred": False, "count": len(members)})
    expansion = {"cluster_node_id": CACHE_FILES_NODE_ID, "cluster_edge_id": display_edge,
                 "nodes": deepcopy(members), "edges": deepcopy(incident), "viewer_only": True}
    return [deepcopy(n) for n in nodes if n.get("id") not in ids] + [cluster], out_edges, expansion
