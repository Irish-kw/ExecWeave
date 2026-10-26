from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the semantic telemetry CI graph")
    parser.add_argument("graph", type=Path)
    args = parser.parse_args()

    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    nodes = {node["id"]: node for node in graph.get("nodes", []) if isinstance(node, dict)}
    edges = [edge for edge in graph.get("edges", []) if isinstance(edge, dict)]
    node_types = {node.get("type") for node in nodes.values()}
    relations = {edge.get("relation") for edge in edges}

    required_types = {"agent", "tool", "mcp_server", "process"}
    if not required_types.issubset(node_types):
        raise RuntimeError(f"missing semantic node types: {sorted(required_types - node_types)}")
    required_relations = {"CALLED_TOOL", "SPAWNED_PROCESS", "CALLED_MCP"}
    if not required_relations.issubset(relations):
        raise RuntimeError(f"missing semantic relations: {sorted(required_relations - relations)}")

    spawned = [edge for edge in edges if edge.get("relation") == "SPAWNED_PROCESS"]
    if not spawned or not all(nodes.get(edge.get("target"), {}).get("type") == "process" for edge in spawned):
        raise RuntimeError("semantic process_reference did not resolve to a runtime process")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
