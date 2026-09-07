from __future__ import annotations

import json
from typing import Any

from .live_view import LIVE_HTML as _BASE_LIVE_HTML
from .viewer_agent_panel import inject_agent_panel
from .viewer_dashboard_clean import fold_budget_bootstrap, inject_live_dashboard_clean
from .viewer_limits import resolve_viewer_limits, viewer_limits_bootstrap
from .viewer_dashboard_focus import inject_live_dashboard_focus
from .viewer_live_layout import inject_live_dashboard_layout


def _align_agent_panel_topology(html: str) -> str:
    """Keep the agent panel's identity/topology authority intact.

    The panel owns the provider-neutral rule: exact conversation identity selects
    content, while only explicit/root-provenance evidence selects the root renderer.
    Rewriting that code here used to promote every derived ``/root`` preview back into
    a canonical root and reintroduced cross-conversation aggregation. The shared shell
    therefore no longer carries a second topology policy.
    """
    return html


def _guard_compact_live_snapshot(html: str) -> str:
    """Keep compact live payloads in protective mode instead of projecting nodes=[]."""
    needle = "function setSnapshot(data){const signature="
    guarded = (
        "function setSnapshot(data){"
        "if(data.live_payload_compact){updateStats(data);enterProtectiveMode(data);return}"
        "const signature="
    )
    if needle not in html:
        return html
    return html.replace(needle, guarded, 1)


def _preserve_semantic_layout_constraints(html: str) -> str:
    """Internalized directly into live_view_process_layout.py.

    Semantic constraints, 3-stage validation pipeline, and 2D grid packing for
    secondary components are now native in the layout engine.
    """
    return html


def _preserve_semantic_arrange(html: str) -> str:
    """Internalized directly into live_view_process_layout.py.

    Arrange single authority scoped to visible nodes/edges without camera fit
    is now native in the layout engine.
    """
    return html


def _route_ordinary_edges_from_final_positions(html: str) -> str:
    """Internalized directly into live_view_process_layout.py.

    Sampled cubic polyline edge routing conforming to M/L SVG contracts is now
    native in the layout engine.
    """
    return html


def _build_dashboard_html() -> str:
    html = inject_live_dashboard_layout(
        inject_live_dashboard_focus(inject_live_dashboard_clean(_BASE_LIVE_HTML))
    )
    html = _preserve_semantic_layout_constraints(html)
    html = _preserve_semantic_arrange(html)
    html = _route_ordinary_edges_from_final_positions(html)
    return _align_agent_panel_topology(inject_agent_panel(_guard_compact_live_snapshot(html)))


DASHBOARD_HTML = _build_dashboard_html()


def _safe_json(value: object) -> str:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def render_static_dashboard_html(
    graph: dict[str, Any],
    *,
    conversation_entries: list[dict[str, Any]] | None = None,
) -> str:
    """Render the exact dashboard shell used by live, backed by embedded snapshots."""
    bootstrap = (
        "<script>window.__execweaveStaticMode=true;"
        f"{fold_budget_bootstrap()}"
        f"{viewer_limits_bootstrap(resolve_viewer_limits())}"
        f"window.__execweaveStaticGraph={_safe_json(graph)};"
        f"window.__execweaveStaticConversations={_safe_json(conversation_entries or [])};"
        "</script>\n"
    )
    html = DASHBOARD_HTML.replace("<script>", bootstrap + "<script>", 1)
    live_start = "applyTheme(initialTheme());applyTransform();poll();"
    static_start = (
        "applyTheme(initialTheme());applyTransform();"
        "setSnapshot(window.__execweaveStaticGraph||{});"
        "setStatus('FINISHED','finished');"
        "window.__execweaveDashboard?.onFinished?.();"
    )
    if live_start not in html:
        raise RuntimeError("shared dashboard startup seam changed")
    html = html.replace(live_start, static_start, 1)
    html = html.replace("<title>ExecWeave Live</title>", "<title>ExecWeave</title>", 1)
    return html.replace(
        "<body>",
        '<body>\n<!-- unified dashboard: theme is owned by the visible #theme-toggle control -->',
        1,
    )