from __future__ import annotations

from typing import Any
from .agent_topology import EVIDENCE_SUBAGENT_LIFECYCLE_HOOK, subagent_topology


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


def _main_agent() -> dict[str, Any]:
    return _entity("agent", "agent:Claude Code", "Claude Code", provider="claude")


def _subagent(payload: dict[str, Any]) -> dict[str, Any] | None:
    session_id = payload.get("session_id")
    agent_id = payload.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id:
        return None
    session = session_id if isinstance(session_id, str) and session_id else "unknown"
    agent_type = payload.get("agent_type")
    name = agent_type if isinstance(agent_type, str) and agent_type else "Claude subagent"
    return _entity(
        "agent",
        f"agent:claude:{session}:subagent:{agent_id}",
        name,
        provider="claude",
        agent_id=agent_id,
        agent_type=name,
        **subagent_topology(
            evidence=EVIDENCE_SUBAGENT_LIFECYCLE_HOOK,
            parent_scope_id=session,
        ),
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
        "provider": "claude",
        "attribution": "claude_hook",
        "evidence_source": "provider_hook",
        "causal": False,
        "inferred": False,
        "provider_agent_id_exact": True,
        "exact_child_agent_linkage": True,
        "subtask_prompt_linkage_asserted": False,
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


def claude_delegation_events(
    payload: dict[str, Any],
    *,
    content_events: list[dict[str, Any]],
    timestamp: str,
) -> list[dict[str, Any]]:
    """Normalize exact Claude SubagentStop return evidence without inventing a task join.

    Claude's SubagentStop hook exposes a stable ``agent_id`` and can expose
    ``last_assistant_message``. ExecWeave therefore records a normalized
    child-to-root result edge and, when the full-fidelity content observer saw
    that final response, a result-payload edge to the same stored content node.

    This deliberately does not create REQUESTED_SUBTASK or ASSIGNED_AGENT_TASK:
    the hook evidence handled here does not establish an exact prompt-to-child join.
    """

    if payload.get("hook_event_name") != "SubagentStop":
        return []
    child = _subagent(payload)
    if child is None:
        return []

    root = _main_agent()
    events = [
        _event(
            timestamp=timestamp,
            event_type="semantic.claude.subagent.result_returned",
            relation="RETURNED_AGENT_RESULT",
            source=child,
            target=root,
        )
    ]

    for observed in content_events:
        if observed.get("relation") != "PRODUCED_ASSISTANT_RESPONSE":
            continue
        source = observed.get("source")
        target = observed.get("target")
        if not isinstance(source, dict) or source.get("id") != child["id"]:
            continue
        if not isinstance(target, dict) or target.get("type") != "observed_content":
            continue
        observed_attributes = observed.get("attributes")
        carried = dict(observed_attributes) if isinstance(observed_attributes, dict) else {}
        carried["normalized_from_relation"] = "PRODUCED_ASSISTANT_RESPONSE"
        events.append(
            _event(
                timestamp=timestamp,
                event_type="semantic.claude.subagent.result_payload",
                relation="HAS_AGENT_RESULT_PAYLOAD",
                source=child,
                target=target,
                attributes=carried,
            )
        )
        break
    return events
