from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Any

_HIDDEN_CONTENT_KINDS = (
    "provider_hook_metadata",
    "hook_metadata",
)

_HIDDEN_NODE_TYPES = frozenset(
    {
        "agent_trace_capability",
    }
)


def _node_attributes(node: dict[str, Any]) -> dict[str, Any]:
    value = node.get("attributes")
    return value if isinstance(value, dict) else {}


def _content_kind(node: dict[str, Any]) -> str:
    attributes = _node_attributes(node)
    viewer = attributes.get("viewer_content")
    if isinstance(viewer, dict):
        value = viewer.get("content_kind")
        if isinstance(value, str):
            return value.lower()
    value = attributes.get("content_kind")
    return value.lower() if isinstance(value, str) else ""


def _is_hidden_metadata_node(node: dict[str, Any]) -> bool:
    if node.get("type") in _HIDDEN_NODE_TYPES:
        return True
    if node.get("type") != "observed_content":
        return False
    kind = _content_kind(node)
    return any(token in kind for token in _HIDDEN_CONTENT_KINDS)


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _tool_name(node: dict[str, Any]) -> str:
    attrs = _node_attributes(node)
    for candidate in (
        attrs.get("tool_name"),
        attrs.get("native_name"),
        node.get("name"),
    ):
        value = _string(candidate)
        if value is not None:
            return value
    return "tool"


def _provider(node: dict[str, Any]) -> str:
    value = _string(_node_attributes(node).get("provider"))
    return value or "unknown"


def _tool_key(provider: str, name: str) -> tuple[str, str]:
    return provider.lower(), name.casefold()


def _viewer_tool_id(provider: str, name: str) -> str:
    digest = hashlib.sha256(f"{provider}\0{name}".encode("utf-8")).hexdigest()[:20]
    return f"viewer-tool:{digest}"


def _edge_sequence(edge: dict[str, Any], key: str) -> int | None:
    value = edge.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _edge_time(edge: dict[str, Any], key: str) -> str | None:
    value = edge.get(key)
    return value if isinstance(value, str) and value else None


def _first(values: list[int | None]) -> int | None:
    present = [value for value in values if value is not None]
    return min(present) if present else None


def _last(values: list[int | None]) -> int | None:
    present = [value for value in values if value is not None]
    return max(present) if present else None


def _first_time(values: list[str | None]) -> str | None:
    present = [value for value in values if value is not None]
    return min(present) if present else None


def _last_time(values: list[str | None]) -> str | None:
    present = [value for value in values if value is not None]
    return max(present) if present else None


def _owner_for_call(
    call_id: str,
    *,
    edges: list[dict[str, Any]],
    node_by_id: dict[str, dict[str, Any]],
) -> str | None:
    direct: list[str] = []
    turns: list[str] = []
    for edge in edges:
        if edge.get("target") != call_id:
            continue
        source_id = edge.get("source")
        if not isinstance(source_id, str):
            continue
        source = node_by_id.get(source_id)
        if source is None:
            continue
        if source.get("type") == "agent":
            direct.append(source_id)
        elif source.get("type") == "agent_turn":
            turns.append(source_id)
    if direct:
        return sorted(direct)[0]

    owners: list[str] = []
    for turn_id in turns:
        for edge in edges:
            if edge.get("target") != turn_id:
                continue
            source_id = edge.get("source")
            if not isinstance(source_id, str):
                continue
            source = node_by_id.get(source_id)
            if source is not None and source.get("type") == "agent":
                owners.append(source_id)
    return sorted(owners)[0] if owners else None


