from __future__ import annotations

import hashlib
import json
from typing import Any

from .content_evidence import content_observation_event
from .content_store import FullFidelityContentStore

_VISIBILITY: dict[str, dict[str, str]] = {
    "claude": {
        "agent_identity_visibility": "provider_exposed_subagent_id",
        "subagent_visibility": "provider_exposed_lifecycle",
        "reasoning_visibility": "not_exposed_by_source",
    },
    "codex": {
        "agent_identity_visibility": "provider_exposed_thread_identity",
        "subagent_visibility": "provider_exposed_rollout_graph",
        "reasoning_visibility": "provider_exposed_plaintext_summary_or_encoded",
    },
    "cursor": {
        "agent_identity_visibility": "provider_exposed_when_subagent_id_present",
        "subagent_visibility": "provider_exposed_lifecycle",
        "reasoning_visibility": "provider_exposed_thinking_text",
    },
    "opencode": {
        "agent_identity_visibility": "provider_exposed_session_identity",
        "subagent_visibility": "provider_exposed_session_parent_id",
        "reasoning_visibility": "provider_exposed_reasoning_part",
    },
    "gemini": {
        "agent_identity_visibility": "provider_root_only",
        "subagent_visibility": "not_exposed_by_source",
        "reasoning_visibility": "not_exposed_by_source",
    },
    "antigravity": {
        "agent_identity_visibility": "provider_root_only",
        "subagent_visibility": "not_exposed_by_source",
        "reasoning_visibility": "not_exposed_by_source",
    },
}


def agent_trace_visibility(provider: str) -> dict[str, str]:
    """Return explicit source-visibility boundaries for one provider integration."""
    normalized = provider.strip().lower()
    return dict(
        _VISIBILITY.get(
            normalized,
            {
                "agent_identity_visibility": "unknown",
                "subagent_visibility": "unknown",
                "reasoning_visibility": "unknown",
            },
        )
    )


_PROVIDER_ROOT_AGENTS: dict[str, tuple[str, str]] = {
    "claude": ("agent:Claude Code", "Claude Code"),
    "codex": ("agent:OpenAI Codex", "OpenAI Codex"),
    "cursor": ("agent:Cursor", "Cursor"),
    "opencode": ("agent:OpenCode", "OpenCode"),
    "gemini": ("agent:Gemini CLI", "Gemini CLI"),
    "antigravity": ("agent:Antigravity", "Antigravity"),
}


def provider_agent_trace_visibility_event(
    provider: str,
    *,
    timestamp: str,
    source: dict[str, Any] | None = None,
    attribution: str = "provider_integration",
    evidence_source: str = "provider_hook",
) -> dict[str, Any]:
    """Materialize what the selected provider surface can and cannot expose."""
    normalized = provider.strip().lower()
    root_id, root_name = _PROVIDER_ROOT_AGENTS.get(
        normalized,
        (f"agent:{provider}", provider),
    )
    actor = source or _entity("agent", root_id, root_name, provider=normalized)
    visibility = agent_trace_visibility(normalized)
    capability = _entity(
        "agent_trace_capability",
        f"agent-trace-capability:{normalized}",
        f"{root_name} trace visibility",
        provider=normalized,
        **visibility,
    )
    return _event(
        timestamp=timestamp,
        event_type=f"semantic.{normalized}.agent_trace.visibility",
        relation="DECLARES_AGENT_TRACE_VISIBILITY",
        source=actor,
        target=capability,
        provider=normalized,
        attribution=attribution,
        evidence_source=evidence_source,
        attributes=visibility,
    )


def _entity(
    kind: str,
    ident: str,
    name: str,
    **attributes: Any,
) -> dict[str, Any]:
    return {
        "type": kind,
        "id": ident,
        "name": name,
        "attributes": attributes,
    }


def opencode_root_agent() -> dict[str, Any]:
    return _entity("agent", "agent:OpenCode", "OpenCode", provider="opencode")


def opencode_session_agent(
    session_id: str,
    *,
    agent_name: str | None = None,
) -> dict[str, Any]:
    name = agent_name if isinstance(agent_name, str) and agent_name else "OpenCode session"
    return _entity(
        "agent",
        f"agent:opencode:session:{session_id}",
        name,
        provider="opencode",
        session_id=session_id,
        native_agent_name=agent_name,
        identity_semantics="provider_session_id",
    )


