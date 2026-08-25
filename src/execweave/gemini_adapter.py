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
_SUPPORTED_EVENTS = {"SessionStart", "BeforeTool", "AfterTool"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _entity(entity_type: str, entity_id: str, *, name: str | None = None, attributes: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"type": entity_type, "id": entity_id, "name": name, "attributes": attributes or {}}


def _event(*, timestamp: str, event_type: str, relation: str, source: dict[str, Any], target: dict[str, Any], attributes: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = {
        "backend": "semantic",
        "attribution": "gemini_hook",
        "evidence_source": "provider_hook",
        "provider": "gemini",
        "causal": False,
    }
    if attributes:
        merged.update(attributes)
    return {"timestamp": timestamp, "event_type": event_type, "relation": relation, "source": source, "target": target, "attributes": merged}


def _clean_text(value: object, *, limit: int) -> tuple[str | None, bool]:
    if not isinstance(value, str):
        return None, False
    text = value.replace("\x00", "")
    return (text, False) if len(text) <= limit else (text[:limit], True)


def _main_agent() -> dict[str, Any]:
    return _entity("agent", "agent:Gemini CLI", name="Gemini CLI")


def _common_attributes(payload: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ("session_id", "cwd", "original_request_name"):
        value = payload.get(key)
        if isinstance(value, (str, int, float, bool)) and value != "":
            result[f"gemini_{key}"] = value
    return result


def _canonical_tool_input(value: object) -> str:
    if not isinstance(value, dict):
        return "{}"
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _tool_fingerprint(tool_name: str, tool_input: object) -> str:
    raw = tool_name + "\0" + _canonical_tool_input(tool_input)
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def _tool_call_entity(payload: dict[str, Any], tool_name: str, *, timestamp: str) -> dict[str, Any]:
    session_id = payload.get("session_id")
    session = session_id if isinstance(session_id, str) and session_id else "unknown"
    fingerprint = _tool_fingerprint(tool_name, payload.get("tool_input"))
    raw = session + "\0" + timestamp + "\0" + fingerprint
    identity = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:24]
    attrs = _common_attributes(payload)
    attrs.update({
        "provider": "gemini",
        "tool_name": tool_name,
        "tool_fingerprint": fingerprint,
        "identity_semantics": "provider_hook_without_unique_tool_call_id",
    })
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        attrs["input_keys"] = sorted(str(key) for key in tool_input)
    return _entity("tool_call", f"tool-call:gemini:{session}:{identity}", name=tool_name, attributes=attrs)


def _mcp_identity(payload: dict[str, Any]) -> tuple[str, str] | None:
    context = payload.get("mcp_context")
    if not isinstance(context, dict):
        return None
    server = context.get("server_name")
    tool = context.get("tool_name")
    if not isinstance(server, str) or not server or not isinstance(tool, str) or not tool:
        return None
    return server, tool


def _tool_entity(payload: dict[str, Any], tool_name: str) -> dict[str, Any]:
    mcp = _mcp_identity(payload)
    if mcp is None:
        return _entity("tool", f"tool:gemini:{tool_name}", name=tool_name, attributes={"provider": "gemini", "native_name": tool_name})
    server, tool = mcp
    return _entity("tool", f"tool:mcp:{server}:{tool}", name=tool, attributes={"provider": "gemini", "native_name": tool_name, "mcp_server": server})


def _command_entity(tool_input: dict[str, Any]) -> dict[str, Any] | None:
    command, truncated = _clean_text(tool_input.get("command"), limit=_MAX_COMMAND_CHARS)
    if not command:
        return None
    digest = hashlib.sha256(command.encode("utf-8", errors="replace")).hexdigest()
    label, _ = _clean_text(command.replace("\n", " "), limit=_MAX_LABEL_CHARS)
    return _entity("command", f"command:sha256:{digest}", name=label, attributes={"command": command, "truncated": truncated})


def _declared_file_entity(payload: dict[str, Any], tool_input: dict[str, Any]) -> dict[str, Any] | None:
    raw = tool_input.get("file_path")
    if not isinstance(raw, str) or not raw:
        raw = tool_input.get("path")
    if not isinstance(raw, str) or not raw:
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
    return _entity("file", f"file:{normalized}", name=normalized.name or str(normalized), attributes={"declared_by_provider_hook": True, "provider": "gemini"})


def _session_start_events(payload: dict[str, Any], *, timestamp: str) -> list[dict[str, Any]]:
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("SessionStart requires session_id")
    attrs = _common_attributes(payload)
    source = payload.get("source")
    if isinstance(source, str) and source:
        attrs["gemini_session_source"] = source
    session = _entity("provider_session", f"provider-session:gemini:{session_id}", name=session_id, attributes={"provider": "gemini"})
    return [_event(timestamp=timestamp, event_type="semantic.gemini.session.started", relation="STARTED_PROVIDER_SESSION", source=_main_agent(), target=session, attributes=attrs)]


def _before_tool_events(payload: dict[str, Any], *, timestamp: str) -> list[dict[str, Any]]:
    tool_name = payload.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name:
        raise ValueError("BeforeTool requires tool_name")
    call = _tool_call_entity(payload, tool_name, timestamp=timestamp)
    tool = _tool_entity(payload, tool_name)
    common = _common_attributes(payload)
    common["tool_identity_semantics"] = "provider_hook_without_unique_tool_call_id"
    events = [
        _event(timestamp=timestamp, event_type="semantic.gemini.tool.requested", relation="REQUESTED_TOOL_CALL", source=_main_agent(), target=call, attributes=common),
        _event(timestamp=timestamp, event_type="semantic.gemini.tool.selected", relation="USES_TOOL", source=call, target=tool, attributes=common),
    ]
    mcp = _mcp_identity(payload)
    if mcp is not None:
        server, _ = mcp
        mcp_entity = _entity("mcp_server", f"mcp-server:gemini:{server}", name=server, attributes={"provider": "gemini"})
        events.extend([
            _event(timestamp=timestamp, event_type="semantic.gemini.mcp.call", relation="VIA_MCP", source=call, target=mcp_entity, attributes=common),
            _event(timestamp=timestamp, event_type="semantic.gemini.mcp.tool", relation="EXPOSES_TOOL", source=mcp_entity, target=tool, attributes=common),
        ])
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        if tool_name == "run_shell_command":
            command = _command_entity(tool_input)
            if command is not None:
                events.append(_event(timestamp=timestamp, event_type="semantic.gemini.command.declared", relation="DECLARED_COMMAND", source=call, target=command, attributes=common))
        if tool_name in {"read_file", "write_file", "replace"}:
            target_file = _declared_file_entity(payload, tool_input)
            if target_file is not None:
                events.append(_event(timestamp=timestamp, event_type="semantic.gemini.file.declared", relation="DECLARED_TARGET", source=call, target=target_file, attributes=common))
    return events


def _after_tool_events(payload: dict[str, Any], *, timestamp: str) -> list[dict[str, Any]]:
    tool_name = payload.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name:
        raise ValueError("AfterTool requires tool_name")
    fingerprint = _tool_fingerprint(tool_name, payload.get("tool_input"))
    session_id = payload.get("session_id")
    session = session_id if isinstance(session_id, str) and session_id else "unknown"
    raw = session + "\0" + timestamp + "\0" + fingerprint
    result_id = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:24]
    attrs = _common_attributes(payload)
    attrs.update({
        "tool_fingerprint": fingerprint,
        "result_identity_semantics": "provider_hook_without_unique_tool_call_id; no direct BeforeTool linkage asserted",
    })
    response = payload.get("tool_response")
    has_error = False
    if isinstance(response, dict):
        attrs["tool_response_keys"] = sorted(str(key) for key in response)
        error = response.get("error")
        has_error = error not in (None, "", False)
        attrs["provider_reported_error"] = has_error
        if has_error:
            attrs["provider_error_type"] = type(error).__name__
    elif response is not None:
        attrs["tool_response_type"] = type(response).__name__
    result = _entity("tool_result", f"tool-result:gemini:{session}:{result_id}", name=f"{tool_name} result", attributes={"provider": "gemini", "tool_name": tool_name, "tool_fingerprint": fingerprint})
    return [_event(timestamp=timestamp, event_type="semantic.gemini.tool.reported_error" if has_error else "semantic.gemini.tool.returned", relation="TOOL_RESULT_REPORTED_ERROR" if has_error else "TOOL_RESULT_RETURNED", source=_tool_entity(payload, tool_name), target=result, attributes=attrs)]


def gemini_hook_to_semantic_events(payload: dict[str, Any], *, timestamp: str | None = None) -> list[dict[str, Any]]:
    hook_event = payload.get("hook_event_name")
    if not isinstance(hook_event, str) or not hook_event:
        raise ValueError("Gemini hook payload requires hook_event_name")
    if hook_event not in _SUPPORTED_EVENTS:
        return []
    provider_timestamp = payload.get("timestamp")
    observed_at = timestamp or (provider_timestamp if isinstance(provider_timestamp, str) and provider_timestamp else None) or _now()
    if hook_event == "SessionStart":
        return _session_start_events(payload, timestamp=observed_at)
    if hook_event == "BeforeTool":
        return _before_tool_events(payload, timestamp=observed_at)
    if hook_event == "AfterTool":
        return _after_tool_events(payload, timestamp=observed_at)
    return []


def append_semantic_records(path: str | Path, records: list[dict[str, Any]]) -> Path:
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        return output
    blob = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for record in records)
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
        raise ValueError("Gemini hook stdin is empty")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Gemini hook stdin is invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Gemini hook stdin must be one JSON object")
    return payload
