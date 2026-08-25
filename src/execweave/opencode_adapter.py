from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_MAX_COMMAND_CHARS = 4096
_MAX_LABEL_CHARS = 160
_SUPPORTED_EVENTS = {"chat.message", "tool.execute.before", "tool.execute.after"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _entity(
    entity_type: str,
    entity_id: str,
    *,
    name: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {"type": entity_type, "id": entity_id, "name": name, "attributes": attributes or {}}


def _event(
    *,
    timestamp: str,
    event_type: str,
    relation: str,
    source: dict[str, Any],
    target: dict[str, Any],
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged = {
        "backend": "semantic",
        "attribution": "opencode_plugin",
        "evidence_source": "provider_plugin",
        "provider": "opencode",
        "causal": False,
    }
    if attributes:
        merged.update(attributes)
    return {
        "timestamp": timestamp,
        "event_type": event_type,
        "relation": relation,
        "source": source,
        "target": target,
        "attributes": merged,
    }


def _clean_text(value: object, *, limit: int) -> tuple[str | None, bool]:
    if not isinstance(value, str):
        return None, False
    text = value.replace("\x00", "")
    return (text, False) if len(text) <= limit else (text[:limit], True)


def _agent() -> dict[str, Any]:
    return _entity("agent", "agent:OpenCode", name="OpenCode")


def _common(payload: dict[str, Any]) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    for source, target in (
        ("sessionID", "opencode_session_id"),
        ("callID", "opencode_call_id"),
        ("messageID", "opencode_message_id"),
        ("agent", "opencode_agent"),
        ("cwd", "opencode_cwd"),
    ):
        value = payload.get(source)
        if isinstance(value, (str, int, float, bool)) and value != "":
            attrs[target] = value
    return attrs


def _tool_entity(tool: str) -> dict[str, Any]:
    return _entity(
        "tool",
        f"tool:opencode:{tool}",
        name=tool,
        attributes={"provider": "opencode", "native_name": tool},
    )


def _tool_call(payload: dict[str, Any], tool: str) -> dict[str, Any]:
    session_id = payload.get("sessionID")
    call_id = payload.get("callID")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("OpenCode tool hook requires sessionID")
    if not isinstance(call_id, str) or not call_id:
        raise ValueError("OpenCode tool hook requires callID")
    attrs = _common(payload)
    attrs.update({"provider": "opencode", "tool_name": tool, "call_id": call_id})
    safe_args = payload.get("args")
    if isinstance(safe_args, dict):
        attrs["input_keys"] = sorted(str(key) for key in safe_args)
    return _entity(
        "tool_call",
        f"tool-call:opencode:{session_id}:{call_id}",
        name=tool,
        attributes=attrs,
    )


def _command_entity(args: dict[str, Any]) -> dict[str, Any] | None:
    command, truncated = _clean_text(args.get("command"), limit=_MAX_COMMAND_CHARS)
    if not command:
        return None
    digest = hashlib.sha256(command.encode("utf-8", errors="replace")).hexdigest()
    label, _ = _clean_text(command.replace("\n", " "), limit=_MAX_LABEL_CHARS)
    return _entity(
        "command",
        f"command:sha256:{digest}",
        name=label,
        attributes={"command": command, "truncated": truncated},
    )


def _declared_file(payload: dict[str, Any], args: dict[str, Any]) -> dict[str, Any] | None:
    raw = None
    for key in ("filePath", "file_path", "path"):
        value = args.get(key)
        if isinstance(value, str) and value:
            raw = value
            break
    if raw is None:
        return None
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        cwd = payload.get("cwd")
        if isinstance(cwd, str) and cwd:
            candidate = Path(cwd) / candidate
    try:
        normalized = candidate.resolve(strict=False)
    except OSError:
        normalized = candidate.absolute()
    return _entity(
        "file",
        f"file:{normalized}",
        name=normalized.name or str(normalized),
        attributes={"declared_by_provider_plugin": True, "provider": "opencode"},
    )


def _chat_message(payload: dict[str, Any], *, timestamp: str) -> list[dict[str, Any]]:
    model = payload.get("model")
    if not isinstance(model, dict):
        return []
    provider_id = model.get("providerID")
    model_id = model.get("modelID")
    if not isinstance(model_id, str) or not model_id:
        return []
    name = f"{provider_id}/{model_id}" if isinstance(provider_id, str) and provider_id else model_id
    return [
        _event(
            timestamp=timestamp,
            event_type="semantic.opencode.model.observed",
            relation="USED_MODEL",
            source=_agent(),
            target=_entity(
                "model",
                f"model:opencode:{name}",
                name=name,
                attributes={
                    "provider": "opencode",
                    "model_provider_id": provider_id,
                    "model_id": model_id,
                },
            ),
            attributes=_common(payload),
        )
    ]


def _before(payload: dict[str, Any], *, timestamp: str) -> list[dict[str, Any]]:
    tool = payload.get("tool")
    if not isinstance(tool, str) or not tool:
        raise ValueError("OpenCode tool.execute.before requires tool")
    call = _tool_call(payload, tool)
    common = _common(payload)
    events = [
        _event(
            timestamp=timestamp,
            event_type="semantic.opencode.tool.requested",
            relation="REQUESTED_TOOL_CALL",
            source=_agent(),
            target=call,
            attributes=common,
        ),
        _event(
            timestamp=timestamp,
            event_type="semantic.opencode.tool.selected",
            relation="USES_TOOL",
            source=call,
            target=_tool_entity(tool),
            attributes=common,
        ),
    ]
    args = payload.get("args")
    if isinstance(args, dict):
        if tool == "bash":
            command = _command_entity(args)
            if command is not None:
                events.append(
                    _event(
                        timestamp=timestamp,
                        event_type="semantic.opencode.command.declared",
                        relation="DECLARED_COMMAND",
                        source=call,
                        target=command,
                        attributes=common,
                    )
                )
        target = _declared_file(payload, args)
        if target is not None:
            events.append(
                _event(
                    timestamp=timestamp,
                    event_type="semantic.opencode.file.declared",
                    relation="DECLARED_TARGET",
                    source=call,
                    target=target,
                    attributes=common,
                )
            )
    return events


def _after(payload: dict[str, Any], *, timestamp: str) -> list[dict[str, Any]]:
    tool = payload.get("tool")
    if not isinstance(tool, str) or not tool:
        raise ValueError("OpenCode tool.execute.after requires tool")
    call = _tool_call(payload, tool)
    return [
        _event(
            timestamp=timestamp,
            event_type="semantic.opencode.tool.returned",
            relation="TOOL_CALL_RETURNED",
            source=call,
            target=_tool_entity(tool),
            attributes=_common(payload),
        )
    ]


def opencode_plugin_to_semantic_events(
    payload: dict[str, Any],
    *,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    hook_event = payload.get("hook_event_name")
    if not isinstance(hook_event, str) or not hook_event:
        raise ValueError("OpenCode payload requires hook_event_name")
    if hook_event not in _SUPPORTED_EVENTS:
        return []
    observed_at = timestamp or _now()
    if hook_event == "chat.message":
        return _chat_message(payload, timestamp=observed_at)
    if hook_event == "tool.execute.before":
        return _before(payload, timestamp=observed_at)
    return _after(payload, timestamp=observed_at)


def append_semantic_records(path: str | Path, records: list[dict[str, Any]]) -> Path:
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        return output
    blob = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for record in records
    )
    lock_dir = output.with_name(output.name + ".lock")
    deadline = time.monotonic() + 5.0
    while True:
        try:
            lock_dir.mkdir()
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timed out waiting for semantic sidecar lock: {lock_dir}")
            time.sleep(0.01)
    try:
        with output.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(blob)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        try:
            lock_dir.rmdir()
        except OSError:
            pass
    return output


def read_plugin_payload(stream: Any = None) -> dict[str, Any]:
    source = stream if stream is not None else sys.stdin
    raw = source.read()
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("OpenCode plugin stdin is empty")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"OpenCode plugin stdin is invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("OpenCode plugin stdin must be one JSON object")
    return payload
