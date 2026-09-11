"""The canvas layout solver, driven directly, once per supported provider.

The solver runs in the browser, over the graph the canvas draws rather than the graph the
projection lays out, so a Python-level assertion about ``viewer_flow`` would not see what
it does. This drives the real script under node with the graph each provider produces and
asserts the properties the layout exists to guarantee: a drawn edge runs left to right,
and no two nodes are placed on top of one another.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from execweave.viewer_flow_canvas import FLOW_CANVAS_SCRIPT
from execweave.viewer_projection import project_viewer_graph
from test_provider_execution_flow_e2e import PROVIDERS, _flow_graph

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is unavailable")

# The solver reads three globals and nothing else. Everything it would touch on a real
# page -- positions, the renderer, the topology -- belongs to applying a solution, not to
# finding one, so a stub graph is enough to exercise it exactly as the browser does.
_HARNESS = """
const payload=JSON.parse(process.argv[2]);
const nodeById=new Map(payload.nodes.map(node=>[node.id,node]));
const edgeById=new Map(payload.edges.map((edge,index)=>[String(index),edge]));
%s
execweaveRememberFlow(payload);
const solved=execweaveFlowSolve();
process.stdout.write(JSON.stringify(Object.fromEntries(solved)));
"""


def _solve(graph: dict[str, object]) -> dict[str, dict[str, float]]:
    # The script goes to a file rather than to ``node -e``: it is long enough that the
    # whole command line runs past what Windows accepts, and the run fails before node
    # is even reached.
    script = _HARNESS % FLOW_CANVAS_SCRIPT
    payload = {
        "nodes": graph["nodes"],
        "edges": graph["edges"],
        "viewer_flow": graph["viewer_flow"],
    }
    with tempfile.TemporaryDirectory() as room:
        entry = Path(room) / "solve.js"
        entry.write_text(script, encoding="utf-8")
        finished = subprocess.run(
            [shutil.which("node"), str(entry), json.dumps(payload)],
            capture_output=True,
            text=True,
            check=False,
        )
    assert finished.returncode == 0, finished.stderr
    return json.loads(finished.stdout)


@pytest.mark.parametrize("provider", PROVIDERS)
def test_every_drawn_edge_runs_left_to_right(provider: str) -> None:
    graph = project_viewer_graph(_flow_graph(provider))
    placed = _solve(graph)
    assert placed, "the solver placed nothing"

    folded = [
        (edge["source"], edge["target"])
        for edge in graph["edges"]
        if edge["source"] in placed
        and edge["target"] in placed
        and placed[edge["target"]]["layer"] <= placed[edge["source"]]["layer"]
    ]
    # These graphs hold no cycle, so nothing has to fold back. An edge that shares a
    # column with its own source is the defect this guards: the router draws it as a
    # right-angled rail into the side of a node that should have been further along.
    assert not folded, f"{provider} folds edges back: {folded}"


@pytest.mark.parametrize("provider", PROVIDERS)
def test_no_two_nodes_are_placed_on_the_same_spot(provider: str) -> None:
    graph = project_viewer_graph(_flow_graph(provider))
    placed = _solve(graph)

    taken: dict[tuple[float, float], str] = {}
    for node_id, at in sorted(placed.items()):
        spot = (at["layer"], at["row"])
        assert spot not in taken, f"{provider}: {node_id} sits on {taken[spot]}"
        taken[spot] = node_id


def test_a_cycle_folds_exactly_the_edge_that_closes_it() -> None:
    """A cycle has no left-to-right order, so one of its edges has to fold back."""
    nodes = [{"id": name, "type": "agent", "name": name, "attributes": {}} for name in "abc"]
    edges = [
        {"source": "a", "target": "b", "relation": "SPAWNED_AGENT"},
        {"source": "b", "target": "c", "relation": "SPAWNED_AGENT"},
        {"source": "c", "target": "a", "relation": "SPAWNED_AGENT"},
    ]
    graph = {
        "nodes": nodes,
        "edges": edges,
        "viewer_flow": {"nodes": [{"id": name} for name in "abc"]},
    }
    placed = _solve(graph)

    folded = [
        (edge["source"], edge["target"])
        for edge in edges
        if placed[edge["target"]]["layer"] <= placed[edge["source"]]["layer"]
    ]
    assert len(folded) == 1, f"expected one folded edge, got {folded}"
    # The two edges that do not close the cycle each still gain a column.
    assert placed["b"]["layer"] > placed["a"]["layer"]
    assert placed["c"]["layer"] > placed["b"]["layer"]


def _synthesised(host: dict[str, object], node_id: str) -> dict[str, object]:
    """What the browser adds: a node copied from another, attributes and all.

    A model context and an orchestration step are built in the browser from the node they
    describe, so they arrive carrying that node's own ``viewer_layer`` and ``viewer_row``
    while being absent from the projection's node list.
    """
    return {
        "id": node_id,
        "type": host["type"],
        "name": node_id,
        "attributes": dict(host.get("attributes") or {}),
    }


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_node_the_projection_never_saw_is_not_placed_on_the_node_it_copies(
    provider: str,
) -> None:
    graph = project_viewer_graph(_flow_graph(provider))
    host = next(node for node in graph["nodes"] if node["type"] == "model")
    stand_in = _synthesised(host, "viewer:model-context:" + str(host["id"]))
    feeder = next(
        edge["source"] for edge in graph["edges"] if edge["target"] == host["id"]
    )
    graph = {
        **graph,
        "nodes": [*graph["nodes"], stand_in],
        "edges": [
            *graph["edges"],
            {"source": feeder, "target": stand_in["id"], "relation": "MODEL_CONTEXT"},
            {"source": stand_in["id"], "target": host["id"], "relation": "MODEL_CONTEXT"},
        ],
    }
    placed = _solve(graph)

    here, there = placed[stand_in["id"]], placed[host["id"]]
    assert (here["layer"], here["row"]) != (there["layer"], there["row"])
    # It leads to the node it was copied from, so it belongs in an earlier column.
    assert here["layer"] < there["layer"]


def test_equal_ranked_nodes_do_not_share_a_column_with_what_they_point_at() -> None:
    """The case that reached the dashboard: a tie broken by id instead of by direction.

    A synthesised node takes its rank from the node that leads to it, which can equal the
    rank of the node it points at. Deciding direction by comparing ranks then lets the
    ids break the tie, and the edge folds back into a node of the same column.
    """
    graph = {
        "nodes": [
            {"id": "a-target", "type": "agent", "name": "target",
             "attributes": {"viewer_layer": 2, "viewer_row": 0}},
            {"id": "p-source", "type": "agent", "name": "source",
             "attributes": {"viewer_layer": 1, "viewer_row": 0}},
            {"id": "z-standin", "type": "tool", "name": "stand-in", "attributes": {}},
        ],
        "edges": [
            {"source": "p-source", "target": "z-standin", "relation": "REQUESTED_TOOL_CALL"},
            {"source": "z-standin", "target": "a-target", "relation": "ASSIGNED_AGENT_TASK"},
        ],
        "viewer_flow": {"nodes": [{"id": "a-target"}, {"id": "p-source"}]},
    }
    placed = _solve(graph)

    assert placed["z-standin"]["layer"] > placed["p-source"]["layer"]
    assert placed["a-target"]["layer"] > placed["z-standin"]["layer"]


def test_a_stand_in_with_no_edge_to_its_original_still_clears_it() -> None:
    """Ownership is membership in the projection's list, not the presence of attributes.

    A stand-in copies the attributes of the node it describes, including its column and
    row. Nothing connects the two, so no edge pushes them apart, and reading those
    attributes back is what put one exactly on top of the other.
    """
    graph = {
        "nodes": [
            {"id": "model:real", "type": "model", "name": "gpt",
             "attributes": {"viewer_layer": 3, "viewer_row": 4}},
            {"id": "viewer:model-context:model:real", "type": "model", "name": "context",
             "attributes": {"viewer_layer": 3, "viewer_row": 4}},
            {"id": "agent:root", "type": "agent", "name": "/root",
             "attributes": {"viewer_layer": 0, "viewer_row": 0}},
        ],
        "edges": [
            {"source": "agent:root", "target": "viewer:model-context:model:real",
             "relation": "MODEL_CONTEXT"},
        ],
        "viewer_flow": {"nodes": [{"id": "model:real"}, {"id": "agent:root"}]},
    }
    placed = _solve(graph)

    here = placed["viewer:model-context:model:real"]
    there = placed["model:real"]
    assert (here["layer"], here["row"]) != (there["layer"], there["row"])
    # Its column comes from the node that leads to it, not from the one it was copied
    # from: inheriting the copy's column is what put the two in the same place.
    assert here["layer"] == placed["agent:root"]["layer"] + 1
    assert here["layer"] < there["layer"]


def test_depth_counted_through_hidden_nodes_survives() -> None:
    """The projection's layer is a floor, not a starting point to be recomputed.

    It counts depth through nodes the canvas withholds. Rebuilding depth from the drawn
    edges alone collapses a long run into a handful of columns, because the nodes that
    made it long are not on the canvas to be counted.
    """
    graph = {
        "nodes": [
            {"id": "early", "type": "agent", "name": "early",
             "attributes": {"viewer_layer": 1, "viewer_row": 0}},
            {"id": "late", "type": "agent", "name": "late",
             "attributes": {"viewer_layer": 6, "viewer_row": 1}},
        ],
        # The chain that separates them ran through nodes the canvas does not draw. The
        # one drawn edge that survives spans the whole distance, and rebuilding depth
        # from it alone would put them in neighbouring columns.
        "edges": [{"source": "early", "target": "late", "relation": "SPAWNED_AGENT"}],
        "viewer_flow": {"nodes": [{"id": "early"}, {"id": "late"}]},
    }
    placed = _solve(graph)

    assert placed["late"]["layer"] - placed["early"]["layer"] == 5
