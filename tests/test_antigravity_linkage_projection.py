from __future__ import annotations

from execweave.antigravity_full_fidelity import _assignment_event
from execweave.antigravity_trace_capability import (
    ANTIGRAVITY_TRACE_VISIBILITY,
    antigravity_agent_trace_visibility_event,
)
from execweave.graph import GraphAccumulator
from execweave.viewer_projection import render_graph_html


_IDENTITY_METHOD = "validated_transcript_record_order_and_provider_ids"


def _graph() -> dict:
    assignment = _assignment_event(
        timestamp="2026-08-28T00:00:01Z",
        conversation_id="parent-conversation",
        step=7,
        subagent_index=0,
        child_id="child-a",
        spec={
            "Prompt": "inspect authentication paths",
            "Role": "security reviewer",
            "TypeName": "research",
            "Workspace": "inherit",
        },
    )
    assignment.update(
        {
            "schema_version": "0.1",
            "session_id": "antigravity-linkage",
            "sequence": 2,
            "event_id": "event-assignment",
        }
    )
    visibility = antigravity_agent_trace_visibility_event(
        timestamp="2026-08-28T00:00:00Z"
    )
    visibility.update(
        {
            "schema_version": "0.1",
            "session_id": "antigravity-linkage",
            "sequence": 1,
            "event_id": "event-visibility",
        }
    )
    accumulator = GraphAccumulator(
        session_id="antigravity-linkage",
        source_path="antigravity-linkage.jsonl",
    )
    accumulator.apply(visibility)
    accumulator.apply(assignment)
    return accumulator.to_dict()


def test_antigravity_visibility_describes_validated_identity_without_lifecycle_overclaim() -> None:
    event = antigravity_agent_trace_visibility_event(timestamp="2026-08-28T00:00:00Z")

    assert event["relation"] == "DECLARES_AGENT_TRACE_VISIBILITY"
    for key, value in ANTIGRAVITY_TRACE_VISIBILITY.items():
        assert event["target"]["attributes"][key] == value
        assert event["attributes"][key] == value
    assert event["target"]["attributes"]["child_lifecycle_visibility"] == (
        "provider_child_hooks_only"
    )
    assert event["target"]["attributes"]["reasoning_visibility"] == "not_exposed_by_source"


def test_antigravity_assignment_exact_identity_survives_graph_materialization() -> None:
    graph = _graph()
    assignment = next(
        edge for edge in graph["edges"] if edge["relation"] == "ASSIGNED_AGENT_TASK"
    )
    child = next(
        node
        for node in graph["nodes"]
        if node["id"] == "agent:antigravity:conversation:child-a"
    )

    assert assignment["identity_exact"] is True
    assert assignment["identity_methods"] == [_IDENTITY_METHOD]
    assert assignment["inferred"] is False
    assert child["attributes"]["lifecycle_authority"] == "child_provider_hooks"
    assert child["attributes"]["execution_observed"] is False


def test_antigravity_viewer_surfaces_exact_linkage_without_transcript_paths() -> None:
    html = render_graph_html(_graph())

    assert "Antigravity Transcript Linkage" in html
    assert "Validated transcript identity" in html
    assert _IDENTITY_METHOD in html
    assert "No timing join" in html
    assert "Child hooks authoritative" in html
    assert "Validated transcript child identity" in html
    assert "Request + validated assignment only" in html
    assert "parent transcript does not establish child execution" in html
    assert "transcriptPath" not in html
    assert "logAbsoluteUri" not in html
