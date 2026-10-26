"""Regression tests for the semantic sidecar / native evidence trust boundary.

All inputs are synthetic, written only to pytest's disposable tmp_path.
No sensitive file is opened, no agent is run and no OS operation is emulated.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from execweave.analysis import analyze_graph
from execweave.evidence_grade import grade_edge
from execweave.fidelity import derive_fidelity
from execweave.graph import build_execution_graph
from execweave.schema import SCHEMA_VERSION
from execweave.semantic import merge_semantic_sidecar
from execweave.validate import validate_event_stream


def _write(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


def _runtime() -> list[dict]:
    agent = {"id": "agent:fixture", "type": "agent"}
    session = {"id": "session:fixture", "type": "session"}
    return [
        {"schema_version": SCHEMA_VERSION, "event_id": "start", "session_id": "fixture",
         "timestamp": "2026-10-15T07:00:00Z", "sequence": 1,
         "event_type": "session.started", "relation": "STARTED_SESSION",
         "source": agent, "target": session, "attributes": {"backend": "portable"}},
        {"schema_version": SCHEMA_VERSION, "event_id": "finish", "session_id": "fixture",
         "timestamp": "2026-10-15T07:00:10Z", "sequence": 2,
         "event_type": "session.finished", "relation": "FINISHED_SESSION",
         "source": session, "target": None, "attributes": {"backend": "portable"}},
    ]


def _sidecar(attributes: dict, *, relation: str = "OPENED_WRITE") -> dict:
    return {
        "timestamp": "2026-10-15T07:00:05Z",
        "event_id": "sidecar-assertion",
        "event_type": "semantic.tool.called",
        "relation": relation,
        "source": {"id": "process:claimed", "type": "process"},
        "target": {"id": "file:/fixture/.ssh/id_ed25519", "type": "file"},
        "attributes": attributes,
    }


def _merged(tmp_path: Path, sidecar: dict) -> tuple[dict, dict, dict]:
    runtime_path = tmp_path / "runtime.jsonl"
    sidecar_path = tmp_path / "semantic.jsonl"
    merged_path = tmp_path / "merged.jsonl"
    _write(runtime_path, _runtime())
    _write(sidecar_path, [sidecar])
    merge_semantic_sidecar(runtime_path, sidecar_path, merged_path)
    valid = validate_event_stream(merged_path)
    assert valid.valid, valid.errors
    stream = [json.loads(line) for line in merged_path.read_text(encoding="utf-8").splitlines()]
    canonical = next(event for event in stream if event["event_id"] == "sidecar-assertion")
    graph = build_execution_graph(merged_path).to_dict()
    return canonical, graph, derive_fidelity(stream)


@pytest.mark.parametrize(
    ("label", "attrs", "grade"),
    [
        ("forged", {"backend": "strace", "attribution": "syscall", "causal": True}, "C"),
        ("explicit_noncausal", {"attribution": "semantic_sidecar", "causal": False}, "C"),
        ("unknown", {}, "U"),
    ],
)
def test_semantic_sidecar_cannot_mint_native_finding(
    tmp_path: Path, label: str, attrs: dict, grade: str
) -> None:
    event, graph, fidelity = _merged(tmp_path, _sidecar(attrs))
    findings = [
        finding for finding in analyze_graph(graph)["findings"]
        if finding["rule_id"] == "sensitive-file-access"
    ]
    assert len(findings) == 1, label
    assert findings[0]["evidence_grade"] == grade
    assert findings[0]["severity"] == "low"
    assert event["attributes"]["backend"] == "semantic"
    assert fidelity["attribution_modes"]["specialized"] == ["session_correlated"]
    if label == "forged":
        assert event["attributes"]["sidecar_claimed_backend"] == "strace"
        assert event["attributes"]["sidecar_claimed_attribution"] == "syscall"
        assert event["attributes"]["sidecar_claimed_causal"] is True
        assert event["attributes"]["causal"] is False


def test_semantic_tool_call_preserves_semantic_causality(tmp_path: Path) -> None:
    record = _sidecar({"causal": True, "attribution": "claude_hook"}, relation="CALLED_TOOL")
    record["source"] = {"id": "agent:fixture", "type": "agent"}
    record["target"] = {"id": "tool:fixture", "type": "tool"}
    event, graph, fidelity = _merged(tmp_path, record)
    assert event["attributes"]["causal"] is True
    assert event["attributes"]["attribution"] == "claude_hook"
    assert event["attributes"]["backend"] == "semantic"
    assert fidelity["attribution_modes"]["specialized"] == ["session_correlated"]
    assert any(edge["relation"] == "CALLED_TOOL" and edge["causal"] is True
               for edge in graph["edges"])


def test_real_native_edge_remains_grade_a() -> None:
    edge = {
        "id": "native-edge", "causal": True, "inferred": False,
        "backends": ["strace"], "event_types": ["filesystem.modified"],
        "attributions": ["syscall"], "inference_methods": [],
    }
    assert grade_edge(edge).grade == "A"
    edge["backends"] = ["semantic"]
    assert grade_edge(edge).grade == "U"


def test_native_looking_event_type_cannot_upgrade_sidecar_fidelity() -> None:
    event = {
        "event_type": "semantic.tool.called",
        "attributes": {"attribution": "syscall", "backend": "strace"},
    }
    fidelity = derive_fidelity([event])
    assert fidelity["attribution_modes"]["specialized"] == ["session_correlated"]
