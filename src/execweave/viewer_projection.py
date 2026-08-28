from __future__ import annotations

from typing import Any

from . import viewer_projection_base as _base
from .viewer_antigravity_linkage_inspector import (
    inject_standalone_antigravity_linkage_inspector,
)
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


def render_graph_html(graph: dict[str, Any]) -> str:
    html = inject_standalone_execution_inspector(_base_render_graph_html(graph))
    return inject_standalone_antigravity_linkage_inspector(html)


_base.render_graph_html = render_graph_html
write_graph_html = _base.write_graph_html
build_viewer_from_graph = _base.build_viewer_from_graph
