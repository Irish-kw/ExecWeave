from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .claude_adapter import append_semantic_records

_MAX_SCAN_BYTES = 16 * 1024 * 1024
_MAX_JSON_LINE_BYTES = 4 * 1024 * 1024
_REVERSE_CHUNK_BYTES = 64 * 1024
_MODEL_OBSERVATION_HOOKS = frozenset({"Stop"})


def _entity(
    entity_type: str,
    entity_id: str,
    *,
    name: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": entity_type,
        "id": entity_id,
        "name": name,
        "attributes": attributes or {},
    }


def _model_entity(model: str) -> dict[str, Any]:
    return _entity(
        "model",
        f"model:claude:{model}",
        name=model,
        attributes={"provider": "claude", "served_model_observation": True},
    )


def _main_agent() -> dict[str, Any]:
    return _entity("agent", "agent:Claude Code", name="Claude Code")


def _base_attributes(payload: dict[str, Any]) -> dict[str, Any]:
    attributes: dict[str, Any] = {
        "backend": "semantic",
        "attribution": "claude_transcript",
        "evidence_source": "provider_transcript",
        "provider": "claude",
        "causal": False,
        "model_observation": "assistant.message.model",
        "switch_initiator": "unknown",
    }
    session_id = payload.get("session_id")
    if isinstance(session_id, str) and session_id:
        attributes["claude_session_id"] = session_id
    return attributes


def _iter_reverse_lines(path: Path):
    """Yield recent complete lines from newest to oldest within a bounded scan window."""
    try:
        size = path.stat().st_size
    except OSError:
        return
    if size <= 0:
        return
    scanned = 0
    position = size
    buffer = b""
    with path.open("rb") as handle:
        while position > 0 and scanned < _MAX_SCAN_BYTES:
            request = min(_REVERSE_CHUNK_BYTES, position, _MAX_SCAN_BYTES - scanned)
            position -= request
            handle.seek(position)
            chunk = handle.read(request)
            if not chunk:
                break
            scanned += len(chunk)
            buffer = chunk + buffer
            parts = buffer.split(b"\n")
            buffer = parts[0]
            for line in reversed(parts[1:]):
                if line:
                    yield line
        if position == 0 and buffer:
            yield buffer


