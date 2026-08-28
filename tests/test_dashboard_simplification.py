from __future__ import annotations

import execweave.live as live_module
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


def _dashboard_graph() -> dict[str, object]:
    agent = {
        "id": "agent:codex:root",
        "type": "agent",
        "name": "/root",
        "attributes": {"provider": "codex", "agent_path": "/root"},
    }
    tool = {
        "id": "tool:codex:wait_agent",
        "type": "tool",
        "name": "wait_agent",
        "attributes": {"provider": "codex", "native_name": "wait_agent"},
    }
    call_a = {
        "id": "tool-call:a",
        "type": "tool_call",
        "name": "wait_agent",
        "attributes": {"provider": "codex", "tool_name": "wait_agent"},
    }
    call_b = {
        "id": "tool-call:b",
        "type": "tool_call",
        "name": "wait_agent",
        "attributes": {"provider": "codex", "tool_name": "wait_agent"},
    }
    metadata = {
        "id": "content:hook-meta",
        "type": "observed_content",
        "name": "codex.provider_hook_metadata",
        "attributes": {"provider": "codex", "content_kind": "codex.provider_hook_metadata"},
    }
    capability = {
        "id": "agent-trace-capability:codex",
        "type": "agent_trace_capability",
        "name": "Codex trace visibility",
        "attributes": {"provider": "codex"},
    }
    return {
        "graph_schema_version": "0.2",
        "session_id": "dashboard-clean",
        "event_count": 8,
        "node_count": 6,
        "edge_count": 7,
        "nodes": [agent, tool, call_a, call_b, metadata, capability],
        "edges": [
            _edge("request-a", agent["id"], call_a["id"], "REQUESTED_TOOL_CALL", 1),
            _edge("uses-a", call_a["id"], tool["id"], "USES_TOOL", 2),
            _edge("request-b", agent["id"], call_b["id"], "REQUESTED_TOOL_CALL", 3),
            _edge("uses-b", call_b["id"], tool["id"], "USES_TOOL", 4),
            _edge("metadata", agent["id"], metadata["id"], "OBSERVED_PROVIDER_METADATA", 5),
            _edge("visibility", agent["id"], capability["id"], "DECLARES_AGENT_TRACE_VISIBILITY", 6),
        ],
    }


def _repeated_process_graph() -> dict[str, object]:
    parent = {
        "id": "process:node",
        "type": "process",
        "name": "node.exe",
        "attributes": {"pid": 100},
        "first_seen": "2026-08-28T00:00:01Z",
        "last_seen": "2026-08-28T00:00:09Z",
    }
    git_a = {
        "id": "process:git:101",
        "type": "process",
        "name": "git.exe",
        "attributes": {"pid": 101, "ppid": 100},
        "first_seen": "2026-08-28T00:00:02Z",
        "last_seen": "2026-08-28T00:00:03Z",
    }
    git_b = {
        "id": "process:git:102",
        "type": "process",
        "name": "git.exe",
        "attributes": {"pid": 102, "ppid": 100},
        "first_seen": "2026-08-28T00:00:04Z",
        "last_seen": "2026-08-28T00:00:05Z",
    }
    staging = {
        "id": "file:staging",
        "type": "file",
        "name": ".execweave-content-xn4uvhqy",
        "attributes": {"path": "content/sha256/.execweave-content-xn4uvhqy"},
    }
    endpoint = {
        "id": "network:104.18.25.193:443",
        "type": "network_endpoint",
        "name": "104.18.25.193:443",
        "attributes": {},
    }
    return {
        "graph_schema_version": "0.2",
        "session_id": "dashboard-process-canonicalization",
        "event_count": 7,
        "node_count": 5,
        "edge_count": 4,
        "nodes": [parent, git_a, git_b, staging, endpoint],
        "edges": [
            _edge("spawn-a", parent["id"], git_a["id"], "SPAWNED", 1),
            _edge("spawn-b", parent["id"], git_b["id"], "SPAWNED", 2),
            _edge("staging-write", git_b["id"], staging["id"], "WROTE", 3),
            _edge("connect", parent["id"], endpoint["id"], "CONNECTED_TO", 4),
        ],
    }


def test_project_viewer_graph_keeps_evidence_contract() -> None:
    graph = _dashboard_graph()
    projected = project_viewer_graph(graph)
    node_ids = {node["id"] for node in projected["nodes"]}

    assert "tool-call:a" in node_ids
    assert "tool-call:b" in node_ids
    assert "content:hook-meta" in node_ids
    assert "agent-trace-capability:codex" in node_ids
    assert "dashboard_projection" not in projected


def test_static_dashboard_cleans_only_canvas_and_keeps_embedded_evidence() -> None:
    html = render_graph_html(_dashboard_graph())

    assert "function execweaveDashboardGraph(data)" in html
    assert "'observed_content','tool_call','agent_turn'" in html
    assert "relation:'CALLED_TOOL'" in html
    assert "viewer_aggregated_tool_call_count" in html
    assert "execweaveDashboardGraphBase" in html
    assert "'agent_trace_capability','session','process'" in html
    assert "mergeTypes=new Set(['model','directory','network_endpoint'])" in html
    assert "execweave-conversation-root-node" in html
    assert "tool-call:a" in html
    assert "content:hook-meta" in html
    assert "agent-trace-capability:codex" in html
    assert "return execweaveDashboardGraph({nodes:uniqueById(nodes),edges:uniqueById(edges)})" in html
    assert "loadPresets();execweavePreferAgentView();applyGraphFilters()" not in html


def test_dashboard_process_canonicalization_is_presentation_only() -> None:
    graph = _repeated_process_graph()
    projected = project_viewer_graph(graph)
    raw_ids = {node["id"] for node in projected["nodes"]}
    html = render_graph_html(graph)

    assert {
        "process:git:101",
        "process:git:102",
        "file:staging",
        "network:104.18.25.193:443",
    } <= raw_ids
    assert "canonicalTypes=new Set(['process'])" in html
    assert "mergeTypes=new Set(['model','directory','network_endpoint'])" in html
    assert "viewer_occurrence_count" in html
    assert "viewer_occurrences" in html
    assert "viewer_original_source" in html
    assert "viewer_edge_occurrence_count" in html
    assert "hidden_internal_staging_node_count" in html
    assert "hidden_context_node_count" in html
    assert "merged_context_node_count" in html
    assert "process:git:101" in html
    assert "process:git:102" in html
    assert ".execweave-content-xn4uvhqy" in html
    assert "104.18.25.193:443" in html


def test_live_dashboard_uses_client_side_summary_without_changing_protocol() -> None:
    html = live_module._LIVE_HTML

    assert "function execweaveDashboardGraph(data)" in html
    assert "getDisplayGraph:" in html
    assert "const display=execweaveDashboardGraph(data)" in html
    assert "const rawNodes=new Map((graph.nodes||[]).map" in html
    assert "relation:'CALLED_TOOL'" in html
    assert "viewer_occurrence_count" in html
    assert "hidden_internal_staging_node_count" in html
    assert "execweaveDashboardGraphBase" in html
    assert "hidden_context_node_count" in html
    assert "mergeTypes=new Set(['model','directory','network_endpoint'])" in html
    assert "execweave-conversation-root-node" in html
    assert "id=\"activity-resizer\"" in html
    assert "execweave.live.activity-height" in html
    assert "pointermove" in html
    assert "provider_hook_metadata" not in html
