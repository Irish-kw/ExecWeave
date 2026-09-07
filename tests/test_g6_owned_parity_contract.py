from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from acceptance.g6_runner import apply_cleanup_failures, validate_owned_evidence  # noqa: E402
from acceptance.reporting import Result, Status  # noqa: E402
from execweave.viewer_projection import project_viewer_graph  # noqa: E402


def _graph(*, create_time: float = 12.5, with_edge: bool = True) -> dict:
    process_id = f"process:4242:{int(create_time * 1_000_000)}"
    endpoint_id = "endpoint:127.0.0.1:443"
    edges = (
        [
            {
                "source": process_id,
                "target": endpoint_id,
                "relation": "CONNECTED_TO",
            }
        ]
        if with_edge
        else []
    )
    return {
        "nodes": [
            {
                "id": process_id,
                "type": "process",
                "name": "python",
                "attributes": {"pid": 4242, "create_time": create_time},
            },
            {
                "id": "file:acceptance",
                "type": "file",
                "name": "acceptance.txt",
                "attributes": {},
            },
            {
                "id": endpoint_id,
                "type": "network_endpoint",
                "name": "127.0.0.1:443",
                "attributes": {},
            },
        ],
        "edges": edges,
    }


def _live_view(graph: dict) -> dict:
    """Mirror live.py: the browser receives the viewer projection, not raw graph IDs."""
    return project_viewer_graph(graph)


def test_g6_requires_exact_pid_create_time_and_owned_network_edge() -> None:
    graph = _graph()
    process_ok, network_ok, parity_ok, _ = validate_owned_evidence(
        graph=graph,
        live_graph=_live_view(graph),
        identity={"pid": 4242, "create_time": 12.5},
    )
    assert process_ok
    assert network_ok
    assert parity_ok

    process_ok, network_ok, _, _ = validate_owned_evidence(
        graph=graph,
        live_graph=_live_view(graph),
        identity={"pid": 4242, "create_time": 13.5},
    )
    assert not process_ok
    assert not network_ok


def test_g6_endpoint_presence_without_owned_edge_is_not_network_evidence() -> None:
    graph = _graph(with_edge=False)
    process_ok, network_ok, parity_ok, _ = validate_owned_evidence(
        graph=graph,
        live_graph=_live_view(graph),
        identity={"pid": 4242, "create_time": 12.5},
    )
    assert process_ok
    assert not network_ok
    assert parity_ok


def test_g6_projected_live_identity_matches_projected_finished_identity() -> None:
    """Loopback collapse must not compare a viewer cluster ID to raw endpoint IDs."""
    graph = _graph()
    live = _live_view(graph)
    live_ids = {
        str(node.get("id") or "")
        for node in live.get("nodes", [])
        if isinstance(node, dict)
    }
    assert "viewer-cluster:local-endpoints" in live_ids
    assert "endpoint:127.0.0.1:443" not in live_ids

    process_ok, network_ok, parity_ok, detail = validate_owned_evidence(
        graph=graph,
        live_graph=live,
        identity={"pid": 4242, "create_time": 12.5},
    )
    assert process_ok
    assert network_ok
    assert parity_ok, detail
    assert "live_only=[]" in detail


def test_g6_finished_graph_must_retain_live_os_evidence() -> None:
    finished = _graph()
    live = _live_view(finished)
    live["nodes"].append(
        {"id": "file:live-only", "type": "file", "name": "live-only", "attributes": {}}
    )
    process_ok, network_ok, parity_ok, detail = validate_owned_evidence(
        graph=finished,
        live_graph=live,
        identity={"pid": 4242, "create_time": 12.5},
    )
    assert process_ok
    assert network_ok
    assert not parity_ok
    assert "file:live-only" in detail


def test_g6_cleanup_instrumentation_is_fail_closed() -> None:
    result = Result("python", "native-os-only", "EW-X", "linux")
    result.check("Cleanup", True, "initial cleanup looked successful")
    apply_cleanup_failures(result, ["browser close failed: fixture"])
    assert result.checks["Cleanup"].status == Status.FAIL
    assert result.status == Status.FAIL
