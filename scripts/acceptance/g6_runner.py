"""Post-validate G6 with exact owned-process and live/finished evidence parity."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import _python_native_acceptance_impl as impl
from acceptance.reporting import Status

_ORIGINAL_RUN_NATIVE = impl._run_native
_ORIGINAL_CHILD_PROGRAM = impl._child_program
_ORIGINAL_LIVE_GRAPH = impl._live_graph
_NETWORK_RELATIONS = frozenset({"CONNECTED_TO", "NETWORK_CONNECTED_TO"})
_RELEVANT_TYPES = frozenset({"process", "file", "network_endpoint"})


def _identity_prefix() -> str:
    return r'''
import json as _ew_json
import os as _ew_os
import psutil as _ew_psutil
from pathlib import Path as _EWPath
_ew_proc = _ew_psutil.Process(_ew_os.getpid())
_EWPath("owned-identity.json").write_text(
    _ew_json.dumps({"pid": _ew_proc.pid, "create_time": _ew_proc.create_time()}),
    encoding="utf-8",
)
'''


def _child_program(marker: str) -> str:
    return _identity_prefix() + "\n" + _ORIGINAL_CHILD_PROGRAM(marker)


def _node_id(node: dict[str, Any]) -> str | None:
    value = node.get("id")
    return value if isinstance(value, str) and value else None


def _owned_process_id(graph: dict[str, Any], identity: dict[str, Any]) -> str | None:
    try:
        wanted_pid = int(identity["pid"])
        wanted_ct = int(float(identity["create_time"]) * 1_000_000)
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    matches: list[str] = []
    for node in graph.get("nodes", []):
        if not isinstance(node, dict) or node.get("type") != "process":
            continue
        attrs = node.get("attributes")
        node_id = _node_id(node)
        if not isinstance(attrs, dict) or node_id is None:
            continue
        try:
            observed = (
                int(attrs.get("pid")),
                int(float(attrs.get("create_time")) * 1_000_000),
            )
        except (TypeError, ValueError, OverflowError):
            continue
        if observed == (wanted_pid, wanted_ct):
            matches.append(node_id)
    return matches[0] if len(matches) == 1 else None


def _has_owned_network_edge(graph: dict[str, Any], process_id: str) -> bool:
    endpoints = {
        node_id
        for node in graph.get("nodes", [])
        if isinstance(node, dict)
        and node.get("type") == "network_endpoint"
        and (node_id := _node_id(node)) is not None
    }
    return any(
        isinstance(edge, dict)
        and str(edge.get("relation") or "").upper() in _NETWORK_RELATIONS
        and edge.get("source") == process_id
        and edge.get("target") in endpoints
        for edge in graph.get("edges", [])
    )


def _relevant_node_ids(graph: dict[str, Any]) -> set[str]:
    return {
        node_id
        for node in graph.get("nodes", [])
        if isinstance(node, dict)
        and node.get("type") in _RELEVANT_TYPES
        and (node_id := _node_id(node)) is not None
    }


def validate_owned_evidence(
    *,
    graph: dict[str, Any],
    live_graph: dict[str, Any],
    identity: dict[str, Any],
) -> tuple[bool, bool, bool, str]:
    process_id = _owned_process_id(graph, identity)
    process_ok = process_id is not None
    network_ok = bool(process_id) and _has_owned_network_edge(graph, str(process_id))
    live_ids = _relevant_node_ids(live_graph)
    finished_ids = _relevant_node_ids(graph)
    parity_ok = bool(live_ids) and live_ids.issubset(finished_ids)
    detail = (
        f"owned_process={process_id or 'missing'}; "
        f"live_relevant={len(live_ids)}; finished_relevant={len(finished_ids)}"
    )
    return process_ok, network_ok, parity_ok, detail


def run_native(
    *,
    output_root: Path,
    execweave_bin: str,
    timeout: float,
):
    """Run the existing journey, then fail closed on weak ownership/parity evidence."""

    captured_live: list[dict[str, Any]] = []

    def capture_live(page: Any) -> dict[str, Any]:
        graph = _ORIGINAL_LIVE_GRAPH(page)
        captured_live.append(graph)
        return graph

    impl._child_program = _child_program
    impl._live_graph = capture_live
    try:
        result = _ORIGINAL_RUN_NATIVE(
            output_root=output_root,
            execweave_bin=execweave_bin,
            timeout=timeout,
        )
    finally:
        impl._child_program = _ORIGINAL_CHILD_PROGRAM
        impl._live_graph = _ORIGINAL_LIVE_GRAPH

    if result.status == Status.SKIP_UNAVAILABLE:
        return result

    run_root = Path(result.artifacts)
    identity_path = run_root / "workspace" / "owned-identity.json"
    graph_path = run_root / "session" / "graph.json"
    try:
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        live_graph = captured_live[-1]
        if not isinstance(identity, dict) or not isinstance(graph, dict):
            raise ValueError("owned identity or finished graph is not an object")
        process_ok, network_ok, parity_ok, detail = validate_owned_evidence(
            graph=graph,
            live_graph=live_graph,
            identity=identity,
        )
    except (OSError, ValueError, json.JSONDecodeError, IndexError) as exc:
        process_ok = network_ok = parity_ok = False
        detail = f"post-validation unavailable: {type(exc).__name__}: {exc}"

    result.check(
        "Process",
        process_ok,
        "Finished graph contains exactly one process matching the child PID/create-time identity",
        detail,
    )
    result.check(
        "Network",
        network_ok,
        "Finished graph contains a network edge sourced by the exact child PID/create-time process",
        detail,
    )
    result.check(
        "Finished viewer",
        parity_ok,
        "All live Process/File/Network node identities remain present in the finished graph after the browser clickability check",
        detail,
    )
    return result
