from __future__ import annotations

import ipaddress
from copy import deepcopy
from typing import Any, Callable

EXTERNAL_NODE_ID = "viewer-cluster:external"
LOCAL_NODE_ID = "viewer-cluster:local-endpoints"


def _string_values(values: list[object]) -> list[str]:
    return sorted({value for value in values if isinstance(value, str) and value})


def _int_values(values: list[object]) -> list[int]:
    return [value for value in values if isinstance(value, int) and not isinstance(value, bool)]


def endpoint_label(node: dict[str, Any]) -> str | None:
    raw = node.get("name")
    if isinstance(raw, str) and raw:
        return raw
    node_id = node.get("id")
    if isinstance(node_id, str):
        for prefix in ("endpoint:", "network_endpoint:"):
            if node_id.startswith(prefix):
                return node_id[len(prefix) :]
    return None


def split_host_port(raw: str) -> tuple[str, str] | None:
    host, separator, port_text = raw.rpartition(":")
    if not separator or not host or not port_text:
        return None
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    return host, port_text


def format_endpoint_address(raw: str) -> str:
    """Record one endpoint as IP:Port; IPv6 uses [addr]:port."""
    label = raw.strip()
    if label.startswith("endpoint:"):
        label = label[len("endpoint:") :]
    elif label.startswith("network_endpoint:"):
        label = label[len("network_endpoint:") :]
    split = split_host_port(label)
    if split is None:
        return label
    host, port_text = split
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return f"{host}:{port_text}"
    if address.version == 6:
        return f"[{host}]:{port_text}"
    return f"{host}:{port_text}"


