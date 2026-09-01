from __future__ import annotations

from .viewer_agent_panel_default import DEFAULT_CHILD_ROUNDS_JS

CODEX_CHILD_ROUNDS_JS = r"""
function execweaveCodexChildRounds(messages,path){return execweaveDefaultChildRounds(messages,path)}
""".strip()

# Phase 1: Codex uses the shared default policy unchanged.
assert DEFAULT_CHILD_ROUNDS_JS
