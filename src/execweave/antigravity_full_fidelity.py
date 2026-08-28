from __future__ import annotations

from typing import Any

from . import antigravity_full_fidelity_collaboration_base as _base
from .antigravity_subagent_linkage import validated_subagent_links
from .content_store import FullFidelityContentStore
from .conversation_archive import antigravity_conversation_archive_events


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


def _assignment_event(
    *,
    timestamp: str,
    conversation_id: str,
    step: int,
    subagent_index: int,
    child_id: str,
    spec: dict[str, Any],
) -> dict[str, Any]:
    role = spec.get("Role") if isinstance(spec.get("Role"), str) else None
    type_name = spec.get("TypeName") if isinstance(spec.get("TypeName"), str) else None
    workspace = spec.get("Workspace") if isinstance(spec.get("Workspace"), str) else None
    subtask = _entity(
        "subtask",
        f"subtask:antigravity:{conversation_id}:{step}:{subagent_index}",
        name=role or type_name or "Antigravity subtask",
        attributes={
            "provider": "antigravity",
            "conversation_id": conversation_id,
            "step_index": step,
            "subagent_index": subagent_index,
            "role": role,
            "type_name": type_name,
            "workspace": workspace,
            "identity_semantics": "provider_invoke_subagent_spec_index",
        },
    )
    child = _entity(
        "agent",
        f"agent:antigravity:conversation:{child_id}",
        name="Antigravity subagent",
        attributes={
            "provider": "antigravity",
            "conversation_id": child_id,
            "identity_semantics": "provider_transcript_result_conversation_id",
            "execution_observed": False,
            "lifecycle_authority": "child_provider_hooks",
        },
    )
    return {
        "timestamp": timestamp,
        "event_type": "semantic.antigravity.subtask.assigned",
        "relation": "ASSIGNED_AGENT_TASK",
        "source": subtask,
        "target": child,
        "attributes": {
            "backend": "semantic",
            "provider": "antigravity",
            "attribution": "antigravity_hook",
            "evidence_source": "provider_hook_plus_validated_transcript",
            "causal": False,
            "inferred": False,
            "identity_exact": True,
            "identity_method": "validated_transcript_record_order_and_provider_ids",
            "provider_collaboration_tool_exact": True,
            "provider_post_tool_success": True,
            "provider_child_identity_exact": True,
            "correlation_method": "validated_transcript_record_order_and_provider_ids",
            "transcript_wire_semantics": "live_verified_implementation_wire",
            "transcript_record_order_validated": True,
            "timing_inference_used": False,
            "child_lifecycle_inferred": False,
            "child_lifecycle_authority": "child_provider_hooks",
        },
    }


def _subagent_assignment_events(
    payload: dict[str, Any],
    *,
    timestamp: str,
) -> list[dict[str, Any]]:
    tool_call = payload.get("toolCall")
    if not isinstance(tool_call, dict) or tool_call.get("name") != "invoke_subagent":
        return []
    args = tool_call.get("args")
    if not isinstance(args, dict):
        return []
    error = payload.get("error")
    if isinstance(error, str) and error.strip():
        return []
    conversation_id = payload.get("conversationId")
    step = payload.get("stepIdx")
    if not isinstance(conversation_id, str) or not conversation_id:
        return []
    if not isinstance(step, int) or isinstance(step, bool) or step < 0:
        return []
    specs = args.get("Subagents")
    if not isinstance(specs, list):
        return []

    links = validated_subagent_links(payload, args=args)
    events: list[dict[str, Any]] = []
    for link in links:
        subagent_index = link["subagent_index"]
        if not isinstance(subagent_index, int) or not 0 <= subagent_index < len(specs):
            return []
        spec = specs[subagent_index]
        child_id = link["conversation_id"]
        if not isinstance(spec, dict) or not isinstance(child_id, str):
            return []
        events.append(
            _assignment_event(
                timestamp=timestamp,
                conversation_id=conversation_id,
                step=step,
                subagent_index=subagent_index,
                child_id=child_id,
                spec=spec,
            )
        )
    return events


def antigravity_hook_to_content_events(
    payload: dict[str, Any],
    *,
    hook_event: str,
    store: FullFidelityContentStore,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    events = _base.antigravity_hook_to_content_events(
        payload,
        hook_event=hook_event,
        store=store,
        timestamp=timestamp,
    )
    if timestamp is None:
        from datetime import datetime, timezone

        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if hook_event == "PostToolUse":
        events.extend(_subagent_assignment_events(payload, timestamp=timestamp))
    elif hook_event == "Stop":
        events.extend(
            antigravity_conversation_archive_events(
                payload,
                store=store,
                timestamp=timestamp,
            )
        )
    return events
