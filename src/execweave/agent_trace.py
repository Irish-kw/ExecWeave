from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .content_evidence import content_observation_event
from .content_store import FullFidelityContentStore
from .agent_topology import EVIDENCE_SUBAGENT_LIFECYCLE_HOOK, subagent_topology
from .agent_topology import root_topology

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
    "codex": ("agent:Codex", "Codex"),
    "cursor": ("agent:Cursor", "Cursor"),
    "opencode": ("agent:OpenCode", "OpenCode"),
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
        **root_topology(),
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


def _declared_opencode_file(
    *,
    payload: dict[str, Any],
    args: Any,
) -> dict[str, Any] | None:
    """Project only an explicitly supplied OpenCode file argument.

    Event-bus tool parts and plugin tool hooks use the same provider file
    argument contract.  Keep path projection metadata-only; file contents stay
    in the full-fidelity content store.
    """
    if not isinstance(args, dict):
        return None
    raw = None
    for key in ("filePath", "file_path", "path"):
        value = args.get(key)
        if isinstance(value, str) and value:
            raw = value
            break
    if raw is None:
        return None
    candidate = Path(raw).expanduser()
    cwd = _string(payload.get("cwd"))
    if not candidate.is_absolute() and cwd is not None:
        candidate = Path(cwd) / candidate
    try:
        normalized = candidate.resolve(strict=False)
    except OSError:
        normalized = candidate.absolute()
    return _entity(
        "file",
        f"file:{normalized}",
        normalized.name or str(normalized),
        provider="opencode",
        declared_by_provider_event_bus=True,
    )


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
        "session_id": session_id,
        "message_id": message_id,
        "role": role,
    }
    for key in ("agent", "modelID", "providerID", "parentID"):
        value = info.get(key)
        if isinstance(value, (str, int, float, bool)) and value != "":
            attributes[key] = value
    tokens = info.get("tokens")
    if isinstance(tokens, dict):
        reasoning = tokens.get("reasoning")
        if isinstance(reasoning, (int, float)) and not isinstance(reasoning, bool):
            attributes["reasoning_tokens"] = reasoning
    return _entity(
        "agent_message",
        f"agent-message:opencode:{session_id}:{message_id}",
        f"{role} message",
        **attributes,
    )


def _part_identity(part: dict[str, Any], session_id: str) -> tuple[str, str]:
    message_id = _string(part.get("messageID")) or _string(part.get("messageId")) or "unknown"
    part_id = _string(part.get("id"))
    if part_id is None:
        canonical = json.dumps(part, ensure_ascii=False, sort_keys=True, default=str)
        part_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    return message_id, part_id


def _session_events(
    *,
    event_type: str,
    body: dict[str, Any],
    payload: dict[str, Any],
    timestamp: str,
) -> list[dict[str, Any]]:
    info = body.get("info")
    if not isinstance(info, dict):
        info = body.get("session")
    if not isinstance(info, dict):
        return []
    session_id = _session_id_from(payload, body, info=info)
    if session_id is None:
        return []
    native_agent = _string(info.get("agent"))
    child = opencode_session_agent(session_id, agent_name=native_agent)
    parent_id = _string(info.get("parentID")) or _string(info.get("parentId"))
    if parent_id is not None:
        return [
            _event(
                timestamp=timestamp,
                event_type="semantic.opencode.agent_session.child",
                relation="HAS_CHILD_AGENT_SESSION",
                source=opencode_session_agent(parent_id),
                target=child,
                provider="opencode",
                attribution="opencode_event_bus",
                evidence_source="provider_plugin",
                attributes={
                    "provider_parent_id_exact": True,
                    "opencode_event_type": event_type,
                    **agent_trace_visibility("opencode"),
                },
            )
        ]
    if event_type == "session.created":
        return [
            _event(
                timestamp=timestamp,
                event_type="semantic.opencode.agent_session.started",
                relation="STARTED_AGENT_SESSION",
                source=opencode_root_agent(),
                target=child,
                provider="opencode",
                attribution="opencode_event_bus",
                evidence_source="provider_plugin",
                attributes={
                    "root_session_from_absence_of_parent_id": True,
                    "opencode_event_type": event_type,
                    **agent_trace_visibility("opencode"),
                },
            )
        ]
    return []


