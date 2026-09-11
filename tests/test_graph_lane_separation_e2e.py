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
    """Evidence can share a flow layer, but remains distinct in its ordered slots."""
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
    file = drawn["file:1"]
    endpoint = drawn[_LOCAL_ENDPOINTS]
    assert file["lane"] == "file", file
    assert endpoint["lane"] == "endpoint", endpoint
    assert file["flow_layer"] == endpoint["flow_layer"] == 2, (file, endpoint)
    assert file["flow_order"] != endpoint["flow_order"], (file, endpoint)


def test_each_evidence_lane_starts_at_its_own_first_row(tmp_path: Path) -> None:
    """The flow contract records evidence order independently of DOM stacking."""
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
    assert {node["flow_layer"] for node in files} == {2}, files
    assert endpoints[0]["flow_layer"] == 2, endpoints
    assert {node["flow_order"] for node in files} == {0}, files
    assert endpoints[0]["flow_order"] == 2, endpoints
    assert {node["flow_row"] for node in files} == {0}, files
    assert endpoints[0]["flow_row"] == 2, endpoints


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
    """Edgeless provider-reported subagents retain semantic agent identity.

    The historical test name is retained. Whether an agent is above or below a viewer-
    only orphan summary is graph-layout policy; this regression instead proves that an
    edgeless child remains an agent-lane node and is never collapsed into file evidence.
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
    assert drawn[_ORPHAN_FILES]["lane"] == "file", drawn[_ORPHAN_FILES]
    agents = {key: node for key, node in drawn.items() if key.startswith("agent:")}
    assert len(agents) == 5, agents
    assert agents["agent:/root"]["lane"] == "root", agents["agent:/root"]
    for key, node in agents.items():
        if key == "agent:/root":
            continue
        assert node["lane"] == "agent", f"{key} lost child-agent identity: {node}"
