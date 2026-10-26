"""Execute the shipped replay planner; expected order is independent of its output."""
from __future__ import annotations

import json
import random
import shutil
import subprocess

import pytest

from execweave.viewer_gif import GIF_SCRIPT


def _plan(graphs: list[dict]) -> list[list[dict]]:
    node = shutil.which("node")
    assert node, "Node.js is required for the executable GIF chronology contract"
    functions = GIF_SCRIPT[
        GIF_SCRIPT.index("function gifEdgeId("):GIF_SCRIPT.index("function gifStepDelayMs(")
    ]
    script = functions + "\nprocess.stdout.write(JSON.stringify(JSON.parse(require('fs').readFileSync(0,'utf8')).map(gifTopologySteps)));"
    result = subprocess.run([node, "-e", script], input=json.dumps(graphs), check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def test_disconnected_node_keeps_its_first_sequence() -> None:
    graph = {
        "nodes": [
            {"id": "root", "type": "agent", "first_sequence": 0},
            {"id": "early", "type": "file", "first_sequence": 1},
            {"id": "late", "type": "file", "first_sequence": 100},
        ],
        "edges": [{"id": "later", "source": "root", "target": "late", "first_sequence": 100}],
    }
    assert [s["nodeId"] for s in _plan([graph])[0] if s["nodeId"]] == ["root", "early", "late"]


def test_timestamp_only_node_is_not_postponed_past_later_sequence_evidence() -> None:
    graph = {
        "nodes": [
            {"id": "root", "type": "agent", "name": "/root"},
            {"id": "early-connected"},
            {"id": "middle-isolated", "first_seen": "2026-09-08T00:00:05Z"},
            {"id": "late-connected"},
        ],
        "edges": [
            {"id": "e1", "source": "root", "target": "early-connected", "first_sequence": 1, "first_seen": "2026-09-08T00:00:01Z"},
            {"id": "e9", "source": "root", "target": "late-connected", "first_sequence": 9, "first_seen": "2026-09-08T00:00:09Z"},
        ],
    }
    assert [s["nodeId"] for s in _plan([graph])[0] if s["nodeId"]] == [
        "root", "early-connected", "middle-isolated", "late-connected"
    ]


def test_root_context_precedes_a_worker_edge() -> None:
    graph = {
        "nodes": [
            {"id": "z-root", "type": "agent", "attributes": {"agent_path": "/root"}},
            {"id": "worker", "type": "agent"},
            {"id": "model", "type": "model"},
        ],
        "edges": [{"id": "use", "source": "worker", "target": "model", "first_sequence": 1}],
    }
    assert _plan([graph])[0][0] == {"nodeId": "z-root", "edgeId": None}


def test_last_sequence_does_not_replace_first_observation_time() -> None:
    graph = {
        "nodes": [{"id": "root"}, {"id": "early"}, {"id": "late"}],
        "edges": [
            {"id": "early-edge", "source": "root", "target": "early", "last_sequence": 999, "timestamp": "2026-09-08T00:00:01Z"},
            {"id": "late-edge", "source": "root", "target": "late", "last_sequence": 2, "timestamp": "2026-09-08T00:00:09Z"},
        ],
    }
    assert [s["edgeId"] for s in _plan([graph])[0] if s["edgeId"]] == ["early-edge", "late-edge"]


@pytest.mark.parametrize("seed", [0, 7, 19])
def test_dense_mixed_order_is_deterministic_and_never_reveals_dangling_edges(seed: int) -> None:
    rng = random.Random(seed)
    nodes = [{"id": "root", "type": "agent", "name": "/root"}]
    edges = []
    for i in range(80):
        node = {"id": f"n{i:03}", "type": "file"}
        if i % 3 == 0:
            node["first_sequence"] = i + 1
        elif i % 3 == 1:
            node["first_seen"] = f"2026-09-08T00:{i // 60:02}:{i % 60:02}Z"
        nodes.append(node)
        if i % 7:
            edges.append({"id": f"e{i:03}", "source": "root" if i % 2 else f"n{i-1:03}", "target": node["id"], "first_sequence": i + 1, "first_seen": f"2026-09-08T00:{i // 60:02}:{i % 60:02}Z"})
    edges += [
        {"id": "return", "source": "n079", "target": "root", "first_sequence": 81},
        {"id": "self", "source": "root", "target": "root", "first_sequence": 82},
    ]
    graphs = []
    for _ in range(10):
        n, e = list(nodes), list(edges)
        rng.shuffle(n)
        rng.shuffle(e)
        graphs.append({"nodes": n, "edges": e})
    plans = _plan(graphs)
    assert all(plan == plans[0] for plan in plans)
    by_edge = {e["id"]: e for e in edges}
    seen_nodes, seen_edges = set(), set()
    for step in plans[0]:
        assert set(step) == {"nodeId", "edgeId"}
        if step["nodeId"] is not None:
            assert step["nodeId"] not in seen_nodes
            seen_nodes.add(step["nodeId"])
        if step["edgeId"] is not None:
            assert step["edgeId"] not in seen_edges
            edge = by_edge[step["edgeId"]]
            assert {edge["source"], edge["target"]} <= seen_nodes
            seen_edges.add(step["edgeId"])
    assert seen_nodes == {n["id"] for n in nodes}
    assert seen_edges == set(by_edge)
