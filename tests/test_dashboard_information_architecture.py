from __future__ import annotations

from pathlib import Path

import execweave.live as live_module
from execweave.content_store import FullFidelityContentStore
from execweave.viewer_projection import project_viewer_graph, render_graph_html


def _node(node_id: str, node_type: str, name: str, **attributes: object) -> dict[str, object]:
    return {
        "id": node_id,
        "type": node_type,
        "name": name,
        "attributes": attributes,
    }


def _edge(edge_id: str, source: str, target: str, relation: str) -> dict[str, object]:
    return {
        "id": edge_id,
        "source": source,
        "target": target,
        "relation": relation,
        "count": 1,
        "first_sequence": 1,
        "last_sequence": 1,
        "first_seen": "2026-08-28T00:00:01Z",
        "last_seen": "2026-08-28T00:00:01Z",
    }


def _mechanical_graph() -> dict[str, object]:
    root = _node("agent:OpenAI Codex", "agent", "OpenAI Codex", provider="codex")
    child = _node(
        "agent:codex:session:subagent:abcdef123456",
        "agent",
        "default",
        provider="codex",
        agent_id="abcdef123456",
        agent_type="default",
    )
    process = _node("process:git", "process", "git.exe", pid=42)
    endpoint = _node("network:github", "network_endpoint", "104.18.25.195:443")
    endpoint_repeat = _node("network:github:repeat", "network_endpoint", "104.18.25.195:443")
    directory = _node("directory:.github", "directory", ".github", path=".github")
    directory_repeat = _node("directory:.github:repeat", "directory", ".github", path=".github/")
    model = _node("model:codex:gpt", "model", "gpt-5.6", provider="codex")
    model_repeat = _node("model:codex:gpt:repeat", "model", "gpt-5.6", provider="codex")
    capability = _node(
        "agent-trace-capability:codex",
        "agent_trace_capability",
        "Codex trace visibility",
        provider="codex",
    )
    internal = _node(
        "file:internal-temp",
        "file",
        ".execweave-content-xn4uvhqy",
        path="content/sha256/.execweave-content-xn4uvhqy",
    )
    meaningful = _node("file:result", "file", "result.txt", path="result.txt")
    nodes = [
        root,
        child,
        process,
        endpoint,
        endpoint_repeat,
        directory,
        directory_repeat,
        model,
        model_repeat,
        capability,
        internal,
        meaningful,
    ]
    edges = [
        _edge("spawn-agent", root["id"], child["id"], "SPAWNED_AGENT"),
        _edge("spawn-process", root["id"], process["id"], "SPAWNED"),
        _edge("connect", process["id"], endpoint["id"], "CONNECTED_TO"),
        _edge("connect-repeat", process["id"], endpoint_repeat["id"], "CONNECTED_TO"),
        _edge("cwd", process["id"], directory["id"], "USED_DIRECTORY"),
        _edge("cwd-repeat", process["id"], directory_repeat["id"], "USED_DIRECTORY"),
        _edge("model", root["id"], model["id"], "USED_MODEL"),
        _edge("model-repeat", root["id"], model_repeat["id"], "USED_MODEL"),
        _edge("capability", root["id"], capability["id"], "DECLARES_AGENT_TRACE_VISIBILITY"),
        _edge("internal", process["id"], internal["id"], "WROTE"),
        _edge("meaningful", root["id"], meaningful["id"], "WROTE_FILE"),
    ]
    return {
        "graph_schema_version": "0.2",
        "session_id": "information-architecture",
        "event_count": len(edges),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }


def test_low_level_dashboard_cleanup_remains_presentation_only() -> None:
    raw = project_viewer_graph(_mechanical_graph())
    raw_types = {str(node["type"]) for node in raw["nodes"]}
    raw_names = {str(node.get("name")) for node in raw["nodes"]}

    assert {"process", "network_endpoint", "directory", "model", "agent_trace_capability"} <= raw_types
    assert ".execweave-content-xn4uvhqy" in raw_names
    assert "dashboard_projection" not in raw

    html = render_graph_html(_mechanical_graph())
    assert "hiddenTypes=new Set(['agent_trace_capability','session','process'" in html
    assert "mergeTypes=new Set(['model','directory','network_endpoint'])" in html
    assert "viewer_occurrence_count" in html
    assert "viewer_edge_occurrence_count" in html
    assert "viewer_flattened_hidden_runtime" in html
    assert "flattened_hidden_runtime_edge_count" in html
    assert "merged_context_node_count" in html
    assert ".execweave-content-" in html
    assert "content/sha256/" in html
    assert "node.type!=='file'||incident.has(node.id)" in html
    # Full raw evidence remains embedded even when the default SVG canvas hides or merges it.
    assert "git.exe" in html
    assert "104.18.25.195:443" in html
    assert ".github" in html
    assert "gpt-5.6" in html
    assert ".execweave-content-xn4uvhqy" in html


def test_model_directory_and_network_nodes_are_retained_but_canonicalized() -> None:
    html = render_graph_html(_mechanical_graph())

    assert "mergeTypes=new Set(['model','directory','network_endpoint'])" in html
    assert "if(type==='model')" in html
    assert "if(type==='directory')" in html
    assert "attrs.host||attrs.hostname||attrs.address||attrs.ip" in html
    assert "viewer_occurrence_ids" in html
    assert "viewer_edge_occurrence_ids" in html
    assert "viewer_flattened_hidden_runtime" in html
    # Raw duplicates still exist in the embedded graph and evidence contract.
    assert "network:github:repeat" in html
    assert "directory:.github:repeat" in html
    assert "model:codex:gpt:repeat" in html


def test_agent_labels_are_human_facing_without_mutating_raw_graph() -> None:
    raw = project_viewer_graph(_mechanical_graph())
    raw_by_id = {str(node["id"]): node for node in raw["nodes"]}
    assert raw_by_id["agent:OpenAI Codex"]["name"] == "OpenAI Codex"
    assert raw_by_id["agent:codex:session:subagent:abcdef123456"]["name"] == "default"

    html = render_graph_html(_mechanical_graph())
    assert "node.id==='agent:OpenAI Codex'" in html
    assert "isRoot?'/root'" in html
    assert "subagent · ${agentId.slice(0,8)}" in html


def test_live_logs_are_vertically_resizable_without_expanding_log_retention() -> None:
    html = live_module._LIVE_HTML

    assert "--activity-height" in html
    assert "activity-resizer" in html
    assert "Resize live logs" in html
    assert "pointerdown" in html
    assert "execweave.live.activity-height" in html
    # The UI resizer is independent from the intentionally bounded dashboard log window.
    assert live_module.LIVE_RAW_EVENT_HISTORY == 320


def test_live_conversation_panel_is_rooted_agent_tree() -> None:
    html = live_module._LIVE_HTML

    assert "execweave-conversation-root-node" in html
    assert "execweave-conversation-children" in html
    assert "agent · waiting" in html
    assert "node.id==='agent:OpenAI Codex'" in html
    assert "isRoot?'/root'" in html
    # Same-agent messages omit the repeated path; cross-agent routes remain explicit.
    assert "sender&&sender!==currentPath" in html
    assert "`${sender||currentPath} → ${recipient}`" in html
    assert (
        "Provider-encrypted payload — plaintext is not exposed by the Codex rollout."
        in html
    )


def test_live_cleanup_preserves_raw_protocol_and_large_graph_guard() -> None:
    html = live_module._LIVE_HTML

    assert "getGraph:()=>graph" in html
    assert "getDisplayGraph:" in html
    assert "const rawNodes=new Map((graph.nodes||[]).map" in html
    assert "const signature=`${data.node_count||0}:${data.edge_count||0}`" in html


def test_content_store_atomic_temp_files_do_not_survive_snapshot(tmp_path: Path) -> None:
    source = tmp_path / "rollout.jsonl"
    payload = b'{"type":"session_meta"}\n{"type":"event_msg"}\n'
    source.write_bytes(payload)
    run_root = tmp_path / "run"

    reference = FullFidelityContentStore(run_root).put_file(
        source,
        content_kind="codex.conversation_transcript.main",
        media_type="text/plain; charset=utf-8",
    )

    stored = run_root / reference.path
    assert stored.read_bytes() == payload
    assert not list((run_root / "content" / "sha256").glob(".execweave-content-*"))