def _tool_for_call(
    call: dict[str, Any],
    *,
    edges: list[dict[str, Any]],
    node_by_id: dict[str, dict[str, Any]],
    tools_by_key: dict[tuple[str, str], str],
) -> str | None:
    call_id = _string(call.get("id"))
    if call_id is None:
        return None
    candidates: list[str] = []
    for edge in edges:
        if edge.get("source") != call_id:
            continue
        target_id = edge.get("target")
        if not isinstance(target_id, str):
            continue
        target = node_by_id.get(target_id)
        if target is not None and target.get("type") == "tool":
            candidates.append(target_id)
    if candidates:
        return sorted(candidates)[0]
    return tools_by_key.get(_tool_key(_provider(call), _tool_name(call)))


def _aggregate_edge(
    *,
    owner_id: str,
    tool_id: str,
    evidence_edges: list[dict[str, Any]],
    count: int,
) -> dict[str, Any]:
    return {
        "id": f"{owner_id}--CALLED_TOOL-->{tool_id}",
        "source": owner_id,
        "target": tool_id,
        "relation": "CALLED_TOOL",
        "count": count,
        "first_seen": _first_time([_edge_time(edge, "first_seen") for edge in evidence_edges]),
        "last_seen": _last_time([_edge_time(edge, "last_seen") for edge in evidence_edges]),
        "first_sequence": _first(
            [_edge_sequence(edge, "first_sequence") for edge in evidence_edges]
        ),
        "last_sequence": _last(
            [_edge_sequence(edge, "last_sequence") for edge in evidence_edges]
        ),
        "event_ids": [],
        "event_types": [],
        "backends": ["viewer_projection"],
        "attributions": ["viewer_tool_call_aggregation"],
        "causal": None,
        "inferred": False,
        "viewer_only": True,
        "aggregation": "repeated_tool_calls",
        "evidence_call_count": count,
    }