def _load_json_line(raw: bytes) -> dict[str, Any] | None:
    if not raw or len(raw) > _MAX_JSON_LINE_BYTES:
        return None
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _record_session_matches(record: dict[str, Any], expected: str | None) -> bool:
    if not expected:
        return True
    for key in ("sessionId", "session_id"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value == expected
    return True


def _assistant_text(message: dict[str, Any]) -> str | None:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    pieces: list[str] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "text":
            continue
        text = block.get("text")
        if isinstance(text, str):
            pieces.append(text)
    return "".join(pieces) if pieces else None


def _text_sha256(text: str | None) -> str | None:
    if text is None:
        return None
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _latest_transcript_model(
    transcript_path: Path,
    *,
    session_id: str | None,
) -> tuple[str, str | None, str | None, str | None, str | None] | None:
    for raw in _iter_reverse_lines(transcript_path):
        record = _load_json_line(raw)
        if record is None or record.get("type") != "assistant":
            continue
        if record.get("isSidechain") is True:
            continue
        if record.get("agentId") or record.get("agent_id"):
            continue
        if not _record_session_matches(record, session_id):
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role not in (None, "assistant"):
            continue
        model = message.get("model")
        if not isinstance(model, str) or not model:
            continue
        if model.startswith("<") and model.endswith(">"):
            continue
        transcript_timestamp = record.get("timestamp")
        observed_at = (
            transcript_timestamp
            if isinstance(transcript_timestamp, str) and transcript_timestamp
            else None
        )
        message_id = message.get("id")
        if not isinstance(message_id, str) or not message_id:
            fallback = record.get("uuid")
            message_id = fallback if isinstance(fallback, str) and fallback else None
        assistant_text = _assistant_text(message)
        return model, observed_at, message_id, assistant_text, _text_sha256(assistant_text)
    return None


def _latest_recorded_served_observation(
    sidecar: Path,
) -> tuple[str, str | None, str | None, str | None] | None:
    if not sidecar.exists():
        return None
    for raw in _iter_reverse_lines(sidecar):
        record = _load_json_line(raw)
        if record is None or record.get("relation") != "SERVED_BY_MODEL":
            continue
        attributes = record.get("attributes")
        if not isinstance(attributes, dict) or attributes.get("provider") != "claude":
            continue
        source = record.get("source")
        if not isinstance(source, dict) or source.get("id") != "agent:Claude Code":
            continue
        target = record.get("target")
        if not isinstance(target, dict) or target.get("type") != "model":
            continue
        name = target.get("name")
        if not isinstance(name, str) or not name:
            target_id = target.get("id")
            prefix = "model:claude:"
            if not isinstance(target_id, str) or not target_id.startswith(prefix):
                continue
            name = target_id[len(prefix) :]
        message_id = attributes.get("claude_transcript_message_id")
        transcript_timestamp = attributes.get("claude_transcript_timestamp")
        text_hash = attributes.get("claude_transcript_message_text_sha256")
        return (
            name,
            message_id if isinstance(message_id, str) and message_id else None,
            transcript_timestamp
            if isinstance(transcript_timestamp, str) and transcript_timestamp
            else None,
            text_hash if isinstance(text_hash, str) and text_hash else None,
        )
    return None


def _same_transcript_message(
    previous: tuple[str, str | None, str | None, str | None] | None,
    *,
    message_id: str | None,
    transcript_timestamp: str | None,
    text_hash: str | None,
) -> bool:
    if previous is None:
        return False
    _, previous_message_id, previous_timestamp, previous_text_hash = previous
    if message_id and previous_message_id:
        return message_id == previous_message_id
    if transcript_timestamp and previous_timestamp:
        return transcript_timestamp == previous_timestamp
    if text_hash and previous_text_hash:
        return text_hash == previous_text_hash
    return False


def claude_transcript_model_events(
    payload: dict[str, Any],
    *,
    sidecar: str | Path,
    timestamp: str,
) -> list[dict[str, Any]]:
    """Return actual-served-model evidence from Claude's local transcript.

    Claude hooks expose ``model`` only on SessionStart. Runtime model selection can
    change later, so this observer uses the provider-written transcript's top-level
    assistant ``message.model`` field at Stop. UI confirmation text such as
    ``Set model to ...`` is intentionally ignored because it does not prove which
    model actually served the next assistant response.
    """
    hook_event = payload.get("hook_event_name")
    if hook_event not in _MODEL_OBSERVATION_HOOKS:
        return []
    if payload.get("agent_id") or payload.get("agentId"):
        return []
    transcript = payload.get("transcript_path")
    if not isinstance(transcript, str) or not transcript:
        return []
    transcript_path = Path(transcript).expanduser()
    if not transcript_path.is_file():
        return []
    session_id_value = payload.get("session_id")
    session_id = session_id_value if isinstance(session_id_value, str) else None
    latest = _latest_transcript_model(transcript_path, session_id=session_id)
    if latest is None:
        return []
    model, transcript_timestamp, message_id, assistant_text, text_hash = latest

    last_assistant_message = payload.get("last_assistant_message")
    if isinstance(last_assistant_message, str) and last_assistant_message:
        if assistant_text != last_assistant_message:
            return []
        validation = "stop.last_assistant_message_match"
    else:
        validation = "stop.latest_top_level_assistant"

    sidecar_path = Path(sidecar).expanduser().resolve()
    previous = _latest_recorded_served_observation(sidecar_path)
    if _same_transcript_message(
        previous,
        message_id=message_id,
        transcript_timestamp=transcript_timestamp,
        text_hash=text_hash,
    ):
        return []
    previous_model = previous[0] if previous is not None else None

    attributes = _base_attributes(payload)
    attributes["model_observation_validation"] = validation
    if transcript_timestamp:
        attributes["claude_transcript_timestamp"] = transcript_timestamp
    if message_id:
        attributes["claude_transcript_message_id"] = message_id
    if text_hash:
        attributes["claude_transcript_message_text_sha256"] = text_hash
    if previous_model is not None and previous_model != model:
        attributes["previous_served_model"] = previous_model
        attributes["runtime_model_transition"] = True

    events = [
        {
            "timestamp": timestamp,
            "event_type": "semantic.claude.model.served",
            "relation": "SERVED_BY_MODEL",
            "source": _main_agent(),
            "target": _model_entity(model),
            "attributes": dict(attributes),
        }
    ]
    if previous_model is not None and previous_model != model:
        transition_attributes = dict(attributes)
        transition_attributes["transition_basis"] = "consecutive_served_model_observations"
        events.append(
            {
                "timestamp": timestamp,
                "event_type": "semantic.claude.model.switched",
                "relation": "SWITCHED_MODEL",
                "source": _model_entity(previous_model),
                "target": _model_entity(model),
                "attributes": transition_attributes,
            }
        )
    return events


def append_claude_transcript_model_events(
    payload: dict[str, Any],
    *,
    sidecar: str | Path,
    timestamp: str,
) -> list[dict[str, Any]]:
    """Serialize runtime-model deduplication across concurrent Claude hook processes."""
    sidecar_path = Path(sidecar).expanduser().resolve()
    lock_dir = sidecar_path.with_name(sidecar_path.name + ".model-observer.lock")
    deadline = time.monotonic() + 5.0
    while True:
        try:
            lock_dir.mkdir(parents=False)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timed out waiting for Claude model observer lock: {lock_dir}")
            time.sleep(0.01)
        except FileNotFoundError:
            sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        events = claude_transcript_model_events(
            payload,
            sidecar=sidecar_path,
            timestamp=timestamp,
        )
        append_semantic_records(sidecar_path, events)
        return events
    finally:
        try:
            lock_dir.rmdir()
        except OSError:
            pass
