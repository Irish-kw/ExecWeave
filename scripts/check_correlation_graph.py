from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify conservative Tool-to-Process correlation")
    parser.add_argument("graph", type=Path)
    args = parser.parse_args()
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    edges = [edge for edge in graph.get("edges", []) if isinstance(edge, dict)]
    inferred = [edge for edge in edges if edge.get("relation") == "CORRELATED_WITH_PROCESS"]
    if len(inferred) != 1:
        raise RuntimeError(f"expected exactly one correlated process edge, found {len(inferred)}")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
