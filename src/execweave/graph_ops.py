from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict, deque
from copy import deepcopy
from pathlib import Path, PurePosixPath
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


def write_graph_payload(graph: dict[str, Any], path: str | Path) -> Path:
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.stat().st_size > 0:
        raise FileExistsError(f"ExecWeave graph output already exists: {output}")
    output.write_text(
        json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output


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
    expansion = graph.get("expansion")
    expansion_clusters = (
        expansion.get("clusters", {})
        if isinstance(expansion, dict) and isinstance(expansion.get("clusters"), dict)
        else {}
    )
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
        "condensed": bool(graph.get("condensed")),
        "expandable_cluster_count": len(expansion_clusters),
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


def _node_bucket(node: dict[str, Any]) -> str:
    node_id = str(node.get("id") or "")
    prefix, _, value = node_id.partition(":")
    if prefix in {"file", "directory", "executable"} and value:
        canonical = value.replace("\\", "/")
        parent = str(PurePosixPath(canonical).parent)
        return parent if parent != "." else "<relative>"
    return "<unknown>"


def _cluster_id(parts: tuple[object, ...]) -> str:
    raw = json.dumps(parts, ensure_ascii=False, separators=(",", ":"), sort_keys=False)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"cluster:{digest}"


def condense_graph(
    graph: dict[str, Any],
    *,
    threshold: int = 8,
    sample_size: int = 8,
    collapsible_types: Iterable[str] = ("file", "directory", "executable"),
    include_expansion: bool = False,
) -> dict[str, Any]:
    """Collapse repetitive leaf resources while preserving runtime topology.

    By default the result stays compact. When ``include_expansion`` is true, the
    original member nodes and their incoming evidence edges are preserved under the
    top-level ``expansion.clusters`` map so a viewer can materialize them on demand.
    The expansion payload copies observed evidence; it does not infer new relations.
    """
    if threshold < 2:
        raise ValueError("threshold must be >= 2")
    if sample_size < 1:
        raise ValueError("sample_size must be >= 1")

    nodes = [deepcopy(node) for node in graph.get("nodes", []) if isinstance(node, dict)]
    edges = [deepcopy(edge) for edge in graph.get("edges", []) if isinstance(edge, dict)]
    node_by_id = {
        node["id"]: node for node in nodes if isinstance(node.get("id"), str)
    }
    incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if isinstance(source, str):
            outgoing[source].append(edge)
        if isinstance(target, str):
            incoming[target].append(edge)

    allowed_types = set(collapsible_types)
    groups: dict[tuple[object, ...], list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for node_id, node in node_by_id.items():
        node_type = node.get("type")
        if node_type not in allowed_types:
            continue
        if outgoing.get(node_id) or len(incoming.get(node_id, [])) != 1:
            continue
        edge = incoming[node_id][0]
        source = edge.get("source")
        relation = edge.get("relation")
        if not isinstance(source, str) or not isinstance(relation, str):
            continue
        key = (
            source,
            relation,
            node_type,
            _node_bucket(node),
            edge.get("causal"),
            tuple(sorted(str(item) for item in (edge.get("backends") or []))),
        )
        groups[key].append((node, edge))

    collapsed_node_ids: set[str] = set()
    collapsed_edge_ids: set[str] = set()
    cluster_nodes: list[dict[str, Any]] = []
    cluster_edges: list[dict[str, Any]] = []
    expansion_clusters: dict[str, dict[str, Any]] = {}
    collapsed_groups = 0

    for key, members in groups.items():
        if len(members) < threshold:
            continue
        collapsed_groups += 1
        source, relation, node_type, bucket, causal, backends = key
        cluster_id = _cluster_id(key)
        member_nodes = [node for node, _ in members]
        member_edges = [edge for _, edge in members]
        collapsed_node_ids.update(
            node["id"] for node in member_nodes if isinstance(node.get("id"), str)
        )
        collapsed_edge_ids.update(
            edge["id"] for edge in member_edges if isinstance(edge.get("id"), str)
        )

        names = [
            str(node.get("name") or node.get("id"))
            for node in member_nodes
            if node.get("name") or node.get("id")
        ]
        first_seen_values = [
            node.get("first_seen") for node in member_nodes if isinstance(node.get("first_seen"), str)
        ]
        last_seen_values = [
            node.get("last_seen") for node in member_nodes if isinstance(node.get("last_seen"), str)
        ]
        first_seq_values = [
            edge.get("first_sequence")
            for edge in member_edges
            if isinstance(edge.get("first_sequence"), int)
        ]
        last_seq_values = [
            edge.get("last_sequence")
            for edge in member_edges
            if isinstance(edge.get("last_sequence"), int)
        ]
        event_ids = [
            str(event_id)
            for edge in member_edges
            for event_id in (edge.get("event_ids") or [])
            if isinstance(event_id, str)
        ]
        event_types = sorted(
            {
                str(event_type)
                for edge in member_edges
                for event_type in (edge.get("event_types") or [])
                if isinstance(event_type, str)
            }
        )
        attributions = sorted(
            {
                str(value)
                for edge in member_edges
                for value in (edge.get("attributions") or [])
                if isinstance(value, str)
            }
        )

        cluster_nodes.append(
            {
                "id": cluster_id,
                "type": f"{node_type}_cluster",
                "name": f"{len(member_nodes)} {node_type}s in {bucket}",
                "attributes": {
                    "collapsed": True,
                    "member_count": len(member_nodes),
                    "member_type": node_type,
                    "directory_bucket": bucket,
                    "sample_members": names[:sample_size],
                    "sample_truncated": len(names) > sample_size,
                    "expandable": include_expansion,
                },
                "first_seen": min(first_seen_values) if first_seen_values else None,
                "last_seen": max(last_seen_values) if last_seen_values else None,
                "event_count": sum(
                    int(node.get("event_count") or 0) for node in member_nodes
                ),
                "event_types": event_types,
            }
        )
        cluster_edge_id = f"{source}--{relation}-->{cluster_id}"
        cluster_edges.append(
            {
                "id": cluster_edge_id,
                "source": source,
                "target": cluster_id,
                "relation": relation,
                "count": sum(int(edge.get("count") or 0) for edge in member_edges),
                "first_seen": min(first_seen_values) if first_seen_values else None,
                "last_seen": max(last_seen_values) if last_seen_values else None,
                "first_sequence": min(first_seq_values) if first_seq_values else None,
                "last_sequence": max(last_seq_values) if last_seq_values else None,
                "event_ids": event_ids[:32],
                "event_ids_truncated": len(event_ids) > 32,
                "evidence_event_count": len(event_ids),
                "event_types": event_types,
                "backends": list(backends),
                "attributions": attributions,
                "causal": causal,
                "collapsed_member_count": len(member_nodes),
            }
        )
        if include_expansion:
            expansion_clusters[cluster_id] = {
                "cluster_node_id": cluster_id,
                "cluster_edge_id": cluster_edge_id,
                "nodes": deepcopy(member_nodes),
                "edges": deepcopy(member_edges),
            }

    condensed_nodes = [
        node for node in nodes if node.get("id") not in collapsed_node_ids
    ] + cluster_nodes
    condensed_edges = [
        edge for edge in edges if edge.get("id") not in collapsed_edge_ids
    ] + cluster_edges

    payload = deepcopy(graph)
    payload["nodes"] = sorted(
        condensed_nodes,
        key=lambda node: (str(node.get("type") or ""), str(node.get("id") or "")),
    )
    payload["edges"] = sorted(
        condensed_edges,
        key=lambda edge: (
            str(edge.get("source") or ""),
            str(edge.get("relation") or ""),
            str(edge.get("target") or ""),
        ),
    )
    payload["node_count"] = len(payload["nodes"])
    payload["edge_count"] = len(payload["edges"])
    payload["condensed"] = True
    payload["condensation"] = {
        "threshold": threshold,
        "sample_size": sample_size,
        "collapsible_types": sorted(allowed_types),
        "original_node_count": len(nodes),
        "original_edge_count": len(edges),
        "collapsed_group_count": collapsed_groups,
        "collapsed_node_count": len(collapsed_node_ids),
        "result_node_count": len(payload["nodes"]),
        "result_edge_count": len(payload["edges"]),
        "expansion_embedded": include_expansion,
    }
    if include_expansion:
        payload["expansion"] = {
            "schema_version": "0.1",
            "clusters": expansion_clusters,
        }
    else:
        payload.pop("expansion", None)
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
