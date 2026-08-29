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
        "attribution": "codex_hook",
        "evidence_source": "provider_hook",
        "provider": "codex",
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
    return _entity("agent", "agent:OpenAI Codex", name="OpenAI Codex")


def _actor(payload: dict[str, Any]) -> dict[str, Any]:
    agent_id = payload.get("agent_id")
    if isinstance(agent_id, str) and agent_id:
        agent_type = payload.get("agent_type")
        name = agent_type if isinstance(agent_type, str) and agent_type else "Codex subagent"
        session_id = payload.get("session_id")
        scope = session_id if isinstance(session_id, str) and session_id else "unknown"
        return _entity(
            "agent",
            f"agent:codex:{scope}:subagent:{agent_id}",
            name=name,
            attributes={
                "provider": "codex",
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
    for key in (
        "session_id",
        "turn_id",
        "cwd",
        "permission_mode",
        "agent_id",
        "agent_type",
        "model",
    ):
        value = payload.get(key)
        if isinstance(value, (str, int, float, bool)) and value != "":
            result[f"codex_{key}"] = value
    return result


def _tool_entity(tool_name: str) -> dict[str, Any]:
    return _entity(
        "tool",
        f"tool:codex:{tool_name}",
        name=tool_name,
        attributes={"provider": "codex", "native_name": tool_name},
    )


def _tool_call_entity(payload: dict[str, Any], tool_name: str) -> dict[str, Any]:
    session_id = payload.get("session_id")
    tool_use_id = payload.get("tool_use_id")
    session = session_id if isinstance(session_id, str) and session_id else "unknown"
    use_id = tool_use_id if isinstance(tool_use_id, str) and tool_use_id else "unknown"
    attrs = _common_attributes(payload)
    attrs.update({"provider": "codex", "tool_name": tool_name, "tool_use_id": use_id})
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        attrs["input_keys"] = sorted(str(key) for key in tool_input)
    return _entity(
        "tool_call",
        f"tool-call:codex:{session}:{use_id}",
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


def _session_start_events(payload: dict[str, Any], *, timestamp: str) -> list[dict[str, Any]]:
    model = payload.get("model")
    if not isinstance(model, str) or not model:
        return []
    attrs = _common_attributes(payload)
    source = payload.get("source")
    if isinstance(source, str) and source:
        attrs["codex_session_source"] = source
    return [
        _event(
            timestamp=timestamp,
            event_type="semantic.codex.model.observed",
            relation="USED_MODEL",
            source=_main_agent(),
            target=_entity(
                "model",
                f"model:codex:{model}",
                name=model,
                attributes={"provider": "codex"},
            ),
            attributes=attrs,
        )
    ]


def _subagent_start_events(payload: dict[str, Any], *, timestamp: str) -> list[dict[str, Any]]:
    agent_id = payload.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id:
        raise ValueError("SubagentStart requires agent_id")
    attrs = _common_attributes(payload)
    attrs["lifecycle"] = "started"
    attrs["identity_semantics"] = (
        "Codex hook exposes child identity but not the parent subagent identity; "
        "root attribution is hook-level only"
    )
    return [
        _event(
            timestamp=timestamp,
            event_type="semantic.codex.subagent.started",
            relation="SPAWNED_AGENT",
            source=_main_agent(),
            target=_actor(payload),
            attributes=attrs,
        )
    ]


def _subagent_stop_events(payload: dict[str, Any], *, timestamp: str) -> list[dict[str, Any]]:
    agent_id = payload.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id:
        raise ValueError("SubagentStop requires agent_id")
    attrs = _common_attributes(payload)
    attrs["lifecycle"] = "stopped"
    return [
        _event(
            timestamp=timestamp,
            event_type="semantic.codex.subagent.stopped",
            relation="SUBAGENT_STOPPED",
            source=_actor(payload),
            target=_main_agent(),
            attributes=attrs,
        )
    ]


def _tool_pre_events(payload: dict[str, Any], *, timestamp: str) -> list[dict[str, Any]]:
    tool_name = payload.get("tool_name")
    tool_use_id = payload.get("tool_use_id")
    if not isinstance(tool_name, str) or not tool_name:
        raise ValueError("PreToolUse requires tool_name")
    if not isinstance(tool_use_id, str) or not tool_use_id:
        raise ValueError("PreToolUse requires tool_use_id")

    call = _tool_call_entity(payload, tool_name)
    tool = _tool_entity(tool_name)
    common = _common_attributes(payload)
    events = [
        _event(
            timestamp=timestamp,
            event_type="semantic.codex.tool.requested",
            relation="REQUESTED_TOOL_CALL",
            source=_actor(payload),
            target=call,
            attributes=common,
        ),
        _event(
            timestamp=timestamp,
            event_type="semantic.codex.tool.selected",
            relation="USES_TOOL",
            source=call,
            target=tool,
            attributes=common,
        ),
    ]

    tool_input = payload.get("tool_input")
    if tool_name == "Bash" and isinstance(tool_input, dict):
        command = _command_entity(tool_input)
        if command is not None:
            events.append(
                _event(
                    timestamp=timestamp,
                    event_type="semantic.codex.command.declared",
                    relation="DECLARED_COMMAND",
                    source=call,
                    target=command,
                    attributes=common,
                )
            )
    return events


def _tool_post_events(payload: dict[str, Any], *, timestamp: str) -> list[dict[str, Any]]:
    tool_name = payload.get("tool_name")
    tool_use_id = payload.get("tool_use_id")
    if not isinstance(tool_name, str) or not tool_name:
        raise ValueError("PostToolUse requires tool_name")
    if not isinstance(tool_use_id, str) or not tool_use_id:
        raise ValueError("PostToolUse requires tool_use_id")

    attrs = _common_attributes(payload)
    response = payload.get("tool_response")
    if isinstance(response, str):
        attrs["tool_response_type"] = "string"
        attrs["tool_response_chars"] = len(response)
    elif response is not None:
        attrs["tool_response_type"] = type(response).__name__
    attrs["outcome_semantics"] = "provider_reported_completion_without_reliable_success_signal"
    return [
        _event(
            timestamp=timestamp,
            event_type="semantic.codex.tool.returned",
            relation="TOOL_CALL_RETURNED",
            source=_tool_call_entity(payload, tool_name),
            target=_tool_entity(tool_name),
            attributes=attrs,
        )
    ]


def codex_hook_to_semantic_events(
    payload: dict[str, Any],
    *,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    hook_event = payload.get("hook_event_name")
    if not isinstance(hook_event, str) or not hook_event:
        raise ValueError("Codex hook payload requires hook_event_name")
    if hook_event not in _SUPPORTED_EVENTS:
        return []
    observed_at = timestamp or _now()
    if hook_event == "SessionStart":
        return _session_start_events(payload, timestamp=observed_at)
    if hook_event == "PreToolUse":
        return _tool_pre_events(payload, timestamp=observed_at)
    if hook_event == "PostToolUse":
        return _tool_post_events(payload, timestamp=observed_at)
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
        raise ValueError("Codex hook stdin is empty")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Codex hook stdin is invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Codex hook stdin must be one JSON object")
    return payload
