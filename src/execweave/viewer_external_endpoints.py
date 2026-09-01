from __future__ import annotations

import ipaddress
from copy import deepcopy
from typing import Any

EXTERNAL_NODE_ID = "viewer-cluster:external"


def _string_values(values: list[object]) -> list[str]:
    return sorted({value for value in values if isinstance(value, str) and value})


def endpoint_label(node: dict[str, Any]) -> str | None:
    raw = node.get("name")
    if isinstance(raw, str) and raw:
        return raw
    node_id = node.get("id")
    if isinstance(node_id, str) and node_id.startswith("endpoint:"):
        return node_id[len("endpoint:") :]
    return None


def split_host_port(raw: str) -> tuple[str, str] | None:
    host, separator, port_text = raw.rpartition(":")
    if not separator or not host or not port_text:
        return None
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    return host, port_text


def is_loopback_host(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host.lower() in {"localhost", "ip6-localhost"}
    return bool(address.is_loopback)


def is_external_network_endpoint(node: dict[str, Any]) -> bool:
    if node.get("type") != "network_endpoint":
        return False
    if node.get("id") == EXTERNAL_NODE_ID or node.get("name") == "External":
        return False
    label = endpoint_label(node)
    if not isinstance(label, str) or not label:
        return False
    split = split_host_port(label)
    host = split[0] if split is not None else label
    return not is_loopback_host(host)


def collapse_external_endpoints(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None]:
    """Fold every non-loopback IP endpoint into one viewer-only External node."""
    members = [
        node
        for node in nodes
        if isinstance(node.get("id"), str) and is_external_network_endpoint(node)
    ]
    if not members:
        return nodes, edges, None
    member_ids = {str(node["id"]) for node in members}
    member_edges = [
        edge
        for edge in edges
        if isinstance(edge, dict)
        and (edge.get("source") in member_ids or edge.get("target") in member_ids)
    ]
    endpoints: list[dict[str, Any]] = []
    for node in sorted(members, key=lambda item: str(item.get("name") or item.get("id") or "")):
        label = endpoint_label(node) or str(node.get("id"))
        endpoints.append(
            {
                "id": node.get("id"),
                "address": label,
                "first_seen": node.get("first_seen"),
                "last_seen": node.get("last_seen"),
                "event_count": int(node.get("event_count") or 0),
            }
        )
    first_seen_values = _string_values([node.get("first_seen") for node in members])
    last_seen_values = _string_values([node.get("last_seen") for node in members])
    event_types = sorted(
        {
            event_type
            for node in members
            for event_type in (node.get("event_types") or [])
            if isinstance(event_type, str) and event_type
        }
    )
    external_node = {
        "id": EXTERNAL_NODE_ID,
        "type": "network_endpoint",
        "name": "External",
        "attributes": {
            "viewer_only": True,
            "collapsed": True,
            "reason": "external_endpoints",
            "member_count": len(members),
            "member_type": "network_endpoint",
            "endpoints": endpoints,
            "viewer_occurrences": [
                {
                    "id": item["id"],
                    "name": item["address"],
                    "first_seen": item["first_seen"],
                    "last_seen": item["last_seen"],
                }
                for item in endpoints
            ],
        },
        "first_seen": min(first_seen_values) if first_seen_values else None,
        "last_seen": max(last_seen_values) if last_seen_values else None,
        "event_count": sum(int(node.get("event_count") or 0) for node in members),
        "event_types": event_types,
    }
    remapped: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        relation = edge.get("relation") or ""
        if source in member_ids:
            source = EXTERNAL_NODE_ID
        if target in member_ids:
            target = EXTERNAL_NODE_ID
        if source == target:
            continue
        if source == EXTERNAL_NODE_ID or target == EXTERNAL_NODE_ID:
            key = (str(source), str(relation), str(target))
            existing = grouped.get(key)
            if existing is None:
                grouped[key] = {
                    **deepcopy(edge),
                    "id": f"{source}--{relation}-->{target}",
                    "source": source,
                    "target": target,
                    "viewer_only": True,
                    "count": max(1, int(edge.get("count") or 0)),
                }
                continue
            existing["count"] = int(existing.get("count") or 0) + max(
                1, int(edge.get("count") or 0)
            )
            continue
        remapped.append(deepcopy(edge))
    projected_nodes = [
        deepcopy(node) for node in nodes if node.get("id") not in member_ids
    ] + [external_node]
    projected_edges = remapped + list(grouped.values())
    expansion = {
        "cluster_node_id": EXTERNAL_NODE_ID,
        "cluster_edge_id": None,
        "nodes": [deepcopy(node) for node in members],
        "edges": [deepcopy(edge) for edge in member_edges],
        "viewer_only": True,
    }
    return projected_nodes, projected_edges, expansion
