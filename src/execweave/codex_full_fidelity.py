from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .agent_topology import EVIDENCE_SUBAGENT_LIFECYCLE_HOOK, subagent_topology
from .content_evidence import content_observation_event, filter_transport_credentials
from .content_store import ContentReference, FullFidelityContentStore

_CONTENT_FIELDS = frozenset({"prompt", "tool_input", "tool_response", "last_assistant_message"})


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


def _actor(payload: dict[str, Any]) -> dict[str, Any]:
    agent_id = payload.get("agent_id")
    if isinstance(agent_id, str) and agent_id:
        agent_type = payload.get("agent_type")
        name = agent_type if isinstance(agent_type, str) and agent_type else "Codex subagent"
        session_id = payload.get("session_id")
        scope = session_id if isinstance(session_id, str) and session_id else "unknown"
        return _entity(
            "agent",
            f"agent:codex:{scope}:subagent:{agent_id}",
            name=name,
            attributes={
                "provider": "codex",
                "agent_id": agent_id,
                "agent_type": name,
                **subagent_topology(
                    evidence=EVIDENCE_SUBAGENT_LIFECYCLE_HOOK,
                    parent_scope_id=scope,
                ),
            },
        )
    return _main_agent()


def _tool_call(payload: dict[str, Any]) -> dict[str, Any] | None:
    tool_name = payload.get("tool_name")
    tool_use_id = payload.get("tool_use_id")
    if not isinstance(tool_name, str) or not tool_name:
        return None
    if not isinstance(tool_use_id, str) or not tool_use_id:
        return None
    session_id = payload.get("session_id")
    session = session_id if isinstance(session_id, str) and session_id else "unknown"
    return _entity(
        "tool_call",
        f"tool-call:codex:{session}:{tool_use_id}",
        name=tool_name,
        attributes={
            "provider": "codex",
            "tool_name": tool_name,
            "tool_use_id": tool_use_id,
        },
    )


def _store_value(
    store: FullFidelityContentStore,
    value: Any,
    *,
    content_kind: str,
) -> ContentReference:
    if isinstance(value, str):
        return store.put_text(value, content_kind=content_kind)
    return store.put_json(value, content_kind=content_kind)


def _content_event(
    *,
    store: FullFidelityContentStore,
    value: Any,
    content_kind: str,
    timestamp: str,
    source: dict[str, Any],
    relation: str,
    observed_field: str,
    hook_event: str,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reference = _store_value(store, value, content_kind=content_kind)
    merged = {"codex_hook_event_name": hook_event}
    if attributes:
        merged.update(attributes)
    return content_observation_event(
        timestamp=timestamp,
        provider="codex",
        source=source,
        reference=reference,
        relation=relation,
        observed_field=observed_field,
        evidence_source="provider_hook",
        attribution="codex_hook",
        attributes=merged,
    )


def _metadata_event(
    payload: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    timestamp: str,
    hook_event: str,
) -> dict[str, Any] | None:
    metadata = {key: value for key, value in payload.items() if key not in _CONTENT_FIELDS}
    filtered, removed = filter_transport_credentials(metadata)
    if not filtered:
        return None
    reference = store.put_json(filtered, content_kind="codex.provider_hook_metadata")
    return content_observation_event(
        timestamp=timestamp,
        provider="codex",
        source=_actor(payload),
        reference=reference,
        relation="OBSERVED_PROVIDER_METADATA",
        observed_field="hook_metadata",
        evidence_source="provider_hook",
        attribution="codex_hook",
        attributes={
            "codex_hook_event_name": hook_event,
            "transport_credentials_excluded": removed,
        },
    )


def codex_hook_to_metadata_events(
    payload: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """Persist provider hook metadata independently from optional content values.

    This is deliberately a separate stage so a failure while storing a prompt,
    tool result, or final assistant message cannot erase already-observed routing
    metadata such as ``agent_transcript_path``.
    """
    hook_event = payload.get("hook_event_name")
    if not isinstance(hook_event, str) or not hook_event:
        raise ValueError("Codex hook payload requires hook_event_name")
    observed_at = timestamp or _now()
    event = _metadata_event(
        payload,
        store=store,
        timestamp=observed_at,
        hook_event=hook_event,
    )
    return [event] if event is not None else []


def codex_hook_to_content_events(
    payload: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    timestamp: str | None = None,
    include_metadata: bool = True,
) -> list[dict[str, Any]]:
    """Persist complete values exposed by the documented Codex hook contract.

    Completeness is limited to values Codex supplies to the hook. This function does not read
    transcript paths or claim access to hidden prompts, internal reasoning, or provider-side stages.

    ``include_metadata`` defaults to true for backwards-compatible direct callers.
    The CLI captures metadata in its own independent stage and passes false here so
    optional content failures cannot discard metadata that was already observed.
    """
    hook_event = payload.get("hook_event_name")
    if not isinstance(hook_event, str) or not hook_event:
        raise ValueError("Codex hook payload requires hook_event_name")

    observed_at = timestamp or _now()
    events: list[dict[str, Any]] = []
    if include_metadata:
        events.extend(
            codex_hook_to_metadata_events(
                payload,
                store=store,
                timestamp=observed_at,
            )
        )

    if hook_event == "UserPromptSubmit" and isinstance(payload.get("prompt"), str):
        events.append(
            _content_event(
                store=store,
                value=payload["prompt"],
                content_kind="codex.user_prompt",
                timestamp=observed_at,
                source=_actor(payload),
                relation="RECEIVED_USER_PROMPT",
                observed_field="prompt",
                hook_event=hook_event,
            )
        )

    if hook_event in {"PreToolUse", "PostToolUse"}:
        call = _tool_call(payload)
        if call is not None and "tool_input" in payload:
            events.append(
                _content_event(
                    store=store,
                    value=payload["tool_input"],
                    content_kind="codex.tool_input",
                    timestamp=observed_at,
                    source=call,
                    relation="HAS_TOOL_INPUT",
                    observed_field="tool_input",
                    hook_event=hook_event,
                )
            )
        if hook_event == "PostToolUse" and call is not None and "tool_response" in payload:
            events.append(
                _content_event(
                    store=store,
                    value=payload["tool_response"],
                    content_kind="codex.tool_response",
                    timestamp=observed_at,
                    source=call,
                    relation="HAS_TOOL_OUTPUT",
                    observed_field="tool_response",
                    hook_event=hook_event,
                    attributes={"model_visible_serialization": False},
                )
            )

    if hook_event == "PermissionRequest" and "tool_input" in payload:
        tool_name = payload.get("tool_name")
        attrs = {"tool_name": tool_name} if isinstance(tool_name, str) and tool_name else None
        events.append(
            _content_event(
                store=store,
                value=payload["tool_input"],
                content_kind="codex.permission_request_tool_input",
                timestamp=observed_at,
                source=_actor(payload),
                relation="REQUESTED_PERMISSION_FOR_TOOL_INPUT",
                observed_field="tool_input",
                hook_event=hook_event,
                attributes=attrs,
            )
        )

    if hook_event in {"Stop", "SubagentStop"} and isinstance(
        payload.get("last_assistant_message"), str
    ):
        content_kind = (
            "codex.subagent_final_response"
            if hook_event == "SubagentStop"
            else "codex.assistant_final_response"
        )
        events.append(
            _content_event(
                store=store,
                value=payload["last_assistant_message"],
                content_kind=content_kind,
                timestamp=observed_at,
                source=_actor(payload),
                relation="PRODUCED_ASSISTANT_RESPONSE",
                observed_field="last_assistant_message",
                hook_event=hook_event,
            )
        )

    return events
