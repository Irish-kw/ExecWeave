from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .content_evidence import content_observation_event, filter_transport_credentials
from .content_store import ContentReference, FullFidelityContentStore
from .agent_topology import EVIDENCE_SUBAGENT_LIFECYCLE_HOOK, subagent_topology

_CONTENT_FIELDS = frozenset(
    {
        "prompt",
        "delta",
        "tool_input",
        "tool_response",
        "tool_calls",
        "error",
        "error_details",
        "last_assistant_message",
    }
)


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


def _main_agent() -> dict[str, Any]:
    return _entity("agent", "agent:Claude Code", name="Claude Code")


def _subagent(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = payload.get("session_id")
    agent_id = payload.get("agent_id")
    session = session_id if isinstance(session_id, str) and session_id else "unknown"
    agent = agent_id if isinstance(agent_id, str) and agent_id else "unknown"
    agent_type = payload.get("agent_type")
    name = agent_type if isinstance(agent_type, str) and agent_type else "Claude subagent"
    return _entity(
        "agent",
        f"agent:claude:{session}:subagent:{agent}",
        name=name,
        attributes={
            "provider": "claude",
            "agent_id": agent,
            "agent_type": name,
            **subagent_topology(
                evidence=EVIDENCE_SUBAGENT_LIFECYCLE_HOOK,
                parent_scope_id=session,
            ),
        },
    )


def _tool_call(payload: dict[str, Any], *, tool_use_id: object = None, tool_name: object = None) -> dict[str, Any]:
    session_id = payload.get("session_id")
    resolved_use_id = tool_use_id if tool_use_id is not None else payload.get("tool_use_id")
    resolved_name = tool_name if tool_name is not None else payload.get("tool_name")
    session = session_id if isinstance(session_id, str) and session_id else "unknown"
    use_id = resolved_use_id if isinstance(resolved_use_id, str) and resolved_use_id else "unknown"
    name = resolved_name if isinstance(resolved_name, str) and resolved_name else "unknown"
    return _entity(
        "tool_call",
        f"tool-call:claude:{session}:{use_id}",
        name=name,
        attributes={"provider": "claude", "tool_name": name, "tool_use_id": use_id},
    )


def _store_value(
    store: FullFidelityContentStore,
    value: Any,
    *,
    content_kind: str,
) -> ContentReference:
    if isinstance(value, str):
        return store.put_text(value, content_kind=content_kind)
    return store.put_json(value, content_kind=content_kind)


def _content_event(
    *,
    store: FullFidelityContentStore,
    value: Any,
    content_kind: str,
    timestamp: str,
    source: dict[str, Any],
    relation: str,
    observed_field: str,
    hook_event: str,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reference = _store_value(store, value, content_kind=content_kind)
    merged = {"claude_hook_event_name": hook_event}
    if attributes:
        merged.update(attributes)
    return content_observation_event(
        timestamp=timestamp,
        provider="claude",
        source=source,
        reference=reference,
        relation=relation,
        observed_field=observed_field,
        evidence_source="provider_hook",
        attribution="claude_hook",
        attributes=merged,
    )


def _metadata_event(
    payload: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    timestamp: str,
    hook_event: str,
) -> dict[str, Any] | None:
    metadata = {key: value for key, value in payload.items() if key not in _CONTENT_FIELDS}
    filtered, removed = filter_transport_credentials(metadata)
    if not filtered:
        return None
    reference = store.put_json(filtered, content_kind="claude.provider_hook_metadata")
    return content_observation_event(
        timestamp=timestamp,
        provider="claude",
        source=_main_agent(),
        reference=reference,
        relation="OBSERVED_PROVIDER_METADATA",
        observed_field="hook_metadata",
        evidence_source="provider_hook",
        attribution="claude_hook",
        attributes={
            "claude_hook_event_name": hook_event,
            "transport_credentials_excluded": removed,
        },
    )


def _tool_content_events(
    payload: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    timestamp: str,
    hook_event: str,
) -> list[dict[str, Any]]:
    call = _tool_call(payload)
    events: list[dict[str, Any]] = []
    if "tool_input" in payload:
        events.append(
            _content_event(
                store=store,
                value=payload["tool_input"],
                content_kind="claude.tool_input",
                timestamp=timestamp,
                source=call,
                relation="HAS_TOOL_INPUT",
                observed_field="tool_input",
                hook_event=hook_event,
            )
        )
    if hook_event == "PostToolUse" and "tool_response" in payload:
        events.append(
            _content_event(
                store=store,
                value=payload["tool_response"],
                content_kind="claude.tool_response_structured",
                timestamp=timestamp,
                source=call,
                relation="HAS_TOOL_OUTPUT",
                observed_field="tool_response",
                hook_event=hook_event,
                attributes={"model_visible_serialization": False},
            )
        )
    if hook_event == "PostToolUseFailure" and isinstance(payload.get("error"), str):
        events.append(
            _content_event(
                store=store,
                value=payload["error"],
                content_kind="claude.tool_error",
                timestamp=timestamp,
                source=call,
                relation="HAS_TOOL_ERROR",
                observed_field="error",
                hook_event=hook_event,
            )
        )
    return events


def _batch_events(
    payload: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    timestamp: str,
) -> list[dict[str, Any]]:
    tool_calls = payload.get("tool_calls")
    if not isinstance(tool_calls, list):
        return []
    events = [
        _content_event(
            store=store,
            value=tool_calls,
            content_kind="claude.tool_batch",
            timestamp=timestamp,
            source=_main_agent(),
            relation="OBSERVED_TOOL_BATCH",
            observed_field="tool_calls",
            hook_event="PostToolBatch",
        )
    ]
    for index, item in enumerate(tool_calls):
        if not isinstance(item, dict):
            continue
        call = _tool_call(
            payload,
            tool_use_id=item.get("tool_use_id"),
            tool_name=item.get("tool_name"),
        )
        common = {"tool_batch_index": index}
        if "tool_input" in item:
            events.append(
                _content_event(
                    store=store,
                    value=item["tool_input"],
                    content_kind="claude.tool_input",
                    timestamp=timestamp,
                    source=call,
                    relation="HAS_TOOL_INPUT",
                    observed_field="tool_calls[].tool_input",
                    hook_event="PostToolBatch",
                    attributes=common,
                )
            )
        if "tool_response" in item:
            events.append(
                _content_event(
                    store=store,
                    value=item["tool_response"],
                    content_kind="claude.tool_result_model_visible",
                    timestamp=timestamp,
                    source=call,
                    relation="MODEL_RECEIVED_TOOL_RESULT",
                    observed_field="tool_calls[].tool_response",
                    hook_event="PostToolBatch",
                    attributes={**common, "model_visible_serialization": True},
                )
            )
    return events


def claude_hook_to_content_events(
    payload: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """Persist complete values exposed by documented Claude Code hooks.

    This records what the provider hook exposes. It does not claim access to hidden
    prompts, internal reasoning, or provider-side stages that are absent from the hook.
    """

    hook_event = payload.get("hook_event_name")
    if not isinstance(hook_event, str) or not hook_event:
        raise ValueError("Claude hook payload requires hook_event_name")
    observed_at = timestamp or _now()
    events: list[dict[str, Any]] = []

    metadata_event = _metadata_event(
        payload,
        store=store,
        timestamp=observed_at,
        hook_event=hook_event,
    )
    if metadata_event is not None:
        events.append(metadata_event)

    if hook_event == "UserPromptSubmit" and isinstance(payload.get("prompt"), str):
        events.append(
            _content_event(
                store=store,
                value=payload["prompt"],
                content_kind="claude.user_prompt",
                timestamp=observed_at,
                source=_main_agent(),
                relation="RECEIVED_USER_PROMPT",
                observed_field="prompt",
                hook_event=hook_event,
            )
        )
    elif hook_event == "MessageDisplay" and isinstance(payload.get("delta"), str):
        display_attrs = {
            key: payload[key]
            for key in ("turn_id", "message_id", "index", "final")
            if key in payload
        }
        events.append(
            _content_event(
                store=store,
                value=payload["delta"],
                content_kind="claude.assistant_display_delta",
                timestamp=observed_at,
                source=_main_agent(),
                relation="DISPLAYED_ASSISTANT_TEXT",
                observed_field="delta",
                hook_event=hook_event,
                attributes=display_attrs,
            )
        )
    elif hook_event in {"PreToolUse", "PostToolUse", "PostToolUseFailure"}:
        events.extend(
            _tool_content_events(
                payload,
                store=store,
                timestamp=observed_at,
                hook_event=hook_event,
            )
        )
    elif hook_event == "PostToolBatch":
        events.extend(_batch_events(payload, store=store, timestamp=observed_at))
    elif hook_event in {"Stop", "SubagentStop"} and isinstance(
        payload.get("last_assistant_message"), str
    ):
        source = _subagent(payload) if hook_event == "SubagentStop" else _main_agent()
        events.append(
            _content_event(
                store=store,
                value=payload["last_assistant_message"],
                content_kind=(
                    "claude.subagent_final_response"
                    if hook_event == "SubagentStop"
                    else "claude.assistant_final_response"
                ),
                timestamp=observed_at,
                source=source,
                relation="PRODUCED_ASSISTANT_RESPONSE",
                observed_field="last_assistant_message",
                hook_event=hook_event,
            )
        )
    elif hook_event == "StopFailure":
        if isinstance(payload.get("error"), str):
            events.append(
                _content_event(
                    store=store,
                    value=payload["error"],
                    content_kind="claude.stop_failure_type",
                    timestamp=observed_at,
                    source=_main_agent(),
                    relation="HAS_STOP_FAILURE",
                    observed_field="error",
                    hook_event=hook_event,
                )
            )
        if isinstance(payload.get("error_details"), str):
            events.append(
                _content_event(
                    store=store,
                    value=payload["error_details"],
                    content_kind="claude.stop_failure_details",
                    timestamp=observed_at,
                    source=_main_agent(),
                    relation="HAS_STOP_FAILURE_DETAILS",
                    observed_field="error_details",
                    hook_event=hook_event,
                )
            )
        if isinstance(payload.get("last_assistant_message"), str):
            events.append(
                _content_event(
                    store=store,
                    value=payload["last_assistant_message"],
                    content_kind="claude.stop_failure_message",
                    timestamp=observed_at,
                    source=_main_agent(),
                    relation="DISPLAYED_STOP_FAILURE",
                    observed_field="last_assistant_message",
                    hook_event=hook_event,
                )
            )
    return events
