from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .content_evidence import content_observation_event, filter_transport_credentials
from .content_store import FullFidelityContentStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _agent() -> dict[str, Any]:
    return {
        "type": "agent",
        "id": "agent:Antigravity",
        "name": "Antigravity",
        "attributes": {},
    }


def antigravity_hook_to_content_events(
    payload: dict[str, Any],
    *,
    hook_event: str,
    store: FullFidelityContentStore,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """Store complete values explicitly supplied by Antigravity's hook contract."""
    observed_at = timestamp or _now()
    events: list[dict[str, Any]] = []

    metadata = {key: value for key, value in payload.items() if key != "toolCall"}
    filtered, removed = filter_transport_credentials(metadata)
    if filtered:
        reference = store.put_json(filtered, content_kind="antigravity.provider_hook_metadata")
        events.append(
            content_observation_event(
                timestamp=observed_at,
                provider="antigravity",
                source=_agent(),
                reference=reference,
                relation="OBSERVED_PROVIDER_METADATA",
                observed_field="hook_metadata",
                evidence_source="provider_hook",
                attribution="antigravity_hook",
                attributes={
                    "antigravity_hook_event_name": hook_event,
                    "transport_credentials_excluded": removed,
                },
            )
        )

    tool_call = payload.get("toolCall")
    if hook_event == "PostToolUse" and isinstance(tool_call, dict) and "args" in tool_call:
        tool_name = tool_call.get("name")
        name = tool_name if isinstance(tool_name, str) and tool_name else "unknown"
        reference = store.put_json(
            tool_call.get("args"),
            content_kind="antigravity.tool_input",
        )
        source = {
            "type": "tool_call_observation",
            "id": (
                "tool-call-observation:antigravity:"
                f"{payload.get('conversationId', 'unknown')}:"
                f"{payload.get('stepIdx', 'unknown')}"
            ),
            "name": name,
            "attributes": {"provider": "antigravity", "tool_name": name},
        }
        events.append(
            content_observation_event(
                timestamp=observed_at,
                provider="antigravity",
                source=source,
                reference=reference,
                relation="OBSERVED_TOOL_INPUT_AFTER_EXECUTION",
                observed_field="toolCall.args",
                evidence_source="provider_hook",
                attribution="antigravity_hook",
                attributes={"antigravity_hook_event_name": hook_event},
            )
        )

    error = payload.get("error")
    if hook_event == "PostToolUse" and isinstance(error, str) and error:
        reference = store.put_text(error, content_kind="antigravity.tool_error")
        events.append(
            content_observation_event(
                timestamp=observed_at,
                provider="antigravity",
                source=_agent(),
                reference=reference,
                relation="OBSERVED_TOOL_ERROR",
                observed_field="error",
                evidence_source="provider_hook",
                attribution="antigravity_hook",
                attributes={"antigravity_hook_event_name": hook_event},
            )
        )

    if hook_event == "Stop" and isinstance(error, str) and error:
        reference = store.put_text(error, content_kind="antigravity.execution_stop_error")
        execution_num = payload.get("executionNum")
        attributes: dict[str, Any] = {"antigravity_hook_event_name": hook_event}
        if isinstance(execution_num, int) and not isinstance(execution_num, bool):
            attributes["antigravity_execution_number"] = execution_num
        events.append(
            content_observation_event(
                timestamp=observed_at,
                provider="antigravity",
                source=_agent(),
                reference=reference,
                relation="OBSERVED_EXECUTION_ERROR_CONTENT",
                observed_field="error",
                evidence_source="provider_hook",
                attribution="antigravity_hook",
                attributes=attributes,
            )
        )
    return events
