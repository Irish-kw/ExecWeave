from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from .agent_topology import EVIDENCE_SUBAGENT_LIFECYCLE_HOOK, subagent_topology

_MAX_COMMAND_CHARS = 4096
_MAX_LABEL_CHARS = 160
_SUPPORTED_EVENTS = {
    "SessionStart",
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "SubagentStart",
    "SubagentStop",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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


def _event(
    *,
    timestamp: str,
    event_type: str,
    relation: str,
    source: dict[str, Any],
    target: dict[str, Any],
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged_attributes: dict[str, Any] = {
        "backend": "semantic",
        "attribution": "claude_hook",
        "evidence_source": "provider_hook",
        "provider": "claude",
        "causal": False,
    }
    if attributes:
        merged_attributes.update(attributes)
    return {
        "timestamp": timestamp,
        "event_type": event_type,
        "relation": relation,
        "source": source,
        "target": target,
        "attributes": merged_attributes,
    }


def _clean_text(value: object, *, limit: int) -> tuple[str | None, bool]:
    if not isinstance(value, str):
        return None, False
    text = value.replace("\x00", "")
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _main_agent() -> dict[str, Any]:
    # Matches the runtime collector's stable Claude Code agent identity.
    return _entity("agent", "agent:Claude Code", name="Claude Code")


def _actor(payload: dict[str, Any]) -> dict[str, Any]:
    agent_id = payload.get("agent_id")
    if isinstance(agent_id, str) and agent_id:
        agent_type = payload.get("agent_type")
        name = agent_type if isinstance(agent_type, str) and agent_type else "Claude subagent"
        session_id = payload.get("session_id")
        scope = session_id if isinstance(session_id, str) and session_id else "unknown"
        return _entity(
            "agent",
            f"agent:claude:{scope}:subagent:{agent_id}",
            name=name,
            attributes={
                "provider": "claude",
                "agent_id": agent_id,
                "agent_type": name,
                **subagent_topology(
                    evidence=EVIDENCE_SUBAGENT_LIFECYCLE_HOOK,
                    parent_scope_id=scope,
                ),
            },
        )
    return _main_agent()


def _common_attributes(payload: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ("session_id", "prompt_id", "cwd", "permission_mode", "agent_id", "agent_type"):
        value = payload.get(key)
        if isinstance(value, (str, int, float, bool)) and value != "":
            result[f"claude_{key}"] = value
    return result


def _parse_mcp_tool(tool_name: str) -> tuple[str, str] | None:
    if not tool_name.startswith("mcp__"):
        return None
    body = tool_name[5:]
    if "__" not in body:
        return None
    server, tool = body.split("__", 1)
    if not server or not tool:
        return None
    return server, tool


def _tool_entity(tool_name: str) -> dict[str, Any]:
    mcp = _parse_mcp_tool(tool_name)
    if mcp is None:
        return _entity(
            "tool",
            f"tool:claude:{tool_name}",
            name=tool_name,
            attributes={"provider": "claude", "native_name": tool_name},
        )
    server, tool = mcp
    return _entity(
        "tool",
        f"tool:mcp:{server}:{tool}",
        name=tool,
        attributes={
            "provider": "claude",
            "native_name": tool_name,
            "mcp_server": server,
        },
    )


def _tool_call_entity(payload: dict[str, Any], tool_name: str) -> dict[str, Any]:
    session_id = payload.get("session_id")
    tool_use_id = payload.get("tool_use_id")
    session = session_id if isinstance(session_id, str) and session_id else "unknown"
    use_id = tool_use_id if isinstance(tool_use_id, str) and tool_use_id else "unknown"
    attrs = _common_attributes(payload)
    attrs.update({"provider": "claude", "tool_name": tool_name, "tool_use_id": use_id})
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        attrs["input_keys"] = sorted(str(key) for key in tool_input)
    return _entity(
        "tool_call",
        f"tool-call:claude:{session}:{use_id}",
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
    return _entity(
        "file",
        f"file:{normalized}",
        name=normalized.name or str(normalized),
        attributes={"declared_by_provider_hook": True},
    )


def _tool_pre_events(payload: dict[str, Any], *, timestamp: str) -> list[dict[str, Any]]:
    tool_name = payload.get("tool_name")
    tool_use_id = payload.get("tool_use_id")
    if not isinstance(tool_name, str) or not tool_name:
        raise ValueError("PreToolUse requires tool_name")
    if not isinstance(tool_use_id, str) or not tool_use_id:
        raise ValueError("PreToolUse requires tool_use_id")

    actor = _actor(payload)
    call = _tool_call_entity(payload, tool_name)
    tool = _tool_entity(tool_name)
    common = _common_attributes(payload)
    events = [
        _event(
            timestamp=timestamp,
            event_type="semantic.claude.tool.requested",
            relation="REQUESTED_TOOL_CALL",
            source=actor,
            target=call,
            attributes=common,
        ),
        _event(
            timestamp=timestamp,
            event_type="semantic.claude.tool.selected",
            relation="USES_TOOL",
            source=call,
            target=tool,
            attributes=common,
        ),
    ]

    mcp = _parse_mcp_tool(tool_name)
    if mcp is not None:
        server, _ = mcp
        mcp_entity = _entity(
            "mcp_server",
            f"mcp-server:claude:{server}",
            name=server,
            attributes={"provider": "claude", "server_segment": server},
        )
        events.extend(
            [
                _event(
                    timestamp=timestamp,
                    event_type="semantic.claude.mcp.call",
                    relation="VIA_MCP",
                    source=call,
                    target=mcp_entity,
                    attributes=common,
                ),
                _event(
                    timestamp=timestamp,
                    event_type="semantic.claude.mcp.tool",
                    relation="EXPOSES_TOOL",
                    source=mcp_entity,
                    target=tool,
                    attributes=common,
                ),
            ]
        )

    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        if tool_name in {"Bash", "PowerShell"}:
            command = _command_entity(tool_input)
            if command is not None:
                events.append(
                    _event(
                        timestamp=timestamp,
                        event_type="semantic.claude.command.declared",
                        relation="DECLARED_COMMAND",
                        source=call,
                        target=command,
                        attributes=common,
                    )
                )
        if tool_name in {"Read", "Edit", "Write", "NotebookEdit"}:
            target_file = _declared_file_entity(payload, tool_input)
            if target_file is not None:
                events.append(
                    _event(
                        timestamp=timestamp,
                        event_type="semantic.claude.file.declared",
                        relation="DECLARED_TARGET",
                        source=call,
                        target=target_file,
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
    tool_use_id = payload.get("tool_use_id")
    if not isinstance(tool_name, str) or not tool_name:
        raise ValueError("tool result hook requires tool_name")
    if not isinstance(tool_use_id, str) or not tool_use_id:
        raise ValueError("tool result hook requires tool_use_id")
    call = _tool_call_entity(payload, tool_name)
    tool = _tool_entity(tool_name)
    attrs = _common_attributes(payload)
    duration = payload.get("duration_ms")
    if isinstance(duration, (int, float)) and not isinstance(duration, bool):
        attrs["duration_ms"] = duration
    if not success:
        attrs["is_interrupt"] = bool(payload.get("is_interrupt", False))
        error, truncated = _clean_text(payload.get("error"), limit=1024)
        if error:
            attrs["error_summary"] = error
            attrs["error_summary_truncated"] = truncated
    return [
        _event(
            timestamp=timestamp,
            event_type=(
                "semantic.claude.tool.succeeded" if success else "semantic.claude.tool.failed"
            ),
            relation="TOOL_CALL_SUCCEEDED" if success else "TOOL_CALL_FAILED",
            source=call,
            target=tool,
            attributes=attrs,
        )
    ]


def _session_start_events(payload: dict[str, Any], *, timestamp: str) -> list[dict[str, Any]]:
    model = payload.get("model")
    if not isinstance(model, str) or not model:
        return []
    return [
        _event(
            timestamp=timestamp,
            event_type="semantic.claude.model.observed",
            relation="USED_MODEL",
            source=_main_agent(),
            target=_entity("model", f"model:claude:{model}", name=model, attributes={"provider": "claude"}),
            attributes=_common_attributes(payload),
        )
    ]


def _subagent_start_events(payload: dict[str, Any], *, timestamp: str) -> list[dict[str, Any]]:
    agent_id = payload.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id:
        raise ValueError("SubagentStart requires agent_id")
    child = _actor(payload)
    return [
        _event(
            timestamp=timestamp,
            event_type="semantic.claude.subagent.started",
            relation="SPAWNED_SUBAGENT",
            source=_main_agent(),
            target=child,
            attributes=_common_attributes(payload),
        )
    ]


def _subagent_stop_events(payload: dict[str, Any], *, timestamp: str) -> list[dict[str, Any]]:
    agent_id = payload.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id:
        raise ValueError("SubagentStop requires agent_id")
    child = _actor(payload)
    return [
        _event(
            timestamp=timestamp,
            event_type="semantic.claude.subagent.finished",
            relation="RETURNED_TO",
            source=child,
            target=_main_agent(),
            attributes=_common_attributes(payload),
        )
    ]


def claude_hook_to_semantic_events(
    payload: dict[str, Any],
    *,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    hook_event = payload.get("hook_event_name")
    if not isinstance(hook_event, str) or not hook_event:
        raise ValueError("Claude hook payload requires hook_event_name")
    if hook_event not in _SUPPORTED_EVENTS:
        return []
    observed_at = timestamp or _now()
    if hook_event == "SessionStart":
        return _session_start_events(payload, timestamp=observed_at)
    if hook_event == "PreToolUse":
        return _tool_pre_events(payload, timestamp=observed_at)
    if hook_event == "PostToolUse":
        return _tool_result_events(payload, timestamp=observed_at, success=True)
    if hook_event == "PostToolUseFailure":
        return _tool_result_events(payload, timestamp=observed_at, success=False)
    if hook_event == "SubagentStart":
        return _subagent_start_events(payload, timestamp=observed_at)
    if hook_event == "SubagentStop":
        return _subagent_stop_events(payload, timestamp=observed_at)
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
        raise ValueError("Claude hook stdin is empty")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Claude hook stdin is invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Claude hook stdin must be one JSON object")
    return payload
