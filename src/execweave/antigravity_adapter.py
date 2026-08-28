from __future__ import annotations

from typing import Any

from .antigravity_adapter_base import (
    append_semantic_records,
    antigravity_hook_to_semantic_events as _base_semantic_events,
    read_hook_payload,
)


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
        "source": {
            "type": "agent",
            "id": "agent:Antigravity",
            "name": "Antigravity",
            "attributes": {"provider": "antigravity"},
        },
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
    return _base_semantic_events(payload, hook_event=hook_event, timestamp=timestamp)
