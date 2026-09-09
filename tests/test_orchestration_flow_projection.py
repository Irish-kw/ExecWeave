from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from execweave.viewer_orchestration_projection import project_model_orchestration_viewer_graph

ROOT = "agent:root"
A1 = "agent:codex:s:subagent:a1"
A2 = "agent:codex:s:subagent:a2"
A3 = "agent:codex:s:subagent:a3"


def _node(node_id: str, node_type: str, name: str, attributes: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"id": node_id, "type": node_type, "name": name, "attributes": attributes or {}}


def _edge(edge_id: str, source: str, relation: str, target: str, sequence: int) -> dict[str, Any]:
    return {
        "id": edge_id,
        "source": source,
        "target": target,
        "relation": relation,
        "count": 1,
        "first_sequence": sequence,
        "last_sequence": sequence,
        "first_seen": f"2026-09-09T00:00:{sequence:02d}Z",
        "last_seen": f"2026-09-09T00:00:{sequence:02d}Z",
    }


def _content(tmp_path: Path, name: str, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    folder = tmp_path / "content" / "sha256"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    node_id = f"observed-content:{name}"
    node = _node(
        node_id,
        "observed_content",
        name,
        {"content_kind": "codex.tool_input", "path": f"content/sha256/{name}.json"},
    )
    return node, node_id


def _call(call_id: str, tool_name: str, model: str) -> dict[str, Any]:
    return _node(
        call_id,
        "tool_call",
        tool_name,
        {"provider": "codex", "tool_name": tool_name, "tool_use_id": call_id, "codex_model": model},
    )


def _graph(tmp_path: Path) -> dict[str, Any]:
    c_send_1, send_1_id = _content(tmp_path, "send-a1", {"target": "a1", "message": "hidden"})
    c_send_2, send_2_id = _content(tmp_path, "send-a2", {"target": "a2", "message": "hidden"})
    c_wait, wait_id = _content(tmp_path, "wait-both", {"targets": ["a1", "a2"], "timeout_ms": 100})
    nodes = [
        _node(ROOT, "agent", "/root", {"agent_role": "root", "root_agent_path": "/root", "provider": "codex"}),
        _node(A1, "agent", "default", {"agent_role": "subagent", "agent_id": "a1", "agent_nickname": "Singer", "provider": "codex"}),
        _node(A2, "agent", "default", {"agent_role": "subagent", "agent_id": "a2", "agent_nickname": "Rawls", "provider": "codex"}),
        _node(A3, "agent", "default", {"agent_role": "subagent", "agent_id": "a3", "agent_nickname": "LunaChild", "provider": "codex"}),
        _node("model:55", "model", "gpt-5.5", {"provider": "codex"}),
        _node("model:luna", "model", "gpt-5.6-luna", {"provider": "codex"}),
        _node("tool:spawn", "tool", "spawn_agent", {"provider": "codex", "native_name": "spawn_agent"}),
        _node("tool:send", "tool", "multi_agent_v1send_input", {"provider": "codex", "native_name": "multi_agent_v1send_input"}),
        _node("tool:wait", "tool", "multi_agent_v1wait_agent", {"provider": "codex", "native_name": "multi_agent_v1wait_agent"}),
        _call("call:spawn-a1", "spawn_agent", "gpt-5.5"),
        _call("call:spawn-a2", "spawn_agent", "gpt-5.5"),
        _call("call:send-a1", "multi_agent_v1send_input", "gpt-5.5"),
        _call("call:send-a2", "multi_agent_v1send_input", "gpt-5.5"),
        _call("call:wait", "multi_agent_v1wait_agent", "gpt-5.5"),
        _call("call:spawn-a3", "spawn_agent", "gpt-5.6-luna"),
        c_send_1,
        c_send_2,
        c_wait,
    ]
    edges = [
        _edge("model55", ROOT, "USED_MODEL", "model:55", 1),
        _edge("modelluna", ROOT, "USED_MODEL", "model:luna", 40),
        _edge("req-s1", ROOT, "REQUESTED_TOOL_CALL", "call:spawn-a1", 10),
        _edge("use-s1", "call:spawn-a1", "USES_TOOL", "tool:spawn", 11),
        _edge("ret-s1", "call:spawn-a1", "TOOL_CALL_RETURNED", "tool:spawn", 12),
        _edge("spawn-a1", ROOT, "SPAWNED_AGENT", A1, 13),
        _edge("req-s2", ROOT, "REQUESTED_TOOL_CALL", "call:spawn-a2", 20),
        _edge("use-s2", "call:spawn-a2", "USES_TOOL", "tool:spawn", 21),
        _edge("ret-s2", "call:spawn-a2", "TOOL_CALL_RETURNED", "tool:spawn", 22),
        _edge("spawn-a2", ROOT, "SPAWNED_AGENT", A2, 23),
        _edge("req-send1", ROOT, "REQUESTED_TOOL_CALL", "call:send-a1", 25),
        _edge("use-send1", "call:send-a1", "USES_TOOL", "tool:send", 26),
        _edge("input-send1", "call:send-a1", "HAS_TOOL_INPUT", send_1_id, 27),
        _edge("req-send2", ROOT, "REQUESTED_TOOL_CALL", "call:send-a2", 28),
        _edge("use-send2", "call:send-a2", "USES_TOOL", "tool:send", 29),
        _edge("input-send2", "call:send-a2", "HAS_TOOL_INPUT", send_2_id, 30),
        _edge("req-wait", ROOT, "REQUESTED_TOOL_CALL", "call:wait", 31),
        _edge("use-wait", "call:wait", "USES_TOOL", "tool:wait", 32),
        _edge("input-wait", "call:wait", "HAS_TOOL_INPUT", wait_id, 33),
        _edge("req-s3", ROOT, "REQUESTED_TOOL_CALL", "call:spawn-a3", 50),
        _edge("use-s3", "call:spawn-a3", "USES_TOOL", "tool:spawn", 51),
        _edge("ret-s3", "call:spawn-a3", "TOOL_CALL_RETURNED", "tool:spawn", 52),
        _edge("spawn-a3", ROOT, "SPAWNED_AGENT", A3, 53),
    ]
    source = tmp_path / "events.semantic.jsonl"
    source.write_text("", encoding="utf-8")
    return {"schema_version": "1.0", "source_path": str(source), "nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}


def test_model_context_and_orchestration_flow_reuses_agent_identity(tmp_path: Path) -> None:
    raw = _graph(tmp_path)
    before = copy.deepcopy(raw)
    projected = project_model_orchestration_viewer_graph(raw)
    assert raw == before

    nodes, edges = projected["nodes"], projected["edges"]
    by_id = {node["id"]: node for node in nodes}
    for agent_id in (ROOT, A1, A2, A3):
        assert sum(node["id"] == agent_id for node in nodes) == 1
    assert by_id[ROOT]["attributes"]["viewer_flow_rank"] == 0
    assert all(by_id[agent_id]["attributes"]["viewer_flow_rank"] == 3 for agent_id in (A1, A2, A3))

    contexts = [node for node in nodes if node["type"] == "model_context"]
    assert {node["name"] for node in contexts} == {"gpt-5.5", "gpt-5.6-luna"}
    assert all(node["attributes"]["viewer_flow_rank"] == 1 for node in contexts)
    context_by_name = {node["name"]: node["id"] for node in contexts}

    actions = [node for node in nodes if node["type"] == "tool_action"]
    action_by_key = {(node["attributes"]["model_name"], node["attributes"]["action_kind"]): node["id"] for node in actions}
    assert set(action_by_key) == {
        ("gpt-5.5", "spawn_agent"),
        ("gpt-5.5", "send_input"),
        ("gpt-5.5", "wait_agent"),
        ("gpt-5.6-luna", "spawn_agent"),
    }
    assert all(node["attributes"]["viewer_flow_rank"] == 2 for node in actions)

    triples = {(edge["source"], edge["relation"], edge["target"]) for edge in edges}
    assert (ROOT, "MODEL_CONTEXT", context_by_name["gpt-5.5"]) in triples
    assert (ROOT, "MODEL_CONTEXT", context_by_name["gpt-5.6-luna"]) in triples
    assert (context_by_name["gpt-5.5"], "ORCHESTRATED_ACTION", action_by_key[("gpt-5.5", "spawn_agent")]) in triples

    spawn55 = action_by_key[("gpt-5.5", "spawn_agent")]
    spawn_luna = action_by_key[("gpt-5.6-luna", "spawn_agent")]
    send = action_by_key[("gpt-5.5", "send_input")]
    wait = action_by_key[("gpt-5.5", "wait_agent")]
    assert {(edge["relation"], edge["target"]) for edge in edges if edge["source"] == spawn55} == {("SPAWNED_AGENT", A1), ("SPAWNED_AGENT", A2)}
    assert {(edge["relation"], edge["target"]) for edge in edges if edge["source"] == spawn_luna} == {("SPAWNED_AGENT", A3)}
    assert {(edge["relation"], edge["target"]) for edge in edges if edge["source"] == send} == {("SENT_INPUT_TO", A1), ("SENT_INPUT_TO", A2)}
    assert {(edge["relation"], edge["target"]) for edge in edges if edge["source"] == wait} == {("WAITED_FOR", A1), ("WAITED_FOR", A2)}

    assert not any(edge["source"] == ROOT and edge["relation"] == "SPAWNED_AGENT" and edge["target"] in {A1, A2, A3} for edge in edges)
    assert not {"model:55", "model:luna", "tool:spawn", "tool:send", "tool:wait"} & set(by_id)
    flow_edges = [edge for edge in edges if edge.get("relation") in {"MODEL_CONTEXT", "ORCHESTRATED_ACTION", "SPAWNED_AGENT", "SENT_INPUT_TO", "WAITED_FOR"}]
    assert flow_edges
    assert all(edge.get("viewer_only") is True for edge in flow_edges)


def test_projected_flow_metadata_reports_reanchoring(tmp_path: Path) -> None:
    projected = project_model_orchestration_viewer_graph(_graph(tmp_path))
    meta = projected["viewer_projection"]
    assert meta["execution_flow_projection"] is True
    assert meta["model_context_node_count"] == 2
    assert meta["orchestration_action_node_count"] == 4
    assert meta["orchestration_action_edge_count"] == 7
    assert meta["orchestration_spawn_edges_reanchored"] == 3