def simplify_dashboard_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """Return a presentation-only graph with telemetry noise collapsed.

    Raw graph evidence is never changed. Provider hook metadata is hidden from the
    dashboard, repeated tool-call instances are folded into stable tool nodes, and
    content nodes that become orphaned only because of that folding are omitted.
    """

    projected = deepcopy(graph)
    nodes = [node for node in projected.get("nodes", []) if isinstance(node, dict)]
    edges = [edge for edge in projected.get("edges", []) if isinstance(edge, dict)]
    original_node_ids = {
        node_id
        for node in nodes
        if isinstance((node_id := node.get("id")), str)
    }

    hidden_metadata_ids = {
        str(node["id"])
        for node in nodes
        if isinstance(node.get("id"), str) and _is_hidden_metadata_node(node)
    }
    if hidden_metadata_ids:
        nodes = [node for node in nodes if node.get("id") not in hidden_metadata_ids]
        edges = [
            edge
            for edge in edges
            if edge.get("source") not in hidden_metadata_ids
            and edge.get("target") not in hidden_metadata_ids
        ]

    node_by_id = {
        str(node["id"]): node
        for node in nodes
        if isinstance(node.get("id"), str) and node.get("id")
    }
    tool_calls = [
        node
        for node in nodes
        if node.get("type") == "tool_call" and isinstance(node.get("id"), str)
    ]
    tool_call_ids = {str(node["id"]) for node in tool_calls}

    tools_by_key: dict[tuple[str, str], str] = {}
    for node in nodes:
        node_id = _string(node.get("id"))
        if node_id is None or node.get("type") != "tool":
            continue
        tools_by_key.setdefault(_tool_key(_provider(node), _tool_name(node)), node_id)

    call_groups: dict[tuple[str | None, str], list[str]] = {}
    call_evidence: dict[tuple[str | None, str], list[dict[str, Any]]] = {}
    synthetic_tools: dict[str, dict[str, Any]] = {}

    for call in tool_calls:
        call_id = str(call["id"])
        tool_id = _tool_for_call(
            call,
            edges=edges,
            node_by_id=node_by_id,
            tools_by_key=tools_by_key,
        )
        if tool_id is None:
            provider = _provider(call)
            name = _tool_name(call)
            tool_id = _viewer_tool_id(provider, name)
            synthetic_tools.setdefault(
                tool_id,
                {
                    "id": tool_id,
                    "type": "tool",
                    "name": name,
                    "attributes": {
                        "provider": provider,
                        "viewer_only": True,
                        "aggregation": "repeated_tool_calls",
                    },
                },
            )
        owner_id = _owner_for_call(call_id, edges=edges, node_by_id=node_by_id)
        key = (owner_id, tool_id)
        call_groups.setdefault(key, []).append(call_id)
        call_evidence.setdefault(key, []).extend(
            edge
            for edge in edges
            if edge.get("source") == call_id or edge.get("target") == call_id
        )

    if tool_call_ids:
        nodes = [node for node in nodes if node.get("id") not in tool_call_ids]
        edges = [
            edge
            for edge in edges
            if edge.get("source") not in tool_call_ids
            and edge.get("target") not in tool_call_ids
        ]

    existing_ids = {
        str(node["id"])
        for node in nodes
        if isinstance(node.get("id"), str) and node.get("id")
    }
    for tool_id, node in sorted(synthetic_tools.items()):
        if tool_id not in existing_ids:
            nodes.append(node)
            existing_ids.add(tool_id)

    tool_counts: dict[str, int] = {}
    aggregate_edges: list[dict[str, Any]] = []
    for (owner_id, tool_id), call_ids in sorted(
        call_groups.items(), key=lambda item: ((item[0][0] or ""), item[0][1])
    ):
        tool_counts[tool_id] = tool_counts.get(tool_id, 0) + len(call_ids)
        if owner_id is None or owner_id not in existing_ids:
            continue
        aggregate_edges.append(
            _aggregate_edge(
                owner_id=owner_id,
                tool_id=tool_id,
                evidence_edges=call_evidence[(owner_id, tool_id)],
                count=len(call_ids),
            )
        )

    if tool_counts:
        updated_nodes: list[dict[str, Any]] = []
        for node in nodes:
            node_id = _string(node.get("id"))
            if node_id is None or node_id not in tool_counts:
                updated_nodes.append(node)
                continue
            clone = deepcopy(node)
            attrs = _node_attributes(clone)
            clone["attributes"] = {
                **attrs,
                "viewer_aggregated_tool_call_count": tool_counts[node_id],
            }
            updated_nodes.append(clone)
        nodes = updated_nodes

    existing_edge_ids = {
        str(edge["id"])
        for edge in edges
        if isinstance(edge.get("id"), str) and edge.get("id")
    }
    edges.extend(edge for edge in aggregate_edges if edge["id"] not in existing_edge_ids)

    incident_ids: set[str] = set()
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if isinstance(source, str):
            incident_ids.add(source)
        if isinstance(target, str):
            incident_ids.add(target)
    orphan_content_ids = {
        str(node["id"])
        for node in nodes
        if node.get("type") == "observed_content"
        and isinstance(node.get("id"), str)
        and node.get("id") not in incident_ids
    }
    if orphan_content_ids:
        nodes = [node for node in nodes if node.get("id") not in orphan_content_ids]

    projected["nodes"] = nodes
    projected["edges"] = edges
    projected["node_count"] = len(nodes)
    projected["edge_count"] = len(edges)

    metadata = projected.get("viewer_projection")
    if not isinstance(metadata, dict):
        metadata = {
            "schema_version": "0.1",
            "viewer_only": True,
            "kind": "dashboard_simplification",
        }
    else:
        metadata = deepcopy(metadata)
    metadata.update(
        {
            "dashboard_simplification": True,
            "hidden_hook_metadata_node_count": len(hidden_metadata_ids),
            "collapsed_tool_call_node_count": len(tool_call_ids),
            "aggregated_tool_edge_count": len(aggregate_edges),
            "pruned_orphan_content_node_count": len(orphan_content_ids),
            "raw_node_count_before_dashboard_simplification": len(original_node_ids),
        }
    )
    projected["viewer_projection"] = metadata
    return projected
