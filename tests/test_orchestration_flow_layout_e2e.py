from __future__ import annotations

from pathlib import Path

import pytest

from execweave.viewer_orchestration_projection import project_model_orchestration_viewer_graph
from test_graph_node_sizing_e2e import _drawn
from test_orchestration_flow_projection import A1, A2, A3, ROOT, _graph

pytestmark = pytest.mark.viewer_e2e


def test_model_action_agent_flow_is_left_to_right_without_duplicate_agents(tmp_path: Path) -> None:
    raw = _graph(tmp_path)
    projected = project_model_orchestration_viewer_graph(raw)
    drawn = _drawn(tmp_path, raw)

    drawn_by_id = {node["id"]: node for node in drawn}
    for agent_id in (ROOT, A1, A2, A3):
        assert sum(node["id"] == agent_id for node in drawn) == 1, (
            f"agent identity must appear exactly once: {agent_id} drawn={drawn}"
        )

    contexts = {
        node["name"]: node
        for node in projected["nodes"]
        if node.get("type") == "model_context"
    }
    actions = {
        (node["attributes"]["model_name"], node["attributes"]["action_kind"]): node
        for node in projected["nodes"]
        if node.get("type") == "tool_action"
    }
    assert set(contexts) == {"gpt-5.5", "gpt-5.6-luna"}
    assert {
        ("gpt-5.5", "spawn_agent"),
        ("gpt-5.5", "send_input"),
        ("gpt-5.5", "wait_agent"),
        ("gpt-5.6-luna", "spawn_agent"),
    } <= set(actions)

    root_x = drawn_by_id[ROOT]["x"]
    for model_name, context in contexts.items():
        context_id = context["id"]
        assert context_id in drawn_by_id, f"missing visible model context {model_name}"
        assert root_x < drawn_by_id[context_id]["x"], (
            f"model context must follow root: root={drawn_by_id[ROOT]} "
            f"context={drawn_by_id[context_id]}"
        )

    flow_edges = [
        edge
        for edge in projected["edges"]
        if edge.get("viewer_only") is True
        and edge.get("relation")
        in {"ORCHESTRATED_ACTION", "SPAWNED_AGENT", "SENT_INPUT_TO", "WAITED_FOR"}
    ]
    assert flow_edges
    for edge in flow_edges:
        source = drawn_by_id.get(edge["source"])
        target = drawn_by_id.get(edge["target"])
        assert source is not None and target is not None, edge
        assert source["x"] < target["x"], (
            f"execution flow must remain left-to-right: edge={edge} source={source} target={target}"
        )

    spawn55 = actions[("gpt-5.5", "spawn_agent")]["id"]
    send55 = actions[("gpt-5.5", "send_input")]["id"]
    wait55 = actions[("gpt-5.5", "wait_agent")]["id"]
    spawn_luna = actions[("gpt-5.6-luna", "spawn_agent")]["id"]
    assert drawn_by_id[contexts["gpt-5.5"]["id"]]["x"] < drawn_by_id[spawn55]["x"]
    assert drawn_by_id[contexts["gpt-5.5"]["id"]]["x"] < drawn_by_id[send55]["x"]
    assert drawn_by_id[contexts["gpt-5.5"]["id"]]["x"] < drawn_by_id[wait55]["x"]
    assert drawn_by_id[contexts["gpt-5.6-luna"]["id"]]["x"] < drawn_by_id[spawn_luna]["x"]

    # The original model and generic orchestration-tool entities remain in the
    # server-side projected evidence, but the Dashboard must not draw both the old
    # resource representation and the new execution-flow representation.
    for superseded_id in ("model:55", "model:luna", "tool:spawn", "tool:send", "tool:wait"):
        assert superseded_id not in drawn_by_id, (
            f"superseded visual node leaked onto canvas: {superseded_id}"
        )
