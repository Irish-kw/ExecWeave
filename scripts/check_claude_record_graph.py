from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify one-command Claude semantic graph")
    parser.add_argument("graph", type=Path)
    args = parser.parse_args()

    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
    edges = [edge for edge in graph.get("edges", []) if isinstance(edge, dict)]
    node_types = {node.get("type") for node in nodes}
    relations = {edge.get("relation") for edge in edges}

    required_types = {"agent", "tool_call", "tool", "command", "process"}
    if not required_types.issubset(node_types):
        raise RuntimeError(f"missing Claude semantic node types: {sorted(required_types - node_types)}")
    required_relations = {"REQUESTED_TOOL_CALL", "USES_TOOL", "DECLARED_COMMAND"}
    if not required_relations.issubset(relations):
        raise RuntimeError(f"missing Claude semantic relations: {sorted(required_relations - relations)}")
    if "SPAWNED_PROCESS" in relations:
        raise RuntimeError("Claude native hook graph must not invent an exact Tool-to-Process edge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
