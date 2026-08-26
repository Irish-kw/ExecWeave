from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from .content_evidence import content_observation_event, filter_transport_credentials
from .content_store import FullFidelityContentStore

_CONTENT_FIELDS = frozenset(
    {
        "message", "parts", "messages", "system", "args", "result", "error",
        "text", "command", "arguments", "command_parts", "params", "headers",
        "description", "parameters", "context", "prompt", "event", "permission",
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _entity(kind: str, ident: str, name: str, **attrs: Any) -> dict[str, Any]:
    return {"type": kind, "id": ident, "name": name, "attributes": attrs}


def _agent() -> dict[str, Any]:
    return _entity("agent", "agent:OpenCode", "OpenCode", provider="opencode")


def _scope(payload: dict[str, Any]) -> str:
    value = payload.get("sessionID")
    return value if isinstance(value, str) and value else "unscoped"


def _tool_call(payload: dict[str, Any]) -> dict[str, Any]:
    tool = payload.get("tool") if isinstance(payload.get("tool"), str) else "unknown"
    call_id = payload.get("callID")
    if isinstance(call_id, str) and call_id:
        return _entity(
            "tool_call",
            f"tool-call:opencode:{_scope(payload)}:{call_id}",
            tool,
            provider="opencode",
            tool_name=tool,
            call_id=call_id,
            identity_semantics="provider_call_id",
        )
    raw = json.dumps([payload.get("hook_event_name"), _scope(payload), tool, payload.get("args")], ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(raw.encode()).hexdigest()[:24]
    return _entity(
        "tool_call_observation",
        f"tool-call-observation:opencode:{_scope(payload)}:{digest}",
        tool,
        provider="opencode",
        tool_name=tool,
        identity_semantics="provider_observation_without_call_id",
        direct_tool_call_linkage_asserted=False,
    )


def _store(store: FullFidelityContentStore, value: Any, kind: str):
    return store.put_text(value, content_kind=kind) if isinstance(value, str) else store.put_json(value, content_kind=kind)


def _observe(
    events: list[dict[str, Any]], store: FullFidelityContentStore, *, value: Any,
    kind: str, timestamp: str, source: dict[str, Any], relation: str, field: str,
    hook: str, **attrs: Any,
) -> None:
    ref = _store(store, value, kind)
    events.append(content_observation_event(
        timestamp=timestamp,
        provider="opencode",
        source=source,
        reference=ref,
        relation=relation,
        observed_field=field,
        evidence_source="provider_plugin",
        attribution="opencode_plugin",
        attributes={"opencode_hook_event_name": hook, **attrs},
    ))


def _metadata(payload: dict[str, Any], store: FullFidelityContentStore, timestamp: str, hook: str):
    raw = {key: value for key, value in payload.items() if key not in _CONTENT_FIELDS}
    filtered, removed = filter_transport_credentials(raw)
    if not filtered:
        return None
    ref = store.put_json(filtered, content_kind="opencode.provider_plugin_metadata")
    return content_observation_event(
        timestamp=timestamp,
        provider="opencode",
        source=_agent(),
        reference=ref,
        relation="OBSERVED_PROVIDER_METADATA",
        observed_field="plugin_metadata",
        evidence_source="provider_plugin",
        attribution="opencode_plugin",
        attributes={"opencode_hook_event_name": hook, "transport_credentials_excluded": removed},
    )


def opencode_plugin_to_content_events(
    payload: dict[str, Any], *, store: FullFidelityContentStore, timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """Persist complete values supplied by OpenCode plugin hooks; no transcript or TLS interception."""
    hook = payload.get("hook_event_name")
    if not isinstance(hook, str) or not hook:
        raise ValueError("OpenCode payload requires hook_event_name")
    ts = timestamp or _now()
    events: list[dict[str, Any]] = []
    metadata = _metadata(payload, store, ts, hook)
    if metadata is not None:
        events.append(metadata)

    if hook == "chat.message":
        if "message" in payload:
            _observe(events, store, value=payload["message"], kind="opencode.user_message", timestamp=ts,
                     source=_agent(), relation="OBSERVED_CHAT_MESSAGE", field="message", hook=hook)
        if "parts" in payload:
            _observe(events, store, value=payload["parts"], kind="opencode.user_message_parts", timestamp=ts,
                     source=_agent(), relation="OBSERVED_CHAT_MESSAGE_PARTS", field="parts", hook=hook)

    if hook == "chat.params":
        if "message" in payload:
            _observe(events, store, value=payload["message"], kind="opencode.inference_message", timestamp=ts,
                     source=_agent(), relation="OBSERVED_INFERENCE_MESSAGE", field="message", hook=hook)
        if "params" in payload:
            _observe(events, store, value=payload["params"], kind="opencode.inference_parameters", timestamp=ts,
                     source=_agent(), relation="OBSERVED_INFERENCE_PARAMETERS", field="params", hook=hook)

    if hook == "chat.headers" and isinstance(payload.get("headers"), dict):
        headers, removed = filter_transport_credentials(payload["headers"])
        _observe(events, store, value=headers, kind="opencode.request_headers_without_credentials", timestamp=ts,
                 source=_agent(), relation="OBSERVED_REQUEST_HEADERS", field="headers", hook=hook,
                 transport_credentials_excluded=removed)

    if hook in {"tool.execute.before", "tool.execute.after"}:
        call = _tool_call(payload)
        if "args" in payload:
            _observe(events, store, value=payload["args"], kind="opencode.tool_input", timestamp=ts,
                     source=call, relation="HAS_TOOL_INPUT", field="args", hook=hook)
        if hook == "tool.execute.after" and "result" in payload:
            _observe(events, store, value=payload["result"], kind="opencode.tool_output", timestamp=ts,
                     source=call, relation="HAS_TOOL_OUTPUT", field="result", hook=hook)

    if hook == "event" and "event" in payload:
        _observe(events, store, value=payload["event"], kind="opencode.bus_event", timestamp=ts,
                 source=_agent(), relation="OBSERVED_PROVIDER_EVENT", field="event", hook=hook,
                 provider_event_type=payload.get("event_type"))

    if hook == "experimental.chat.messages.transform" and "messages" in payload:
        _observe(events, store, value=payload["messages"], kind="opencode.model_context_messages", timestamp=ts,
                 source=_agent(), relation="OBSERVED_MODEL_CONTEXT", field="messages", hook=hook)
    if hook == "experimental.chat.system.transform" and "system" in payload:
        _observe(events, store, value=payload["system"], kind="opencode.system_prompt", timestamp=ts,
                 source=_agent(), relation="OBSERVED_SYSTEM_PROMPT", field="system", hook=hook)
    if hook == "experimental.text.complete" and isinstance(payload.get("text"), str):
        _observe(events, store, value=payload["text"], kind="opencode.completed_text", timestamp=ts,
                 source=_agent(), relation="PRODUCED_ASSISTANT_TEXT", field="text", hook=hook)

    if hook == "command.execute.before":
        for field, relation in (("command", "OBSERVED_COMMAND"), ("arguments", "OBSERVED_COMMAND_ARGUMENTS"), ("command_parts", "OBSERVED_COMMAND_PARTS")):
            if field in payload:
                _observe(events, store, value=payload[field], kind=f"opencode.{field}", timestamp=ts,
                         source=_agent(), relation=relation, field=field, hook=hook)

    if hook == "tool.definition":
        for field, relation in (("description", "OBSERVED_TOOL_DESCRIPTION"), ("parameters", "OBSERVED_TOOL_SCHEMA")):
            if field in payload:
                _observe(events, store, value=payload[field], kind=f"opencode.tool_{field}", timestamp=ts,
                         source=_agent(), relation=relation, field=field, hook=hook,
                         tool_id=payload.get("toolID"))

    if hook == "permission.ask" and "permission" in payload:
        _observe(events, store, value=payload["permission"], kind="opencode.permission_request", timestamp=ts,
                 source=_agent(), relation="OBSERVED_PERMISSION_REQUEST", field="permission", hook=hook,
                 decision=payload.get("decision"))

    if hook == "experimental.session.compacting":
        for field, relation in (("context", "OBSERVED_COMPACTION_CONTEXT"), ("prompt", "OBSERVED_COMPACTION_PROMPT")):
            if field in payload:
                _observe(events, store, value=payload[field], kind=f"opencode.compaction_{field}", timestamp=ts,
                         source=_agent(), relation=relation, field=field, hook=hook)
    return events
