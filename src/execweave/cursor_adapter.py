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
_SUPPORTED_EVENTS = {"sessionStart", "preToolUse", "postToolUse", "postToolUseFailure"}


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
        "attribution": "cursor_hook",
        "evidence_source": "provider_hook",
        "provider": "cursor",
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
    return _entity("agent", "agent:Cursor", name="Cursor")


def _scope(payload: dict[str, Any]) -> str:
    for key in ("conversation_id", "session_id", "generation_id"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return "unknown"


def _common_attributes(payload: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in (
        "conversation_id",
        "generation_id",
        "session_id",
        "cursor_version",
        "cwd",
        "model",
        "model_id",
    ):
        value = payload.get(key)
        if isinstance(value, (str, int, float, bool)) and value != "":
            result[f"cursor_{key}"] = value
    roots = payload.get("workspace_roots")
    if isinstance(roots, list):
        result["cursor_workspace_root_count"] = len(roots)
    return result


def _tool_entity(tool_name: str) -> dict[str, Any]:
    if tool_name.startswith("MCP:"):
        native = tool_name[4:] or tool_name
        return _entity(
            "tool",
            f"tool:cursor:mcp:{native}",
            name=native,
            attributes={
                "provider": "cursor",
                "native_name": tool_name,
                "mcp_tool": True,
                "mcp_server_identity_available": False,
            },
        )
    return _entity(
        "tool",
        f"tool:cursor:{tool_name}",
        name=tool_name,
        attributes={"provider": "cursor", "native_name": tool_name},
    )


def _tool_call_entity(payload: dict[str, Any], tool_name: str) -> dict[str, Any]:
    tool_use_id = payload.get("tool_use_id")
    if not isinstance(tool_use_id, str) or not tool_use_id:
        raise ValueError("Cursor tool hook requires tool_use_id")
    attrs = _common_attributes(payload)
    attrs.update({"provider": "cursor", "tool_name": tool_name, "tool_use_id": tool_use_id})
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        attrs["input_keys"] = sorted(str(key) for key in tool_input)
    return _entity(
        "tool_call",
        f"tool-call:cursor:{_scope(payload)}:{tool_use_id}",
        name=tool_name,
        attributes=attrs,
    )


def _command_entity(tool_input: dict[str, Any]) -> dict[str, Any] | None:
    command, truncated = _clean_text(tool_input.get("command"), limit=_MAX_COMMAND_CHARS)
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


def _declared_file_entity(payload: dict[str, Any], tool_input: dict[str, Any]) -> dict[str, Any] | None:
    raw = None
    for key in ("file_path", "filePath", "path", "notebook_path", "notebookPath"):
        candidate = tool_input.get(key)
        if isinstance(candidate, str) and candidate:
            raw = candidate
            break
    if not isinstance(raw, str) or not raw:
        return None
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        cwd = payload.get("cwd")
        if not isinstance(cwd, str) or not cwd:
            cwd = tool_input.get("working_directory")
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
        attributes={"declared_by_provider_hook": True, "provider": "cursor"},
    )


def _session_start_events(payload: dict[str, Any], *, timestamp: str) -> list[dict[str, Any]]:
    model = payload.get("model_id")
    if not isinstance(model, str) or not model:
        model = payload.get("model")
    if not isinstance(model, str) or not model:
        return []
    return [
        _event(
            timestamp=timestamp,
            event_type="semantic.cursor.model.observed",
            relation="USED_MODEL",
            source=_agent(),
            target=_entity(
                "model",
                f"model:cursor:{model}",
                name=model,
                attributes={"provider": "cursor"},
            ),
            attributes=_common_attributes(payload),
        )
    ]


def _pre_tool_events(payload: dict[str, Any], *, timestamp: str) -> list[dict[str, Any]]:
    tool_name = payload.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name:
        raise ValueError("Cursor preToolUse requires tool_name")
    call = _tool_call_entity(payload, tool_name)
    tool = _tool_entity(tool_name)
    common = _common_attributes(payload)
    events = [
        _event(
            timestamp=timestamp,
            event_type="semantic.cursor.tool.requested",
            relation="REQUESTED_TOOL_CALL",
            source=_agent(),
            target=call,
            attributes=common,
        ),
        _event(
            timestamp=timestamp,
            event_type="semantic.cursor.tool.selected",
            relation="USES_TOOL",
            source=call,
            target=tool,
            attributes=common,
        ),
    ]
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        if tool_name == "Shell":
            command = _command_entity(tool_input)
            if command is not None:
                events.append(
                    _event(
                        timestamp=timestamp,
                        event_type="semantic.cursor.command.declared",
                        relation="DECLARED_COMMAND",
                        source=call,
                        target=command,
                        attributes=common,
                    )
                )
        if tool_name.strip().lower() in {"read", "edit", "write", "delete", "notebookedit"}:
            target = _declared_file_entity(payload, tool_input)
            if target is not None:
                events.append(
                    _event(
                        timestamp=timestamp,
                        event_type="semantic.cursor.file.declared",
                        relation="DECLARED_TARGET",
                        source=call,
                        target=target,
                        attributes=common,
                    )
                )
    return events


def _tool_result_events(
    payload: dict[str, Any],
    *,
    timestamp: str,
    success: bool,
) -> list[dict[str, Any]]:
    tool_name = payload.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name:
        raise ValueError("Cursor tool result hook requires tool_name")
    call = _tool_call_entity(payload, tool_name)
    attrs = _common_attributes(payload)
    if not success:
        attrs["provider_reported_failure"] = True
    return [
        _event(
            timestamp=timestamp,
            event_type=(
                "semantic.cursor.tool.returned" if success else "semantic.cursor.tool.failed"
            ),
            relation="TOOL_CALL_RETURNED" if success else "TOOL_CALL_FAILED",
            source=call,
            target=_tool_entity(tool_name),
            attributes=attrs,
        )
    ]


def cursor_hook_to_semantic_events(
    payload: dict[str, Any],
    *,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    hook_event = payload.get("hook_event_name")
    if not isinstance(hook_event, str) or not hook_event:
        raise ValueError("Cursor hook payload requires hook_event_name")
    if hook_event not in _SUPPORTED_EVENTS:
        return []
    observed_at = timestamp or _now()
    if hook_event == "sessionStart":
        return _session_start_events(payload, timestamp=observed_at)
    if hook_event == "preToolUse":
        return _pre_tool_events(payload, timestamp=observed_at)
    if hook_event == "postToolUse":
        return _tool_result_events(payload, timestamp=observed_at, success=True)
    if hook_event == "postToolUseFailure":
        return _tool_result_events(payload, timestamp=observed_at, success=False)
    return []


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


def read_hook_payload(stream: Any = None) -> dict[str, Any]:
    source = stream if stream is not None else sys.stdin
    raw = source.read()
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Cursor hook stdin is empty")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Cursor hook stdin is invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Cursor hook stdin must be one JSON object")
    return payload
