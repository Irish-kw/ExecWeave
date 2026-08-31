"""Files get a column of their own, and evidence with no path to the spine sits below it.

``execweaveLane`` used to send ``file`` into the ``endpoint`` lane by the same branch
that catches ``network`` and ``socket``, so a run with real filesystem activity piled
files and network endpoints into one column. Separately, a node is placed by its type
alone, so an evidence island unrelated to the execution spine still took a row inside a
lane and stretched every edge that passed it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from test_graph_node_sizing_e2e import _drawn


def _spine() -> dict[str, Any]:
    """A root, a subagent, a model and a tool: the execution flow, all connected."""
    return {
        "schema_version": "1.0",
        "nodes": [
            {"id": "agent:/root", "type": "agent", "name": "/root",
             "attributes": {"agent_role": "root", "agent_path": "/root"}},
            {"id": "agent:/root/a", "type": "agent", "name": "a",
             "attributes": {"agent_role": "child", "agent_path": "/root/a"}},
            {"id": "model:m", "type": "model", "name": "gpt", "attributes": {}},
            {"id": "tool:t", "type": "tool", "name": "read", "attributes": {}},
        ],
        "edges": [
            {"id": "s1", "source": "agent:/root", "target": "agent:/root/a",
             "relation": "SPAWNED_AGENT", "attributes": {}},
            {"id": "s2", "source": "agent:/root/a", "target": "model:m",
             "relation": "USED_MODEL", "attributes": {}},
            {"id": "s3", "source": "agent:/root/a", "target": "tool:t",
             "relation": "USES_TOOL", "attributes": {}},
        ],
    }


def test_files_and_endpoints_no_longer_share_a_column(tmp_path: Path) -> None:
    graph = _spine()
    graph["nodes"].append({"id": "file:1", "type": "file", "name": "notes.md", "attributes": {}})
    graph["nodes"].append(
        {"id": "endpoint:1", "type": "network_endpoint", "name": "1.1.1.1:443", "attributes": {}}
    )
    graph["edges"].append({"id": "f1", "source": "agent:/root/a", "target": "file:1",
                           "relation": "WROTE_FILE", "attributes": {}})
    graph["edges"].append({"id": "n1", "source": "agent:/root/a", "target": "endpoint:1",
                           "relation": "REACHED", "attributes": {}})

    drawn = {node["id"]: node for node in _drawn(tmp_path, graph)}
    assert drawn["file:1"]["lane"] == "file", drawn["file:1"]
    assert drawn["endpoint:1"]["lane"] == "endpoint", drawn["endpoint:1"]
    assert drawn["file:1"]["x"] != drawn["endpoint:1"]["x"], (
        f"files and endpoints are still in one column at x={drawn['file:1']['x']}"
    )


def test_each_evidence_lane_starts_at_its_own_first_row(tmp_path: Path) -> None:
    """The lanes shared one row counter, so whichever came second began part-way down.

    Checking only that files start at the top cannot see this: files were first in the
    shared list. Both lanes have to start at the same first row.
    """
    graph = _spine()
    for index in range(3):
        graph["nodes"].append(
            {"id": f"file:{index}", "type": "file", "name": f"f{index}.md", "attributes": {}}
        )
        graph["edges"].append(
            {"id": f"fe{index}", "source": "agent:/root/a", "target": f"file:{index}",
             "relation": "WROTE_FILE", "attributes": {}}
        )
    for index in range(2):
        graph["nodes"].append(
            {"id": f"endpoint:{index}", "type": "network_endpoint",
             "name": f"10.0.0.{index}:443", "attributes": {}}
        )
        graph["edges"].append(
            {"id": f"ne{index}", "source": "agent:/root/a", "target": f"endpoint:{index}",
             "relation": "REACHED", "attributes": {}}
        )

    drawn = _drawn(tmp_path, graph)
    files = [node for node in drawn if node["lane"] == "file"]
    endpoints = [node for node in drawn if node["lane"] == "endpoint"]
    assert len(files) == 3 and len(endpoints) == 2, (files, endpoints)
    assert min(node["y"] for node in files) == 80, files
    assert min(node["y"] for node in endpoints) == 80, (
        f"the endpoint lane starts below its first row, so it is still sharing a "
        f"counter with the file lane: {endpoints}"
    )


def test_disconnected_evidence_sits_below_the_spine(tmp_path: Path) -> None:
    """No spine node may share a row band with evidence that cannot reach it."""
    graph = _spine()
    for index in range(6):
        graph["nodes"].append(
            {"id": f"orphan:{index}", "type": "file",
             "name": f"orphan{index}.tmp", "attributes": {}}
        )

    drawn = _drawn(tmp_path, graph)
    spine = [node for node in drawn if not node["id"].startswith("orphan:")]
    orphans = [node for node in drawn if node["id"].startswith("orphan:")]
    assert len(orphans) == 6, orphans

    spine_floor = max(node["y"] + node["height"] for node in spine)
    orphan_top = min(node["y"] for node in orphans)
    assert orphan_top > spine_floor, (
        f"disconnected evidence starts at {orphan_top}, inside the spine which ends "
        f"at {spine_floor}"
    )


def test_a_connected_file_stays_beside_the_spine(tmp_path: Path) -> None:
    """Only unreachable evidence is demoted; a file the run wrote is part of the flow."""
    graph = _spine()
    graph["nodes"].append({"id": "file:1", "type": "file", "name": "report.md", "attributes": {}})
    graph["edges"].append({"id": "f1", "source": "agent:/root/a", "target": "file:1",
                           "relation": "WROTE_FILE", "attributes": {}})

    drawn = {node["id"]: node for node in _drawn(tmp_path, graph)}
    spine_floor = max(
        node["y"] + node["height"] for key, node in drawn.items() if key != "file:1"
    )
    assert drawn["file:1"]["y"] < spine_floor, (
        f"a connected file was demoted to the secondary band: {drawn['file:1']}"
    )


def test_a_subagent_is_never_demoted_even_with_no_edge_to_its_root(tmp_path: Path) -> None:
    """Codex records subagents with no edge back to the root that spawned them.

    Reading the graph alone therefore makes every subagent its own component, and
    banding pushed all of them into the region meant for stray evidence — below the
    run they are the point of. An agent belongs to the spine whether or not the
    provider recorded an edge to it.
    """
    graph = _spine()
    graph["edges"] = [edge for edge in graph["edges"] if edge["id"] != "s1"]
    for index in range(3):
        graph["nodes"].append(
            {"id": f"agent:/root/lone{index}", "type": "agent", "name": f"lone{index}",
             "attributes": {"agent_role": "child", "agent_path": f"/root/lone{index}"}}
        )
    graph["nodes"].append(
        {"id": "orphan:1", "type": "file", "name": "/tmp/stray.tmp", "attributes": {}}
    )

    drawn = {node["id"]: node for node in _drawn(tmp_path, graph)}
    root = drawn["agent:/root"]
    orphan = drawn["orphan:1"]
    for key, node in drawn.items():
        if not key.startswith("agent:"):
            continue
        assert node["y"] < orphan["y"], (
            f"{key} was demoted below stray evidence at y={orphan['y']}: {node}"
        )
    lone = drawn["agent:/root/lone0"]
    assert abs(lone["y"] - root["y"]) < 600, (
        f"an edgeless subagent is far from its root: root={root['y']} lone={lone['y']}"
    )
