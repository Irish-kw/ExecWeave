from __future__ import annotations

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from test_viewer_agent_isolation_e2e import _browser, _launch

pytestmark = pytest.mark.viewer_e2e


def _edge(identity: str, source: str, target: str, relation: str, sequence: int):
    return {
        "id": identity,
        "source": source,
        "target": target,
        "relation": relation,
        "first_sequence": sequence,
        "last_sequence": sequence,
        "attributes": {
            "provider": "codex",
            "evidence_source": "provider_fixture",
        },
    }


def test_model_switch_places_each_spawned_child_under_its_own_evidenced_model():
    root = "agent:codex:root"
    singer = "agent:codex:Singer"
    nova = "agent:codex:Nova"
    m55 = "model:codex:gpt-5.5"
    luna = "model:codex:gpt-5.6-luna"
    graph = {
        "schema_version": "1.0",
        "session_id": "target-model-context",
        "nodes": [
            {"id": root, "type": "agent", "name": "/root",
             "attributes": {"provider": "codex", "agent_role": "root", "agent_path": "/root"}},
            {"id": singer, "type": "agent", "name": "Singer",
             "attributes": {"provider": "codex", "agent_id": "Singer"}},
            {"id": nova, "type": "agent", "name": "Nova",
             "attributes": {"provider": "codex", "agent_id": "Nova"}},
            {"id": m55, "type": "model", "name": "gpt-5.5",
             "attributes": {"provider": "codex"}},
            {"id": luna, "type": "model", "name": "gpt-5.6-luna",
             "attributes": {"provider": "codex"}},
        ],
        "edges": [
            _edge("root-55", root, m55, "USED_MODEL", 1),
            _edge("spawn-singer", root, singer, "SPAWNED_AGENT", 2),
            _edge("singer-55", singer, m55, "USED_MODEL", 3),
            _edge("root-luna", root, luna, "SWITCHED_MODEL", 4),
            _edge("spawn-nova", root, nova, "SPAWNED_AGENT", 5),
            _edge("nova-luna", nova, luna, "USED_MODEL", 6),
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
    assert [node["id"] for node in agents].count(singer) == 1
    assert [node["id"] for node in agents].count(nova) == 1

    contexts = {
        node["attributes"]["model_resource_id"]: node
        for node in display["nodes"]
        if node.get("attributes", {}).get("viewer_model_context")
    }
    assert set(contexts) == {m55, luna}

    spawn_actions = [
        node for node in display["nodes"]
        if node.get("attributes", {}).get("viewer_orchestration_action")
        and node.get("name") == "spawn_agent"
    ]
    assert len(spawn_actions) == 2, spawn_actions
    by_model = {node["attributes"]["model_resource_id"]: node for node in spawn_actions}
    assert set(by_model) == {m55, luna}

    assert any(
        edge["source"] == contexts[m55]["id"]
        and edge["target"] == by_model[m55]["id"]
        for edge in display["edges"]
    )
    assert any(
        edge["source"] == by_model[m55]["id"] and edge["target"] == singer
        for edge in display["edges"]
    )
    assert any(
        edge["source"] == contexts[luna]["id"]
        and edge["target"] == by_model[luna]["id"]
        for edge in display["edges"]
    )
    assert any(
        edge["source"] == by_model[luna]["id"] and edge["target"] == nova
        for edge in display["edges"]
    )

    assert positions[root]["x"] < positions[contexts[m55]["id"]]["x"]
    assert positions[contexts[m55]["id"]]["x"] < positions[by_model[m55]["id"]]["x"]
    assert positions[by_model[m55]["id"]]["x"] < positions[singer]["x"]
    assert positions[root]["x"] < positions[contexts[luna]["id"]]["x"]
    assert positions[contexts[luna]["id"]]["x"] < positions[by_model[luna]["id"]]["x"]
    assert positions[by_model[luna]["id"]]["x"] < positions[nova]["x"]
    assert metrics["NODE_OVERLAPS"] == 0
    assert metrics["EDGE_NODE_INTERSECTIONS"] == 0
