from __future__ import annotations

from execweave.viewer_agent_panel import _AGENT_PANEL_JS
from execweave.viewer_external_endpoints import (
    EXTERNAL_NODE_ID,
    LOCAL_NODE_ID,
    collapse_external_endpoints,
    collapse_local_endpoints,
    format_endpoint_address,
)
from execweave.viewer_projection import project_viewer_graph


def _endpoint(address: str) -> dict[str, object]:
    return {
        "id": f"endpoint:{address}",
        "type": "network_endpoint",
        "name": address,
        "event_count": 1,
        "event_types": ["network.connection"],
    }


def _strace_endpoint(address: str) -> dict[str, object]:
    return {
        "id": f"network_endpoint:{address}",
        "type": "network_endpoint",
        "name": address,
        "event_count": 1,
        "event_types": ["network.connection"],
    }


def test_external_and_local_nodes_hold_ips_from_every_provider_process() -> None:
    """Endpoint folding is process/runtime evidence and never provider-specific."""
    nodes = [
        {"id": "agent:Claude Code", "type": "agent", "name": "Claude Code"},
        {"id": "agent:OpenAI Codex", "type": "agent", "name": "OpenAI Codex"},
        {"id": "agent:Antigravity", "type": "agent", "name": "Antigravity"},
        {"id": "agent:Cursor", "type": "agent", "name": "Cursor"},
        {"id": "process:claude", "type": "process", "name": "claude"},
        {"id": "process:codex", "type": "process", "name": "codex"},
        {"id": "process:agy", "type": "process", "name": "agy"},
        {"id": "process:cursor", "type": "process", "name": "cursor"},
        _endpoint("20.27.177.113:443"),
        _endpoint("172.217.113.4:443"),
        _strace_endpoint("8.8.8.8:443"),
        _endpoint("104.18.25.193:443"),
        _endpoint("13.107.42.14:443"),
        _endpoint("127.0.0.1:9"),
        _endpoint("localhost:11434"),
    ]
    edges = [
        {"id": "claude-net", "source": "process:claude", "target": "endpoint:20.27.177.113:443", "relation": "CONNECTED_TO", "count": 1},
        {"id": "codex-net", "source": "process:codex", "target": "endpoint:172.217.113.4:443", "relation": "CONNECTED_TO", "count": 1},
        {"id": "agy-net", "source": "process:agy", "target": "network_endpoint:8.8.8.8:443", "relation": "CONNECTED_TO", "count": 1},
        {"id": "cursor-net", "source": "process:cursor", "target": "endpoint:13.107.42.14:443", "relation": "CONNECTED_TO", "count": 1},
        {"id": "cursor-loop", "source": "process:cursor", "target": "endpoint:127.0.0.1:9", "relation": "CONNECTED_TO", "count": 1},
        {"id": "claude-local", "source": "process:claude", "target": "endpoint:localhost:11434", "relation": "CONNECTED_TO", "count": 1},
    ]
    graph = {"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}
    projected = project_viewer_graph(graph)
    node_by_id = {node["id"]: node for node in projected["nodes"]}
    assert node_by_id[EXTERNAL_NODE_ID]["name"] == "External"
    assert node_by_id[LOCAL_NODE_ID]["name"] == "Local endpoints"
    external_addresses = {item["address"] for item in node_by_id[EXTERNAL_NODE_ID]["attributes"]["endpoints"]}
    assert external_addresses == {"20.27.177.113:443", "172.217.113.4:443", "8.8.8.8:443", "104.18.25.193:443", "13.107.42.14:443"}
    local_addresses = {item["address"] for item in node_by_id[LOCAL_NODE_ID]["attributes"]["endpoints"]}
    assert local_addresses == {"127.0.0.1:9", "localhost:11434"}
    assert all(":" in item and item == format_endpoint_address(item) for item in external_addresses)
    leftovers = [node["id"] for node in projected["nodes"] if node.get("type") == "network_endpoint" and node.get("id") not in {EXTERNAL_NODE_ID, LOCAL_NODE_ID}]
    assert leftovers == []
    targets = {edge["target"] for edge in projected["edges"] if edge.get("relation") == "CONNECTED_TO"}
    assert targets == {EXTERNAL_NODE_ID, LOCAL_NODE_ID}


def test_one_external_node_holds_ips_from_every_provider_process() -> None:
    """Historical test ID retained; the stronger contract now also folds loopback locally."""
    test_external_and_local_nodes_hold_ips_from_every_provider_process()


def test_same_ip_port_from_two_processes_stays_on_one_external_node() -> None:
    nodes = [
        {"id": "process:claude", "type": "process", "name": "claude"},
        {"id": "process:codex", "type": "process", "name": "codex"},
        _endpoint("1.1.1.1:443"),
        {"id": "network_endpoint:1.1.1.1:443", "type": "network_endpoint", "name": "1.1.1.1:443", "event_count": 2, "event_types": ["network.connection"]},
    ]
    edges = [
        {"id": "a", "source": "process:claude", "target": "endpoint:1.1.1.1:443", "relation": "CONNECTED_TO", "count": 1},
        {"id": "b", "source": "process:codex", "target": "network_endpoint:1.1.1.1:443", "relation": "CONNECTED_TO", "count": 1},
    ]
    projected = project_viewer_graph({"nodes": nodes, "edges": edges, "node_count": 4, "edge_count": 2})
    external = [node for node in projected["nodes"] if node.get("id") == EXTERNAL_NODE_ID]
    assert len(external) == 1
    assert [item["address"] for item in external[0]["attributes"]["endpoints"]] == ["1.1.1.1:443"]
    leftover = [node["id"] for node in projected["nodes"] if node.get("type") == "network_endpoint" and node.get("id") != EXTERNAL_NODE_ID]
    assert leftover == []
    targets = {edge["target"] for edge in projected["edges"] if edge.get("relation") == "CONNECTED_TO"}
    assert targets == {EXTERNAL_NODE_ID}


def test_local_helper_keeps_ip_port_time_and_sequence() -> None:
    nodes = [{**_endpoint("127.0.0.1:50000"), "first_seen": "2026-09-07T00:00:01Z", "last_seen": "2026-09-07T00:00:02Z"}]
    edges = [{"id": "a", "source": "process:p", "target": "endpoint:127.0.0.1:50000", "relation": "CONNECTED_TO", "count": 1, "first_seen": "2026-09-07T00:00:01Z", "last_seen": "2026-09-07T00:00:02Z", "first_sequence": 10, "last_sequence": 11, "event_ids": ["net-10", "net-11"]}]
    folded_nodes, folded_edges, expansion = collapse_local_endpoints(nodes, edges)
    assert expansion is not None
    local = next(node for node in folded_nodes if node["id"] == LOCAL_NODE_ID)
    item = local["attributes"]["endpoints"][0]
    assert item["address"] == "127.0.0.1:50000"
    assert item["first_seen"] == "2026-09-07T00:00:01Z"
    assert item["last_seen"] == "2026-09-07T00:00:02Z"
    assert item["first_sequence"] == 10
    assert item["last_sequence"] == 11
    assert item["event_ids"] == ["net-10", "net-11"]
    assert folded_edges[0]["target"] == LOCAL_NODE_ID


def test_ipv6_external_address_uses_brackets() -> None:
    nodes = [_endpoint("2001:db8::1:443"), _endpoint("[2001:db8::2]:443")]
    edges = [
        {"id": "a", "source": "process:p", "target": "endpoint:2001:db8::1:443", "relation": "CONNECTED_TO", "count": 1},
        {"id": "b", "source": "process:p", "target": "endpoint:[2001:db8::2]:443", "relation": "CONNECTED_TO", "count": 1},
    ]
    folded_nodes, _, expansion = collapse_external_endpoints(nodes, edges)
    assert expansion is not None
    external = next(node for node in folded_nodes if node["id"] == EXTERNAL_NODE_ID)
    assert {item["address"] for item in external["attributes"]["endpoints"]} == {"[2001:db8::1]:443", "[2001:db8::2]:443"}


def test_endpoint_inspector_lists_recorded_ip_ports_not_just_the_cluster_name() -> None:
    source = _AGENT_PANEL_JS
    assert "kind==='network_endpoint'" in source
    assert "a.endpoints" in source
    assert "externalEndpointLine" in source
    assert "item?.address" in source
    assert "add('Address',node?.name)" in source


def test_external_inspector_lists_recorded_ip_ports_not_just_the_name() -> None:
    """Historical test ID retained; the shared endpoint inspector covers both clusters."""
    test_endpoint_inspector_lists_recorded_ip_ports_not_just_the_cluster_name()


def test_collapse_helpers_do_not_read_provider_fields() -> None:
    external_nodes = [_endpoint("1.1.1.1:443"), _endpoint("9.9.9.9:443")]
    external_edges = [
        {"id": "a", "source": "process:anything", "target": "endpoint:1.1.1.1:443", "relation": "CONNECTED_TO", "count": 1},
        {"id": "b", "source": "process:anything", "target": "endpoint:9.9.9.9:443", "relation": "CONNECTED_TO", "count": 1},
    ]
    folded_nodes, folded_edges, expansion = collapse_external_endpoints(external_nodes, external_edges)
    assert expansion is not None
    assert [node["name"] for node in folded_nodes] == ["External"]
    assert all(edge["target"] == EXTERNAL_NODE_ID for edge in folded_edges)

    local_nodes = [_endpoint("127.0.0.1:11434"), _endpoint("[::1]:8080")]
    local_edges = [
        {"id": "c", "source": "process:anything", "target": "endpoint:127.0.0.1:11434", "relation": "CONNECTED_TO", "count": 1},
        {"id": "d", "source": "process:anything", "target": "endpoint:[::1]:8080", "relation": "CONNECTED_TO", "count": 1},
    ]
    folded_nodes, folded_edges, expansion = collapse_local_endpoints(local_nodes, local_edges)
    assert expansion is not None
    assert [node["name"] for node in folded_nodes] == ["Local endpoints"]
    assert all(edge["target"] == LOCAL_NODE_ID for edge in folded_edges)


def test_collapse_helper_does_not_read_provider_fields() -> None:
    """Historical test ID retained; both local and external helpers remain provider-neutral."""
    test_collapse_helpers_do_not_read_provider_fields()
