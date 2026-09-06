"""Verification test for scripts/measure_graph_metrics.py.

Validates that the metrics extraction tool correctly evaluates the canonical
fixtures and satisfies all Section 5 requirements.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add repo root and scripts to sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from measure_graph_metrics import (
    FIXTURE_FACTORIES,
    evaluate_graph_metrics,
)


def test_metrics_tool_fixtures() -> None:
    expected_fields = [
        "graph_width",
        "graph_height",
        "aspect_ratio",
        "fit_scale",
        "edge_crossings",
        "max_edge_length",
        "p95_edge_length",
        "secondary_component_count",
        "visible_node_count",
        "visible_edge_count",
    ]

    for name, factory in FIXTURE_FACTORIES.items():
        graph = factory()
        metrics = evaluate_graph_metrics(graph)

        # Check all 10 required fields exist
        for field in expected_fields:
            assert field in metrics, f"Missing {field} in {name} metrics"

        # Check metric ranges and types
        assert metrics["graph_width"] > 0, f"Invalid width for {name}: {metrics['graph_width']}"
        assert metrics["graph_height"] > 0, f"Invalid height for {name}: {metrics['graph_height']}"
        assert metrics["aspect_ratio"] > 0, f"Invalid aspect ratio for {name}: {metrics['aspect_ratio']}"
        assert metrics["fit_scale"] > 0, f"Invalid fit scale for {name}: {metrics['fit_scale']}"
        assert metrics["edge_crossings"] >= 0, f"Invalid crossings for {name}: {metrics['edge_crossings']}"
        assert metrics["max_edge_length"] > 0, f"Invalid max edge length for {name}: {metrics['max_edge_length']}"
        assert metrics["p95_edge_length"] > 0, f"Invalid p95 edge length for {name}: {metrics['p95_edge_length']}"
        assert metrics["visible_node_count"] > 0, f"Invalid node count for {name}: {metrics['visible_node_count']}"
        assert metrics["visible_edge_count"] > 0, f"Invalid edge count for {name}: {metrics['visible_edge_count']}"

        if name == "multi-agent":
            # Multi-agent fixture baseline crossings must match tests/test_graph_edge_routing_e2e.py (73)
            assert metrics["edge_crossings"] == 73, (
                f"Multi-agent crossings ({metrics['edge_crossings']}) does not match baseline 73"
            )
            assert metrics["visible_node_count"] == 15
            assert metrics["visible_edge_count"] == 31
            assert metrics["secondary_component_count"] == 0

        elif name == "secondary-heavy":
            assert metrics["secondary_component_count"] == 10
            assert metrics["visible_node_count"] == 17
            assert metrics["visible_edge_count"] == 6

        elif name == "single-agent":
            assert metrics["visible_node_count"] == 10
            assert metrics["visible_edge_count"] == 9
            assert metrics["secondary_component_count"] == 0

    print("All fixture validations passed successfully!")


def test_artifact_before_metrics() -> None:
    artifact_path = REPO_ROOT / "artifacts" / "before-metrics.json"
    assert artifact_path.exists(), f"Artifact does not exist at {artifact_path}"

    data = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert "single-agent" in data
    assert "secondary-heavy" in data
    assert "multi-agent" in data

    multi = data["multi-agent"]
    assert multi["edge_crossings"] == 73
    assert multi["visible_node_count"] == 15
    assert multi["visible_edge_count"] == 31

    sec = data["secondary-heavy"]
    assert sec["secondary_component_count"] == 10

    single = data["single-agent"]
    assert single["visible_node_count"] == 10

    print("Artifact before-metrics.json verified successfully!")


if __name__ == "__main__":
    test_metrics_tool_fixtures()
    test_artifact_before_metrics()
