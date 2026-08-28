from __future__ import annotations

import hashlib
import json
from typing import Any

from .antigravity_full_fidelity_base import (
    antigravity_hook_to_content_events as _base_content_events,
)
from .content_evidence import content_observation_event
from .content_store import FullFidelityContentStore


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


def _conversation_agent(conversation_id: str) -> dict[str, Any]:
    return _entity(
        "agent",
        f"agent:antigravity:conversation:{conversation_id}",
        name="Antigravity conversation",
        attributes={
            "provider": "antigravity",
            "conversation_id": conversation_id,
            "identity_semantics": "provider_conversation_id",
        },
    )


def _event(
    *,
    timestamp: str,
    event_type: str,
    relation: str,
    source: dict[str, Any],
    target: dict[str, Any],
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "backend": "semantic",
        "provider": "antigravity",
        "attribution": "antigravity_hook",
        "evidence_source": "provider_hook",
        "causal": False,
        "inferred": False,
        "provider_collaboration_tool_exact": True,
        "provider_post_tool_success": True,
    }
    if attributes:
        merged.update(attributes)
    return {
        "timestamp": timestamp,
        "event_type": event_type,
        "relation": relation,
        "source": source,
        "target": target,
        "attributes": merged,
    }


def _digest(*values: object) -> str:
    raw = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _invoke_subagent_events(
    payload: dict[str, Any],
    *,
    args: dict[str, Any],
    store: FullFidelityContentStore,
    timestamp: str,
) -> list[dict[str, Any]]:
    conversation_id = payload["conversationId"]
    step = payload["stepIdx"]
    parent = _conversation_agent(conversation_id)
    specs = args.get("Subagents")
    if not isinstance(specs, list):
        return []

    events: list[dict[str, Any]] = []
    for index, spec in enumerate(specs):
        if not isinstance(spec, dict):
            continue
        role = spec.get("Role") if isinstance(spec.get("Role"), str) else None
        type_name = spec.get("TypeName") if isinstance(spec.get("TypeName"), str) else None
        workspace = spec.get("Workspace") if isinstance(spec.get("Workspace"), str) else None
        subtask = _entity(
            "subtask",
            f"subtask:antigravity:{conversation_id}:{step}:{index}",
            name=role or type_name or "Antigravity subtask",
            attributes={
                "provider": "antigravity",
                "conversation_id": conversation_id,
                "step_index": step,
                "subagent_index": index,
                "role": role,
                "type_name": type_name,
                "workspace": workspace,
                "child_identity_exposed": False,
                "identity_semantics": "provider_invoke_subagent_spec_index",
            },
        )
        events.append(
            _event(
                timestamp=timestamp,
                event_type="semantic.antigravity.subtask.requested",
                relation="REQUESTED_SUBTASK",
                source=parent,
                target=subtask,
                attributes={"child_identity_exposed": False},
            )
        )
        if type_name:
            profile = _entity(
                "agent_profile",
                f"agent-profile:antigravity:{type_name}",
                name=type_name,
                attributes={"provider": "antigravity", "native_agent_name": type_name},
            )
            events.append(
                _event(
                    timestamp=timestamp,
                    event_type="semantic.antigravity.subtask.targeted",
                    relation="TARGETS_AGENT_PROFILE",
                    source=subtask,
                    target=profile,
                    attributes={"child_identity_exposed": False},
                )
            )
        prompt = spec.get("Prompt")
        if isinstance(prompt, str):
            reference = store.put_text(
                prompt,
                content_kind="antigravity.subtask_prompt",
            )
            events.append(
                content_observation_event(
                    timestamp=timestamp,
                    provider="antigravity",
                    source=subtask,
                    reference=reference,
                    relation="HAS_SUBTASK_PROMPT",
                    observed_field="toolCall.args.Subagents[].Prompt",
                    evidence_source="provider_hook",
                    attribution="antigravity_hook",
                    attributes={
                        "provider_collaboration_tool_exact": True,
                        "provider_post_tool_success": True,
                        "child_identity_exposed": False,
                    },
                )
            )
    return events


