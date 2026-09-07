"""Files get a column of their own, and disconnected evidence stays identifiable.

``execweaveLane`` used to send ``file`` into the ``endpoint`` lane by the same branch
that catches ``network`` and ``socket``, so a run with real filesystem activity piled
files and network endpoints into one column. Degree-zero files are now presentation-
collapsed into one expandable summary node, so tests distinguish evidence identity
from graph-layout policy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from test_graph_node_sizing_e2e import _drawn

pytestmark = pytest.mark.viewer_e2e

_LOCAL_ENDPOINTS = "viewer-cluster:local-endpoints"
_ORPHAN_FILES = "viewer-cluster:orphan-files"


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
        {"id": "endpoint:1", "type": "network_endpoint", "name": "127.0.0.1:443", "attributes": {}}
    )
    graph["edges"].append({"id": "f1", "source": "agent:/root/a", "target": "file:1",
                           "relation": "WROTE_FILE", "attributes": {}})
    graph["edges"].append({"id": "n1", "source": "agent:/root/a", "target": "endpoint:1",
                           "relation": "REACHED", "attributes": {}})

    drawn = {node["id"]: node for node in _drawn(tmp_path, graph)}
    assert drawn["file:1"]["lane"] == "file", drawn["file:1"]
    assert drawn[_LOCAL_ENDPOINTS]["lane"] == "endpoint", drawn[_LOCAL_ENDPOINTS]
    assert drawn["file:1"]["x"] != drawn[_LOCAL_ENDPOINTS]["x"], (
        f"files and endpoints are still in one column at x={drawn['file:1']['x']}"
    )


def test_each_evidence_lane_starts_at_its_own_first_row(tmp_path: Path) -> None:
    """The lanes shared one row counter, so whichever came second began part-way down.

    Checking only that files start at the top cannot see this: files were first in the
    shared list. Both lanes have to start at the same first row. Loopback endpoint
    instances are presentation-collapsed, so this checks the Local endpoints lane node.
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
             "name": f"127.0.0.{index + 1}:443", "attributes": {}}
        )
        graph["edges"].append(
            {"id": f"ne{index}", "source": "agent:/root/a", "target": f"endpoint:{index}",
             "relation": "REACHED", "attributes": {}}
        )

    drawn = _drawn(tmp_path, graph)
    files = [node for node in drawn if node["lane"] == "file"]
    endpoints = [node for node in drawn if node["lane"] == "endpoint"]
    assert len(files) == 3 and len(endpoints) == 1, (files, endpoints)
    assert endpoints[0]["id"] == _LOCAL_ENDPOINTS, endpoints
    # Dagre may change vertical ordering; this contract is that the two evidence
    # lanes begin independently, not that either one owns a hard-coded canvas origin.
    file_top = min(node["y"] for node in files)
    endpoint_top = min(node["y"] for node in endpoints)
    assert abs(file_top - endpoint_top) < 130, (
        f"one evidence lane still appears to inherit the other's row counter: "
        f"files={files}, endpoints={endpoints}"
    )


def test_disconnected_evidence_sits_below_the_spine(tmp_path: Path) -> None:
    """Disconnected file evidence collapses to one explicit file-lane summary node.

    The historical test name is retained. The old vertical-band assertion applied to
    every raw orphan node; those nodes are no longer drawn individually, so positioning
    the single summary cluster is a separate graph-layout concern.
    """
    graph = _spine()
    for index in range(6):
        graph["nodes"].append(
            {"id": f"orphan:{index}", "type": "file",
             "name": f"orphan{index}.tmp", "attributes": {}}
        )

    drawn = _drawn(tmp_path, graph)
    by_id = {node["id"]: node for node in drawn}
    assert _ORPHAN_FILES in by_id, drawn
    assert by_id[_ORPHAN_FILES]["lane"] == "file", by_id[_ORPHAN_FILES]
    assert not [node_id for node_id in by_id if node_id.startswith("orphan:")], by_id


def test_a_connected_file_stays_beside_the_spine(tmp_path: Path) -> None:
    """Connected evidence must stay above the cluster used for stray evidence."""
    graph = _spine()
    graph["nodes"].append({"id": "file:1", "type": "file", "name": "report.md", "attributes": {}})
    graph["nodes"].append({"id": "orphan:1", "type": "file", "name": "stray.tmp", "attributes": {}})
    graph["edges"].append({"id": "f1", "source": "agent:/root/a", "target": "file:1",
                           "relation": "WROTE_FILE", "attributes": {}})

    drawn = {node["id"]: node for node in _drawn(tmp_path, graph)}
    assert drawn["file:1"]["y"] < drawn[_ORPHAN_FILES]["y"], (
        f"connected evidence was demoted with stray evidence: "
        f"connected={drawn['file:1']} orphan={drawn[_ORPHAN_FILES]}"
    )


def test_a_subagent_is_never_demoted_even_with_no_edge_to_its_root(tmp_path: Path) -> None:
    """Edgeless provider-reported subagents remain execution-spine agents.

    The orphan-file summary node no longer defines an agent's vertical placement; that
    would couple semantic agent identity to viewer-only summary-node geometry.
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
    assert drawn[_ORPHAN_FILES]["lane"] == "file", drawn[_ORPHAN_FILES]
    agents = {key: node for key, node in drawn.items() if key.startswith("agent:")}
    assert len(agents) == 5, agents
    for key, node in agents.items():
        assert node["lane"] == "root", f"{key} left the root execution lane: {node}"
        assert abs(node["y"] - root["y"]) < 600, (
            f"{key} is far from its root despite being an agent: root={root['y']} node={node['y']}"
        )
