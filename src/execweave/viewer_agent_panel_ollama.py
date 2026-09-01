from __future__ import annotations

from .viewer_agent_panel_default import DEFAULT_CHILD_ROUNDS_JS

OLLAMA_CHILD_ROUNDS_JS = r"""
function execweaveOllamaChildRounds(messages,path){return execweaveDefaultChildRounds(messages,path)}
""".strip()

assert DEFAULT_CHILD_ROUNDS_JS
