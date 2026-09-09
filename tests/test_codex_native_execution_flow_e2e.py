from __future__ import annotations

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from test_viewer_agent_isolation_e2e import _browser, _launch

pytestmark = pytest.mark.viewer_e2e


def test_tagged_codex_interaction_and_implicit_wait_use_one_child_identity():
    root_id = "agent:codex:rollout:r:thread:root"
    child_id = "agent:codex:rollout:r:thread:child"
    model_id = "model:codex:gpt-5.5"
    interaction_id = "agent-interaction:codex:r:edge-1"
    wait_call_id = "tool-call:codex:rollout:r:wait-1"
    wait_tool_id = "tool:codex:wait_agent"
    graph = {
        "schema_version": "1.0",
        "session_id": "codex-native-flow",
        "nodes": [
            {
                "id": root_id,
                "type": "agent",
                "name": "/root",
                "first_sequence": 1,
                "attributes": {
                    "provider": "codex",
                    "agent_role": "root",
                    "agent_path": "/root",
                    "thread_id": "root",
                    "default_model": "gpt-5.5",
                },
            },
            {
                "id": child_id,
                "type": "agent",
                "name": "Singer",
                "first_sequence": 4,
                "attributes": {
                    "provider": "codex",
                    "thread_id": "child",
                    "nickname": "Singer",
                },
            },
            {
                "id": model_id,
                "type": "model",
                "name": "gpt-5.5",
                "attributes": {"provider": "codex"},
            },
            {
                "id": interaction_id,
                "type": "agent_interaction",
                "name": "spawn_agent",
                "first_sequence": 3,
                "attributes": {
                    "provider": "codex",
                    "rollout_id": "r",
                    "interaction_edge_id": "edge-1",
                    "kind": {"type": "spawn_agent"},
                    "source_anchor": "root",
                    "target_anchor": "child",
                },
            },
            {
                "id": wait_call_id,
                "type": "tool_call",
                "name": "wait_agent",
                "first_sequence": 6,
                "attributes": {
                    "provider": "codex",
                    "rollout_id": "r",
                    "tool_call_id": "wait-1",
                    "kind": {"type": "wait_agent"},
                },
            },
            {
                "id": wait_tool_id,
                "type": "tool",
                "name": "wait_agent",
                "attributes": {"provider": "codex", "native_name": "wait_agent"},
            },
        ],
        "edges": [
            {
                "id": "model",
                "source": root_id,
                "target": model_id,
                "relation": "USED_MODEL",
                "first_sequence": 2,
                "attributes": {
                    "provider": "codex",
                    "evidence_source": "codex_rollout_trace",
                },
            },
            {
                "id": "interaction-start",
                "source": root_id,
                "target": interaction_id,
                "relation": "STARTED_AGENT_INTERACTION",
                "first_sequence": 3,
                "attributes": {
                    "provider": "codex",
                    "evidence_source": "codex_rollout_trace",
                },
            },
            {
                "id": "interaction-target",
                "source": interaction_id,
                "target": child_id,
                "relation": "TARGETED_BY_AGENT_INTERACTION",
                "first_sequence": 4,
                "attributes": {
                    "provider": "codex",
                    "evidence_source": "codex_rollout_trace",
                },
            },
            {
                "id": "spawn-direct",
                "source": root_id,
                "target": child_id,
                "relation": "SPAWNED_AGENT",
                "first_sequence": 4,
                "attributes": {
                    "provider": "codex",
                    "evidence_source": "codex_rollout_trace",
                    "interaction_edge_id": "edge-1",
                },
            },
            {
                "id": "wait-request",
                "source": root_id,
                "target": wait_call_id,
                "relation": "REQUESTED_TOOL_CALL",
                "first_sequence": 6,
                "attributes": {
                    "provider": "codex",
                    "evidence_source": "codex_rollout_trace",
                },
            },
            {
                "id": "wait-tool",
                "source": wait_call_id,
                "target": wait_tool_id,
                "relation": "USES_TOOL",
                "first_sequence": 7,
                "attributes": {
                    "provider": "codex",
                    "evidence_source": "codex_rollout_trace",
                },
            },
        ],
    }
    graph["node_count"] = len(graph["nodes"])
    graph["edge_count"] = len(graph["edges"])

    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 900})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.set_content(render_static_dashboard_html(graph))
            page.wait_for_selector(".node")
            display = page.evaluate("window.__execweaveCore.getDisplayGraph()")
            positions = page.evaluate(
                """() => Object.fromEntries([...document.querySelectorAll('.node')].map(g => {
                    const m=(g.getAttribute('transform')||'').match(/translate\\(([-0-9.]+) ([-0-9.]+)\\)/);
                    return [g.dataset.id, {x:m?Number(m[1]):0,y:m?Number(m[2]):0}];
                }))"""
            )
            metrics = page.evaluate("window.__execweavePr70.metrics()")
            assert not errors, errors
        finally:
            browser.close()

    agents = [node for node in display["nodes"] if node["type"] == "agent"]
    assert [node["id"] for node in agents].count(child_id) == 1
    contexts = [
        node for node in display["nodes"]
        if node.get("attributes", {}).get("viewer_model_context")
    ]
    actions = {
        node["name"]: node
        for node in display["nodes"]
        if node.get("attributes", {}).get("viewer_orchestration_action")
    }
    assert len(contexts) == 1 and contexts[0]["name"] == "gpt-5.5"
    assert {"spawn_agent", "wait_agent"} <= set(actions)
    for action_name in ("spawn_agent", "wait_agent"):
        assert any(
            edge["source"] == contexts[0]["id"] and edge["target"] == actions[action_name]["id"]
            for edge in display["edges"]
        )
        assert any(
            edge["source"] == actions[action_name]["id"] and edge["target"] == child_id
            for edge in display["edges"]
        )
    assert positions[root_id]["x"] < positions[contexts[0]["id"]]["x"]
    assert positions[contexts[0]["id"]]["x"] < positions[actions["spawn_agent"]["id"]]["x"]
    assert positions[actions["spawn_agent"]["id"]]["x"] < positions[child_id]["x"]
    assert metrics["NODE_OVERLAPS"] == 0
    assert metrics["EDGE_NODE_INTERSECTIONS"] == 0