def _message_events(
    *,
    body: dict[str, Any],
    payload: dict[str, Any],
    timestamp: str,
) -> list[dict[str, Any]]:
    info = body.get("info")
    if not isinstance(info, dict):
        info = body.get("message")
    if not isinstance(info, dict):
        return []
    session_id = _session_id_from(payload, body, info=info)
    if session_id is None:
        return []
    agent_name = _string(info.get("agent"))
    agent = opencode_session_agent(session_id, agent_name=agent_name)
    message = _message_entity(info, session_id)
    role = _string(info.get("role")) or "unknown"
    events: list[dict[str, Any]] = []
    if role == "assistant":
        events.append(
            _event(
                timestamp=timestamp,
                event_type="semantic.opencode.agent_message.produced",
                relation="PRODUCED_ASSISTANT_MESSAGE",
                source=agent,
                target=message,
                provider="opencode",
                attribution="opencode_event_bus",
                evidence_source="provider_plugin",
                attributes=agent_trace_visibility("opencode"),
            )
        )
    elif role == "user":
        events.append(
            _event(
                timestamp=timestamp,
                event_type="semantic.opencode.agent_message.delivered",
                relation="DELIVERED_USER_MESSAGE",
                source=message,
                target=agent,
                provider="opencode",
                attribution="opencode_event_bus",
                evidence_source="provider_plugin",
                attributes=agent_trace_visibility("opencode"),
            )
        )
    if agent_name is not None:
        profile = _entity(
            "agent_profile",
            f"agent-profile:opencode:{agent_name}",
            agent_name,
            provider="opencode",
            native_agent_name=agent_name,
        )
        events.append(
            _event(
                timestamp=timestamp,
                event_type="semantic.opencode.agent_profile.used",
                relation="USED_AGENT_PROFILE",
                source=agent,
                target=profile,
                provider="opencode",
                attribution="opencode_event_bus",
                evidence_source="provider_plugin",
            )
        )
    return events


def _reasoning_part_events(
    *,
    part: dict[str, Any],
    session_id: str,
    timestamp: str,
    store: FullFidelityContentStore,
) -> list[dict[str, Any]]:
    text = part.get("text")
    if not isinstance(text, str):
        return []
    message_id, part_id = _part_identity(part, session_id)
    agent = opencode_session_agent(session_id)
    return [
        _content(
            store=store,
            value=text,
            content_kind="opencode.reasoning.text",
            timestamp=timestamp,
            source=agent,
            relation="PRODUCED_REASONING_TEXT",
            observed_field="event.properties.part.text",
            attributes={
                "reasoning_readable": True,
                "provider_labels_as_reasoning": True,
                "provider_schema_type": "reasoning",
                "message_id": message_id,
                "part_id": part_id,
                **agent_trace_visibility("opencode"),
            },
        )
    ]


def _subtask_part_events(
    *,
    part: dict[str, Any],
    session_id: str,
    timestamp: str,
    store: FullFidelityContentStore,
) -> list[dict[str, Any]]:
    message_id, part_id = _part_identity(part, session_id)
    description = _string(part.get("description")) or "OpenCode subtask"
    subtask = _entity(
        "subtask",
        f"subtask:opencode:{session_id}:{message_id}:{part_id}",
        description,
        provider="opencode",
        session_id=session_id,
        message_id=message_id,
        part_id=part_id,
    )
    agent = opencode_session_agent(session_id)
    events = [
        _event(
            timestamp=timestamp,
            event_type="semantic.opencode.subtask.requested",
            relation="REQUESTED_SUBTASK",
            source=agent,
            target=subtask,
            provider="opencode",
            attribution="opencode_event_bus",
            evidence_source="provider_plugin",
            attributes={"exact_child_session_linkage_asserted": False},
        )
    ]
    target_agent = _string(part.get("agent"))
    if target_agent is not None:
        profile = _entity(
            "agent_profile",
            f"agent-profile:opencode:{target_agent}",
            target_agent,
            provider="opencode",
            native_agent_name=target_agent,
        )
        events.append(
            _event(
                timestamp=timestamp,
                event_type="semantic.opencode.subtask.targeted",
                relation="TARGETS_AGENT_PROFILE",
                source=subtask,
                target=profile,
                provider="opencode",
                attribution="opencode_event_bus",
                evidence_source="provider_plugin",
                attributes={"exact_child_session_linkage_asserted": False},
            )
        )
    for field, kind, relation in (
        ("prompt", "opencode.subtask_prompt", "HAS_SUBTASK_PROMPT"),
        ("description", "opencode.subtask_description", "HAS_SUBTASK_DESCRIPTION"),
    ):
        value = part.get(field)
        if isinstance(value, str):
            events.append(
                _content(
                    store=store,
                    value=value,
                    content_kind=kind,
                    timestamp=timestamp,
                    source=subtask,
                    relation=relation,
                    observed_field=f"event.properties.part.{field}",
                    attributes={"exact_child_session_linkage_asserted": False},
                )
            )
    return events


