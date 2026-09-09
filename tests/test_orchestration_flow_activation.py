from __future__ import annotations

from execweave.viewer_orchestration_projection import project_model_orchestration_viewer_graph


def test_model_only_graph_does_not_activate_orchestration_flow() -> None:
    graph = {
        "schema_version": "1.0",
        "nodes": [
            {
                "id": "agent:/root",
                "type": "agent",
                "name": "/root",
                "attributes": {"agent_role": "root", "agent_path": "/root"},
            },
            {
                "id": "agent:/root/a",
                "type": "agent",
                "name": "a",
                "attributes": {"agent_role": "child", "agent_path": "/root/a"},
            },
            {"id": "model:m", "type": "model", "name": "gpt", "attributes": {}},
        ],
        "edges": [
            {
                "id": "spawn",
                "source": "agent:/root",
                "target": "agent:/root/a",
                "relation": "SPAWNED_AGENT",
                "attributes": {},
            },
            {
                "id": "model",
                "source": "agent:/root/a",
                "target": "model:m",
                "relation": "USED_MODEL",
                "attributes": {},
            },
        ],
    }

    projected = project_model_orchestration_viewer_graph(graph)
    assert not [node for node in projected["nodes"] if node.get("type") in {"model_context", "tool_action"}]
    assert not [edge for edge in projected["edges"] if edge.get("relation") in {"MODEL_CONTEXT", "ORCHESTRATED_ACTION"}]
    for node in projected["nodes"]:
        if node.get("type") == "agent":
            assert "viewer_flow_rank" not in (node.get("attributes") or {})
            assert "viewer_execution_flow_identity" not in (node.get("attributes") or {})
