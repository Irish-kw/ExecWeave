from execweave.graph_ops import condense_graph


def _graph(file_count: int = 10) -> dict:
    process_id = "process:s1:100"
    nodes = [
        {"id": process_id, "type": "process", "name": "python", "event_count": 1},
        {
            "id": "network_endpoint:1.2.3.4:443",
            "type": "network_endpoint",
            "name": "1.2.3.4:443",
            "event_count": 1,
        },
    ]
    edges = [
        {
            "id": f"{process_id}--CONNECTED_TO-->network_endpoint:1.2.3.4:443",
            "source": process_id,
            "target": "network_endpoint:1.2.3.4:443",
            "relation": "CONNECTED_TO",
            "count": 1,
            "causal": True,
            "backends": ["strace"],
            "attributions": ["syscall"],
            "event_ids": ["net-1"],
            "event_types": ["network.connection"],
            "first_sequence": 1,
            "last_sequence": 1,
        }
    ]
    for index in range(file_count):
        node_id = f"file:/repo/src/file_{index}.py"
        nodes.append(
            {
                "id": node_id,
                "type": "file",
                "name": f"file_{index}.py",
                "event_count": 1,
                "first_seen": f"2026-08-25T00:00:{index:02d}Z",
                "last_seen": f"2026-08-25T00:00:{index:02d}Z",
            }
        )
        edges.append(
            {
                "id": f"{process_id}--OPENED_READ-->{node_id}",
                "source": process_id,
                "target": node_id,
                "relation": "OPENED_READ",
                "count": 1,
                "causal": True,
                "backends": ["strace"],
                "attributions": ["syscall"],
                "event_ids": [f"file-{index}"],
                "event_types": ["filesystem.open"],
                "first_sequence": index + 2,
                "last_sequence": index + 2,
            }
        )
    return {
        "graph_schema_version": "0.1",
        "session_id": "s1",
        "event_count": file_count + 1,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }


def test_condense_graph_groups_repetitive_file_leaves() -> None:
    original = _graph(10)
    condensed = condense_graph(original, threshold=4, sample_size=3)

    clusters = [node for node in condensed["nodes"] if node["type"] == "file_cluster"]
    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster["attributes"]["member_count"] == 10
    assert cluster["attributes"]["directory_bucket"] == "/repo/src"
    assert len(cluster["attributes"]["sample_members"]) == 3
    assert cluster["attributes"]["sample_truncated"] is True

    cluster_edges = [edge for edge in condensed["edges"] if edge["target"] == cluster["id"]]
    assert len(cluster_edges) == 1
    assert cluster_edges[0]["relation"] == "OPENED_READ"
    assert cluster_edges[0]["count"] == 10
    assert cluster_edges[0]["causal"] is True
    assert cluster_edges[0]["collapsed_member_count"] == 10

    assert any(node["type"] == "process" for node in condensed["nodes"])
    assert any(node["type"] == "network_endpoint" for node in condensed["nodes"])
    assert any(edge["relation"] == "CONNECTED_TO" for edge in condensed["edges"])
    assert condensed["condensation"]["collapsed_node_count"] == 10
    assert original["node_count"] == 12


def test_condense_graph_does_not_collapse_small_groups() -> None:
    original = _graph(3)
    condensed = condense_graph(original, threshold=4)
    assert not any(node["type"] == "file_cluster" for node in condensed["nodes"])
    assert condensed["node_count"] == original["node_count"]
    assert condensed["edge_count"] == original["edge_count"]


def test_condense_graph_validates_options() -> None:
    graph = _graph(2)
    try:
        condense_graph(graph, threshold=1)
    except ValueError as exc:
        assert "threshold" in str(exc)
    else:
        raise AssertionError("threshold=1 should fail")
