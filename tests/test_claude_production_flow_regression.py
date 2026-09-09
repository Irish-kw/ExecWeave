from __future__ import annotations

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from test_viewer_agent_isolation_e2e import _browser, _launch

pytestmark = pytest.mark.viewer_e2e


def _production_edge(edge_id: str, source: str, target: str, relation: str, sequence: int, event_type: str):
    """Match GraphEdge.to_dict(): provenance is top-level, not edge.attributes."""
    timestamp = f"2026-09-09T05:12:{sequence:02d}.000000Z"
    return {
        "id": edge_id,
        "source": source,
        "target": target,
        "relation": relation,
        "count": 1,
        "evidence_event_count": 1,
        "first_seen": timestamp,
        "last_seen": timestamp,
        "first_sequence": sequence,
        "last_sequence": sequence,
        "event_ids": [f"event:{edge_id}"],
        "event_types": [event_type],
        "backends": ["semantic"],
        "attributions": ["claude_hook"],
        "causal": False,
        "inferred": None,
        "inference_methods": [],
        "identity_exact": None,
        "identity_methods": [],
        "identity_hashes": [],
        "confidence_min": None,
        "confidence_max": None,
        "confidence_semantics": [],
        "supporting_event_ids": [],
    }


def _claude_graph():
    root = {"id": "agent:Claude Code", "type": "agent", "name": "Claude Code", "attributes": {}}
    model = {
        "id": "model:claude:claude-haiku-4-5-20251001",
        "type": "model",
        "name": "claude-haiku-4-5-20251001",
        "attributes": {"provider": "claude"},
    }
    child_ids = [
        "agent:claude:session:subagent:a294d4fbc09886b9b",
        "agent:claude:session:subagent:ae64fddc9240f86d9",
        "agent:claude:session:subagent:a628a9da7d12486b1",
    ]
    children = [
        {
            "id": child_id,
            "type": "agent",
            "name": "claude",
            "attributes": {
                "provider": "claude",
                "agent_role": "subagent",
                "agent_id": child_id.rsplit(":", 1)[-1],
                "parent_agent_path": "/root",
                "parent_relation_source": "provider_subagent_lifecycle_hook",
                "parent_scope_id": "session",
            },
        }
        for child_id in child_ids
    ]
    edges = [
        _production_edge(
            "model-observed",
            root["id"],
            model["id"],
            "USED_MODEL",
            1,
            "semantic.claude.model.observed",
        ),
        *[
            _production_edge(
                f"spawn-{index}",
                root["id"],
                child_id,
                "SPAWNED_SUBAGENT",
                10 + index,
                "semantic.claude.subagent.started",
            )
            for index, child_id in enumerate(child_ids)
        ],
    ]
    return {
        "schema_version": "0.2",
        "session_id": "claude-production-shape",
        "nodes": [root, model, *children],
        "edges": edges,
        "node_count": 5,
        "edge_count": len(edges),
    }, child_ids


def test_real_graph_edge_shape_places_claude_subagents_after_model_context():
    graph, child_ids = _claude_graph()
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={"width": 1800, "height": 1000})
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
            assert not errors, errors
        finally:
            browser.close()

    contexts = [
        node for node in display["nodes"]
        if node.get("attributes", {}).get("viewer_model_context")
    ]
    assert len(contexts) == 1
    assert contexts[0]["name"] == "claude-haiku-4-5-20251001"

    actions = [
        node for node in display["nodes"]
        if node.get("attributes", {}).get("viewer_orchestration_action")
        and node.get("name") == "spawn_agent"
    ]
    assert len(actions) == 1
    action = actions[0]
    context = contexts[0]

    projected_targets = {
        edge["target"] for edge in display["edges"]
        if edge["source"] == action["id"] and edge["relation"] == "SPAWNED_AGENT"
    }
    assert projected_targets == set(child_ids)
    assert not any(
        edge["source"] == "agent:Claude Code"
        and edge["target"] in child_ids
        and edge["relation"] == "SPAWNED_SUBAGENT"
        for edge in display["edges"]
    )

    assert positions["agent:Claude Code"]["x"] < positions[context["id"]]["x"]
    assert positions[context["id"]]["x"] < positions[action["id"]]["x"]
    for child_id in child_ids:
        assert positions[action["id"]]["x"] < positions[child_id]["x"]