def _agent_part_events(
    *,
    part: dict[str, Any],
    session_id: str,
    timestamp: str,
) -> list[dict[str, Any]]:
    name = _string(part.get("name")) or _string(part.get("agent"))
    if name is None:
        return []
    profile = _entity(
        "agent_profile",
        f"agent-profile:opencode:{name}",
        name,
        provider="opencode",
        native_agent_name=name,
    )
    return [
        _event(
            timestamp=timestamp,
            event_type="semantic.opencode.agent_profile.observed",
            relation="USED_AGENT_PROFILE",
            source=opencode_session_agent(session_id),
            target=profile,
            provider="opencode",
            attribution="opencode_event_bus",
            evidence_source="provider_plugin",
        )
    ]


def _tool_part_events(
    *,
    part: dict[str, Any],
    payload: dict[str, Any],
    session_id: str,
    timestamp: str,
    store: FullFidelityContentStore,
) -> list[dict[str, Any]]:
    call_id = _string(part.get("callID")) or _string(part.get("callId"))
    tool_name = _string(part.get("tool")) or "unknown"
    if call_id is None:
        return []
    call = _entity(
        "tool_call",
        f"tool-call:opencode:{session_id}:{call_id}",
        tool_name,
        provider="opencode",
        session_id=session_id,
        call_id=call_id,
        tool_name=tool_name,
        identity_semantics="provider_call_id",
    )
    tool = _entity(
        "tool",
        f"tool:opencode:{tool_name}",
        tool_name,
        provider="opencode",
        native_name=tool_name,
    )
    agent = opencode_session_agent(session_id)
    events = [
        _event(
            timestamp=timestamp,
            event_type="semantic.opencode.tool.bus_observed",
            relation="OBSERVED_TOOL_CALL",
            source=agent,
            target=call,
            provider="opencode",
            attribution="opencode_event_bus",
            evidence_source="provider_plugin",
        ),
        _event(
            timestamp=timestamp,
            event_type="semantic.opencode.tool.bus_selected",
            relation="USES_TOOL",
            source=call,
            target=tool,
            provider="opencode",
            attribution="opencode_event_bus",
            evidence_source="provider_plugin",
        ),
    ]
    state = part.get("state")
    if isinstance(state, dict):
        target = _declared_opencode_file(
            payload=payload,
            args=state.get("input"),
        )
        if target is not None:
            events.append(
                _event(
                    timestamp=timestamp,
                    event_type="semantic.opencode.file.declared",
                    relation="DECLARED_TARGET",
                    source=call,
                    target=target,
                    provider="opencode",
                    attribution="opencode_event_bus",
                    evidence_source="provider_plugin",
                    attributes={"provider_event_projection": True},
                )
            )
        for field, kind, relation in (
            ("input", "opencode.tool_state_input", "OBSERVED_TOOL_INPUT_FROM_PROVIDER_EVENT"),
            ("output", "opencode.tool_state_output", "RECEIVED_TOOL_OUTPUT_FROM_PROVIDER_EVENT"),
            ("error", "opencode.tool_state_error", "RECEIVED_TOOL_ERROR_FROM_PROVIDER_EVENT"),
        ):
            if field in state:
                events.append(
                    _content(
                        store=store,
                        value=state[field],
                        content_kind=kind,
                        timestamp=timestamp,
                        source=call,
                        relation=relation,
                        observed_field=f"event.properties.part.state.{field}",
                        attributes={"provider_event_projection": True},
                    )
                )
    return events


