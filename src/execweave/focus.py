from __future__ import annotations

from collections import defaultdict, deque
from copy import deepcopy
from typing import Any, Iterable, Literal

FocusDirection = Literal["both", "in", "out"]


def focus_graph(
    graph: dict[str, Any],
    *,
    anchors: Iterable[str],
    hops: int = 1,
    direction: FocusDirection = "both",
    relations: Iterable[str] = (),
    causal_only: bool = False,
) -> dict[str, Any]:
    """Return an evidence-preserving neighborhood around one or more graph nodes.

    Traversal only follows edges already present in the input graph. The operation
    never creates inferred edges. ``direction`` controls traversal relative to edge
    direction, while the returned payload contains the induced set of eligible edges
    between all selected nodes.
    """
    if hops < 0:
        raise ValueError("hops must be >= 0")
    if direction not in {"both", "in", "out"}:
        raise ValueError("direction must be one of: both, in, out")

    requested_anchors = list(dict.fromkeys(str(anchor) for anchor in anchors if str(anchor)))
    if not requested_anchors:
        raise ValueError("at least one anchor node ID is required")

    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
    edges = [edge for edge in graph.get("edges", []) if isinstance(edge, dict)]
    node_by_id = {
        node["id"]: node for node in nodes if isinstance(node.get("id"), str)
    }
    missing = [anchor for anchor in requested_anchors if anchor not in node_by_id]
    if missing:
        raise ValueError(f"anchor node not found: {missing[0]}")

    requested_relations = set(relations)
    eligible_edges: list[dict[str, Any]] = []
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        relation = edge.get("relation")
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        if source not in node_by_id or target not in node_by_id:
            continue
        if requested_relations and relation not in requested_relations:
            continue
        if causal_only and edge.get("causal") is not True:
            continue
        eligible_edges.append(edge)
        outgoing[source].append(edge)
        incoming[target].append(edge)

    selected: set[str] = set(requested_anchors)
    queue: deque[tuple[str, int]] = deque((anchor, 0) for anchor in requested_anchors)
    best_depth = {anchor: 0 for anchor in requested_anchors}

    while queue:
        current, depth = queue.popleft()
        if depth >= hops:
            continue

        candidates: list[tuple[str, dict[str, Any]]] = []
        if direction in {"both", "out"}:
            candidates.extend((edge["target"], edge) for edge in outgoing.get(current, []))
        if direction in {"both", "in"}:
            candidates.extend((edge["source"], edge) for edge in incoming.get(current, []))

        for neighbor, _edge in candidates:
            next_depth = depth + 1
            selected.add(neighbor)
            previous = best_depth.get(neighbor)
            if previous is None or next_depth < previous:
                best_depth[neighbor] = next_depth
                queue.append((neighbor, next_depth))

    focused_nodes = [deepcopy(node) for node in nodes if node.get("id") in selected]
    focused_edges = [
        deepcopy(edge)
        for edge in eligible_edges
        if edge.get("source") in selected and edge.get("target") in selected
    ]

    payload = deepcopy(graph)
    payload["nodes"] = focused_nodes
    payload["edges"] = focused_edges
    payload["node_count"] = len(focused_nodes)
    payload["edge_count"] = len(focused_edges)
    payload["focus"] = {
        "anchors": requested_anchors,
        "hops": hops,
        "direction": direction,
        "relations": sorted(requested_relations),
        "causal_only": causal_only,
        "source_node_count": len(nodes),
        "source_edge_count": len(edges),
    }

    expansion = payload.get("expansion")
    if isinstance(expansion, dict) and isinstance(expansion.get("clusters"), dict):
        expansion["clusters"] = {
            cluster_id: value
            for cluster_id, value in expansion["clusters"].items()
            if cluster_id in selected
        }

    return payload
