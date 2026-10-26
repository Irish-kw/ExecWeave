from __future__ import annotations

from typing import Any

from .agent_trace import provider_agent_trace_visibility_event

ANTIGRAVITY_TRACE_VISIBILITY: dict[str, str] = {
    "agent_identity_visibility": "provider_exposed_validated_transcript_child_identity",
    "subagent_visibility": "provider_exposed_request_and_validated_assignment_only",
    "reasoning_visibility": "not_exposed_by_source",
    "child_lifecycle_visibility": "provider_child_hooks_only",
    "transcript_linkage_semantics": "live_verified_implementation_wire",
}


def antigravity_agent_trace_visibility_event(
    *,
    timestamp: str,
    attribution: str = "antigravity_hook",
    evidence_source: str = "provider_hook",
) -> dict[str, Any]:
    """Describe Antigravity visibility without overstating transcript lifecycle evidence."""
    event = provider_agent_trace_visibility_event(
        "antigravity",
        timestamp=timestamp,
        attribution=attribution,
        evidence_source=evidence_source,
    )
    target = event.get("target")
    event_attributes = event.get("attributes")
    if not isinstance(target, dict) or not isinstance(event_attributes, dict):
        raise RuntimeError("Antigravity visibility event shape changed")
    target_attributes = target.get("attributes")
    if not isinstance(target_attributes, dict):
        raise RuntimeError("Antigravity visibility capability shape changed")
    visibility = dict(ANTIGRAVITY_TRACE_VISIBILITY)
    target_attributes.update(visibility)
    event_attributes.update(visibility)
    return event
