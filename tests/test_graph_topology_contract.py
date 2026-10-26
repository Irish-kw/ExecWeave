"""The shared dashboard topology contract, judged on hand-built page snapshots.

``scripts/acceptance/graph_topology.py`` decides whether a drawn graph is one a
user can follow; the provider fixtures and the real-provider journeys both rely
on it. These snapshots pin each rule on its own, so a rule that stops firing is
caught without a browser.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from acceptance import graph_topology  # noqa: E402
from acceptance.graph_topology import ROOT  # noqa: E402

_ROW = 120.0


def _snapshot(nodes: list[tuple], edges: list[tuple]) -> dict[str, Any]:
    """Nodes are ``(id, type, name, column)``; a ``model`` node is a model context.

    Edges are ``(source, relation, target)`` plus an optional feedback flag.
    Every node gets its own row so boxes never overlap unless a test says so.
    """
    drawn, display_nodes = [], []
    for row, (node_id, kind, name, column) in enumerate(nodes):
        x, y = column * 200.0, row * _ROW
        drawn.append(
            {"id": node_id, "x": x, "y": y, "box": {"left": x, "right": x + 80, "top": y, "bottom": y + 30}}
        )
        display_nodes.append({"id": node_id, "type": kind, "name": name, "model_context": kind == "model"})
    display_edges, paths = [], []
    for index, (source, relation, target, *flag) in enumerate(edges):
        edge_id = f"e{index}"
        display_edges.append(
            {"id": edge_id, "source": source, "target": target, "relation": relation, "feedback": bool(flag and flag[0])}
        )
        paths.append(
            {"id": edge_id, "source": source, "target": target, "relation": relation.lower(), "length": 50.0, "hits": []}
        )
    return {"nodes": drawn, "paths": paths, "labels": [], "display": {"nodes": display_nodes, "edges": display_edges}}


def _switch_run() -> tuple[list[tuple], list[tuple]]:
    """``ollama run llama3.2``, then ``/load qwen3`` inside the same REPL session."""
    nodes = [
        ("root", "agent", "Ollama", 0),
        ("ctx-a", "model", "llama3.2", 1),
        ("ctx-b", "model", "qwen3", 1),
        ("session", "session", "run", 2),
    ]
    edges = [
        ("root", "MODEL_CONTEXT", "ctx-a"),
        ("root", "MODEL_CONTEXT", "ctx-b"),
        ("ctx-a", "USED_IN_SESSION", "session"),
        ("ctx-b", "USED_IN_SESSION", "session"),
    ]
    return nodes, edges


def _matching(problems: list[str], text: str) -> list[str]:
    return [problem for problem in problems if text in problem]


def test_root_model_session_is_accepted() -> None:
    problems, feeds = graph_topology.violations(
        _snapshot(
            [("root", "agent", "Ollama", 0), ("ctx", "model", "llama3.2", 1), ("session", "session", "run", 2)],
            [("root", "MODEL_CONTEXT", "ctx"), ("ctx", "USED_IN_SESSION", "session")],
        )
    )
    assert problems == []
    assert feeds == [frozenset({"llama3.2"})]


def test_model_switch_enters_from_the_root_into_the_same_session() -> None:
    problems, feeds = graph_topology.violations(_snapshot(*_switch_run()))
    assert problems == []
    assert feeds == [frozenset({"llama3.2", "qwen3"})]
    assert graph_topology.feeds_match(feeds, [frozenset({"llama3.2", "qwen3"})])
    # A switch is one session fed twice, not two sessions.
    assert not graph_topology.feeds_match(feeds, [frozenset({"llama3.2"}), frozenset({"qwen3"})])


def test_new_provider_session_gets_its_own_session_node() -> None:
    nodes, edges = _switch_run()
    nodes = nodes + [("session-2", "session", "run 2", 2)]
    edges = edges[:3] + [("ctx-b", "USED_IN_SESSION", "session-2")]
    problems, feeds = graph_topology.violations(_snapshot(nodes, edges))
    assert problems == []
    assert graph_topology.feeds_match(feeds, [frozenset({"llama3.2"}), frozenset({"qwen3"})])


def test_session_straight_off_the_root_only_when_no_model_was_observed() -> None:
    problems, feeds = graph_topology.violations(
        _snapshot(
            [("root", "agent", "script", 0), ("session", "session", "run", 1)],
            [("root", "RECORDED_IN_SESSION", "session")],
        )
    )
    assert problems == []
    assert feeds == [frozenset({ROOT})]


def test_session_hung_off_the_root_with_its_model_after_it_is_rejected() -> None:
    # The old drawing: root -> session -> model.
    snapshot = _snapshot(
        [("root", "agent", "Ollama", 0), ("session", "session", "run", 1), ("ctx", "model", "llama3.2", 2)],
        [("root", "RECORDED_IN_SESSION", "session"), ("session", "USED_MODEL", "ctx")],
    )
    problems, feeds = graph_topology.violations(snapshot)
    assert _matching(problems, "model node llama3.2 must enter only from the root via MODEL_CONTEXT")
    assert _matching(problems, "model node llama3.2 leads nowhere")
    assert _matching(problems, "model nodes that feed no session: ['llama3.2']")
    assert not graph_topology.feeds_match(feeds, [frozenset({"llama3.2"})])


def test_session_entered_from_both_the_root_and_a_model_is_rejected() -> None:
    problems, _ = graph_topology.violations(
        _snapshot(
            [("root", "agent", "Ollama", 0), ("ctx", "model", "llama3.2", 1), ("session", "session", "run", 2)],
            [
                ("root", "MODEL_CONTEXT", "ctx"),
                ("ctx", "USED_IN_SESSION", "session"),
                ("root", "RECORDED_IN_SESSION", "session"),
            ],
        )
    )
    assert _matching(problems, "session session must enter from model nodes")


def test_switched_model_not_entering_from_the_root_is_rejected() -> None:
    nodes, edges = _switch_run()
    nodes[2] = ("ctx-b", "model", "qwen3", 2)
    nodes[3] = ("session", "session", "run", 3)
    edges[1] = ("ctx-a", "MODEL_CONTEXT", "ctx-b")
    problems, _ = graph_topology.violations(_snapshot(nodes, edges))
    assert _matching(problems, "model node qwen3 must enter only from the root via MODEL_CONTEXT")


def test_isolated_node_is_rejected() -> None:
    nodes, edges = _switch_run()
    problems, _ = graph_topology.violations(_snapshot(nodes + [("api", "inference_api", "ollama", 1)], edges))
    assert _matching(problems, "isolated nodes: ['api']")
    assert _matching(problems, "expected one root")


def test_second_root_and_unreachable_nodes_are_rejected() -> None:
    nodes, edges = _switch_run()
    nodes = nodes + [("launcher", "process", "ollama", 0), ("tool", "tool", "Bash", 3)]
    edges = edges + [("launcher", "SPAWNED", "tool")]
    problems, _ = graph_topology.violations(_snapshot(nodes, edges))
    assert _matching(problems, "expected one root; nodes with no forward way in: ['launcher', 'root']")


def test_duplicate_edge_and_self_loop_are_rejected() -> None:
    nodes, edges = _switch_run()
    edges = edges + [("ctx-a", "USED_IN_SESSION", "session"), ("session", "USED_IN_SESSION", "session", True)]
    problems, _ = graph_topology.violations(_snapshot(nodes, edges))
    assert _matching(problems, "duplicate edge ('ctx-a', 'USED_IN_SESSION', 'session') x2")
    assert _matching(problems, "self-loop USED_IN_SESSION on session")


def test_backward_edge_must_be_marked_feedback_and_only_then() -> None:
    nodes, edges = _switch_run()
    unmarked = graph_topology.violations(_snapshot(nodes, edges + [("session", "RETURNED_TO", "root")]))[0]
    assert _matching(unmarked, "RETURNED_TO session (x 400.0) -> root (x 0.0) is drawn backwards but feedback=False")
    marked = graph_topology.violations(_snapshot(nodes, edges + [("session", "RETURNED_TO", "root", True)]))[0]
    assert marked == []
    mislabelled = graph_topology.violations(_snapshot(nodes, edges[:3] + [("ctx-b", "USED_IN_SESSION", "session", True)]))[0]
    assert _matching(mislabelled, "is drawn forwards but feedback=True")


def test_two_nodes_of_one_model_feeding_one_session_are_rejected() -> None:
    nodes, edges = _switch_run()
    nodes[2] = ("ctx-b", "model", "llama3.2:latest", 1)
    problems, feeds = graph_topology.violations(_snapshot(nodes, edges))
    assert _matching(problems, "is fed by more than one node of model ['llama3.2']")
    # Normalizing the spelling must not hide the second node from the expectation either.
    assert not graph_topology.feeds_match(feeds, [frozenset({"llama3.2"})])


def test_ollama_latest_tag_is_the_same_model() -> None:
    assert graph_topology.model_name("llama3.2:latest") == "llama3.2"
    assert graph_topology.model_name("qwen2.5:0.5b") == "qwen2.5:0.5b"
    assert graph_topology.feeds_match([frozenset({"llama3.2:latest"})], [frozenset({"llama3.2"})])
    assert graph_topology.feeds_match(
        [frozenset({"qwen2.5:0.5b", "smollm2:135m"})], [frozenset({"smollm2:135m", "qwen2.5:0.5b"})]
    )
    assert not graph_topology.feeds_match([frozenset({"qwen2.5:0.5b"})], [frozenset({"qwen2.5:1.5b"})])
    assert not graph_topology.feeds_match([frozenset({"a"}), frozenset({"a"})], [frozenset({"a"})])


def test_drawn_nodes_must_be_the_display_graph() -> None:
    snapshot = _snapshot(*_switch_run())
    snapshot["nodes"] = snapshot["nodes"][:-1]
    problems, feeds = graph_topology.violations(snapshot)
    assert _matching(problems, "never drawn ['session']")
    assert feeds == []
    empty = {"nodes": [], "paths": [], "labels": [], "display": {"nodes": [], "edges": []}}
    assert graph_topology.violations(empty)[0] == ["the page draws no graph"]


def test_paths_and_labels_stay_clear() -> None:
    snapshot = _snapshot(*_switch_run())
    snapshot["paths"][0]["hits"] = ["ctx-b"]
    snapshot["paths"][1]["length"] = 0
    snapshot["paths"][2]["target"] = "ctx-b"
    box = snapshot["nodes"][3]["box"]
    snapshot["labels"] = [
        {"id": "e2", "text": "used", "box": {"left": 900, "right": 960, "top": 0, "bottom": 10}},
        {"id": "e3", "text": "also used", "box": {"left": 930, "right": 990, "top": 5, "bottom": 15}},
        {"id": "e0", "text": "model", "box": dict(box)},
    ]
    problems, _ = graph_topology.violations(snapshot)
    assert _matching(problems, "path e0 runs through ['ctx-b']")
    assert _matching(problems, "edge e1 has no visible path")
    assert _matching(problems, "path e2 is drawn between the wrong nodes")
    assert _matching(problems, "labels overlap: 'used' / 'also used'")
    assert _matching(problems, "label 'model' covers node session")


class _Page:
    """Just enough of a Playwright page for ``inspect``."""

    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.snapshot = snapshot

    def wait_for_selector(self, selector: str, timeout: float) -> None:
        assert selector == ".node"

    def wait_for_function(self, script: str, timeout: float) -> None:
        pass

    def evaluate(self, script: str) -> Any:
        return self.snapshot if script == graph_topology.COLLECT_JS else True


def test_inspect_keeps_the_snapshot_and_names_the_surface(tmp_path: Path) -> None:
    page = _Page(_snapshot(*_switch_run()))
    problems, feeds = graph_topology.inspect(
        page, tmp_path, "live", expect_feeds=[frozenset({"llama3.2:latest", "qwen3"})]
    )
    assert problems == []
    assert feeds == [frozenset({"llama3.2", "qwen3"})]
    record = json.loads((tmp_path / "graph-topology-live.json").read_text(encoding="utf-8"))
    assert record["surface"] == "live" and record["problems"] == []
    assert record["expected_feeds"] == [["llama3.2:latest", "qwen3"]]

    problems, _ = graph_topology.inspect(page, tmp_path, "finished", expect_feeds=[frozenset({"llama3.2"})])
    assert problems == ["finished: sessions are fed by [['llama3.2', 'qwen3']], expected [['llama3.2']]"]
    record = json.loads((tmp_path / "graph-topology-finished.json").read_text(encoding="utf-8"))
    assert record["problems"] == [problems[0].removeprefix("finished: ")]


def test_summary_counts_what_it_leaves_out() -> None:
    problems = [f"p{index}" for index in range(15)]
    assert graph_topology.summary(problems) == [*problems[:12], "... and 3 more"]
    assert graph_topology.summary(problems[:2]) == problems[:2]
