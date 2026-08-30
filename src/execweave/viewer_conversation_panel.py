from __future__ import annotations

from typing import Any


def inject_standalone_conversation_panel(
    html: str,
    *,
    entries: list[dict[str, Any]] | None = None,
) -> str:
    """Compatibility no-op.

    v0.7.9 has a single compact agent inspector in ``viewer_agent_panel``.
    Conversation evidence remains in the shared index; this legacy renderer must
    never add a second panel, fetch loop, raw-evidence link, or alternate DOM tree.
    """
    del entries
    return html


def inject_live_conversation_panel(html: str) -> str:
    """Compatibility no-op; live uses the same compact agent inspector as snapshots."""
    return html
