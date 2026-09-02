from __future__ import annotations

import re
from typing import Any

_MAX_PREVIEW_MESSAGES = 80
_MAX_PREVIEW_TEXT_CHARS = 6000
_USER_KINDS = (
    "user_prompt",
    "user_message",
    "request_prompt",
    "prompt_submission_candidate",
)
_ASSISTANT_FINAL_KINDS = (
    "assistant_final_response",
    "subagent_final_response",
    "completed_text",
)
_ASSISTANT_RESPONSE_KINDS = ("assistant_response", "assistant_display")
_SUBAGENT_TASK_KINDS = (
    "subagent_task",
    "subagent_description",
    "subtask_prompt",
    "subtask_description",
)
_SUBAGENT_SUMMARY_KINDS = ("subagent_summary", "subagent_final_response")
_ANTIGRAVITY_USER_REQUEST_RE = re.compile(
    r"<USER_REQUEST>\s*(?P<body>.*?)\s*</USER_REQUEST>",
    re.DOTALL,
)
_ANTIGRAVITY_INBOUND_MESSAGE_RE = re.compile(
    r"\[Message\][^\n]*\bcontent=(?P<body>.*?)(?:\n*</SYSTEM_MESSAGE>|\Z)",
    re.DOTALL,
)


def _trim_text(value: str) -> str:
    value = value.strip()
    if len(value) <= _MAX_PREVIEW_TEXT_CHARS:
        return value
    return value[: _MAX_PREVIEW_TEXT_CHARS - 1] + "…"


def _message(
    *,
    timestamp: object,
    ordinal: object,
    kind: str,
    sender: str | None,
    recipient: str | None,
    text: str | None,
    phase: str | None = None,
    task_name: str | None = None,
    content_state: str = "plaintext",
) -> dict[str, Any]:
    return {
        "timestamp": timestamp if isinstance(timestamp, str) else None,
        "ordinal": ordinal if isinstance(ordinal, int) and not isinstance(ordinal, bool) else None,
        "kind": kind,
        "sender": sender,
        "recipient": recipient,
        "text": _trim_text(text) if isinstance(text, str) and text.strip() else None,
        "content_state": content_state,
        "phase": phase,
        "task_name": task_name,
    }


def _text_parts(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "").lower()
            if item_type in {"text", "input_text", "output_text", "text_delta", "message"}:
                text = item.get("text") or item.get("content")
                if isinstance(text, str) and text:
                    parts.append(text)
        return "\n".join(parts).strip()
    if isinstance(value, dict):
        for key in ("text", "content", "message", "output_text"):
            text = value.get(key)
            if isinstance(text, str) and text:
                return text.strip()
        content = value.get("content")
        if isinstance(content, list):
            return _text_parts(content)
    return ""


def _antigravity_user_text(text: str) -> str:
    match = _ANTIGRAVITY_USER_REQUEST_RE.search(text)
    return match.group("body").strip() if match is not None else text.strip()


def _antigravity_inbound_message_text(text: str) -> str:
    match = _ANTIGRAVITY_INBOUND_MESSAGE_RE.search(text)
    return match.group("body").strip() if match is not None else ""


def _antigravity_send_message_text(record: dict[str, Any]) -> str:
    calls = record.get("tool_calls")
    if not isinstance(calls, list):
        return ""
    bodies: list[str] = []
    for call in calls:
        if not isinstance(call, dict) or call.get("name") != "send_message":
            continue
        args = call.get("args")
        if not isinstance(args, dict):
            continue
        message = args.get("Message")
        if isinstance(message, str) and message.strip():
            bodies.append(message.strip())
    return "\n\n".join(bodies)
