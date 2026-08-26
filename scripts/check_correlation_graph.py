from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _portable_sampling_allows_no_match(graph: dict[str, Any]) -> bool:
    fidelity = graph.get("fidelity")
    if not isinstance(fidelity, dict):
        return False
    backends = fidelity.get("backend_observed")
    unsupported = fidelity.get("claims_not_supported")
    return (
        isinstance(backends, list)
        and "portable" in backends
        and isinstance(unsupported, list)
        and "complete_process_tree" in unsupported
    )


def validate_correlation_graph(graph: dict[str, Any]) -> None:
    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
    edges = [edge for edge in graph.get("edges", []) if isinstance(edge, dict)]
    inferred = [edge for edge in edges if edge.get("relation") == "CORRELATED_WITH_PROCESS"]

    if not inferred and _portable_sampling_allows_no_match(graph):
        return
    if len(inferred) != 1:
        processes = [
            {
                "id": node.get("id"),
                "name": node.get("name"),
                "attributes": node.get("attributes"),
            }
            for node in nodes
            if node.get("type") == "process"
        ]
        commands = [
            {
                "id": node.get("id"),
                "name": node.get("name"),
                "attributes": node.get("attributes"),
            }
            for node in nodes
            if node.get("type") == "command"
        ]
        raise RuntimeError(
            "expected exactly one correlated process edge, "
            f"found {len(inferred)}; commands={json.dumps(commands, sort_keys=True)}; "
            f"processes={json.dumps(processes, sort_keys=True)}"
        )
    edge = inferred[0]
    if edge.get("inferred") is not True:
        raise RuntimeError("correlation edge is not marked inferred=true")
    if edge.get("causal") is not False:
        raise RuntimeError("correlation edge must remain causal=false")
    if not edge.get("inference_methods"):
        raise RuntimeError("correlation edge is missing inference method")
    confidence = edge.get("confidence_max")
    if not isinstance(confidence, (int, float)) or confidence < 0.8:
        raise RuntimeError("correlation edge is missing a conservative confidence score")
    if not edge.get("supporting_event_ids"):
        raise RuntimeError("correlation edge is missing supporting event IDs")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify conservative Tool-to-Process correlation")
    parser.add_argument("graph", type=Path)
    args = parser.parse_args()
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    if not isinstance(graph, dict):
        raise RuntimeError("graph must be a JSON object")
    validate_correlation_graph(graph)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
