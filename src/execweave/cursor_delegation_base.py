from __future__ import annotations

from typing import Any

from .agent_trace import agent_trace_visibility, cursor_root_agent, cursor_subagent
from .content_evidence import content_observation_event
from .content_store import FullFidelityContentStore


def _entity(kind: str, ident: str, name: str, **attributes: Any) -> dict[str, Any]:
    return {
        "type": kind,
        "id": ident,
        "name": name,
        "attributes": attributes,
    }


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
        "provider": "cursor",
        "attribution": "cursor_hook",
        "evidence_source": "provider_hook",
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


def _scope(payload: dict[str, Any]) -> str:
    for key in ("conversation_id", "session_id", "generation_id"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return "unknown"


def _subtask(payload: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    subagent_id = child.get("attributes", {}).get("subagent_id")
    description = payload.get("description")
    task = payload.get("task")
    name = (
        description
        if isinstance(description, str) and description
        else task
        if isinstance(task, str) and task
        else "Cursor subtask"
    )
    if len(name) > 160:
        name = name[:157] + "..."
    return _entity(
        "subtask",
        f"subtask:cursor:{_scope(payload)}:subagent:{subagent_id}",
        name,
        provider="cursor",
        subagent_id=subagent_id,
        identity_semantics="provider_subagent_id",
        exact_child_agent_linkage=True,
    )


def _content(
    *,
    store: FullFidelityContentStore,
    value: str,
    content_kind: str,
    timestamp: str,
    source: dict[str, Any],
    relation: str,
    observed_field: str,
) -> dict[str, Any]:
    reference = store.put_text(value, content_kind=content_kind)
    return content_observation_event(
        timestamp=timestamp,
        provider="cursor",
        source=source,
        reference=reference,
        relation=relation,
        observed_field=observed_field,
        evidence_source="provider_hook",
        attribution="cursor_hook",
        event_type="semantic.cursor.delegation.content",
        attributes={
            "cursor_hook_event_name": "subagentStart"
            if relation.startswith("HAS_SUBTASK_")
            else "subagentStop",
            "provider_subagent_id_exact": True,
            "exact_child_agent_linkage": True,
            **agent_trace_visibility("cursor"),
        },
    )


def cursor_delegation_events(
    payload: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    timestamp: str,
) -> list[dict[str, Any]]:
    """Normalize exact Cursor subagent delegation into common communication edges.

    Cursor ``subagentStart`` exposes the child ``subagent_id`` together with the
    delegated task. ExecWeave therefore links the request, subtask, and child
    directly without timing inference. ``subagentStop`` reuses the same stable
    child identity and records the returned result edge. If the child ID is absent,
    this projection emits nothing rather than inventing a parent/child join.
    """
    hook = payload.get("hook_event_name")
    if hook not in {"subagentStart", "subagentStop"}:
        return []
    child = cursor_subagent(payload)
    if child is None:
        return []

    root = cursor_root_agent()
    subtask = _subtask(payload, child)
    visibility = agent_trace_visibility("cursor")
    exact = {
        "provider_subagent_id_exact": True,
        "exact_child_agent_linkage": True,
        **visibility,
    }
    events: list[dict[str, Any]] = []

    if hook == "subagentStart":
        events.extend(
            [
                _event(
                    timestamp=timestamp,
                    event_type="semantic.cursor.subtask.requested",
                    relation="REQUESTED_SUBTASK",
                    source=root,
                    target=subtask,
                    attributes=exact,
                ),
                _event(
                    timestamp=timestamp,
                    event_type="semantic.cursor.subtask.assigned",
                    relation="ASSIGNED_AGENT_TASK",
                    source=subtask,
                    target=child,
                    attributes=exact,
                ),
            ]
        )
        task = payload.get("task")
        if isinstance(task, str):
            events.append(
                _content(
                    store=store,
                    value=task,
                    content_kind="cursor.subtask_prompt",
                    timestamp=timestamp,
                    source=subtask,
                    relation="HAS_SUBTASK_PROMPT",
                    observed_field="task",
                )
            )
        description = payload.get("description")
        if isinstance(description, str):
            events.append(
                _content(
                    store=store,
                    value=description,
                    content_kind="cursor.subtask_description",
                    timestamp=timestamp,
                    source=subtask,
                    relation="HAS_SUBTASK_DESCRIPTION",
                    observed_field="description",
                )
            )
        return events

    events.append(
        _event(
            timestamp=timestamp,
            event_type="semantic.cursor.subagent.result_returned",
            relation="RETURNED_AGENT_RESULT",
            source=child,
            target=root,
            attributes=exact,
        )
    )
    summary = payload.get("summary")
    if isinstance(summary, str):
        events.append(
            _content(
                store=store,
                value=summary,
                content_kind="cursor.agent_result",
                timestamp=timestamp,
                source=child,
                relation="HAS_AGENT_RESULT_PAYLOAD",
                observed_field="summary",
            )
        )
    return events
