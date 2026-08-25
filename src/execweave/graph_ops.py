from __future__ import annotations

import json
from collections import Counter, deque
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable


def load_graph(path: str | Path) -> dict[str, Any]:
    graph_path = Path(path).expanduser().resolve()
    try:
        payload = json.loads(graph_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"graph does not exist: {graph_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"graph is not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("graph root must be a JSON object")
    if not isinstance(payload.get("nodes"), list) or not isinstance(payload.get("edges"), list):
        raise ValueError("graph must contain nodes and edges arrays")
    return payload


def graph_summary(graph: dict[str, Any]) -> dict[str, Any]:
    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
    edges = [edge for edge in graph.get("edges", []) if isinstance(edge, dict)]
    node_types = Counter(
        node.get("type") for node in nodes if isinstance(node.get("type"), str)
    )
    relations = Counter(
        edge.get("relation") for edge in edges if isinstance(edge.get("relation"), str)
    )
    causal_edges = sum(1 for edge in edges if edge.get("causal") is True)
    noncausal_edges = sum(1 for edge in edges if edge.get("causal") is False)
    mixed_edges = len(edges) - causal_edges - noncausal_edges
    return {
        "session_id": graph.get("session_id"),
        "event_count": graph.get("event_count"),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_types": dict(sorted(node_types.items())),
        "relations": dict(sorted(relations.items())),
        "causal_edges": causal_edges,
        "noncausal_edges": noncausal_edges,
        "mixed_or_unknown_causal_edges": mixed_edges,
    }


def filter_graph(
    graph: dict[str, Any],
    *,
    node_types: Iterable[str] = (),
    relations: Iterable[str] = (),
    causal_only: bool = False,
    backends: Iterable[str] = (),
) -> dict[str, Any]:
    requested_node_types = set(node_types)
    requested_relations = set(relations)
    requested_backends = set(backends)

    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
    edges = [edge for edge in graph.get("edges", []) if isinstance(edge, dict)]

    if requested_node_types:
        selected_nodes = {
            node.get("id")
            for node in nodes
            if node.get("type") in requested_node_types and isinstance(node.get("id"), str)
        }
    else:
        selected_nodes = {
            node.get("id") for node in nodes if isinstance(node.get("id"), str)
        }

    filtered_edges: list[dict[str, Any]] = []
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source not in selected_nodes or target not in selected_nodes:
            continue
        if requested_relations and edge.get("relation") not in requested_relations:
            continue
        if causal_only and edge.get("causal") is not True:
            continue
        edge_backends = set(edge.get("backends") or [])
        if requested_backends and not requested_backends.intersection(edge_backends):
            continue
        filtered_edges.append(deepcopy(edge))

    connected_nodes: set[str] = set()
    for edge in filtered_edges:
        source = edge.get("source")
        target = edge.get("target")
        if isinstance(source, str):
            connected_nodes.add(source)
        if isinstance(target, str):
            connected_nodes.add(target)

    # Preserve isolated nodes only when the caller explicitly selected a node type.
    keep_nodes = selected_nodes if requested_node_types else connected_nodes
    filtered_nodes = [
        deepcopy(node)
        for node in nodes
        if isinstance(node.get("id"), str) and node.get("id") in keep_nodes
    ]

    payload = deepcopy(graph)
    payload["nodes"] = filtered_nodes
    payload["edges"] = filtered_edges
    payload["node_count"] = len(filtered_nodes)
    payload["edge_count"] = len(filtered_edges)
    payload["filter"] = {
        "node_types": sorted(requested_node_types),
        "relations": sorted(requested_relations),
        "causal_only": causal_only,
        "backends": sorted(requested_backends),
    }
    return payload


def find_paths(
    graph: dict[str, Any],
    *,
    source: str,
    target: str,
    max_depth: int = 6,
    max_paths: int = 20,
    relations: Iterable[str] = (),
    causal_only: bool = False,
) -> list[dict[str, Any]]:
    if max_depth < 1:
        raise ValueError("max_depth must be >= 1")
    if max_paths < 1:
        raise ValueError("max_paths must be >= 1")

    nodes = {
        node.get("id"): node
        for node in graph.get("nodes", [])
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }
    if source not in nodes:
        raise ValueError(f"source node not found: {source}")
    if target not in nodes:
        raise ValueError(f"target node not found: {target}")

    requested_relations = set(relations)
    adjacency: dict[str, list[dict[str, Any]]] = {}
    for edge in graph.get("edges", []):
        if not isinstance(edge, dict):
            continue
        if requested_relations and edge.get("relation") not in requested_relations:
            continue
        if causal_only and edge.get("causal") is not True:
            continue
        edge_source = edge.get("source")
        edge_target = edge.get("target")
        if not isinstance(edge_source, str) or not isinstance(edge_target, str):
            continue
        adjacency.setdefault(edge_source, []).append(edge)

    queue: deque[tuple[str, list[str], list[dict[str, Any]]]] = deque()
    queue.append((source, [source], []))
    results: list[dict[str, Any]] = []

    while queue and len(results) < max_paths:
        current, node_path, edge_path = queue.popleft()
        if len(edge_path) >= max_depth:
            continue
        for edge in adjacency.get(current, []):
            next_node = edge["target"]
            if next_node in node_path:
                continue
            next_nodes = [*node_path, next_node]
            next_edges = [*edge_path, edge]
            if next_node == target:
                results.append(
                    {
                        "nodes": next_nodes,
                        "relations": [item.get("relation") for item in next_edges],
                        "edges": deepcopy(next_edges),
                    }
                )
                if len(results) >= max_paths:
                    break
                continue
            queue.append((next_node, next_nodes, next_edges))

    return results
