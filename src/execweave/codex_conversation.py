from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_MAX_IDENTITY_SCAN_LINES = 64
_MAX_PREVIEW_MESSAGES = 80
_MAX_PREVIEW_TEXT_CHARS = 6000


def _canonical_absolute_path(value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        path = Path(value).expanduser()
        if not path.is_absolute():
            return None
        return path.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return None


def _codex_sessions_root() -> Path:
    configured = os.environ.get("CODEX_HOME")
    home = Path(configured).expanduser() if configured else Path.home() / ".codex"
    return (home / "sessions").resolve(strict=False)


def _inside_codex_sessions(path: Path) -> bool:
    try:
        path.relative_to(_codex_sessions_root())
    except ValueError:
        return False
    return True


def _session_meta_identity(payload: dict[str, Any]) -> dict[str, Any] | None:
    thread_id = payload.get("id") or payload.get("session_id")
    if not isinstance(thread_id, str) or not thread_id:
        return None
    source = payload.get("source")
    spawn: dict[str, Any] = {}
    if isinstance(source, dict):
        subagent = source.get("subagent")
        if isinstance(subagent, dict):
            candidate = subagent.get("thread_spawn")
            if isinstance(candidate, dict):
                spawn = candidate
    agent_path = payload.get("agent_path") or spawn.get("agent_path")
    nickname = payload.get("agent_nickname") or spawn.get("agent_nickname")
    parent_thread_id = payload.get("parent_thread_id") or spawn.get("parent_thread_id")
    history_start = payload.get("subagent_history_start_ordinal")
    return {
        "thread_id": thread_id,
        "parent_thread_id": parent_thread_id if isinstance(parent_thread_id, str) else None,
        "agent_path": agent_path if isinstance(agent_path, str) else None,
        "agent_nickname": nickname if isinstance(nickname, str) else None,
        "subagent_history_start_ordinal": (
            history_start
            if isinstance(history_start, int) and not isinstance(history_start, bool) and history_start >= 0
            else None
        ),
    }


def codex_rollout_identity(path: str | Path) -> dict[str, Any] | None:
    """Read only leading Codex session metadata needed for exact thread identity."""
    source = Path(path).expanduser().resolve(strict=False)
    try:
        with source.open("r", encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                if index >= _MAX_IDENTITY_SCAN_LINES:
                    break
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    return None
                if record.get("type") != "session_meta":
                    continue
                payload = record.get("payload")
                return _session_meta_identity(payload) if isinstance(payload, dict) else None
    except (OSError, RuntimeError, UnicodeError):
        return None
    return None


def validated_codex_transcript(payload: dict[str, Any]) -> tuple[Path, dict[str, Any]] | None:
    """Validate a hook-supplied rollout path before ExecWeave reads or copies it."""
    path = _canonical_absolute_path(payload.get("transcript_path"))
    if path is None or path.suffix.lower() != ".jsonl" or not path.name.startswith("rollout-"):
        return None
    if not _inside_codex_sessions(path) or not path.is_file():
        return None
    agent_id = payload.get("agent_id")
    session_id = payload.get("session_id")
    expected = agent_id if isinstance(agent_id, str) and agent_id else session_id
    if not isinstance(expected, str) or not expected or not path.stem.endswith(f"-{expected}"):
        return None
    identity = codex_rollout_identity(path)
    if identity is None or identity.get("thread_id") != expected:
        return None
    if isinstance(agent_id, str) and agent_id and isinstance(session_id, str) and session_id:
        parent = identity.get("parent_thread_id")
        if isinstance(parent, str) and parent and parent != session_id:
            return None
    return path, identity


def codex_rollout_identity_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    validated = validated_codex_transcript(payload)
    return validated[1] if validated is not None else None


def _content_text(content: object) -> str:
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for part in content:
        if not isinstance(part, dict) or part.get("type") not in {"input_text", "output_text", "Text"}:
            continue
        text = part.get("text")
        if isinstance(text, str) and text:
            parts.append(text)
    return "\n".join(parts).strip()


def _trim_text(value: str) -> str:
    if len(value) <= _MAX_PREVIEW_TEXT_CHARS:
        return value
    return value[: _MAX_PREVIEW_TEXT_CHARS - 1] + "…"


def _agent_message_header(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    before_payload, marker, after_payload = text.partition("Payload:")
    for line in before_payload.splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            continue
        normalized = key.strip().lower().replace(" ", "_")
        if normalized in {"message_type", "task_name", "sender"} and value.strip():
            result[normalized] = value.strip()
    if marker and after_payload.strip():
        result["payload_text"] = after_payload.strip()
    return result


def _message(timestamp: object, ordinal: object, **fields: Any) -> dict[str, Any]:
    return {
        "timestamp": timestamp if isinstance(timestamp, str) else None,
        "ordinal": ordinal if isinstance(ordinal, int) and not isinstance(ordinal, bool) else None,
        **fields,
    }


def codex_rollout_preview(path: str | Path) -> dict[str, Any] | None:
    """Extract visible conversation items without exposing hidden/system context."""
    source = Path(path).expanduser().resolve(strict=False)
    identity = codex_rollout_identity(source)
    if identity is None:
        return None
    cutoff = identity.get("subagent_history_start_ordinal")
    min_ordinal = cutoff if isinstance(cutoff, int) else 0
    agent_path = identity.get("agent_path")
    if not isinstance(agent_path, str) or not agent_path:
        agent_path = "/root" if identity.get("parent_thread_id") is None else None
    messages: list[dict[str, Any]] = []
    try:
        with source.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ordinal = record.get("ordinal")
                if isinstance(ordinal, int) and ordinal < min_ordinal:
                    continue
                if record.get("type") != "response_item":
                    continue
                payload = record.get("payload")
                if not isinstance(payload, dict):
                    continue
                payload_type = payload.get("type")
                if payload_type == "agent_message":
                    content = payload.get("content")
                    header = _agent_message_header(_content_text(content))
                    encrypted = isinstance(content, list) and any(
                        isinstance(part, dict) and part.get("type") == "encrypted_content"
                        for part in content
                    )
                    messages.append(
                        _message(
                            record.get("timestamp"),
                            ordinal,
                            kind=header.get("message_type", "agent_message").lower(),
                            sender=payload.get("author") or header.get("sender"),
                            recipient=payload.get("recipient"),
                            text=None if encrypted else header.get("payload_text"),
                            content_state="provider_encrypted" if encrypted else "plaintext",
                            phase=None,
                            task_name=header.get("task_name"),
                        )
                    )
                elif payload_type == "message":
                    role = payload.get("role")
                    phase = payload.get("phase")
                    text = _content_text(payload.get("content"))
                    if role == "assistant" and text and phase in {"commentary", "final_answer"}:
                        messages.append(
                            _message(
                                record.get("timestamp"),
                                ordinal,
                                kind="assistant_message",
                                sender=agent_path,
                                recipient=None,
                                text=_trim_text(text),
                                content_state="plaintext",
                                phase=phase,
                                task_name=None,
                            )
                        )
                    elif role == "user" and text:
                        metadata = payload.get("internal_chat_message_metadata_passthrough")
                        kinds = metadata.get("content_item_kinds") if isinstance(metadata, dict) else None
                        if isinstance(kinds, list) and "user.text" in kinds:
                            messages.append(
                                _message(
                                    record.get("timestamp"),
                                    ordinal,
                                    kind="user_message",
                                    sender="user",
                                    recipient=agent_path,
                                    text=_trim_text(text),
                                    content_state="plaintext",
                                    phase=None,
                                    task_name=None,
                                )
                            )
                elif (
                    payload_type == "function_call"
                    and payload.get("namespace") == "collaboration"
                    and payload.get("name") == "send_message"
                ):
                    arguments = payload.get("arguments")
                    try:
                        parsed = json.loads(arguments) if isinstance(arguments, str) else arguments
                    except json.JSONDecodeError:
                        parsed = None
                    if isinstance(parsed, dict):
                        target = parsed.get("target")
                        value = parsed.get("message")
                        encrypted = isinstance(value, str) and value.startswith("gAAAAA")
                        messages.append(
                            _message(
                                record.get("timestamp"),
                                ordinal,
                                kind="send_message",
                                sender=agent_path,
                                recipient=target if isinstance(target, str) else None,
                                text=(
                                    _trim_text(value)
                                    if isinstance(value, str) and value and not encrypted
                                    else None
                                ),
                                content_state="provider_encrypted" if encrypted else "plaintext",
                                phase=None,
                                task_name=None,
                            )
                        )
    except (OSError, RuntimeError, UnicodeError):
        return None
    truncated = len(messages) > _MAX_PREVIEW_MESSAGES
    if truncated:
        messages = messages[:10] + messages[-(_MAX_PREVIEW_MESSAGES - 10) :]
    return {
        "thread_id": identity.get("thread_id"),
        "parent_thread_id": identity.get("parent_thread_id"),
        "agent_path": agent_path,
        "agent_nickname": identity.get("agent_nickname"),
        "message_count": len(messages),
        "messages_truncated": truncated,
        "messages": messages,
    }
