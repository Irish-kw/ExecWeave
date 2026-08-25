import json
from pathlib import Path

import pytest

from execweave.graph_ops import (
    filter_graph,
    find_paths,
    graph_summary,
    load_graph,
    write_graph_payload,
)


def _graph() -> dict:
    return {
        "graph_schema_version": "0.1",
        "session_id": "s1",
        "event_count": 6,
        "node_count": 5,
        "edge_count": 4,
        "nodes": [
            {"id": "agent:a", "type": "agent"},
            {"id": "session:s1", "type": "session"},
            {"id": "process:p1", "type": "process"},
            {"id": "file:/tmp/a", "type": "file"},
            {"id": "network_endpoint:1.2.3.4:443", "type": "network_endpoint"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "agent:a",
                "target": "session:s1",
                "relation": "STARTED_SESSION",
                "causal": None,
                "backends": [],
            },
            {
                "id": "e2",
                "source": "session:s1",
                "target": "process:p1",
                "relation": "LAUNCHED",
                "causal": True,
                "backends": ["strace"],
            },
            {
                "id": "e3",
                "source": "process:p1",
                "target": "network_endpoint:1.2.3.4:443",
                "relation": "CONNECTED_TO",
                "causal": True,
                "backends": ["strace"],
            },
            {
                "id": "e4",
                "source": "session:s1",
                "target": "file:/tmp/a",
                "relation": "OBSERVED_FILE_CHANGE",
                "causal": False,
                "backends": ["portable"],
            },
        ],
    }


def test_graph_summary_counts_types_relations_and_causality() -> None:
    summary = graph_summary(_graph())
    assert summary["node_count"] == 5
    assert summary["edge_count"] == 4
    assert summary["node_types"]["process"] == 1
    assert summary["relations"]["CONNECTED_TO"] == 1
    assert summary["causal_edges"] == 2
    assert summary["noncausal_edges"] == 1


def test_filter_graph_can_keep_only_causal_strace_edges() -> None:
    filtered = filter_graph(_graph(), causal_only=True, backends=["strace"])
    relations = {edge["relation"] for edge in filtered["edges"]}
    assert relations == {"LAUNCHED", "CONNECTED_TO"}
    node_ids = {node["id"] for node in filtered["nodes"]}
    assert "file:/tmp/a" not in node_ids
    assert "process:p1" in node_ids


def test_filter_graph_by_node_type_removes_cross_type_edges() -> None:
    filtered = filter_graph(_graph(), node_types=["process", "network_endpoint"])
    assert len(filtered["edges"]) == 1
    assert filtered["edges"][0]["relation"] == "CONNECTED_TO"
    assert {node["type"] for node in filtered["nodes"]} == {"process", "network_endpoint"}


def test_find_paths_respects_direction_and_causal_filter() -> None:
    graph = _graph()
    paths = find_paths(
        graph,
        source="session:s1",
        target="network_endpoint:1.2.3.4:443",
        causal_only=True,
    )
    assert len(paths) == 1
    assert paths[0]["nodes"] == [
        "session:s1",
        "process:p1",
        "network_endpoint:1.2.3.4:443",
    ]
    assert paths[0]["relations"] == ["LAUNCHED", "CONNECTED_TO"]

    no_path = find_paths(
        graph,
        source="process:p1",
        target="file:/tmp/a",
        causal_only=True,
    )
    assert no_path == []


def test_find_paths_rejects_missing_nodes() -> None:
    with pytest.raises(ValueError, match="source node not found"):
        find_paths(_graph(), source="missing", target="process:p1")


def test_load_and_write_graph_payload(tmp_path: Path) -> None:
    output = tmp_path / "graph.json"
    written = write_graph_payload(_graph(), output)
    assert written == output.resolve()
    loaded = load_graph(output)
    assert loaded["session_id"] == "s1"
    assert json.loads(output.read_text(encoding="utf-8"))["edge_count"] == 4

    with pytest.raises(FileExistsError):
        write_graph_payload(_graph(), output)
