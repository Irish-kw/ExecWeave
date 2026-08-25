import json
from pathlib import Path

import pytest

from execweave.cli import main
from execweave.focus import focus_graph


def _graph() -> dict:
    nodes = [
        {"id": node_id, "type": "process", "name": node_id}
        for node_id in ("a", "b", "c", "d", "e")
    ]
    edges = [
        {"id": "e1", "source": "a", "target": "b", "relation": "R1", "causal": True},
        {"id": "e2", "source": "b", "target": "c", "relation": "R2", "causal": True},
        {"id": "e3", "source": "d", "target": "b", "relation": "R1", "causal": True},
        {"id": "e4", "source": "c", "target": "e", "relation": "R3", "causal": False},
    ]
    return {
        "graph_schema_version": "0.1",
        "session_id": "s1",
        "event_count": 4,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }


def _ids(payload: dict) -> set[str]:
    return {node["id"] for node in payload["nodes"]}


def _edge_ids(payload: dict) -> set[str]:
    return {edge["id"] for edge in payload["edges"]}


def test_focus_zero_hop_keeps_only_anchor() -> None:
    focused = focus_graph(_graph(), anchors=["b"], hops=0)
    assert _ids(focused) == {"b"}
    assert focused["edges"] == []


def test_focus_one_hop_respects_direction() -> None:
    outgoing = focus_graph(_graph(), anchors=["b"], hops=1, direction="out")
    incoming = focus_graph(_graph(), anchors=["b"], hops=1, direction="in")
    both = focus_graph(_graph(), anchors=["b"], hops=1, direction="both")

    assert _ids(outgoing) == {"b", "c"}
    assert _edge_ids(outgoing) == {"e2"}
    assert _ids(incoming) == {"a", "b", "d"}
    assert _edge_ids(incoming) == {"e1", "e3"}
    assert _ids(both) == {"a", "b", "c", "d"}
    assert _edge_ids(both) == {"e1", "e2", "e3"}


def test_focus_filters_before_traversal() -> None:
    relation_limited = focus_graph(
        _graph(),
        anchors=["b"],
        hops=2,
        direction="both",
        relations=["R1"],
    )
    causal_only = focus_graph(
        _graph(),
        anchors=["c"],
        hops=1,
        direction="out",
        causal_only=True,
    )

    assert _ids(relation_limited) == {"a", "b", "d"}
    assert _edge_ids(relation_limited) == {"e1", "e3"}
    assert _ids(causal_only) == {"c"}
    assert causal_only["edges"] == []


def test_focus_preserves_selected_cluster_expansion_only() -> None:
    graph = _graph()
    graph["nodes"].append({"id": "cluster:x", "type": "file_cluster", "name": "files"})
    graph["edges"].append(
        {
            "id": "e5",
            "source": "b",
            "target": "cluster:x",
            "relation": "OPENED_READ",
            "causal": True,
        }
    )
    graph["expansion"] = {
        "schema_version": "0.1",
        "clusters": {
            "cluster:x": {"nodes": [{"id": "file:x", "type": "file"}], "edges": []},
            "cluster:unused": {"nodes": [{"id": "file:y", "type": "file"}], "edges": []},
        },
    }

    focused = focus_graph(graph, anchors=["b"], hops=1, direction="out")
    assert "cluster:x" in _ids(focused)
    assert set(focused["expansion"]["clusters"]) == {"cluster:x"}


def test_focus_validates_arguments() -> None:
    with pytest.raises(ValueError, match="hops"):
        focus_graph(_graph(), anchors=["b"], hops=-1)
    with pytest.raises(ValueError, match="anchor"):
        focus_graph(_graph(), anchors=[])
    with pytest.raises(ValueError, match="not found"):
        focus_graph(_graph(), anchors=["missing"])


def test_graph_focus_cli_writes_artifact(tmp_path: Path) -> None:
    source = tmp_path / "graph.json"
    output = tmp_path / "focused.json"
    source.write_text(json.dumps(_graph()), encoding="utf-8")

    result = main(
        [
            "graph-focus",
            str(source),
            "b",
            "--hops",
            "1",
            "--direction",
            "out",
            "--output",
            str(output),
        ]
    )

    assert result == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert _ids(payload) == {"b", "c"}
    assert payload["focus"]["anchors"] == ["b"]
    assert payload["focus"]["direction"] == "out"
    assert payload["focus"]["hops"] == 1
