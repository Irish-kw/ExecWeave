from __future__ import annotations

from pathlib import Path
from typing import Any

from . import viewer_projection_base as _base
from .conversation_records import conversation_index_payload, write_conversation_records
from .dashboard_shell import render_static_dashboard_html

VIEWER_MAX_DOM_ELEMENTS = _base.VIEWER_MAX_DOM_ELEMENTS
VIEWER_MAX_EDGES = _base.VIEWER_MAX_EDGES
VIEWER_MAX_NODES = _base.VIEWER_MAX_NODES
EPHEMERAL_PORT_MIN = _base.EPHEMERAL_PORT_MIN
LOOPBACK_CLUSTER_THRESHOLD = _base.LOOPBACK_CLUSTER_THRESHOLD
internal_hook_process_ids_in_event = _base.internal_hook_process_ids_in_event
is_internal_hook_runtime_event = _base.is_internal_hook_runtime_event
strip_internal_hook_processes = _base.strip_internal_hook_processes
strip_internal_hook_execution_graph = _base.strip_internal_hook_execution_graph
project_viewer_graph = _base.project_viewer_graph


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


def render_graph_html(graph: dict[str, Any]) -> str:
    """Render the final graph with the exact same shell used by the live dashboard."""
    entries = _conversation_entries(graph, _run_root_from_graph(graph))
    return render_static_dashboard_html(
        project_viewer_graph(graph),
        conversation_entries=entries,
    )


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
        render_static_dashboard_html(
            project_viewer_graph(graph),
            conversation_entries=payload["entries"],
        ),
        encoding="utf-8",
    )
    if open_browser:
        import webbrowser

        webbrowser.open(output.as_uri())
    return output


_base.render_graph_html = render_graph_html
_base.write_graph_html = write_graph_html
build_viewer_from_graph = _base.build_viewer_from_graph
