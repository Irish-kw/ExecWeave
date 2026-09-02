from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .conversation_preview_transcript import (
    _antigravity_inbound_message_text,
    _antigravity_send_message_text,
    _antigravity_user_text,
    _message,
    _text_parts,
)


def _structured_messages(
    value: object,
    *,
    timestamp: object,
    ordinal: object,
    agent_path: str,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if isinstance(value.get("message"), dict):
            candidates.append(value["message"])
        elif any(key in value for key in ("role", "content", "text")):
            candidates.append(value)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                if isinstance(item.get("message"), dict):
                    candidates.append(item["message"])
                elif any(key in item for key in ("role", "content", "text")):
                    candidates.append(item)
    messages: list[dict[str, Any]] = []
    for item in candidates:
        role = str(item.get("role") or "").lower()
        if role in {"system", "developer", "tool", "function"}:
            continue
        text = _text_parts(item.get("content")) or _text_parts(item.get("text"))
        if not text:
            continue
        if role in {"user", "human"}:
            messages.append(_message(timestamp=timestamp, ordinal=ordinal, kind="user_message", sender="user", recipient=agent_path, text=text))
        elif role in {"assistant", "model", "agent"}:
            messages.append(_message(timestamp=timestamp, ordinal=ordinal, kind="assistant_message", sender=agent_path, recipient=None, text=text, phase="response"))
    return messages


def _line_transcript_messages(
    path: Path,
    *,
    timestamp: object,
    ordinal: object,
    agent_path: str,
    antigravity: bool = False,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        if antigravity:
            role = str(record.get("source") or "").strip().lower()
            record_type = str(record.get("type") or "").strip().lower()
            text = _text_parts(record.get("content") or record.get("text"))
            record_timestamp = record.get("created_at") or record.get("timestamp") or timestamp
            step_index = record.get("step_index")
            record_ordinal = step_index if isinstance(step_index, int) and not isinstance(step_index, bool) else (ordinal if isinstance(ordinal, int) else 0) + index
            if role in {"user_explicit", "user", "human"} and record_type in {"user_input", "user_message", ""}:
                if text:
                    messages.append(_message(timestamp=record_timestamp, ordinal=record_ordinal, kind="user_message", sender="user", recipient=agent_path, text=_antigravity_user_text(text)))
                continue
            if role in {"model", "assistant"} and record_type == "planner_response":
                outbound = _antigravity_send_message_text(record)
                if outbound:
                    messages.append(_message(timestamp=record_timestamp, ordinal=record_ordinal, kind="assistant_message", sender=agent_path, recipient=None, text=outbound, phase="planner_response"))
                    continue
                if text:
                    messages.append(_message(timestamp=record_timestamp, ordinal=record_ordinal, kind="assistant_message", sender=agent_path, recipient=None, text=text, phase="planner_response"))
                continue
            if role == "system" and record_type == "system_message":
                inbound = _antigravity_inbound_message_text(text)
                if inbound:
                    messages.append(_message(timestamp=record_timestamp, ordinal=record_ordinal, kind="subagent_task", sender="user", recipient=agent_path, text=inbound, phase="assignment"))
                continue
            continue
        record_timestamp = record.get("timestamp") or timestamp
        record_ordinal = record.get("ordinal")
        if not isinstance(record_ordinal, int):
            record_ordinal = (ordinal if isinstance(ordinal, int) else 0) + index
        record_type = str(record.get("type") or "").lower()
        payload = record.get("message")
        if isinstance(payload, dict):
            role = str(payload.get("role") or record_type).lower()
            text = _text_parts(payload.get("content"))
        else:
            role = record_type
            text = _text_parts(record.get("content") or record.get("text"))
        if not text:
            continue
        if role in {"user", "human"}:
            messages.append(_message(timestamp=record_timestamp, ordinal=record_ordinal, kind="user_message", sender="user", recipient=agent_path, text=text))
        elif role in {"assistant", "model"}:
            messages.append(_message(timestamp=record_timestamp, ordinal=record_ordinal, kind="assistant_message", sender=agent_path, recipient=None, text=text, phase="response"))
    return messages
