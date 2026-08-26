from __future__ import annotations

import pytest

from scripts.check_correlation_graph import validate_correlation_graph


def _graph(*, backend: str, unsupported: list[str], edges: list[dict] | None = None) -> dict:
    return {
        "nodes": [],
        "edges": edges or [],
        "fidelity": {
            "backend_observed": [backend],
            "claims_not_supported": unsupported,
        },
    }


def test_portable_missing_process_observation_does_not_invent_correlation() -> None:
    graph = _graph(
        backend="portable",
        unsupported=["complete_process_tree"],
    )

    validate_correlation_graph(graph)


def test_nonportable_missing_positive_correlation_still_fails() -> None:
    graph = _graph(
        backend="strace",
        unsupported=["complete_process_tree"],
    )

    with pytest.raises(RuntimeError, match="expected exactly one correlated process edge"):
        validate_correlation_graph(graph)


def test_multiple_correlations_always_fail_even_for_portable() -> None:
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

    with pytest.raises(RuntimeError, match="found 2"):
        validate_correlation_graph(graph)
