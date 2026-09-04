from __future__ import annotations

from pathlib import Path
from typing import Any

from . import viewer_projection_base as _base
from .conversation_records import (
    conversation_index_payload,
    conversation_record_entries,
    write_conversation_records,
)
from .dashboard_shell import render_static_dashboard_html
from .viewer_external_endpoints import (
    EXTERNAL_NODE_ID,
    collapse_external_endpoints,
)

VIEWER_MAX_DOM_ELEMENTS = _base.VIEWER_MAX_DOM_ELEMENTS
VIEWER_MAX_EDGES = _base.VIEWER_MAX_EDGES
VIEWER_MAX_NODES = _base.VIEWER_MAX_NODES
EPHEMERAL_PORT_MIN = _base.EPHEMERAL_PORT_MIN
LOOPBACK_CLUSTER_THRESHOLD = _base.LOOPBACK_CLUSTER_THRESHOLD
internal_hook_process_ids_in_event = _base.internal_hook_process_ids_in_event
is_internal_hook_runtime_event = _base.is_internal_hook_runtime_event
strip_internal_hook_processes = _base.strip_internal_hook_processes
strip_internal_hook_execution_graph = _base.strip_internal_hook_execution_graph
_base_project_viewer_graph = _base.project_viewer_graph

_REPEATED_DETAIL_TYPES = frozenset({"agent_operation", "tool_result"})


def _node_attributes(node: dict[str, Any]) -> dict[str, Any]:
    value = node.get("attributes")
    return value if isinstance(value, dict) else {}


