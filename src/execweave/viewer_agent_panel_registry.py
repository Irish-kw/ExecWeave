from __future__ import annotations

# Phase 1 isolation map. Each provider panel currently forwards to default.

PANEL_PROVIDERS = (
    "codex",
    "claude",
    "antigravity",
    "cursor",
    "opencode",
    "ollama",
)

SHARED_LAYOUT_MODULES = (
    "viewer_projection",
    "viewer_projection_base",
    "live_view_readability",
    "live_view_process_layout",
    "viewer_external_endpoints",
)
