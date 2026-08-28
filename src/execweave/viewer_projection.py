from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Any

from . import viewer_projection_base as _base
from .conversation_records import conversation_record_entries, write_conversation_records
from .viewer_antigravity_linkage_inspector import inject_standalone_antigravity_linkage_inspector
from .viewer_conversation_panel import inject_standalone_conversation_panel
from .viewer_conversation_tree import inject_standalone_conversation_tree
from .viewer_dashboard_clean import inject_standalone_dashboard_clean
from .viewer_execution_inspector import inject_standalone_execution_inspector

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
_base_render_graph_html = _base.render_graph_html


def _render_enriched_graph_html(
    graph: dict[str, Any],
    *,
    conversation_entries: list[dict[str, Any]] | None = None,
) -> str:
    html = inject_standalone_execution_inspector(_base_render_graph_html(graph))
    html = inject_standalone_antigravity_linkage_inspector(html)
    html = inject_standalone_conversation_panel(html, entries=conversation_entries)
    html = inject_standalone_conversation_tree(html)
    return inject_standalone_dashboard_clean(html)


def render_graph_html(graph: dict[str, Any]) -> str:
    return _render_enriched_graph_html(graph)


def write_graph_html(
    graph: dict[str, Any],
    path: str | Path,
    *,
    open_browser: bool = False,
) -> Path:
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.stat().st_size > 0:
        raise FileExistsError(f"ExecWeave viewer output already exists: {output}")
    write_conversation_records(graph, output.parent)
    entries = conversation_record_entries(graph, output.parent)
    output.write_text(
        _render_enriched_graph_html(graph, conversation_entries=entries),
        encoding="utf-8",
    )
    if open_browser:
        webbrowser.open(output.as_uri())
    return output


_base.render_graph_html = render_graph_html
_base.write_graph_html = write_graph_html
build_viewer_from_graph = _base.build_viewer_from_graph