def _step_part_events(
    *,
    part: dict[str, Any],
    session_id: str,
    timestamp: str,
) -> list[dict[str, Any]]:
    message_id, part_id = _part_identity(part, session_id)
    step = _entity(
        "agent_step",
        f"agent-step:opencode:{session_id}:{message_id}:{part_id}",
        "OpenCode step",
        provider="opencode",
        session_id=session_id,
        message_id=message_id,
        part_id=part_id,
    )
    attrs: dict[str, Any] = {}
    for key in ("reason", "cost"):
        value = part.get(key)
        if isinstance(value, (str, int, float, bool)) and value != "":
            attrs[key] = value
    tokens = part.get("tokens")
    if isinstance(tokens, dict):
        attrs["tokens"] = tokens
    return [
        _event(
            timestamp=timestamp,
            event_type="semantic.opencode.agent_step.completed",
            relation="COMPLETED_AGENT_STEP",
            source=opencode_session_agent(session_id),
            target=step,
            provider="opencode",
            attribution="opencode_event_bus",
            evidence_source="provider_plugin",
            attributes=attrs,
        )
    ]


def _compaction_part_events(
    *,
    part: dict[str, Any],
    session_id: str,
    timestamp: str,
) -> list[dict[str, Any]]:
    message_id, part_id = _part_identity(part, session_id)
    compact = _entity(
        "compaction",
        f"compaction:opencode:{session_id}:{message_id}:{part_id}",
        "OpenCode compaction",
        provider="opencode",
        session_id=session_id,
        message_id=message_id,
        part_id=part_id,
    )
    return [
        _event(
            timestamp=timestamp,
            event_type="semantic.opencode.context.compacted",
            relation="COMPACTED_CONTEXT",
            source=opencode_session_agent(session_id),
            target=compact,
            provider="opencode",
            attribution="opencode_event_bus",
            evidence_source="provider_plugin",
        )
    ]


def _part_events(
    *,
    body: dict[str, Any],
    payload: dict[str, Any],
    timestamp: str,
    store: FullFidelityContentStore,
) -> list[dict[str, Any]]:
    part = body.get("part")
    if not isinstance(part, dict):
        return []
    session_id = _session_id_from(payload, body, part=part)
    if session_id is None:
        return []
    kind = _string(part.get("type"))
    if kind == "reasoning":
        return _reasoning_part_events(
            part=part,
            session_id=session_id,
            timestamp=timestamp,
            store=store,
        )
    if kind == "subtask":
        return _subtask_part_events(
            part=part,
            session_id=session_id,
            timestamp=timestamp,
            store=store,
        )
    if kind == "agent":
        return _agent_part_events(part=part, session_id=session_id, timestamp=timestamp)
    if kind == "tool":
        return _tool_part_events(
            part=part,
            payload=payload,
            session_id=session_id,
            timestamp=timestamp,
            store=store,
        )
    if kind == "step-finish":
        return _step_part_events(part=part, session_id=session_id, timestamp=timestamp)
    if kind == "compaction":
        return _compaction_part_events(part=part, session_id=session_id, timestamp=timestamp)
    return []


