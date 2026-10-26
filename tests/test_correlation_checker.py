from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_correlation_graph.py"


def _graph(*, backend: str, unsupported: list[str], edges: list[dict] | None = None) -> dict:
    return {
        "nodes": [],
        "edges": edges or [],
        "fidelity": {
            "backend_observed": [backend],
            "claims_not_supported": unsupported,
        },
    }


def _run_checker(tmp_path: Path, graph: dict) -> subprocess.CompletedProcess[str]:
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(graph), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(_SCRIPT), str(path)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_portable_missing_process_observation_does_not_invent_correlation(tmp_path: Path) -> None:
    graph = _graph(
        backend="portable",
        unsupported=["complete_process_tree"],
    )

    result = _run_checker(tmp_path, graph)

    assert result.returncode == 0, result.stderr


def test_nonportable_missing_positive_correlation_still_fails(tmp_path: Path) -> None:
    graph = _graph(
        backend="strace",
        unsupported=["complete_process_tree"],
    )

    result = _run_checker(tmp_path, graph)

    assert result.returncode != 0
    assert "expected exactly one correlated process edge" in result.stderr


def test_multiple_correlations_always_fail_even_for_portable(tmp_path: Path) -> None:
    edge = {
        "relation": "CORRELATED_WITH_PROCESS",
        "inferred": True,
        "causal": False,
        "inference_methods": ["unique_process_cmdline_match"],
        "confidence_max": 0.8,
        "supporting_event_ids": ["event-1"],
    }
    graph = _graph(
        backend="portable",
        unsupported=["complete_process_tree"],
        edges=[edge, dict(edge)],
    )

    result = _run_checker(tmp_path, graph)

    assert result.returncode != 0
    assert "found 2" in result.stderr
