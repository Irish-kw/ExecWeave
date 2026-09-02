from __future__ import annotations

from typing import Any


def _ollama_current_turn(preview: dict[str, Any]) -> None:
    """Reduce a cumulative Ollama chat request to the exact turn this exchange created."""
    messages = [message for message in preview.get("messages") or [] if isinstance(message, dict)]
    users = [
        message
        for message in messages
        if message.get("sender") == "user"
        and message.get("content_role") == "ollama_request_surface"
    ]
    response_assistants = [
        message
        for message in messages
        if message.get("content_role") == "ollama_response_surface"
        and str(message.get("kind") or "").startswith("assistant")
    ]
    if not users:
        return
    current = [users[-1]]
    if response_assistants:
        current.append(response_assistants[-1])
    preview["message_count"] = len(current)
    preview["messages_truncated"] = False
    preview["messages"] = current


def _ollama_root_agent_id(graph: dict[str, Any]) -> str | None:
    candidates = []
    for node in graph.get("nodes", []):
        if not isinstance(node, dict) or node.get("type") != "agent":
            continue
        node_id = node.get("id")
        if isinstance(node_id, str) and node_id.lower() == "agent:ollama":
            candidates.append(node_id)
    return candidates[0] if len(candidates) == 1 else None