def opencode_agent_trace_events(
    payload: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    timestamp: str,
) -> list[dict[str, Any]]:
    """Project explicit OpenCode event-bus agent/reasoning evidence into common graph semantics.

    The raw bus event remains stored independently by ``opencode_full_fidelity``.
    This projection never infers a delegating parent from a tool hook and only
    creates parent-child agent edges when OpenCode explicitly supplies ``parentID``.
    """

    hook = _string(payload.get("hook_event_name"))
    if hook is None:
        return []

    if hook in {"tool.execute.before", "tool.execute.after"}:
        session_id = _string(payload.get("sessionID"))
        call_id = _string(payload.get("callID"))
        tool_name = _string(payload.get("tool")) or "unknown"
        if session_id is None or call_id is None:
            return []
        call = _entity(
            "tool_call",
            f"tool-call:opencode:{session_id}:{call_id}",
            tool_name,
            provider="opencode",
            session_id=session_id,
            call_id=call_id,
            tool_name=tool_name,
            identity_semantics="provider_call_id",
        )
        return [
            _event(
                timestamp=timestamp,
                event_type="semantic.opencode.agent.tool_owned",
                relation="OWNED_TOOL_CALL",
                source=opencode_session_agent(
                    session_id,
                    agent_name=_string(payload.get("agent")),
                ),
                target=call,
                provider="opencode",
                attribution="opencode_plugin",
                evidence_source="provider_plugin",
                attributes={
                    "provider_session_id_exact": True,
                    **agent_trace_visibility("opencode"),
                },
            )
        ]

    if hook == "experimental.text.complete" and isinstance(payload.get("text"), str):
        session_id = _string(payload.get("sessionID"))
        if session_id is None:
            return []
        reference = store.put_text(
            payload["text"],
            content_kind="opencode.completed_text",
        )
        return [
            content_observation_event(
                timestamp=timestamp,
                provider="opencode",
                source=opencode_session_agent(
                    session_id,
                    agent_name=_string(payload.get("agent")),
                ),
                reference=reference,
                relation="PRODUCED_ASSISTANT_TEXT",
                observed_field="text",
                evidence_source="provider_plugin",
                attribution="opencode_plugin",
                event_type="semantic.opencode.agent.text",
                attributes=agent_trace_visibility("opencode"),
            )
        ]

    if hook != "event":
        return []

    raw_event = payload.get("event")
    if not isinstance(raw_event, dict):
        return []
    event_type = _string(raw_event.get("type")) or _string(payload.get("event_type"))
    if event_type is None:
        return []
    body = _opencode_event_body(raw_event)
    if event_type in {"session.created", "session.updated"}:
        events = _session_events(
            event_type=event_type,
            body=body,
            payload=payload,
            timestamp=timestamp,
        )
        if event_type == "session.created":
            events.append(
                provider_agent_trace_visibility_event(
                    "opencode",
                    timestamp=timestamp,
                    source=_opencode_agent_for_payload(payload),
                    attribution="opencode_event_bus",
                    evidence_source="provider_plugin",
                )
            )
        return events
    if event_type == "message.updated":
        return _message_events(body=body, payload=payload, timestamp=timestamp)
    if event_type == "message.part.updated":
        return _part_events(
            body=body,
            payload=payload,
            timestamp=timestamp,
            store=store,
        )
    return []


def cursor_root_agent() -> dict[str, Any]:
    return _entity("agent", "agent:Cursor", "Cursor", provider="cursor")


