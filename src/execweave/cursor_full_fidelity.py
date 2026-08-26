from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .content_evidence import content_observation_event, filter_transport_credentials
from .content_store import FullFidelityContentStore

_CONTENT_FIELDS = frozenset(
    {
        "prompt", "text", "task", "summary", "description", "agent_message",
        "tool_input", "tool_output", "error_message", "content", "edits",
        "command", "output", "result_json",
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _entity(kind: str, ident: str, name: str, **attrs: Any) -> dict[str, Any]:
    return {"type": kind, "id": ident, "name": name, "attributes": attrs}


def _agent() -> dict[str, Any]:
    return _entity("agent", "agent:Cursor", "Cursor", provider="cursor")


def _scope(payload: dict[str, Any]) -> str:
    for key in ("conversation_id", "session_id", "generation_id"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return "unknown"


def _tool_call(payload: dict[str, Any], hook: str) -> dict[str, Any]:
    name = payload.get("tool_name") if isinstance(payload.get("tool_name"), str) else "unknown"
    use_id = payload.get("tool_use_id")
    if isinstance(use_id, str) and use_id:
        return _entity(
            "tool_call", f"tool-call:cursor:{_scope(payload)}:{use_id}", name,
            provider="cursor", tool_name=name, tool_use_id=use_id,
            identity_semantics="provider_tool_use_id",
        )
    raw = json.dumps(
        [hook, _scope(payload), name, payload.get("generation_id"), payload.get("tool_input")],
        ensure_ascii=False, sort_keys=True, default=str,
    )
    digest = hashlib.sha256(raw.encode()).hexdigest()[:24]
    return _entity(
        "tool_call_observation", f"tool-call-observation:cursor:{_scope(payload)}:{digest}", name,
        provider="cursor", tool_name=name,
        identity_semantics="provider_hook_observation_without_unique_tool_call_id",
        direct_tool_call_linkage_asserted=False,
    )


def _file(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("file_path") if isinstance(payload.get("file_path"), str) else "unknown"
    candidate = Path(raw).expanduser() if raw != "unknown" else Path(raw)
    try:
        normalized = str(candidate.resolve(strict=False)) if raw != "unknown" else raw
    except OSError:
        normalized = str(candidate.absolute())
    return _entity(
        "file", f"file:{normalized}", Path(normalized).name or normalized,
        provider="cursor", provider_path=raw, declared_by_provider_hook=True,
    )


def _subagent(payload: dict[str, Any], hook: str) -> dict[str, Any]:
    sub_id = payload.get("subagent_id")
    sub_type = payload.get("subagent_type") if isinstance(payload.get("subagent_type"), str) else "Cursor subagent"
    if isinstance(sub_id, str) and sub_id:
        return _entity(
            "agent", f"agent:cursor:{_scope(payload)}:subagent:{sub_id}", sub_type,
            provider="cursor", subagent_id=sub_id, identity_semantics="provider_subagent_id",
        )
    raw = json.dumps(
        [hook, _scope(payload), sub_type, payload.get("task"), payload.get("description"), payload.get("status")],
        ensure_ascii=False, sort_keys=True, default=str,
    )
    digest = hashlib.sha256(raw.encode()).hexdigest()[:24]
    return _entity(
        "subagent_observation", f"subagent-observation:cursor:{_scope(payload)}:{digest}", sub_type,
        provider="cursor", identity_semantics="provider_hook_observation_without_subagent_id",
        direct_start_stop_linkage_asserted=False,
    )


def _observe(
    events: list[dict[str, Any]], store: FullFidelityContentStore, *, value: Any,
    kind: str, timestamp: str, source: dict[str, Any], relation: str,
    field: str, hook: str, **attrs: Any,
) -> None:
    ref = store.put_text(value, content_kind=kind) if isinstance(value, str) else store.put_json(value, content_kind=kind)
    events.append(
        content_observation_event(
            timestamp=timestamp, provider="cursor", source=source, reference=ref,
            relation=relation, observed_field=field, evidence_source="provider_hook",
            attribution="cursor_hook", attributes={"cursor_hook_event_name": hook, **attrs},
        )
    )


def _metadata(
    payload: dict[str, Any], store: FullFidelityContentStore, timestamp: str, hook: str,
) -> dict[str, Any] | None:
    raw = {key: value for key, value in payload.items() if key not in _CONTENT_FIELDS}
    filtered, removed = filter_transport_credentials(raw)
    if not filtered:
        return None
    ref = store.put_json(filtered, content_kind="cursor.provider_hook_metadata")
    return content_observation_event(
        timestamp=timestamp, provider="cursor", source=_agent(), reference=ref,
        relation="OBSERVED_PROVIDER_METADATA", observed_field="hook_metadata",
        evidence_source="provider_hook", attribution="cursor_hook",
        attributes={"cursor_hook_event_name": hook, "transport_credentials_excluded": removed},
    )


def cursor_hook_to_content_events(
    payload: dict[str, Any], *, store: FullFidelityContentStore,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """Persist complete values supplied by Cursor hooks; never read transcript_path."""
    hook = payload.get("hook_event_name")
    if not isinstance(hook, str) or not hook:
        raise ValueError("Cursor hook payload requires hook_event_name")
    ts = timestamp or _now()
    events: list[dict[str, Any]] = []
    metadata = _metadata(payload, store, ts, hook)
    if metadata is not None:
        events.append(metadata)

    if hook == "beforeSubmitPrompt" and isinstance(payload.get("prompt"), str):
        _observe(events, store, value=payload["prompt"], kind="cursor.user_prompt", timestamp=ts,
                 source=_agent(), relation="RECEIVED_USER_PROMPT", field="prompt", hook=hook)

    if hook in {"preToolUse", "postToolUse", "postToolUseFailure"}:
        call = _tool_call(payload, hook)
        if "tool_input" in payload:
            _observe(events, store, value=payload["tool_input"], kind="cursor.tool_input", timestamp=ts,
                     source=call, relation="OBSERVED_TOOL_INPUT", field="tool_input", hook=hook)
        if isinstance(payload.get("agent_message"), str):
            _observe(events, store, value=payload["agent_message"], kind="cursor.agent_message", timestamp=ts,
                     source=call, relation="OBSERVED_AGENT_MESSAGE", field="agent_message", hook=hook)
        if hook == "postToolUse" and "tool_output" in payload:
            _observe(events, store, value=payload["tool_output"], kind="cursor.tool_output", timestamp=ts,
                     source=call, relation="RECEIVED_TOOL_OUTPUT", field="tool_output", hook=hook,
                     provider_value_is_json_stringified_result=True)
        if hook == "postToolUseFailure" and isinstance(payload.get("error_message"), str):
            _observe(events, store, value=payload["error_message"], kind="cursor.tool_failure", timestamp=ts,
                     source=call, relation="RECEIVED_TOOL_ERROR", field="error_message", hook=hook)

    if hook in {"beforeShellExecution", "afterShellExecution"}:
        if isinstance(payload.get("command"), str):
            relation = "OBSERVED_SHELL_COMMAND_BEFORE_EXECUTION" if hook.startswith("before") else "OBSERVED_SHELL_COMMAND_AFTER_EXECUTION"
            _observe(events, store, value=payload["command"], kind="cursor.shell_command", timestamp=ts,
                     source=_agent(), relation=relation, field="command", hook=hook)
        if hook == "afterShellExecution" and isinstance(payload.get("output"), str):
            _observe(events, store, value=payload["output"], kind="cursor.shell_output", timestamp=ts,
                     source=_agent(), relation="RECEIVED_SHELL_OUTPUT", field="output", hook=hook)

    if hook in {"beforeMCPExecution", "afterMCPExecution"}:
        if isinstance(payload.get("command"), str):
            _observe(events, store, value=payload["command"], kind="cursor.mcp_server_command", timestamp=ts,
                     source=_agent(), relation="OBSERVED_MCP_SERVER_COMMAND", field="command", hook=hook,
                     mcp_server_identity_asserted=False)
        if "tool_input" in payload:
            _observe(events, store, value=payload["tool_input"], kind="cursor.mcp_tool_input", timestamp=ts,
                     source=_agent(), relation="OBSERVED_MCP_TOOL_INPUT", field="tool_input", hook=hook)
        if hook == "afterMCPExecution" and "result_json" in payload:
            _observe(events, store, value=payload["result_json"], kind="cursor.mcp_tool_result", timestamp=ts,
                     source=_agent(), relation="RECEIVED_MCP_TOOL_RESULT", field="result_json", hook=hook)

    if hook in {"beforeReadFile", "beforeTabFileRead"} and isinstance(payload.get("content"), str):
        _observe(events, store, value=payload["content"], kind="cursor.file_content_before_read", timestamp=ts,
                 source=_file(payload), relation="OBSERVED_FILE_CONTENT_BEFORE_READ", field="content", hook=hook,
                 read_completion_asserted=False)
    if hook in {"afterFileEdit", "afterTabFileEdit"} and isinstance(payload.get("edits"), list):
        _observe(events, store, value=payload["edits"], kind="cursor.file_edits", timestamp=ts,
                 source=_file(payload), relation="OBSERVED_FILE_EDITS", field="edits", hook=hook,
                 complete_post_edit_file_snapshot_asserted=False)

    if hook in {"afterAgentResponse", "afterAgentThought"} and isinstance(payload.get("text"), str):
        thought = hook == "afterAgentThought"
        _observe(events, store, value=payload["text"], kind="cursor.agent_thought" if thought else "cursor.assistant_response",
                 timestamp=ts, source=_agent(), relation="OBSERVED_AGENT_THOUGHT" if thought else "PRODUCED_ASSISTANT_RESPONSE",
                 field="text", hook=hook, **({"provider_labels_as_thinking_text": True} if thought else {}))

    if hook in {"subagentStart", "subagentStop"}:
        sub = _subagent(payload, hook)
        for field, relation in (("task", "OBSERVED_SUBAGENT_TASK"), ("description", "OBSERVED_SUBAGENT_DESCRIPTION"), ("summary", "RECEIVED_SUBAGENT_SUMMARY")):
            if isinstance(payload.get(field), str) and (field == "task" or hook == "subagentStop"):
                _observe(events, store, value=payload[field], kind=f"cursor.subagent_{field}", timestamp=ts,
                         source=sub, relation=relation, field=field, hook=hook)
    return events