def _normalized_label(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _repeat_detail_key(node: dict[str, Any]) -> tuple[str, str, str] | None:
    """Group only display-detail nodes whose individual identity is not topology."""
    node_type = str(node.get("type") or "")
    if node_type not in _REPEATED_DETAIL_TYPES:
        return None
    label = _normalized_label(node.get("name"))
    if not label:
        return None
    attributes = _node_attributes(node)
    provider = _normalized_label(attributes.get("provider"))
    if not provider:
        parts = str(node.get("id") or "").split(":", 2)
        provider = _normalized_label(parts[1]) if len(parts) > 2 else "unknown"
    outcome = tuple(
        (key, str(attributes[key]))
        for key in ("provider_reported_error", "status", "outcome", "success", "error")
        if attributes.get(key) is not None
    )
    return ("repeated-detail", provider, f"{node_type}:{label}:{outcome!r}")


def _antigravity_role_key(node: dict[str, Any]) -> tuple[str, str, str] | None:
    """Join AGY executions only with validated parent+role-path evidence."""
    if node.get("type") != "agent":
        return None
    attributes = _node_attributes(node)
    if _normalized_label(attributes.get("provider")) != "antigravity":
        return None
    if attributes.get("agent_role") != "subagent":
        return None
    parent = attributes.get("parent_scope_id")
    path = attributes.get("provider_role_path")
    evidence = attributes.get("parent_relation_source")
    slot = attributes.get("provider_role_slot")
    if not all(isinstance(value, str) and value for value in (parent, path, evidence)):
        return None
    if not isinstance(slot, int) or isinstance(slot, bool) or slot < 0:
        return None
    if evidence != "provider_validated_child_transcript":
        return None
    role_type = _normalized_label(attributes.get("provider_role_type"))
    workspace = _normalized_label(attributes.get("provider_role_workspace"))
    return ("antigravity-role", parent, f"{path}\0{slot}\0{role_type}\0{workspace}")


def _earlier(first: object, second: object) -> object:
    if not first:
        return second
    if not second:
        return first
    return first if str(first) <= str(second) else second


def _later(first: object, second: object) -> object:
    if not first:
        return second
    if not second:
        return first
    return first if str(first) >= str(second) else second


def _merge_projected_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    list_fields = {
        "attributions",
        "backends",
        "event_ids",
        "event_types",
        "supporting_event_ids",
    }
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        relation = edge.get("relation")
        if not all(isinstance(value, str) and value for value in (source, target, relation)):
            continue
        key = (source, relation, target)
        current = merged.get(key)
        if current is None:
            merged[key] = dict(edge)
            continue
        current_evidence = int(
            current.get("evidence_event_count", current.get("count", 0)) or 0
        )
        edge_evidence = int(
            edge.get("evidence_event_count", edge.get("count", 0)) or 0
        )
        current["count"] = int(current.get("count", 0) or 0) + int(edge.get("count", 0) or 0)
        current["evidence_event_count"] = current_evidence + edge_evidence
        current["first_seen"] = _earlier(current.get("first_seen"), edge.get("first_seen"))
        current["last_seen"] = _later(current.get("last_seen"), edge.get("last_seen"))
        first_sequences = [
            value
            for value in (current.get("first_sequence"), edge.get("first_sequence"))
            if isinstance(value, int) and not isinstance(value, bool)
        ]
        last_sequences = [
            value
            for value in (current.get("last_sequence"), edge.get("last_sequence"))
            if isinstance(value, int) and not isinstance(value, bool)
        ]
        if first_sequences:
            current["first_sequence"] = min(first_sequences)
        if last_sequences:
            current["last_sequence"] = max(last_sequences)
        for field in list_fields:
            values: list[Any] = []
            for candidate in (current.get(field), edge.get(field)):
                if isinstance(candidate, list):
                    values.extend(candidate)
            if values:
                current[field] = list(dict.fromkeys(values))
        current["viewer_canonicalized"] = True
    return sorted(
        merged.values(),
        key=lambda edge: (
            str(edge.get("source") or ""),
            str(edge.get("relation") or ""),
            str(edge.get("target") or ""),
        ),
    )


def _collapse_repeated_viewer_nodes(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    """Collapse repeated result nodes and validated AGY role continuations for display."""
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for node in nodes:
        key = _repeat_detail_key(node) or _antigravity_role_key(node)
        if key is not None:
            groups.setdefault(key, []).append(node)

    canonical: dict[str, str] = {}
    replacements: dict[str, dict[str, Any]] = {}
    repeated_detail_count = 0
    antigravity_continuation_count = 0
    for key, members in groups.items():
        if len(members) < 2:
            continue
        members.sort(
            key=lambda node: (
                str(node.get("first_seen") or ""),
                str(node.get("id") or ""),
            )
        )
        base = members[0]
        base_id = str(base["id"])
        member_ids = [str(member["id"]) for member in members]
        for member_id in member_ids:
            canonical[member_id] = base_id
        occurrences = [
            {
                "id": member["id"],
                "first_seen": member.get("first_seen"),
                "last_seen": member.get("last_seen"),
            }
            for member in members
        ]
        attributes = {
            **_node_attributes(base),
            "viewer_canonicalized": True,
            "viewer_member_ids": member_ids,
            "viewer_occurrence_count": len(members),
            "viewer_occurrences": occurrences,
        }
        if key[0] == "antigravity-role":
            attributes["viewer_logical_agent_continuation"] = True
            attributes["viewer_agent_member_ids"] = member_ids
            attributes["provider_conversation_ids"] = [
                value
                for value in (
                    _node_attributes(member).get("conversation_id") for member in members
                )
                if isinstance(value, str) and value
            ]
            antigravity_continuation_count += len(members) - 1
        else:
            repeated_detail_count += len(members) - 1
        replacements[base_id] = {
            **base,
            "first_seen": min(
                (str(member.get("first_seen")) for member in members if member.get("first_seen")),
                default="",
            )
            or None,
            "last_seen": max(
                (str(member.get("last_seen") or "") for member in members),
                default="",
            )
            or None,
            "event_count": sum(int(member.get("event_count", 0) or 0) for member in members),
            "evidence_event_count": sum(
                int(member.get("evidence_event_count", member.get("event_count", 0)) or 0)
                for member in members
            ),
            "attributes": attributes,
        }

    if not canonical:
        return nodes, edges, {
            "repeated_detail_node_count": 0,
            "antigravity_continuation_node_count": 0,
        }

    collapsed_nodes: list[dict[str, Any]] = []
    for node in nodes:
        node_id = str(node.get("id") or "")
        representative = canonical.get(node_id)
        if representative is None:
            collapsed_nodes.append(node)
        elif representative == node_id:
            collapsed_nodes.append(replacements[node_id])

    reanchored: list[dict[str, Any]] = []
    for edge in edges:
        source = canonical.get(str(edge.get("source") or ""), edge.get("source"))
        target = canonical.get(str(edge.get("target") or ""), edge.get("target"))
        reanchored.append(
            {
                **edge,
                "source": source,
                "target": target,
                **(
                    {
                        "viewer_canonicalized": True,
                        "viewer_original_source": edge.get("source"),
                        "viewer_original_target": edge.get("target"),
                    }
                    if source != edge.get("source") or target != edge.get("target")
                    else {}
                ),
            }
        )
    return collapsed_nodes, _merge_projected_edges(reanchored), {
        "repeated_detail_node_count": repeated_detail_count,
        "antigravity_continuation_node_count": antigravity_continuation_count,
    }


def _viewer_child_session_edges(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Add parent→child edges when the live hook stream omitted ASSIGNED_AGENT_TASK."""
    run_root = _run_root_from_graph(graph)
    if run_root is None:
        return []
    try:
        entries = conversation_record_entries(graph, run_root)
    except (OSError, RuntimeError, ValueError):
        return []
    node_ids = {
        node.get("id")
        for node in graph.get("nodes", [])
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }
    existing = {
        (edge.get("source"), edge.get("target"))
        for edge in graph.get("edges", [])
        if isinstance(edge, dict)
        and edge.get("relation") in {"HAS_CHILD_AGENT_SESSION", "ASSIGNED_AGENT_TASK"}
    }
    parent_by_path: dict[str, str] = {}
    children: list[tuple[str, str]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        source_id = entry.get("source_id")
        preview = entry.get("conversation_preview")
        if not isinstance(source_id, str) or source_id not in node_ids:
            continue
        if not isinstance(preview, dict):
            continue
        path = preview.get("agent_path")
        if preview.get("is_root") is True and isinstance(path, str) and path:
            parent_by_path[path] = source_id
            continue
        parent_path = preview.get("parent_agent_path")
        if (
            preview.get("is_root") is False
            and isinstance(parent_path, str)
            and parent_path
        ):
            children.append((source_id, parent_path))
    edges: list[dict[str, Any]] = []
    for child_id, parent_path in children:
        parent_id = parent_by_path.get(parent_path)
        if parent_id is None or (parent_id, child_id) in existing:
            continue
        existing.add((parent_id, child_id))
        edges.append(
            {
                "id": f"viewer:{parent_id}--HAS_CHILD_AGENT_SESSION-->{child_id}",
                "source": parent_id,
                "target": child_id,
                "relation": "HAS_CHILD_AGENT_SESSION",
                "count": 1,
                "inferred": False,
                "viewer_only": True,
                "attributions": ["viewer_antigravity_transcript_parent_child"],
            }
        )
    return edges


def project_viewer_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """Keep loopback clustering, then fold outbound IPs into one External node."""
    projected = _base_project_viewer_graph(graph)
    nodes = [node for node in projected.get("nodes", []) if isinstance(node, dict)]
    edges = [edge for edge in projected.get("edges", []) if isinstance(edge, dict)]
    extra = _viewer_child_session_edges(graph)
    if extra:
        edges.extend(extra)
        projected = dict(projected)
        projected["edges"] = edges
        projected["edge_count"] = len(edges)
    nodes, edges, expansion = collapse_external_endpoints(nodes, edges)
    result = dict(projected)
    result["nodes"] = nodes
    result["edges"] = edges
    result["node_count"] = len(nodes)
    result["edge_count"] = len(edges)
    metadata = dict(
        result.get("viewer_projection")
        or {"schema_version": "0.1", "viewer_only": True}
    )
    if expansion is not None:
        existing_expansion = result.get("expansion")
        payload = dict(existing_expansion) if isinstance(existing_expansion, dict) else {}
        clusters = dict(payload.get("clusters") or {})
        clusters[EXTERNAL_NODE_ID] = expansion
        payload["clusters"] = clusters
        payload.setdefault("schema_version", "0.1")
        result["expansion"] = payload
        metadata["kind"] = (
            "combined"
            if metadata.get("kind") and metadata.get("kind") != "external_endpoints"
            else "external_endpoints"
        )
        metadata["external_endpoint_count"] = len(expansion.get("nodes") or [])

    nodes, edges, collapse_counts = _collapse_repeated_viewer_nodes(nodes, edges)
    if expansion is None and not any(collapse_counts.values()):
        return projected
    result["nodes"] = nodes
    result["edges"] = edges
    result["node_count"] = len(nodes)
    result["edge_count"] = len(edges)
    if any(collapse_counts.values()):
        metadata.update(collapse_counts)
        metadata["kind"] = "combined"
    result["viewer_projection"] = metadata
    return result


def _run_root_from_graph(graph: dict[str, Any]) -> Path | None:
    source = graph.get("source_path")
    if not isinstance(source, str) or not source:
        return None
    try:
        path = Path(source).expanduser().resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return None
    return path.parent


def _conversation_entries(
    graph: dict[str, Any],
    run_root: Path | None,
) -> list[dict[str, Any]]:
    if run_root is None:
        return []
    try:
        payload = conversation_index_payload(graph, run_root)
    except (OSError, RuntimeError, ValueError):
        return []
    entries = payload.get("entries")
    return entries if isinstance(entries, list) else []


def _render_unified_dashboard(
    graph: dict[str, Any],
    entries: list[dict[str, Any]],
) -> str:
    """Render exactly one product shell for both live and finalized runs."""
    return render_static_dashboard_html(
        project_viewer_graph(graph),
        conversation_entries=entries,
    )


def render_graph_html(graph: dict[str, Any]) -> str:
    """Render the final graph with the exact same shell used by the live dashboard."""
    entries = _conversation_entries(graph, _run_root_from_graph(graph))
    return _render_unified_dashboard(graph, entries)


def write_graph_html(
    graph: dict[str, Any],
    path: str | Path,
    *,
    open_browser: bool = False,
) -> Path:
    """Persist the live dashboard as an offline final snapshot."""
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.stat().st_size > 0:
        raise FileExistsError(f"ExecWeave viewer output already exists: {output}")
    payload = conversation_index_payload(graph, output.parent)
    write_conversation_records(graph, output.parent, payload=payload)
    output.write_text(
        _render_unified_dashboard(graph, payload["entries"]),
        encoding="utf-8",
    )
    if open_browser:
        import webbrowser

        webbrowser.open(output.as_uri())
    return output


_base.render_graph_html = render_graph_html
_base.write_graph_html = write_graph_html
build_viewer_from_graph = _base.build_viewer_from_graph