def _send_message_events(
    payload: dict[str, Any],
    *,
    args: dict[str, Any],
    store: FullFidelityContentStore,
    timestamp: str,
) -> list[dict[str, Any]]:
    conversation_id = payload["conversationId"]
    step = payload["stepIdx"]
    recipient = args.get("Recipient")
    message_text = args.get("Message")
    if not isinstance(recipient, str) or not recipient:
        return []
    if not isinstance(message_text, str):
        return []

    author = _conversation_agent(conversation_id)
    message = _entity(
        "agent_message",
        f"agent-message:antigravity:{conversation_id}:{step}:{_digest(recipient, message_text)}",
        name="Antigravity agent message",
        attributes={
            "provider": "antigravity",
            "author": conversation_id,
            "recipient": recipient,
            "step_index": step,
            "provider_recipient_exact": True,
            "delivery_observed": False,
            "consumption_observed": False,
        },
    )
    recipient_address = _entity(
        "agent",
        f"agent:antigravity:conversation:{recipient}",
        name="Antigravity recipient",
        attributes={
            "provider": "antigravity",
            "conversation_id": recipient,
            "identity_semantics": "provider_recipient_conversation_id",
            "routing_identity_only": True,
            "execution_observed": False,
        },
    )
    reference = store.put_text(
        message_text,
        content_kind="antigravity.agent_message.payload",
    )
    return [
        _event(
            timestamp=timestamp,
            event_type="semantic.antigravity.agent_message.sent",
            relation="SENT_AGENT_MESSAGE",
            source=author,
            target=message,
            attributes={
                "delivery_observed": False,
                "consumption_observed": False,
            },
        ),
        _event(
            timestamp=timestamp,
            event_type="semantic.antigravity.agent_message.addressed",
            relation="TARGETS_AGENT_ADDRESS",
            source=message,
            target=recipient_address,
            attributes={
                "provider_recipient_exact": True,
                "delivery_observed": False,
            },
        ),
        content_observation_event(
            timestamp=timestamp,
            provider="antigravity",
            source=message,
            reference=reference,
            relation="HAS_AGENT_MESSAGE_PAYLOAD",
            observed_field="toolCall.args.Message",
            evidence_source="provider_hook",
            attribution="antigravity_hook",
            attributes={
                "provider_collaboration_tool_exact": True,
                "provider_post_tool_success": True,
                "delivery_observed": False,
                "consumption_observed": False,
            },
        ),
    ]


def _manage_subagent_events(
    payload: dict[str, Any],
    *,
    args: dict[str, Any],
    timestamp: str,
) -> list[dict[str, Any]]:
    conversation_id = payload["conversationId"]
    step = payload["stepIdx"]
    action = args.get("Action")
    if not isinstance(action, str) or not action:
        return []
    ids = args.get("ConversationIds")
    conversation_ids = (
        [value for value in ids if isinstance(value, str) and value]
        if isinstance(ids, list)
        else []
    )
    operation = _entity(
        "agent_operation",
        f"agent-operation:antigravity:{conversation_id}:{step}:manage_subagents",
        name=f"manage_subagents {action}",
        attributes={
            "provider": "antigravity",
            "action": action,
            "conversation_ids": conversation_ids,
            "result_details_exposed": False,
        },
    )
    return [
        _event(
            timestamp=timestamp,
            event_type="semantic.antigravity.subagents.managed",
            relation="MANAGED_SUBAGENTS",
            source=_conversation_agent(conversation_id),
            target=operation,
            attributes={
                "management_action": action,
                "result_details_exposed": False,
            },
        )
    ]


def _collaboration_events(
    payload: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    timestamp: str,
) -> list[dict[str, Any]]:
    tool_call = payload.get("toolCall")
    if not isinstance(tool_call, dict):
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
    name = tool_call.get("name")
    args = tool_call.get("args")
    if not isinstance(name, str) or not isinstance(args, dict):
        return []
    if name == "invoke_subagent":
        return _invoke_subagent_events(
            payload,
            args=args,
            store=store,
            timestamp=timestamp,
        )
    if name == "send_message":
        return _send_message_events(
            payload,
            args=args,
            store=store,
            timestamp=timestamp,
        )
    if name == "manage_subagents":
        return _manage_subagent_events(
            payload,
            args=args,
            timestamp=timestamp,
        )
    return []


def antigravity_hook_to_content_events(
    payload: dict[str, Any],
    *,
    hook_event: str,
    store: FullFidelityContentStore,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    events = _base_content_events(
        payload,
        hook_event=hook_event,
        store=store,
        timestamp=timestamp,
    )
    if hook_event != "PostToolUse":
        return events
    if timestamp is None:
        from datetime import datetime, timezone

        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    events.extend(_collaboration_events(payload, store=store, timestamp=timestamp))
    return events
