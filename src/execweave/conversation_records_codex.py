from __future__ import annotations

from typing import Any


def drop_root_user_prompts_from_codex_children(entries: list[dict[str, Any]]) -> None:
    """Child threads must not carry the user's prompt to /root."""
    for entry in entries:
        if str(entry.get("provider") or "").lower() != "codex":
            continue
        preview = entry.get("conversation_preview")
        if not isinstance(preview, dict) or preview.get("is_root") is True:
            continue
        if preview.get("agent_path") == "/root":
            continue
        messages = preview.get("messages")
        if not isinstance(messages, list):
            continue
        preview["messages"] = [
            message
            for message in messages
            if not (
                isinstance(message, dict)
                and str(message.get("sender") or "") == "user"
                and str(message.get("recipient") or "") == "/root"
            )
        ]


def _same_merged_execution(
    representative_entry: dict[str, Any],
    merged_preview: dict[str, Any],
    observed_entry: dict[str, Any],
    observed_preview: dict[str, Any],
) -> bool:
    if str(observed_entry.get("provider") or "").lower() != "codex":
        return False
    if observed_preview.get("agent_path") != merged_preview.get("agent_path"):
        return False

    representative_source = representative_entry.get("source_id")
    observed_source = observed_entry.get("source_id")
    if (
        isinstance(representative_source, str)
        and representative_source
        and observed_source == representative_source
    ):
        return True

    evidence_thread_ids = {
        value
        for value in merged_preview.get("evidence_thread_ids") or []
        if isinstance(value, str) and value
    }
    published_thread = merged_preview.get("thread_id")
    if isinstance(published_thread, str) and published_thread:
        evidence_thread_ids.add(published_thread)
    observed_thread = observed_preview.get("thread_id")
    return isinstance(observed_thread, str) and observed_thread in evidence_thread_ids
