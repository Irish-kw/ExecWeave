from __future__ import annotations

from typing import Any

from .agent_topology import ROOT_PATH


def _normalized_preview_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _parent_agent_path(path: str) -> str:
    parent = path.rsplit("/", 1)[0] if "/" in path else ""
    return parent or ROOT_PATH


def _is_antigravity_addressed_task(message: dict[str, Any], path: str) -> bool:
    if str(message.get("recipient") or "") != path:
        return False
    kind = str(message.get("kind") or "")
    role = str(message.get("content_role") or "")
    return kind == "subagent_task" or role == "antigravity_addressed_task"


def sanitize_antigravity_preview_messages(entries: list[dict[str, Any]]) -> None:
    """Canonicalize child assignments and drop copies pasted onto /root."""
    child_replies: set[str] = set()
    child_assignments: set[str] = set()
    for entry in entries:
        if str(entry.get("provider") or "").lower() != "antigravity":
            continue
        preview = entry.get("conversation_preview")
        if not isinstance(preview, dict) or preview.get("is_root") is not False:
            continue
        path = str(preview.get("agent_path") or "")
        for message in preview.get("messages") or []:
            if not isinstance(message, dict):
                continue
            kind = str(message.get("kind") or "")
            sender = str(message.get("sender") or "")
            text = _normalized_preview_text(message.get("text"))
            if _is_antigravity_addressed_task(message, path) and text:
                child_assignments.add(text)
            if kind not in {"assistant_message", "subagent_final_response"}:
                continue
            if path and sender and sender != path:
                continue
            if text:
                child_replies.add(text)

    for entry in entries:
        if str(entry.get("provider") or "").lower() != "antigravity":
            continue
        preview = entry.get("conversation_preview")
        if not isinstance(preview, dict):
            continue
        messages = [message for message in preview.get("messages") or [] if isinstance(message, dict)]
        path = str(preview.get("agent_path") or "")
        is_root = preview.get("is_root") is True or path == ROOT_PATH
        kept: list[dict[str, Any]] = []
        assignment_texts: set[str] = set()
        if not is_root:
            for message in messages:
                kind = str(message.get("kind") or "")
                if kind in {"task", "subagent_task"} or str(
                    message.get("content_role") or ""
                ) == "antigravity_addressed_task":
                    text = _normalized_preview_text(message.get("text"))
                    if text:
                        assignment_texts.add(text)
        for original in messages:
            message = original
            kind = str(message.get("kind") or "")
            recipient = str(message.get("recipient") or "")
            text = _normalized_preview_text(message.get("text"))
            if is_root:
                if kind == "subagent_task" and recipient in {"", ROOT_PATH, "/root"}:
                    continue
                if kind == "assistant_message" and text and text in child_assignments:
                    continue
                if text and text in child_replies and kind != "assistant_message":
                    continue
            else:
                if _is_antigravity_addressed_task(message, path):
                    sender = str(message.get("sender") or "")
                    message = dict(message)
                    message["kind"] = "task"
                    message["phase"] = "assignment"
                    message["content_role"] = "antigravity_addressed_task"
                    if sender in {"", "user"}:
                        message["sender"] = _parent_agent_path(path)
                    kind = "task"
                if (
                    kind == "user_message"
                    and text
                    and text in assignment_texts
                    and recipient == path
                ):
                    continue
            kept.append(message)
        preview["messages"] = kept
        preview["message_count"] = len(kept)
