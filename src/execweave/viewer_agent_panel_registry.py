from __future__ import annotations

# Phase 1 isolation map only. Render rules still live in viewer_agent_panel.py
# until each provider panel is extracted with identical behavior.

PANEL_PROVIDERS = (
    "codex",
    "claude",
    "antigravity",
    "cursor",
    "gemini",
    "opencode",
    "ollama",
)

SHARED_LAYOUT_MODULES = (
    "viewer_projection",
    "viewer_projection_base",
    "live_view_readability",
)
