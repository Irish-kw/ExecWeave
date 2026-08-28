from __future__ import annotations

from copy import deepcopy

from execweave.viewer_projection import project_viewer_graph, render_graph_html


def _edge(edge_id: str, source: str, target: str, relation: str, sequence: int) -> dict[str, object]:
    return {
        "id": edge_id,
        "source": source,
        "target": target,
        "relation": relation,
        "count": 1,
        "first_sequence": sequence,
        "last_sequence": sequence,
        "first_seen": f"2026-08-28T00:00:{sequence:02d}Z",
        "last_seen": f"2026-08-28T00:00:{sequence:02d}Z",
    }


def test_dashboard_hides_hook_metadata_and_aggregates_repeated_tool_calls() -> None:
    agent = {"id": "agent:codex:root", "type": "agent", "name": "/root", "attributes": {"provider": "codex"}}
    tool = {"id": "tool:codex:wait_agent", "type": "tool", "name": "wait_agent", "attributes": {"provider": "codex", "native_name": "wait_agent"}}
    call_a = {"id": "tool-call:a", "type": "tool_call", "name": "wait_agent", "attributes": {"provider": "codex", "tool_name": "wait_agent"}}
    call_b = {"id": "tool-call:b", "type": "tool_call", "name": "wait_agent", "attributes": {"provider": "codex", "tool_name": "wait_agent"}}
    metadata = {"id": "content:hook-meta", "type": "observed_content", "name": "codex.provider_hook_metadata", "attributes": {"provider": "codex", "content_kind": "codex.provider_hook_metadata"}}
    tool_input = {"id": "content:tool-input", "type": "observed_content", "name": "codex.tool_input", "attributes": {"provider": "codex", "content_kind": "codex.tool_input"}}
    graph = {
        "graph_schema_version": "0.2",
        "session_id": "dashboard-clean",
        "event_count": 8,
        "node_count": 6,
        "edge_count": 7,
        "nodes": [agent, tool, call_a, call_b, metadata, tool_input],
        "edges": [
            _edge("request-a", agent["id"], call_a["id"], "REQUESTED_TOOL_CALL", 1),
            _edge("uses-a", call_a["id"], tool["id"], "USES_TOOL", 2),
            _edge("request-b", agent["id"], call_b["id"], "REQUESTED_TOOL_CALL", 3),
            _edge("uses-b", call_b["id"], tool["id"], "USES_TOOL", 4),
            _edge("input-a", call_a["id"], tool_input["id"], "HAS_TOOL_INPUT", 5),
            _edge("metadata-a", agent["id"], metadata["id"], "OBSERVED_PROVIDER_METADATA", 6),
            _edge("metadata-b", agent["id"], metadata["id"], "OBSERVED_PROVIDER_METADATA", 7),
        ],
    }
    original = deepcopy(graph)
    projected = project_viewer_graph(graph)

    assert graph == original
    node_ids = {node["id"] for node in projected["nodes"]}
    assert "content:hook-meta" not in node_ids
    assert "tool-call:a" not in node_ids
    assert "tool-call:b" not in node_ids
    assert "content:tool-input" not in node_ids
    assert "agent:codex:root" in node_ids
    assert "tool:codex:wait_agent" in node_ids

    tool_nodes = [node for node in projected["nodes"] if node["type"] == "tool"]
    assert len(tool_nodes) == 1
    assert tool_nodes[0]["attributes"]["viewer_aggregated_tool_call_count"] == 2
    aggregated = [edge for edge in projected["edges"] if edge.get("relation") == "CALLED_TOOL"]
    assert len(aggregated) == 1
    assert aggregated[0]["source"] == "agent:codex:root"
    assert aggregated[0]["target"] == "tool:codex:wait_agent"
    assert aggregated[0]["count"] == 2
    assert aggregated[0]["viewer_only"] is True
    assert aggregated[0]["evidence_call_count"] == 2

    projection = projected["viewer_projection"]
    assert projection["dashboard_simplification"] is True
    assert projection["hidden_hook_metadata_node_count"] == 1
    assert projection["collapsed_tool_call_node_count"] == 2
    assert projection["aggregated_tool_edge_count"] == 1
    assert projection["pruned_orphan_content_node_count"] == 1


def test_dashboard_keeps_one_shared_tool_node_with_per_agent_counts() -> None:
    agents = [
        {"id": "agent:a", "type": "agent", "name": "/root/a", "attributes": {"provider": "codex"}},
        {"id": "agent:b", "type": "agent", "name": "/root/b", "attributes": {"provider": "codex"}},
    ]
    tool = {"id": "tool:codex:send_message", "type": "tool", "name": "send_message", "attributes": {"provider": "codex", "native_name": "send_message"}}
    calls = [
        {"id": f"tool-call:{index}", "type": "tool_call", "name": "send_message", "attributes": {"provider": "codex", "tool_name": "send_message"}}
        for index in range(3)
    ]
    graph = {
        "graph_schema_version": "0.2",
        "session_id": "shared-tool",
        "event_count": 6,
        "node_count": 6,
        "edge_count": 6,
        "nodes": [*agents, tool, *calls],
        "edges": [
            _edge("a-1", "agent:a", "tool-call:0", "REQUESTED_TOOL_CALL", 1),
            _edge("u-1", "tool-call:0", tool["id"], "USES_TOOL", 2),
            _edge("a-2", "agent:a", "tool-call:1", "REQUESTED_TOOL_CALL", 3),
            _edge("u-2", "tool-call:1", tool["id"], "USES_TOOL", 4),
            _edge("b-1", "agent:b", "tool-call:2", "REQUESTED_TOOL_CALL", 5),
            _edge("u-3", "tool-call:2", tool["id"], "USES_TOOL", 6),
        ],
    }
    projected = project_viewer_graph(graph)

    tool_nodes = [node for node in projected["nodes"] if node["type"] == "tool"]
    assert [node["id"] for node in tool_nodes] == ["tool:codex:send_message"]
    assert tool_nodes[0]["attributes"]["viewer_aggregated_tool_call_count"] == 3
    counts = {edge["source"]: edge["count"] for edge in projected["edges"] if edge.get("relation") == "CALLED_TOOL"}
    assert counts == {"agent:a": 2, "agent:b": 1}


def test_standalone_dashboard_does_not_force_agent_only_filter() -> None:
    graph = {
        "graph_schema_version": "0.2",
        "session_id": "agent-and-tool",
        "event_count": 1,
        "node_count": 2,
        "edge_count": 1,
        "nodes": [
            {"id": "agent:a", "type": "agent", "name": "/root/a", "attributes": {"provider": "codex"}},
            {"id": "tool:codex:send_message", "type": "tool", "name": "send_message", "attributes": {"provider": "codex"}},
        ],
        "edges": [_edge("agent-tool", "agent:a", "tool:codex:send_message", "USES_TOOL", 1)],
    }
    html = render_graph_html(graph)

    assert "function execweavePreferAgentView()" in html
    assert "loadPresets();execweavePreferAgentView();applyGraphFilters()" not in html
    assert "tool:codex:send_message" in html