def is_loopback_host(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host.lower() in {"localhost", "ip6-localhost"}
    return bool(address.is_loopback)


def _endpoint_host(node: dict[str, Any]) -> str | None:
    label = endpoint_label(node)
    if not isinstance(label, str) or not label:
        return None
    split = split_host_port(label)
    return split[0] if split is not None else label


def is_local_network_endpoint(node: dict[str, Any]) -> bool:
    if node.get("type") != "network_endpoint":
        return False
    if node.get("id") in {EXTERNAL_NODE_ID, LOCAL_NODE_ID}:
        return False
    if node.get("name") in {"External", "Local endpoints"}:
        return False
    host = _endpoint_host(node)
    return isinstance(host, str) and bool(host) and is_loopback_host(host)


def is_external_network_endpoint(node: dict[str, Any]) -> bool:
    if node.get("type") != "network_endpoint":
        return False
    if node.get("id") in {EXTERNAL_NODE_ID, LOCAL_NODE_ID}:
        return False
    if node.get("name") in {"External", "Local endpoints"}:
        return False
    host = _endpoint_host(node)
    return isinstance(host, str) and bool(host) and not is_loopback_host(host)


def _collapse_endpoint_group(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    predicate: Callable[[dict[str, Any]], bool],
    cluster_id: str,
    cluster_name: str,
    reason: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None]:
    members = [
        node
        for node in nodes
        if isinstance(node.get("id"), str) and predicate(node)
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
    incident_by_member: dict[str, list[dict[str, Any]]] = {member_id: [] for member_id in member_ids}
    for edge in member_edges:
        for candidate in (edge.get("source"), edge.get("target")):
            if isinstance(candidate, str) and candidate in incident_by_member:
                incident_by_member[candidate].append(edge)

    endpoints_by_address: dict[str, dict[str, Any]] = {}
    for node in sorted(members, key=lambda item: str(item.get("name") or item.get("id") or "")):
        member_id = str(node["id"])
        label = endpoint_label(node) or member_id
        address = format_endpoint_address(str(label))
        incident = incident_by_member.get(member_id, [])
        node_first = node.get("first_seen")
        node_last = node.get("last_seen")
        edge_first = _string_values([edge.get("first_seen") for edge in incident])
        edge_last = _string_values([edge.get("last_seen") for edge in incident])
        first_sequence_values = _int_values([edge.get("first_sequence") for edge in incident])
        last_sequence_values = _int_values([edge.get("last_sequence") for edge in incident])
        event_ids = [
            event_id
            for edge in incident
            for event_id in (edge.get("event_ids") or [])
            if isinstance(event_id, str) and event_id
        ]
        first_seen_values = [value for value in [node_first, *edge_first] if isinstance(value, str) and value]
        last_seen_values = [value for value in [node_last, *edge_last] if isinstance(value, str) and value]
        occurrence = {
            "id": member_id,
            "address": address,
            "first_seen": min(first_seen_values) if first_seen_values else None,
            "last_seen": max(last_seen_values) if last_seen_values else None,
            "first_sequence": min(first_sequence_values) if first_sequence_values else None,
            "last_sequence": max(last_sequence_values) if last_sequence_values else None,
            "event_count": int(node.get("event_count") or 0),
            "event_ids": list(dict.fromkeys(event_ids))[:32],
        }
        existing = endpoints_by_address.get(address)
        if existing is None:
            endpoints_by_address[address] = occurrence
            continue
        existing["event_count"] = int(existing.get("event_count") or 0) + occurrence["event_count"]
        ids = list(dict.fromkeys([*(existing.get("member_ids") or [existing.get("id")]), member_id]))
        existing["member_ids"] = [value for value in ids if isinstance(value, str) and value]
        for field, chooser in (("first_seen", min), ("last_seen", max)):
            values = [value for value in (existing.get(field), occurrence.get(field)) if isinstance(value, str) and value]
            existing[field] = chooser(values) if values else None
        first_values = [value for value in (existing.get("first_sequence"), occurrence.get("first_sequence")) if isinstance(value, int) and not isinstance(value, bool)]
        last_values = [value for value in (existing.get("last_sequence"), occurrence.get("last_sequence")) if isinstance(value, int) and not isinstance(value, bool)]
        existing["first_sequence"] = min(first_values) if first_values else None
        existing["last_sequence"] = max(last_values) if last_values else None
        existing["event_ids"] = list(dict.fromkeys([*(existing.get("event_ids") or []), *(occurrence.get("event_ids") or [])]))[:32]

    endpoints = [endpoints_by_address[address] for address in sorted(endpoints_by_address)]
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
    cluster_node = {
        "id": cluster_id,
        "type": "network_endpoint",
        "name": cluster_name,
        "attributes": {
            "viewer_only": True,
            "collapsed": True,
            "expandable": True,
            "reason": reason,
            "member_count": len(members),
            "member_type": "network_endpoint",
            "endpoints": endpoints,
            "viewer_occurrences": [
                {
                    "id": item["id"],
                    "name": item["address"],
                    "first_seen": item["first_seen"],
                    "last_seen": item["last_seen"],
                    "first_sequence": item["first_sequence"],
                    "last_sequence": item["last_sequence"],
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
            source = cluster_id
        if target in member_ids:
            target = cluster_id
        if source == target:
            continue
        if source == cluster_id or target == cluster_id:
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
                    "viewer_occurrences": [
                        {
                            "edge_id": edge.get("id"),
                            "source": edge.get("source"),
                            "target": edge.get("target"),
                            "first_seen": edge.get("first_seen"),
                            "last_seen": edge.get("last_seen"),
                            "first_sequence": edge.get("first_sequence"),
                            "last_sequence": edge.get("last_sequence"),
                        }
                    ],
                }
                continue
            existing["count"] = int(existing.get("count") or 0) + max(1, int(edge.get("count") or 0))
            occurrences = existing.setdefault("viewer_occurrences", [])
            if isinstance(occurrences, list):
                occurrences.append(
                    {
                        "edge_id": edge.get("id"),
                        "source": edge.get("source"),
                        "target": edge.get("target"),
                        "first_seen": edge.get("first_seen"),
                        "last_seen": edge.get("last_seen"),
                        "first_sequence": edge.get("first_sequence"),
                        "last_sequence": edge.get("last_sequence"),
                    }
                )
            continue
        remapped.append(deepcopy(edge))

    projected_nodes = [deepcopy(node) for node in nodes if node.get("id") not in member_ids] + [cluster_node]
    projected_edges = remapped + list(grouped.values())
    expansion = {
        "cluster_node_id": cluster_id,
        "cluster_edge_id": None,
        "nodes": [deepcopy(node) for node in members],
        "edges": [deepcopy(edge) for edge in member_edges],
        "viewer_only": True,
    }
    return projected_nodes, projected_edges, expansion


def collapse_local_endpoints(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None]:
    """Fold every loopback endpoint into one provider-neutral Local endpoints node."""
    return _collapse_endpoint_group(
        nodes,
        edges,
        predicate=is_local_network_endpoint,
        cluster_id=LOCAL_NODE_ID,
        cluster_name="Local endpoints",
        reason="local_endpoints",
    )


def collapse_external_endpoints(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None]:
    """Fold every non-loopback endpoint into one provider-neutral External node."""
    return _collapse_endpoint_group(
        nodes,
        edges,
        predicate=is_external_network_endpoint,
        cluster_id=EXTERNAL_NODE_ID,
        cluster_name="External",
        reason="external_endpoints",
    )
