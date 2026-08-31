from __future__ import annotations

from typing import Any

from . import antigravity_adapter_base as _base

append_semantic_records = _base.append_semantic_records
read_hook_payload = _base.read_hook_payload
_base_semantic_events = _base.antigravity_hook_to_semantic_events


def _conversation_agent(payload: dict[str, Any]) -> dict[str, Any]:
    conversation_id = payload.get("conversationId")
    if isinstance(conversation_id, str) and conversation_id:
        return {
            "type": "agent",
            "id": f"agent:antigravity:conversation:{conversation_id}",
            "name": "Antigravity conversation",
            "attributes": {
                "provider": "antigravity",
                "conversation_id": conversation_id,
                "identity_semantics": "provider_conversation_id",
            },
        }
    return {
        "type": "agent",
        "id": "agent:Antigravity",
        "name": "Antigravity",
        "attributes": {"provider": "antigravity"},
    }


def _canonicalize_agent_identity(
    events: list[dict[str, Any]],
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    canonical = _conversation_agent(payload)
    if canonical["id"] == "agent:Antigravity":
        return events
    for event in events:
        for endpoint in ("source", "target"):
            entity = event.get(endpoint)
            if (
                isinstance(entity, dict)
                and entity.get("type") == "agent"
                and entity.get("id") == "agent:Antigravity"
            ):
                event[endpoint] = canonical
    return events


def _post_tool_observation(payload: dict[str, Any], *, timestamp: str) -> dict[str, Any]:
    conversation_id = payload.get("conversationId")
    if not isinstance(conversation_id, str) or not conversation_id:
        raise ValueError("Antigravity PostToolUse payload has no conversationId")
    step = payload.get("stepIdx")
    if not isinstance(step, int) or isinstance(step, bool) or step < 0:
        raise ValueError("Antigravity PostToolUse payload has no valid stepIdx")

    attributes: dict[str, Any] = {
        "backend": "semantic",
        "provider": "antigravity",
        "attribution": "antigravity_hook",
        "evidence_source": "provider_hook",
        "causal": False,
        "inferred": False,
        "provider_contract_exact": True,
        "provider_step_index_exact": True,
        "provider_tool_identity_exposed": False,
        "tool_call_payload_present": False,
        "antigravity_conversation_id": conversation_id,
        "antigravity_step_index": step,
    }
    model = payload.get("modelName")
    if isinstance(model, str) and model:
        attributes["antigravity_model_name"] = model
    return {
        "timestamp": timestamp,
        "event_type": "semantic.antigravity.tool.completed_without_identity",
        "relation": "OBSERVED_TOOL_CALL",
        "source": _conversation_agent(payload),
        "target": {
            "type": "tool_call_observation",
            "id": f"tool-call-observation:antigravity:{conversation_id}:{step}",
            "name": "completed tool (identity unavailable)",
            "attributes": {
                "provider": "antigravity",
                "conversation_id": conversation_id,
                "step_index": step,
                "identity_semantics": "provider_post_tool_step_without_tool_identity",
                "tool_identity_exposed": False,
            },
        },
        "attributes": attributes,
    }


def antigravity_hook_to_semantic_events(
    payload: dict[str, Any],
    *,
    hook_event: str,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """Handle both current 2.0 PostToolUse and older/null-toolCall CLI payloads."""
    if hook_event == "PostToolUse" and not isinstance(payload.get("toolCall"), dict):
        if timestamp is None:
            from datetime import datetime, timezone

            timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return [_post_tool_observation(payload, timestamp=timestamp)]
    events = _base_semantic_events(payload, hook_event=hook_event, timestamp=timestamp)
    return _canonicalize_agent_identity(events, payload)
