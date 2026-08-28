from __future__ import annotations

from typing import Any


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _event_body(payload: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    if payload.get("hook_event_name") != "event":
        return None
    raw = payload.get("event")
    if not isinstance(raw, dict) or raw.get("type") != "message.part.updated":
        return None
    properties = raw.get("properties")
    if not isinstance(properties, dict):
        return None
    return "message.part.updated", properties


def _agent(session_id: str, *, agent_name: str | None = None) -> dict[str, Any]:
    attributes: dict[str, Any] = {
        "provider": "opencode",
        "session_id": session_id,
        "identity_semantics": "provider_session_id",
    }
    if agent_name:
        attributes["native_agent_name"] = agent_name
    return {
        "type": "agent",
        "id": f"agent:opencode:session:{session_id}",
        "name": agent_name or "OpenCode session",
        "attributes": attributes,
    }


def _tool_call(session_id: str, call_id: str) -> dict[str, Any]:
    return {
        "type": "tool_call",
        "id": f"tool-call:opencode:{session_id}:{call_id}",
        "name": "task",
        "attributes": {
            "provider": "opencode",
            "session_id": session_id,
            "call_id": call_id,
            "tool_name": "task",
            "identity_semantics": "provider_call_id",
        },
    }


def opencode_task_session_events(
    payload: dict[str, Any],
    *,
    timestamp: str,
) -> list[dict[str, Any]]:
    """Project exact OpenCode Task tool metadata into child-session assignment evidence."""
    parsed = _event_body(payload)
    if parsed is None:
        return []
    event_type, body = parsed
    part = body.get("part")
    if not isinstance(part, dict) or part.get("type") != "tool":
        return []
    if _string(part.get("tool")) != "task":
        return []

    current_session = (
        _string(part.get("sessionID"))
        or _string(part.get("sessionId"))
        or _string(payload.get("sessionID"))
    )
    call_id = _string(part.get("callID")) or _string(part.get("callId"))
    state = part.get("state")
    if current_session is None or call_id is None or not isinstance(state, dict):
        return []

    metadata = state.get("metadata")
    if not isinstance(metadata, dict):
        return []
    parent_session = _string(metadata.get("parentSessionId"))
    child_session = _string(metadata.get("sessionId"))
    if (
        parent_session is None
        or child_session is None
        or parent_session != current_session
    ):
        return []

    state_input = state.get("input")
    if not isinstance(state_input, dict):
        state_input = {}
    agent_name = _string(state_input.get("subagent_type"))
    task_id = _string(state_input.get("task_id"))
    background = state_input.get("background")

    attributes: dict[str, Any] = {
        "backend": "semantic",
        "provider": "opencode",
        "evidence_source": "provider_plugin",
        "attribution": "opencode_task_tool_metadata",
        "causal": False,
        "inferred": False,
        "opencode_event_type": event_type,
        "provider_task_session_id_exact": True,
        "provider_parent_session_id_exact": True,
        "assignment_basis": "task_tool_state.metadata.sessionId",
        "task_session_mode": "resume_requested" if task_id else "new_requested",
    }
    if task_id:
        attributes["requested_task_id"] = task_id
    if isinstance(background, bool):
        attributes["background_requested"] = background

    return [
        {
            "timestamp": timestamp,
            "event_type": "semantic.opencode.task_session.assigned",
            "relation": "ASSIGNED_AGENT_TASK",
            "source": _tool_call(current_session, call_id),
            "target": _agent(child_session, agent_name=agent_name),
            "attributes": attributes,
        }
    ]
