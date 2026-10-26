from __future__ import annotations

import pytest

from test_provider_execution_flow_e2e import _display

pytestmark = pytest.mark.viewer_e2e


def test_projected_orchestration_consumes_matching_raw_tool_visuals():
    _, display, _, raw, metrics, _ = _display("codex")
    visible_ids = {node["id"] for node in display["nodes"]}
    raw_ids = {node["id"] for node in raw["nodes"]}

    # The provider evidence remains in the raw graph for inspection/provenance.
    for kind in ("spawn_agent", "send_input", "wait_agent"):
        assert f"tool:codex:{kind}" in raw_ids
        assert f"tool-call:codex:{kind}" in raw_ids

    # The main graph owns exactly one action visual per owner/model/action group.
    # Raw tool/call nodes are folded into that action rather than appearing beside it.
    for kind in ("spawn_agent", "send_input", "wait_agent"):
        assert f"tool:codex:{kind}" not in visible_ids
        assert f"tool-call:codex:{kind}" not in visible_ids
        projected = [
            node for node in display["nodes"]
            if node.get("attributes", {}).get("viewer_orchestration_action")
            and node.get("name") == kind
        ]
        assert len(projected) == 1, (kind, projected)
        assert projected[0]["attributes"]["evidence_node_ids"], projected[0]

    agents = [node for node in display["nodes"] if node["type"] == "agent"]
    assert [node["name"] for node in agents].count("Singer") == 1
    assert [node["name"] for node in agents].count("Rawls") == 1
    assert metrics["NODE_OVERLAPS"] == 0
    assert metrics["EDGE_NODE_INTERSECTIONS"] == 0
