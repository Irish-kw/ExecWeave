from __future__ import annotations

from .viewer_agent_panel_default import DEFAULT_CHILD_ROUNDS_JS

GEMINI_CHILD_ROUNDS_JS = r"""
function execweaveGeminiChildRounds(messages,path){return execweaveDefaultChildRounds(messages,path)}
""".strip()

assert DEFAULT_CHILD_ROUNDS_JS
