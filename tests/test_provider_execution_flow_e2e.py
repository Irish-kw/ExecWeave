from __future__ import annotations

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from test_viewer_agent_isolation_e2e import _browser, _launch

pytestmark = pytest.mark.viewer_e2e

PROVIDERS = (
    "claude",
    "codex",
    "antigravity",
    "cursor",
    "opencode",
    "ollama",
    "llamacpp",
    "vllm",
    "lmstudio",
    "anthropic",
    "openrouter",
    "litellm",
    "openai-compatible",
)


def _edge(edge_id: str, source: str, target: str, relation: str, seq: int, **attrs):
    return {
        "id": edge_id,
        "source": source,
        "target": target,
        "relation": relation,
        "first_sequence": seq,
        "last_sequence": seq,
        "attributes": attrs,
    }


def _flow_graph(provider: str):
    root = {
        "id": f"agent:{provider}:root",
        "type": "agent",
        "name": "/root",
        "attributes": {
            "provider": provider,
            "agent_role": "root",
            "agent_path": "/root",
        },
    }
    singer = {
        "id": f"agent:{provider}:Singer",
        "type": "agent",
        "name": "Singer",
        "attributes": {"provider": provider, "agent_id": "Singer"},
    }
    rawls = {
        "id": f"agent:{provider}:Rawls",
        "type": "agent",
        "name": "Rawls",
        "attributes": {"provider": provider, "agent_id": "Rawls"},
    }
    m55 = {
        "id": f"model:{provider}:gpt-5.5",
        "type": "model",
        "name": "gpt-5.5",
        "attributes": {"provider": provider},
    }
    luna = {
        "id": f"model:{provider}:gpt-5.6-luna",
        "type": "model",
        "name": "gpt-5.6-luna",
        "attributes": {"provider": provider},
    }

    nodes = [root, singer, rawls, m55, luna]
    edges = [
        _edge("model-55", root["id"], m55["id"], "USED_MODEL", 1),
    ]

    def add_call(kind: str, seq: int, model: str, **extra):
        call = {
            "id": f"tool-call:{provider}:{kind}",
            "type": "tool_call",
            "name": kind,
            "attributes": {
                "provider": provider,
                "tool_name": kind,
                "model": model,
                **extra,
            },
        }
        tool = {
            "id": f"tool:{provider}:{kind}",
            "type": "tool",
            "name": kind,
            "attributes": {"provider": provider, "native_name": kind},
        }
        nodes.extend([call, tool])
        edges.extend(
            [
                _edge(f"request-{kind}", root["id"], call["id"], "REQUESTED_TOOL_CALL", seq),
                _edge(f"uses-{kind}", call["id"], tool["id"], "USES_TOOL", seq + 1),
            ]
        )

    add_call("spawn_agent", 2, "gpt-5.5")
    edges.extend(
        [
            _edge("spawn-singer", root["id"], singer["id"], "SPAWNED_AGENT", 4, model="gpt-5.5"),
            _edge("spawn-rawls", root["id"], rawls["id"], "SPAWNED_AGENT", 4, model="gpt-5.5"),
        ]
    )
    add_call("send_input", 5, "gpt-5.5")
    edges.extend(
        [
            _edge("send-singer", root["id"], singer["id"], "SENT_AGENT_MESSAGE", 7, model="gpt-5.5"),
            _edge("send-rawls", root["id"], rawls["id"], "SENT_AGENT_MESSAGE", 7, model="gpt-5.5"),
        ]
    )
    edges.append(_edge("model-luna", root["id"], luna["id"], "SWITCHED_MODEL", 8))
    add_call(
        "wait_agent",
        9,
        "gpt-5.6-luna",
        target_agent_ids=["Singer", "Rawls"],
    )
    return {
        "schema_version": "1.0",
        "session_id": f"flow-{provider}",
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


def _display(provider: str):
    graph = _flow_graph(provider)
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
            raw = page.evaluate("window.__execweaveCore.getGraph()")
            assert not errors, errors
            return graph, display, positions, raw
        finally:
            browser.close()


@pytest.mark.parametrize("provider", PROVIDERS)
def test_every_provider_uses_model_orchestration_unique_agent_flow(provider):
    graph, display, positions, raw = _display(provider)
    edges = display["edges"]

    assert len(raw["nodes"]) == len(graph["nodes"])
    assert any(edge["relation"] == "SPAWNED_AGENT" for edge in raw["edges"])

    agent_nodes = [node for node in display["nodes"] if node["type"] == "agent"]
    assert len(agent_nodes) == 3
    assert {node["name"] for node in agent_nodes} == {"/root", "Singer", "Rawls"}

    contexts = [node for node in display["nodes"] if node.get("attributes", {}).get("viewer_model_context")]
    assert {node["name"] for node in contexts} == {"gpt-5.5", "gpt-5.6-luna"}

    actions = {
        node["name"]: node
        for node in display["nodes"]
        if node.get("attributes", {}).get("viewer_orchestration_action")
    }
    assert {"spawn_agent", "send_input", "wait_agent"} <= set(actions)

    root_id = f"agent:{provider}:root"
    singer_id = f"agent:{provider}:Singer"
    rawls_id = f"agent:{provider}:Rawls"
    context_55 = next(node for node in contexts if node["name"] == "gpt-5.5")
    context_luna = next(node for node in contexts if node["name"] == "gpt-5.6-luna")

    assert any(
        edge["source"] == root_id
        and edge["target"] == context_55["id"]
        and edge["relation"] == "MODEL_CONTEXT"
        for edge in edges
    )
    assert any(
        edge["source"] == root_id
        and edge["target"] == context_luna["id"]
        and edge["relation"] == "MODEL_CONTEXT"
        for edge in edges
    )
    assert any(
        edge["source"] == context_55["id"]
        and edge["target"] == actions["spawn_agent"]["id"]
        for edge in edges
    )
    assert any(
        edge["source"] == context_55["id"]
        and edge["target"] == actions["send_input"]["id"]
        for edge in edges
    )
    assert any(
        edge["source"] == context_luna["id"]
        and edge["target"] == actions["wait_agent"]["id"]
        for edge in edges
    )

    for action_name in ("spawn_agent", "send_input", "wait_agent"):
        targets = {
            edge["target"]
            for edge in edges
            if edge["source"] == actions[action_name]["id"]
        }
        assert {singer_id, rawls_id} <= targets

    assert not any(
        edge["source"] == root_id
        and edge["target"] in {singer_id, rawls_id}
        and edge["relation"] in {"SPAWNED_AGENT", "SENT_AGENT_MESSAGE"}
        for edge in edges
    )

    assert positions[root_id]["x"] < positions[context_55["id"]]["x"]
    assert positions[context_55["id"]]["x"] < positions[actions["spawn_agent"]["id"]]["x"]
    assert positions[actions["spawn_agent"]["id"]]["x"] < positions[singer_id]["x"]
    assert positions[actions["spawn_agent"]["id"]]["x"] < positions[rawls_id]["x"]

    projection = display["dashboard_projection"]
    assert projection["execution_flow_projection"] is True
    assert projection["unique_agent_node_count"] == 3


def test_model_switch_keeps_action_contexts_separate_without_cloning_agents():
    _, display, _, _ = _display("codex")
    actions = [
        node
        for node in display["nodes"]
        if node.get("attributes", {}).get("viewer_orchestration_action")
    ]
    by_name = {node["name"]: node for node in actions}
    assert by_name["spawn_agent"]["attributes"]["model_resource_id"].endswith("gpt-5.5")
    assert by_name["send_input"]["attributes"]["model_resource_id"].endswith("gpt-5.5")
    assert by_name["wait_agent"]["attributes"]["model_resource_id"].endswith("gpt-5.6-luna")
    assert len([node for node in display["nodes"] if node["name"] == "Singer" and node["type"] == "agent"]) == 1
    assert len([node for node in display["nodes"] if node["name"] == "Rawls" and node["type"] == "agent"]) == 1