def cursor_subagent(
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    subagent_id = _string(payload.get("subagent_id"))
    if subagent_id is None:
        return None
    scope = None
    for key in ("conversation_id", "session_id", "generation_id"):
        scope = _string(payload.get(key))
        if scope is not None:
            break
    if scope is None:
        scope = "unknown"
    subagent_type = _string(payload.get("subagent_type")) or "Cursor subagent"
    return _entity(
        "agent",
        f"agent:cursor:{scope}:subagent:{subagent_id}",
        subagent_type,
        provider="cursor",
        subagent_id=subagent_id,
        subagent_type=subagent_type,
        identity_semantics="provider_subagent_id",
        **subagent_topology(
            evidence=EVIDENCE_SUBAGENT_LIFECYCLE_HOOK,
            parent_scope_id=scope,
        ),
    )


def cursor_agent_trace_events(
    payload: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    timestamp: str,
) -> list[dict[str, Any]]:
    """Add exact Cursor subagent ownership/reasoning edges when the hook exposes IDs."""

    hook = _string(payload.get("hook_event_name"))
    if hook is None:
        return []
    child = cursor_subagent(payload)
    visibility = agent_trace_visibility("cursor")
    events: list[dict[str, Any]] = []

    if hook == "sessionStart":
        events.append(
            provider_agent_trace_visibility_event(
                "cursor",
                timestamp=timestamp,
                source=cursor_root_agent(),
                attribution="cursor_hook",
                evidence_source="provider_hook",
            )
        )

    if hook == "subagentStart" and child is not None:
        events.append(
            _event(
                timestamp=timestamp,
                event_type="semantic.cursor.subagent.started",
                relation="SPAWNED_SUBAGENT",
                source=cursor_root_agent(),
                target=child,
                provider="cursor",
                attribution="cursor_hook",
                evidence_source="provider_hook",
                attributes={**visibility, "provider_subagent_id_exact": True},
            )
        )
    elif hook == "subagentStop" and child is not None:
        events.append(
            _event(
                timestamp=timestamp,
                event_type="semantic.cursor.subagent.finished",
                relation="RETURNED_TO",
                source=child,
                target=cursor_root_agent(),
                provider="cursor",
                attribution="cursor_hook",
                evidence_source="provider_hook",
                attributes={**visibility, "provider_subagent_id_exact": True},
            )
        )

    if hook in {"preToolUse", "postToolUse", "postToolUseFailure"} and child is not None:
        tool_use_id = _string(payload.get("tool_use_id"))
        tool_name = _string(payload.get("tool_name")) or "unknown"
        if tool_use_id is not None:
            scope = None
            for key in ("conversation_id", "session_id", "generation_id"):
                scope = _string(payload.get(key))
                if scope is not None:
                    break
            if scope is None:
                scope = "unknown"
            call = _entity(
                "tool_call",
                f"tool-call:cursor:{scope}:{tool_use_id}",
                tool_name,
                provider="cursor",
                tool_name=tool_name,
                tool_use_id=tool_use_id,
            )
            events.append(
                _event(
                    timestamp=timestamp,
                    event_type="semantic.cursor.subagent.tool_owned",
                    relation="OWNED_TOOL_CALL",
                    source=child,
                    target=call,
                    provider="cursor",
                    attribution="cursor_hook",
                    evidence_source="provider_hook",
                    attributes={**visibility, "provider_subagent_id_exact": True},
                )
            )

    if hook in {"beforeShellExecution", "afterShellExecution", "beforeMCPExecution", "afterMCPExecution"} and child is not None:
        operation = _entity(
            "agent_operation",
            "agent-operation:cursor:"
            + hashlib.sha256(
                json.dumps(
                    [
                        hook,
                        child["id"],
                        payload.get("command"),
                        payload.get("tool_name"),
                        payload.get("tool_use_id"),
                    ],
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                ).encode("utf-8")
            ).hexdigest()[:24],
            hook,
            provider="cursor",
            hook_event_name=hook,
        )
        events.append(
            _event(
                timestamp=timestamp,
                event_type="semantic.cursor.subagent.operation_owned",
                relation="OWNED_AGENT_OPERATION",
                source=child,
                target=operation,
                provider="cursor",
                attribution="cursor_hook",
                evidence_source="provider_hook",
                attributes={**visibility, "provider_subagent_id_exact": True},
            )
        )

    if hook == "afterAgentThought" and isinstance(payload.get("text"), str):
        actor = child or cursor_root_agent()
        reference = store.put_text(payload["text"], content_kind="cursor.agent_thought")
        events.append(
            content_observation_event(
                timestamp=timestamp,
                provider="cursor",
                source=actor,
                reference=reference,
                relation="PRODUCED_REASONING_TEXT",
                observed_field="text",
                evidence_source="provider_hook",
                attribution="cursor_hook",
                event_type="semantic.cursor.reasoning.observed",
                attributes={
                    "cursor_hook_event_name": hook,
                    "reasoning_readable": True,
                    "provider_labels_as_thinking_text": True,
                    **visibility,
                },
            )
        )
    elif hook == "afterAgentResponse" and isinstance(payload.get("text"), str) and child is not None:
        reference = store.put_text(payload["text"], content_kind="cursor.subagent_response")
        events.append(
            content_observation_event(
                timestamp=timestamp,
                provider="cursor",
                source=child,
                reference=reference,
                relation="PRODUCED_ASSISTANT_RESPONSE",
                observed_field="text",
                evidence_source="provider_hook",
                attribution="cursor_hook",
                event_type="semantic.cursor.subagent.response",
                attributes={
                    "cursor_hook_event_name": hook,
                    "provider_subagent_id_exact": True,
                    **visibility,
                },
            )
        )
    return events
