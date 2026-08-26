from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from .content_evidence import content_observation_event, filter_transport_credentials
from .content_store import ContentReference, FullFidelityContentStore

_CONTENT_FIELDS = frozenset(
    {
        "prompt",
        "prompt_response",
        "llm_request",
        "llm_response",
        "tool_input",
        "tool_response",
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
    return _entity("agent", "agent:Gemini CLI", name="Gemini CLI")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _tool_observation(
    payload: dict[str, Any],
    *,
    hook_event: str,
    timestamp: str,
) -> dict[str, Any]:
    tool_name = payload.get("tool_name")
    name = tool_name if isinstance(tool_name, str) and tool_name else "unknown"
    session_id = payload.get("session_id")
    session = session_id if isinstance(session_id, str) and session_id else "unknown"
    fingerprint_input = {
        "session_id": session,
        "hook_event_name": hook_event,
        "timestamp": timestamp,
        "tool_name": name,
        "tool_input": payload.get("tool_input"),
    }
    digest = hashlib.sha256(_canonical_json(fingerprint_input).encode("utf-8")).hexdigest()[:24]
    return _entity(
        "tool_call_observation",
        f"tool-call-observation:gemini:{session}:{digest}",
        name=name,
        attributes={
            "provider": "gemini",
            "tool_name": name,
            "hook_event_name": hook_event,
            "identity_semantics": "provider_hook_observation_without_unique_tool_call_id",
            "direct_before_after_linkage_asserted": False,
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
    merged: dict[str, Any] = {"gemini_hook_event_name": hook_event}
    if attributes:
        merged.update(attributes)
    return content_observation_event(
        timestamp=timestamp,
        provider="gemini",
        source=source,
        reference=reference,
        relation=relation,
        observed_field=observed_field,
        evidence_source="provider_hook",
        attribution="gemini_hook",
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
    reference = store.put_json(filtered, content_kind="gemini.provider_hook_metadata")
    return content_observation_event(
        timestamp=timestamp,
        provider="gemini",
        source=_main_agent(),
        reference=reference,
        relation="OBSERVED_PROVIDER_METADATA",
        observed_field="hook_metadata",
        evidence_source="provider_hook",
        attribution="gemini_hook",
        attributes={
            "gemini_hook_event_name": hook_event,
            "transport_credentials_excluded": removed,
        },
    )


def gemini_hook_to_content_events(
    payload: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """Persist complete values exposed by Gemini CLI hooks.

    ``complete_from_source`` means ExecWeave stores the entire value delivered to the hook.
    It does not claim Gemini exposed non-text model parts, hidden reasoning, or lifecycle
    stages that are absent from the hook contract.
    """

    hook_event = payload.get("hook_event_name")
    if not isinstance(hook_event, str) or not hook_event:
        raise ValueError("Gemini hook payload requires hook_event_name")

    provider_timestamp = payload.get("timestamp")
    observed_at = timestamp or (
        provider_timestamp
        if isinstance(provider_timestamp, str) and provider_timestamp
        else _now()
    )
    events: list[dict[str, Any]] = []

    metadata_event = _metadata_event(
        payload,
        store=store,
        timestamp=observed_at,
        hook_event=hook_event,
    )
    if metadata_event is not None:
        events.append(metadata_event)

    if hook_event == "BeforeAgent" and isinstance(payload.get("prompt"), str):
        events.append(
            _content_event(
                store=store,
                value=payload["prompt"],
                content_kind="gemini.user_prompt",
                timestamp=observed_at,
                source=_main_agent(),
                relation="RECEIVED_USER_PROMPT",
                observed_field="prompt",
                hook_event=hook_event,
            )
        )

    elif hook_event == "AfterAgent":
        if isinstance(payload.get("prompt"), str):
            events.append(
                _content_event(
                    store=store,
                    value=payload["prompt"],
                    content_kind="gemini.user_prompt",
                    timestamp=observed_at,
                    source=_main_agent(),
                    relation="OBSERVED_AGENT_PROMPT",
                    observed_field="prompt",
                    hook_event=hook_event,
                )
            )
        if isinstance(payload.get("prompt_response"), str):
            events.append(
                _content_event(
                    store=store,
                    value=payload["prompt_response"],
                    content_kind="gemini.assistant_final_response",
                    timestamp=observed_at,
                    source=_main_agent(),
                    relation="PRODUCED_ASSISTANT_RESPONSE",
                    observed_field="prompt_response",
                    hook_event=hook_event,
                )
            )

    elif hook_event in {"BeforeModel", "BeforeToolSelection"} and "llm_request" in payload:
        events.append(
            _content_event(
                store=store,
                value=payload["llm_request"],
                content_kind="gemini.llm_request",
                timestamp=observed_at,
                source=_main_agent(),
                relation=(
                    "OBSERVED_LLM_REQUEST_BEFORE_MODEL"
                    if hook_event == "BeforeModel"
                    else "OBSERVED_LLM_REQUEST_BEFORE_TOOL_SELECTION"
                ),
                observed_field="llm_request",
                hook_event=hook_event,
                attributes={"final_request_after_all_hooks_asserted": False},
            )
        )

    elif hook_event == "AfterModel":
        if "llm_request" in payload:
            events.append(
                _content_event(
                    store=store,
                    value=payload["llm_request"],
                    content_kind="gemini.llm_request",
                    timestamp=observed_at,
                    source=_main_agent(),
                    relation="OBSERVED_LLM_REQUEST_FOR_RESPONSE",
                    observed_field="llm_request",
                    hook_event=hook_event,
                )
            )
        if "llm_response" in payload:
            events.append(
                _content_event(
                    store=store,
                    value=payload["llm_response"],
                    content_kind="gemini.llm_response_chunk",
                    timestamp=observed_at,
                    source=_main_agent(),
                    relation="RECEIVED_LLM_RESPONSE_CHUNK",
                    observed_field="llm_response",
                    hook_event=hook_event,
                    attributes={"streaming_chunk": True},
                )
            )

    elif hook_event in {"BeforeTool", "AfterTool"}:
        tool_observation = _tool_observation(
            payload,
            hook_event=hook_event,
            timestamp=observed_at,
        )
        if "tool_input" in payload:
            events.append(
                _content_event(
                    store=store,
                    value=payload["tool_input"],
                    content_kind="gemini.tool_input",
                    timestamp=observed_at,
                    source=tool_observation,
                    relation=(
                        "OBSERVED_TOOL_INPUT_BEFORE_EXECUTION"
                        if hook_event == "BeforeTool"
                        else "OBSERVED_TOOL_INPUT_AFTER_EXECUTION"
                    ),
                    observed_field="tool_input",
                    hook_event=hook_event,
                    attributes={"direct_before_after_linkage_asserted": False},
                )
            )
        if hook_event == "AfterTool" and "tool_response" in payload:
            events.append(
                _content_event(
                    store=store,
                    value=payload["tool_response"],
                    content_kind="gemini.tool_response",
                    timestamp=observed_at,
                    source=tool_observation,
                    relation="RECEIVED_TOOL_OUTPUT",
                    observed_field="tool_response",
                    hook_event=hook_event,
                    attributes={"direct_before_after_linkage_asserted": False},
                )
            )

    return events
