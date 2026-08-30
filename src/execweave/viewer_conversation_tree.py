from __future__ import annotations


def inject_standalone_conversation_tree(html: str) -> str:
    """Compatibility no-op.

    The standalone conversation tree was retired in v0.7.9. Agent selection is
    rendered exclusively by ``viewer_agent_panel`` so live and viewer.html share
    one DOM and one attribution path.
    """
    return html


def inject_live_conversation_tree(html: str) -> str:
    """Compatibility no-op; live no longer builds a hidden second conversation DOM."""
    return html
