from __future__ import annotations

from typing import Any

from .content_evidence import content_observation_event
from .content_store import FullFidelityContentStore
from .agent_topology import EVIDENCE_PARENT_SESSION_ID, root_topology, subagent_topology


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


def _agent(
    session_id: str,
    *,
    agent_name: str | None = None,
    parent_session_id: str | None = None,
) -> dict[str, Any]:
    """Build an OpenCode session agent node.

    A session is only a child when the task tool's own metadata names its
    ``parentSessionId``. Without that, a session id is just a session id and the
    agent stays root.
    """
    attributes: dict[str, Any] = {
        "provider": "opencode",
        "session_id": session_id,
        "identity_semantics": "provider_session_id",
    }
    if parent_session_id:
        attributes.update(
            subagent_topology(
                evidence=EVIDENCE_PARENT_SESSION_ID,
                parent_scope_id=parent_session_id,
            )
        )
    else:
        attributes.update(root_topology())
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


def _task_content_event(
    *,
    child: dict[str, Any],
    value: str,
    content_kind: str,
    relation: str,
    observed_field: str,
    store: FullFidelityContentStore,
    timestamp: str,
    attributes: dict[str, Any],
) -> dict[str, Any]:
    reference = store.put_text(value, content_kind=content_kind)
    return content_observation_event(
        timestamp=timestamp,
        provider="opencode",
        source=child,
        reference=reference,
        relation=relation,
        observed_field=observed_field,
        evidence_source="provider_plugin",
        attribution="opencode_task_tool_metadata",
        event_type="semantic.opencode.task_session.content",
        attributes={
            **attributes,
            "conversation_projection_basis": "exact_task_tool_child_session_metadata",
        },
    )


def opencode_task_session_events(
    payload: dict[str, Any],
    *,
    timestamp: str,
    store: FullFidelityContentStore | None = None,
) -> list[dict[str, Any]]:
    """Project exact OpenCode Task metadata into child-session assignment evidence.

    When a content store is supplied, the same provider-exposed task prompt and
    description are also attached to the exact child session so the dashboard can
    render the delegated task inside that child agent's conversation thread.
    """
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

    child = _agent(child_session, agent_name=agent_name, parent_session_id=parent_session)
    events: list[dict[str, Any]] = [
        {
            "timestamp": timestamp,
            "event_type": "semantic.opencode.task_session.assigned",
            "relation": "ASSIGNED_AGENT_TASK",
            "source": _tool_call(current_session, call_id),
            "target": child,
            "attributes": attributes,
        }
    ]

    if store is not None:
        prompt = state_input.get("prompt")
        if isinstance(prompt, str) and prompt:
            events.append(
                _task_content_event(
                    child=child,
                    value=prompt,
                    content_kind="opencode.subtask_prompt",
                    relation="OBSERVED_SUBAGENT_TASK",
                    observed_field="event.properties.part.state.input.prompt",
                    store=store,
                    timestamp=timestamp,
                    attributes=attributes,
                )
            )
        description = state_input.get("description")
        if isinstance(description, str) and description:
            events.append(
                _task_content_event(
                    child=child,
                    value=description,
                    content_kind="opencode.subtask_description",
                    relation="OBSERVED_SUBAGENT_DESCRIPTION",
                    observed_field="event.properties.part.state.input.description",
                    store=store,
                    timestamp=timestamp,
                    attributes=attributes,
                )
            )
    return events
