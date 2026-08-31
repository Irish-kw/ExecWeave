from __future__ import annotations

import json
from typing import Any

from .live_view import LIVE_HTML as _BASE_LIVE_HTML
from .viewer_agent_panel import inject_agent_panel
from .viewer_dashboard_clean import fold_budget_bootstrap, inject_live_dashboard_clean
from .viewer_dashboard_focus import inject_live_dashboard_focus
from .viewer_live_layout import inject_live_dashboard_layout


def _build_dashboard_html() -> str:
    html = inject_live_dashboard_layout(
        inject_live_dashboard_focus(inject_live_dashboard_clean(_BASE_LIVE_HTML))
    )
    return inject_agent_panel(html)


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
