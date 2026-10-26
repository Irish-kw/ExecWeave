from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from execweave.live import _LiveState
from execweave.viewer_external_endpoints import EXTERNAL_NODE_ID, LOCAL_NODE_ID
from execweave.viewer_projection import project_viewer_graph, render_graph_html


def _process(process_id: str) -> dict[str, object]:
    return {"id": process_id, "type": "process", "name": "ollama"}


def _endpoint(address: str) -> dict[str, object]:
    return {
        "id": f"endpoint:{address}",
        "type": "network_endpoint",
        "name": address,
        "event_count": 1,
        "event_types": ["network.connection"],
    }


def _connected(process_id: str, address: str, sequence: int) -> dict[str, object]:
    endpoint_id = f"endpoint:{address}"
    return {
        "id": f"{process_id}--CONNECTED_TO-->{endpoint_id}",
        "source": process_id,
        "target": endpoint_id,
        "relation": "CONNECTED_TO",
        "count": 1,
        "first_sequence": sequence,
        "last_sequence": sequence,
        "event_ids": [f"network-{sequence}"],
        "event_types": ["network.connection"],
        "backends": ["portable"],
        "attributions": ["process_polling"],
        "causal": True,
    }


def _graph(
    groups: dict[str, list[str]],
    *,
    extra_nodes: list[dict[str, object]] | None = None,
    extra_edges: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    nodes: list[dict[str, object]] = []
    edges: list[dict[str, object]] = []
    sequence = 1
    for process_id, addresses in groups.items():
        nodes.append(_process(process_id))
        for address in addresses:
            nodes.append(_endpoint(address))
            edges.append(_connected(process_id, address, sequence))
            sequence += 1
    nodes.extend(extra_nodes or [])
    edges.extend(extra_edges or [])
    return {
        "graph_schema_version": "0.1",
        "session_id": "projection-test",
        "event_count": len(edges),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }


def _clusters(projected: dict[str, object]) -> dict[str, dict[str, object]]:
    expansion = projected.get("expansion")
    assert isinstance(expansion, dict)
    clusters = expansion.get("clusters")
    assert isinstance(clusters, dict)
    return clusters


def _local(projected: dict[str, object]) -> dict[str, object]:
    return next(
        node
        for node in projected["nodes"]
        if isinstance(node, dict) and node.get("id") == LOCAL_NODE_ID
    )


def test_collapses_four_loopback_ephemeral_endpoints_without_mutating_raw_graph() -> None:
    raw = _graph(
        {
            "process:ollama:1": [
                "127.0.0.1:49152",
                "127.0.0.1:50001",
                "127.0.0.2:50002",
                "127.255.255.254:65535",
            ]
        }
    )
    before = deepcopy(raw)

    projected = project_viewer_graph(raw)

    assert raw == before
    projection = projected["viewer_projection"]
    assert isinstance(projection, dict)
    assert projection["viewer_only"] is True
    assert projection["cluster_count"] == 1
    assert projection["local_endpoint_count"] == 4
    local = _local(projected)
    assert local["type"] == "network_endpoint"
    assert local["name"] == "Local endpoints"
    attributes = local["attributes"]
    assert isinstance(attributes, dict)
    assert attributes["viewer_only"] is True
    assert attributes["member_count"] == 4
    assert attributes["reason"] == "local_endpoints"
    assert {item["address"] for item in attributes["endpoints"]} == {
        "127.0.0.1:49152",
        "127.0.0.1:50001",
        "127.0.0.2:50002",
        "127.255.255.254:65535",
    }

    expansion = _clusters(projected)[LOCAL_NODE_ID]
    assert expansion["viewer_only"] is True
    assert {node["id"] for node in expansion["nodes"]} == {
        "endpoint:127.0.0.1:49152",
        "endpoint:127.0.0.1:50001",
        "endpoint:127.0.0.2:50002",
        "endpoint:127.255.255.254:65535",
    }
    assert len(expansion["edges"]) == 4
    base_ids = {node["id"] for node in projected["nodes"]}
    assert "endpoint:127.0.0.1:49152" not in base_ids
    assert projected["node_count"] == 2
    assert projected["edge_count"] == 1
    edge = projected["edges"][0]
    assert edge["source"] == "process:ollama:1"
    assert edge["target"] == LOCAL_NODE_ID
    assert edge["count"] == 4


def test_threshold_requires_at_least_four_eligible_endpoints() -> None:
    """Historical ID retained: Local endpoints intentionally has no count threshold now."""
    raw = _graph(
        {"process:p1": ["127.0.0.1:50001", "127.0.0.1:50002", "127.0.0.1:50003"]}
    )
    before = deepcopy(raw)
    projected = project_viewer_graph(raw)
    assert raw == before
    assert projected["viewer_projection"]["local_endpoint_count"] == 3
    assert _local(projected)["attributes"]["member_count"] == 3
    assert projected["edges"][0]["count"] == 3


def test_edge_without_string_id_is_not_eligible_for_collapse() -> None:
    """Historical ID retained: endpoint identity, not edge-id formatting, controls folding."""
    addresses = [f"127.0.0.1:{50000 + index}" for index in range(4)]
    raw = _graph({"process:p1": addresses})
    edge = raw["edges"][0]
    assert isinstance(edge, dict)
    edge.pop("id")
    before = deepcopy(raw)

    projected = project_viewer_graph(raw)

    assert raw == before
    assert {node["id"] for node in projected["nodes"]} == {"process:p1", LOCAL_NODE_ID}
    assert len(projected["edges"]) == 1
    assert projected["edges"][0]["target"] == LOCAL_NODE_ID
    occurrences = projected["edges"][0]["viewer_occurrences"]
    assert any(item["edge_id"] is None for item in occurrences)


def test_low_ports_and_non_loopback_addresses_do_not_collapse() -> None:
    """Historical ID retained: all loopback ports fold locally; non-loopback folds External."""
    raw = _graph(
        {
            "process:p1": [
                "127.0.0.1:49151",
                "192.168.1.2:50001",
                "10.0.0.1:50002",
                "8.8.8.8:50003",
                "127.0.0.1:50004",
            ]
        }
    )
    projected = project_viewer_graph(raw)
    node_ids = {node["id"] for node in projected["nodes"] if isinstance(node, dict)}
    assert {LOCAL_NODE_ID, EXTERNAL_NODE_ID, "process:p1"} == node_ids
    local = _local(projected)
    assert {item["address"] for item in local["attributes"]["endpoints"]} == {
        "127.0.0.1:49151",
        "127.0.0.1:50004",
    }
    external = next(node for node in projected["nodes"] if node["id"] == EXTERNAL_NODE_ID)
    assert external["name"] == "External"
    assert {item["address"] for item in external["attributes"]["endpoints"]} == {
        "192.168.1.2:50001",
        "10.0.0.1:50002",
        "8.8.8.8:50003",
    }
    assert not any(
        node.get("id", "").startswith("endpoint:") for node in projected["nodes"]
    )


def test_ipv6_loopback_endpoints_collapse_with_bracketed_or_plain_names() -> None:
    raw = _graph(
        {
            "process:p1": [
                "::1:50001",
                "[::1]:50002",
                "::1:50003",
                "[::1]:50004",
            ]
        }
    )
    projected = project_viewer_graph(raw)
    assert projected["viewer_projection"]["cluster_count"] == 1
    local = _local(projected)
    assert local["attributes"]["member_count"] == 4
    assert {item["address"] for item in local["attributes"]["endpoints"]} == {
        "[::1]:50001",
        "[::1]:50002",
        "[::1]:50003",
        "[::1]:50004",
    }


def test_groups_are_kept_separate_per_source_process() -> None:
    """Historical ID retained: occurrences share one Local node but source edges stay separate."""
    raw = _graph(
        {
            "process:p1": [f"127.0.0.1:{50000 + index}" for index in range(4)],
            "process:p2": [f"127.0.0.1:{51000 + index}" for index in range(4)],
        }
    )
    projected = project_viewer_graph(raw)
    assert projected["viewer_projection"]["cluster_count"] == 1
    assert _local(projected)["attributes"]["member_count"] == 8
    local_edges = [
        edge
        for edge in projected["edges"]
        if edge.get("relation") == "CONNECTED_TO" and edge.get("target") == LOCAL_NODE_ID
    ]
    assert {edge["source"] for edge in local_edges} == {"process:p1", "process:p2"}
    assert {edge["count"] for edge in local_edges} == {4}


def test_endpoint_with_additional_incident_semantic_edge_is_not_collapsed() -> None:
    """Historical ID retained: extra semantic evidence is remapped, never discarded."""
    addresses = [f"127.0.0.1:{50000 + index}" for index in range(4)]
    target = f"endpoint:{addresses[0]}"
    raw = _graph(
        {"process:p1": addresses},
        extra_nodes=[{"id": "tool:semantic", "type": "tool", "name": "semantic"}],
        extra_edges=[
            {
                "id": "tool:semantic--OBSERVED_ENDPOINT-->endpoint",
                "source": "tool:semantic",
                "target": target,
                "relation": "OBSERVED_ENDPOINT",
                "count": 1,
            }
        ],
    )
    before = deepcopy(raw)
    projected = project_viewer_graph(raw)
    assert raw == before
    assert _local(projected)["attributes"]["member_count"] == 4
    assert any(
        edge.get("source") == "tool:semantic"
        and edge.get("target") == LOCAL_NODE_ID
        and edge.get("relation") == "OBSERVED_ENDPOINT"
        for edge in projected["edges"]
    )
    expansion = _clusters(projected)[LOCAL_NODE_ID]
    assert any(edge.get("id") == "tool:semantic--OBSERVED_ENDPOINT-->endpoint" for edge in expansion["edges"])


def test_endpoint_with_multiple_incoming_connections_is_not_collapsed() -> None:
    """Historical ID retained: multiple source processes remain as distinct Local edges."""
    addresses = [f"127.0.0.1:{50000 + index}" for index in range(4)]
    target = addresses[0]
    raw = _graph(
        {"process:p1": addresses},
        extra_nodes=[_process("process:p2")],
        extra_edges=[_connected("process:p2", target, 99)],
    )
    before = deepcopy(raw)
    projected = project_viewer_graph(raw)
    assert raw == before
    local_edges = [
        edge
        for edge in projected["edges"]
        if edge.get("relation") == "CONNECTED_TO" and edge.get("target") == LOCAL_NODE_ID
    ]
    assert {edge["source"] for edge in local_edges} == {"process:p1", "process:p2"}
    assert next(edge for edge in local_edges if edge["source"] == "process:p1")["count"] == 4
    assert next(edge for edge in local_edges if edge["source"] == "process:p2")["count"] == 1


def test_existing_expansion_payload_is_preserved_and_merged() -> None:
    raw = _graph(
        {"process:p1": [f"127.0.0.1:{50000 + index}" for index in range(4)]}
    )
    raw["expansion"] = {
        "schema_version": "0.1",
        "clusters": {
            "cluster:existing": {
                "cluster_node_id": "cluster:existing",
                "cluster_edge_id": "edge:existing",
                "nodes": [],
                "edges": [],
            }
        },
    }
    projected = project_viewer_graph(raw)
    clusters = _clusters(projected)
    assert "cluster:existing" in clusters
    assert LOCAL_NODE_ID in clusters
    assert len(clusters) == 2


def test_projected_renderer_embeds_expandable_cluster_without_changing_raw_graph() -> None:
    raw = _graph(
        {"process:p1": [f"127.0.0.1:{50000 + index}" for index in range(4)]}
    )
    before = deepcopy(raw)
    html = render_graph_html(raw)

    assert raw == before
    embedded = html.split("window.__execweaveStaticGraph=", 1)[1].split(
        ";window.__execweaveStaticConversations=", 1
    )[0]
    payload = json.loads(embedded)
    assert payload["viewer_projection"]["viewer_only"] is True
    local = next(node for node in payload["nodes"] if node["id"] == LOCAL_NODE_ID)
    assert local["type"] == "network_endpoint"
    assert local["attributes"]["expandable"] is True
    assert LOCAL_NODE_ID in payload["expansion"]["clusters"]
    assert "window.__execweaveStaticGraph=" in html
    assert "Expand cluster" not in html


def _network_event(sequence: int, address: str) -> dict[str, object]:
    return {
        "schema_version": "0.2",
        "event_id": f"network-{sequence}",
        "session_id": "live-projection",
        "timestamp": f"2026-08-27T00:00:{sequence:02d}Z",
        "sequence": sequence,
        "event_type": "network.connection",
        "relation": "CONNECTED_TO",
        "source": {
            "id": "process:ollama:1",
            "type": "process",
            "name": "ollama",
            "attributes": {"pid": 100},
        },
        "target": {
            "id": f"endpoint:{address}",
            "type": "network_endpoint",
            "name": address,
        },
        "attributes": {
            "backend": "portable",
            "attribution": "process_polling",
            "causal": True,
        },
    }


def _append(path: Path, event: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def test_live_switches_to_projected_snapshot_when_cluster_becomes_active(tmp_path: Path) -> None:
    event_path = tmp_path / "events.jsonl"
    event_path.write_text("", encoding="utf-8")
    state = _LiveState("live-projection", event_path)
    for index in range(4):
        _append(event_path, _network_event(index + 1, f"127.0.0.1:{50000 + index}"))

    response = state.live_update(0)

    assert response["kind"] == "snapshot"
    graph = response["graph"]
    assert graph["viewer_projection"]["viewer_only"] is True
    assert graph["node_count"] == 2
    assert graph["edge_count"] == 1
    assert _local(graph)["attributes"]["member_count"] == 4


def test_live_keeps_delta_protocol_before_projection_threshold(tmp_path: Path) -> None:
    """Historical ID retained: Local folding is active immediately, so snapshot is required."""
    event_path = tmp_path / "events.jsonl"
    event_path.write_text("", encoding="utf-8")
    state = _LiveState("live-projection", event_path)
    for index in range(3):
        _append(event_path, _network_event(index + 1, f"127.0.0.1:{50000 + index}"))

    response = state.live_update(0)

    assert response["kind"] == "snapshot"
    graph = response["graph"]
    assert graph["viewer_projection"]["local_endpoint_count"] == 3
    assert graph["node_count"] == 2
    assert graph["edge_count"] == 1
    assert _local(graph)["attributes"]["member_count"] == 3
