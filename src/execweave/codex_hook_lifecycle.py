from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

CODEX_HOOKS_REFERENCE = "https://learn.chatgpt.com/docs/hooks"

OFFICIAL_CODEX_HOOK_EVENTS = frozenset(
    {
        "SessionStart",
        "SessionEnd",
        "PreToolUse",
        "PermissionRequest",
        "PostToolUse",
        "PreCompact",
        "PostCompact",
        "UserPromptSubmit",
        "SubagentStart",
        "SubagentStop",
        "Stop",
        "Interrupt",
    }
)

_PROJECTED_EVENTS = frozenset(
    {
        "SessionStart",
        "SessionEnd",
        "PermissionRequest",
        "PreCompact",
        "PostCompact",
        "Stop",
        "Interrupt",
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
    return _entity("agent", "agent:OpenAI Codex", name="OpenAI Codex")


def _session(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("Codex official hook payload requires session_id")
    return _entity(
        "provider_session",
        f"provider-session:codex:{session_id}",
        name=session_id,
        attributes={"provider": "codex", "session_id": session_id},
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
        "provider": "codex",
        "evidence_source": "provider_hook",
        "attribution": "codex_official_hook_contract",
        "causal": False,
        "inferred": False,
        "official_hook_contract": True,
        "official_hook_reference": CODEX_HOOKS_REFERENCE,
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


def _common(payload: dict[str, Any]) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    for key in ("session_id", "turn_id", "cwd", "model", "permission_mode"):
        value = payload.get(key)
        if isinstance(value, (str, int, float, bool)) and value != "":
            attrs[f"codex_{key}"] = value
    attrs["codex_hook_event_name"] = payload.get("hook_event_name")
    return attrs


def _observation_id(
    payload: dict[str, Any],
    *,
    timestamp: str,
    phase: str,
) -> str:
    stable = {
        "session_id": payload.get("session_id"),
        "turn_id": payload.get("turn_id"),
        "hook_event_name": payload.get("hook_event_name"),
        "trigger": payload.get("trigger"),
        "tool_name": payload.get("tool_name"),
        "phase": phase,
        "timestamp": timestamp,
    }
    raw = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _session_start(payload: dict[str, Any], timestamp: str) -> list[dict[str, Any]]:
    attrs = _common(payload)
    source = payload.get("source")
    if isinstance(source, str) and source:
        attrs["codex_session_source"] = source
    return [
        _event(
            timestamp=timestamp,
            event_type="semantic.codex.session.started",
            relation="STARTED_PROVIDER_SESSION",
            source=_main_agent(),
            target=_session(payload),
            attributes=attrs,
        )
    ]


def _session_end(payload: dict[str, Any], timestamp: str) -> list[dict[str, Any]]:
    attrs = _common(payload)
    reason = payload.get("reason")
    if isinstance(reason, str) and reason:
        attrs["codex_session_end_reason"] = reason
    attrs["main_thread_only_by_contract"] = True
    return [
        _event(
            timestamp=timestamp,
            event_type="semantic.codex.session.ended",
            relation="OBSERVED_PROVIDER_SESSION_END",
            source=_main_agent(),
            target=_session(payload),
            attributes=attrs,
        )
    ]


def _permission_request(payload: dict[str, Any], timestamp: str) -> list[dict[str, Any]]:
    turn_id = payload.get("turn_id")
    tool_name = payload.get("tool_name")
    if not isinstance(turn_id, str) or not turn_id:
        raise ValueError("PermissionRequest requires turn_id")
    if not isinstance(tool_name, str) or not tool_name:
        raise ValueError("PermissionRequest requires tool_name")

    attrs = _common(payload)
    attrs["tool_name"] = tool_name
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        attrs["tool_input_keys"] = sorted(str(key) for key in tool_input)
        description = tool_input.get("description")
        if isinstance(description, str) and description:
            attrs["description_present"] = True

    observation_id = _observation_id(payload, timestamp=timestamp, phase="permission_request")
    request = _entity(
        "permission_request",
        f"permission-request:codex:{observation_id}",
        name=f"{tool_name} permission request",
        attributes={
            "provider": "codex",
            "session_id": payload.get("session_id"),
            "turn_id": turn_id,
            "tool_name": tool_name,
            "identity_semantics": "provider_hook_observation_without_tool_use_id",
        },
    )
    return [
        _event(
            timestamp=timestamp,
            event_type="semantic.codex.permission.requested",
            relation="OBSERVED_PERMISSION_REQUEST",
            source=_main_agent(),
            target=request,
            attributes=attrs,
        )
    ]


def _compaction(
    payload: dict[str, Any],
    timestamp: str,
    *,
    phase: str,
) -> list[dict[str, Any]]:
    turn_id = payload.get("turn_id")
    trigger = payload.get("trigger")
    if not isinstance(turn_id, str) or not turn_id:
        raise ValueError(f"{payload.get('hook_event_name')} requires turn_id")
    if trigger not in {"manual", "auto"}:
        raise ValueError(f"{payload.get('hook_event_name')} requires trigger manual or auto")

    observation_id = _observation_id(payload, timestamp=timestamp, phase=phase)
    node = _entity(
        "context_compaction",
        f"context-compaction-observation:codex:{observation_id}",
        name=f"Codex compaction {phase}",
        attributes={
            "provider": "codex",
            "session_id": payload.get("session_id"),
            "turn_id": turn_id,
            "trigger": trigger,
            "phase": phase,
            "pairing_semantics": "no_pre_post_pairing_asserted_without_provider_compaction_id",
        },
    )
    attrs = _common(payload)
    attrs.update(
        {
            "compaction_trigger": trigger,
            "compaction_phase": phase,
            "pre_post_pairing_asserted": False,
        }
    )
    relation = "OBSERVED_PRE_COMPACTION" if phase == "pre" else "COMPACTED_CONTEXT"
    event_type = (
        "semantic.codex.compaction.before"
        if phase == "pre"
        else "semantic.codex.compaction.after"
    )
    return [
        _event(
            timestamp=timestamp,
            event_type=event_type,
            relation=relation,
            source=_main_agent(),
            target=node,
            attributes=attrs,
        )
    ]


def _stop(payload: dict[str, Any], timestamp: str) -> list[dict[str, Any]]:
    turn_id = payload.get("turn_id")
    if not isinstance(turn_id, str) or not turn_id:
        raise ValueError("Stop requires turn_id")
    observation_id = _observation_id(payload, timestamp=timestamp, phase="stop")
    stop = _entity(
        "agent_turn_stop",
        f"agent-turn-stop:codex:{observation_id}",
        name=f"Codex turn stop {turn_id}",
        attributes={
            "provider": "codex",
            "session_id": payload.get("session_id"),
            "turn_id": turn_id,
            "stop_hook_active": payload.get("stop_hook_active"),
            "completion_semantics": (
                "provider_stop_hook_fired_after_response; hook_may_request_continuation"
            ),
        },
    )
    attrs = _common(payload)
    active = payload.get("stop_hook_active")
    if isinstance(active, bool):
        attrs["stop_hook_active"] = active
    attrs["last_assistant_message_stored_separately"] = isinstance(
        payload.get("last_assistant_message"), str
    )
    return [
        _event(
            timestamp=timestamp,
            event_type="semantic.codex.turn.stop_observed",
            relation="OBSERVED_TURN_STOP",
            source=_main_agent(),
            target=stop,
            attributes=attrs,
        )
    ]


def _interrupt(payload: dict[str, Any], timestamp: str) -> list[dict[str, Any]]:
    turn_id = payload.get("turn_id")
    if not isinstance(turn_id, str) or not turn_id:
        raise ValueError("Interrupt requires turn_id")
    observation_id = _observation_id(payload, timestamp=timestamp, phase="interrupt")
    interrupt = _entity(
        "agent_turn_interrupt",
        f"agent-turn-interrupt:codex:{observation_id}",
        name=f"Codex turn interrupt {turn_id}",
        attributes={
            "provider": "codex",
            "session_id": payload.get("session_id"),
            "turn_id": turn_id,
            "interrupt_semantics": "provider_interrupt_hook_observation",
        },
    )
    attrs = _common(payload)
    attrs["interrupt_cannot_be_blocked_by_hook"] = True
    return [
        _event(
            timestamp=timestamp,
            event_type="semantic.codex.turn.interrupted",
            relation="OBSERVED_TURN_INTERRUPT",
            source=_main_agent(),
            target=interrupt,
            attributes=attrs,
        )
    ]


def codex_official_hook_lifecycle_events(
    payload: dict[str, Any],
    *,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """Project only semantics explicitly documented by the current Codex Hooks contract."""

    hook_event = payload.get("hook_event_name")
    if not isinstance(hook_event, str) or not hook_event:
        raise ValueError("Codex hook payload requires hook_event_name")
    if hook_event not in OFFICIAL_CODEX_HOOK_EVENTS or hook_event not in _PROJECTED_EVENTS:
        return []

    observed_at = timestamp or _now()
    _session(payload)

    if hook_event == "SessionStart":
        return _session_start(payload, observed_at)
    if hook_event == "SessionEnd":
        return _session_end(payload, observed_at)
    if hook_event == "PermissionRequest":
        return _permission_request(payload, observed_at)
    if hook_event == "PreCompact":
        return _compaction(payload, observed_at, phase="pre")
    if hook_event == "PostCompact":
        return _compaction(payload, observed_at, phase="post")
    if hook_event == "Stop":
        return _stop(payload, observed_at)
    if hook_event == "Interrupt":
        return _interrupt(payload, observed_at)
    return []
