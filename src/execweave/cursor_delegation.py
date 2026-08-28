from __future__ import annotations

from typing import Any

from .content_store import FullFidelityContentStore
from .cursor_delegation_base import cursor_delegation_events as _base_cursor_delegation_events


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _triggering_task_call(payload: dict[str, Any]) -> dict[str, Any] | None:
    conversation_id = _string(payload.get("conversation_id"))
    parent_conversation_id = _string(payload.get("parent_conversation_id"))
    tool_call_id = _string(payload.get("tool_call_id"))
    if (
        conversation_id is None
        or parent_conversation_id is None
        or tool_call_id is None
        or conversation_id != parent_conversation_id
    ):
        return None
    return {
        "type": "tool_call",
        "id": f"tool-call:cursor:{conversation_id}:{tool_call_id}",
        "name": "Task",
        "attributes": {
            "provider": "cursor",
            "tool_name": "Task",
            "tool_use_id": tool_call_id,
            "identity_semantics": "provider_tool_use_id",
        },
    }


def cursor_delegation_events(
    payload: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    timestamp: str,
) -> list[dict[str, Any]]:
    """Extend exact Cursor delegation with the provider-exposed triggering Task call."""
    events = _base_cursor_delegation_events(
        payload,
        store=store,
        timestamp=timestamp,
    )
    if payload.get("hook_event_name") != "subagentStart" or not events:
        return events

    call = _triggering_task_call(payload)
    if call is None:
        return events

    requested = next(
        (
            event
            for event in events
            if event.get("relation") == "REQUESTED_SUBTASK"
            and isinstance(event.get("target"), dict)
            and event["target"].get("type") == "subtask"
        ),
        None,
    )
    if requested is None:
        return events

    attributes = dict(requested.get("attributes") or {})
    attributes.update(
        {
            "provider_tool_call_id_exact": True,
            "provider_parent_conversation_id_exact": True,
            "trigger_basis": "subagentStart.tool_call_id",
        }
    )
    events.append(
        {
            "timestamp": timestamp,
            "event_type": "semantic.cursor.subtask.triggered_by_task_call",
            "relation": "REQUESTED_SUBTASK",
            "source": call,
            "target": requested["target"],
            "attributes": attributes,
        }
    )
    return events
