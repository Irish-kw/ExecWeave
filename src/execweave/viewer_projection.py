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
    if expansion is None:
        return projected
    result = dict(projected)
    result["nodes"] = nodes
    result["edges"] = edges
    result["node_count"] = len(nodes)
    result["edge_count"] = len(edges)
    existing_expansion = result.get("expansion")
    payload = dict(existing_expansion) if isinstance(existing_expansion, dict) else {}
    clusters = dict(payload.get("clusters") or {})
    clusters[EXTERNAL_NODE_ID] = expansion
    payload["clusters"] = clusters
    payload.setdefault("schema_version", "0.1")
    result["expansion"] = payload
    metadata = dict(result.get("viewer_projection") or {"schema_version": "0.1", "viewer_only": True})
    metadata["kind"] = (
        "combined"
        if metadata.get("kind") and metadata.get("kind") != "external_endpoints"
        else "external_endpoints"
    )
    metadata["external_endpoint_count"] = len(expansion.get("nodes") or [])
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