def _opencode_agent_for_payload(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = payload.get("sessionID")
    agent_name = payload.get("agent")
    if isinstance(session_id, str) and session_id:
        return opencode_session_agent(
            session_id,
            agent_name=agent_name if isinstance(agent_name, str) else None,
        )
    return opencode_root_agent()


def _event(
    *,
    timestamp: str,
    event_type: str,
    relation: str,
    source: dict[str, Any],
    target: dict[str, Any],
    provider: str,
    attribution: str,
    evidence_source: str,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "backend": "semantic",
        "provider": provider,
        "attribution": attribution,
        "evidence_source": evidence_source,
        "causal": False,
        "inferred": False,
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


def _opencode_event_body(event: dict[str, Any]) -> dict[str, Any]:
    properties = event.get("properties")
    if isinstance(properties, dict):
        return properties
    data = event.get("data")
    if isinstance(data, dict):
        return data
    return event


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _session_id_from(
    payload: dict[str, Any],
    body: dict[str, Any],
    *,
    info: dict[str, Any] | None = None,
    part: dict[str, Any] | None = None,
) -> str | None:
    candidates: list[Any] = []
    if info is not None:
        candidates.extend((info.get("sessionID"), info.get("sessionId"), info.get("session_id")))
    if part is not None:
        candidates.extend((part.get("sessionID"), part.get("sessionId"), part.get("session_id")))
    candidates.extend(
        (
            body.get("sessionID"),
            body.get("sessionId"),
            body.get("session_id"),
            payload.get("sessionID"),
        )
    )
    if info is not None:
        candidates.append(info.get("id"))
    for candidate in candidates:
        value = _string(candidate)
        if value is not None:
            return value
    return None


def _content(
    *,
    store: FullFidelityContentStore,
    value: Any,
    content_kind: str,
    timestamp: str,
    source: dict[str, Any],
    relation: str,
    observed_field: str,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reference = (
        store.put_text(value, content_kind=content_kind)
        if isinstance(value, str)
        else store.put_json(value, content_kind=content_kind)
    )
    return content_observation_event(
        timestamp=timestamp,
        provider="opencode",
        source=source,
        reference=reference,
        relation=relation,
        observed_field=observed_field,
        evidence_source="provider_plugin",
        attribution="opencode_event_bus",
        event_type="semantic.opencode.agent_trace.content",
        attributes=attributes,
    )


def _message_entity(info: dict[str, Any], session_id: str) -> dict[str, Any]:
    message_id = _string(info.get("id")) or _string(info.get("messageID")) or "unknown"
    role = _string(info.get("role")) or "unknown"
    attributes: dict[str, Any] = {
        "provider": "opencode",
        "message_id": message_id,
        "role": role,
        "session_id": session_id,
    }
    parent_id = _string(info.get("parentID")) or _string(info.get("parentId"))
    if parent_id is not None:
        attributes["parent_message_id"] = parent_id
    return _entity(
        "message",
        f"message:opencode:{session_id}:{message_id}",
        f"{role} message",
        **attributes,
    )


def _message_part_text(part: dict[str, Any]) -> str | None:
    text = part.get("text")
    if isinstance(text, str) and text:
        return text
    content = part.get("content")
    if isinstance(content, str) and content:
        return content
    return None


def _message_role(info: dict[str, Any]) -> str | None:
    role = info.get("role")
    return role if isinstance(role, str) and role else None


def _message_agent_name(info: dict[str, Any]) -> str | None:
    agent = info.get("agent")
    return agent if isinstance(agent, str) and agent else None


def _content_kind_for_message(role: str | None, part_type: str | None) -> str:
    normalized_role = role or "unknown"
    normalized_type = part_type or "text"
    return f"opencode.{normalized_role}_message.{normalized_type}"


def _message_part_events(
    payload: dict[str, Any],
    body: dict[str, Any],
    *,
    timestamp: str,
) -> list[dict[str, Any]]:
    info = body.get("info")
    part = body.get("part")
    if not isinstance(info, dict) or not isinstance(part, dict):
        return []
    session_id = _session_id_from(payload, body, info=info, part=part)
    if session_id is None:
        return []
    text = _message_part_text(part)
    if text is None:
        return []
    role = _message_role(info)
    agent_name = _message_agent_name(info)
    source = opencode_session_agent(session_id, agent_name=agent_name)
    relation = "PRODUCED_ASSISTANT_RESPONSE" if role == "assistant" else "RECEIVED_USER_PROMPT"
    part_type = _string(part.get("type"))
    content = _content(
        store=FullFidelityContentStore(payload["__execweave_store_root"]),
        value=text,
        content_kind=_content_kind_for_message(role, part_type),
        timestamp=timestamp,
        source=source,
        relation=relation,
        observed_field="message_part_text",
        attributes={
            "message_id": _string(info.get("id")) or _string(info.get("messageID")),
            "part_id": _string(part.get("id")),
            "part_type": part_type,
        },
    )
    event = _event(
        timestamp=timestamp,
        event_type="semantic.opencode.agent_trace.message_part",
        relation="OBSERVED_MESSAGE_PART",
        source=_message_entity(info, session_id),
        target=content["target"],
        provider="opencode",
        attribution="opencode_event_bus",
        evidence_source="provider_plugin",
    )
    return [content, event]


def _subtask_events(
    payload: dict[str, Any],
    body: dict[str, Any],
    *,
    timestamp: str,
) -> list[dict[str, Any]]:
    part = body.get("part")
    if not isinstance(part, dict):
        return []
    session_id = _session_id_from(payload, body, part=part)
    if session_id is None:
        return []
    prompt = part.get("prompt")
    if not isinstance(prompt, str) or not prompt:
        return []
    source = opencode_session_agent(session_id)
    content = _content(
        store=FullFidelityContentStore(payload["__execweave_store_root"]),
        value=prompt,
        content_kind="opencode.subtask_prompt",
        timestamp=timestamp,
        source=source,
        relation="DELEGATED_SUBTASK",
        observed_field="subtask_prompt",
        attributes={"part_type": _string(part.get("type"))},
    )
    return [content]


def opencode_agent_trace_events(
    payload: dict[str, Any],
    *,
    timestamp: str,
    store: FullFidelityContentStore,
) -> list[dict[str, Any]]:
    """Project OpenCode session/message/subtask evidence without inferring missing linkage."""
    body = _opencode_event_body(payload)
    event_type = _string(payload.get("type")) or _string(body.get("type"))
    prepared = dict(payload)
    prepared["__execweave_store_root"] = str(store.run_root)
    if event_type in {"message.part.updated", "message.updated"}:
        return _message_part_events(prepared, body, timestamp=timestamp)
    if event_type in {"part.updated", "message.part.updated"}:
        return _subtask_events(prepared, body, timestamp=timestamp)
    return []
