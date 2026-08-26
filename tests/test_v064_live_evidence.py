from __future__ import annotations

import json
import sys
from pathlib import Path

from execweave.live import _LiveState, run_live


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _runtime_records() -> list[dict[str, object]]:
    return [
        {
            "schema_version": "0.2",
            "event_id": "start",
            "session_id": "s1",
            "timestamp": "2026-08-26T00:00:00Z",
            "sequence": 1,
            "event_type": "session.started",
            "relation": "STARTED_SESSION",
            "source": {"id": "agent:test", "type": "agent", "name": "test"},
            "target": {"id": "session:s1", "type": "session", "name": "s1"},
            "attributes": {"backend": "portable", "causal": True},
        },
        {
            "schema_version": "0.2",
            "event_id": "proc",
            "session_id": "s1",
            "timestamp": "2026-08-26T00:00:01Z",
            "sequence": 2,
            "event_type": "process.started",
            "relation": "LAUNCHED",
            "source": {"id": "session:s1", "type": "session", "name": "s1"},
            "target": {
                "id": "process:s1:123",
                "type": "process",
                "name": "python",
                "attributes": {"pid": 123, "create_time": 1787702400.5},
            },
            "attributes": {"backend": "portable", "causal": True},
        },
    ]


def _semantic_record(
    event_id: str = "semantic-1",
    *,
    relation: str = "REQUESTED_TOOL_CALL",
    padding: str | None = None,
) -> dict[str, object]:
    attributes: dict[str, object] = {"causal": False}
    if padding is not None:
        attributes["padding"] = padding
    return {
        "event_id": event_id,
        "timestamp": "2026-08-26T00:00:02Z",
        "event_type": "agent.tool.requested",
        "relation": relation,
        "source": {"id": f"tool-call:{event_id}", "type": "tool_call", "name": "shell"},
        "target": {
            "id": "process-ref:123",
            "type": "process_reference",
            "attributes": {"pid": 123},
        },
        "attributes": attributes,
    }


def test_live_state_incrementally_ingests_specialized_sidecar(tmp_path: Path) -> None:
    runtime = tmp_path / "events.jsonl"
    semantic = tmp_path / "semantic.jsonl"
    _write_jsonl(runtime, _runtime_records())
    _write_jsonl(semantic, [_semantic_record()])

    state = _LiveState("s1", runtime, semantic)
    payload = state.snapshot()

    assert payload["event_count"] == 3
    assert payload["live_evidence_counts"] == {"os_runtime": 2, "specialized": 1}
    assert payload["live_specialized_provisional"] is True
    assert any(
        edge["relation"] == "REQUESTED_TOOL_CALL"
        and edge["target"] == "process:s1:123"
        for edge in payload["edges"]
    )
    assert all(edge["event_ids"] == [] for edge in payload["edges"])


def test_live_sidecar_can_arrive_before_runtime_identity_is_ready(tmp_path: Path) -> None:
    runtime = tmp_path / "events.jsonl"
    semantic = tmp_path / "semantic.jsonl"
    runtime.write_text("", encoding="utf-8")
    _write_jsonl(semantic, [_semantic_record()])
    state = _LiveState("s1", runtime, semantic)

    early = state.snapshot()
    assert early["event_count"] == 0
    assert early["live_evidence_counts"] == {"os_runtime": 0, "specialized": 0}

    _write_jsonl(runtime, _runtime_records())
    ready = state.snapshot()
    assert ready["event_count"] == 3
    assert ready["live_evidence_counts"] == {"os_runtime": 2, "specialized": 1}
    assert any(edge["relation"] == "REQUESTED_TOOL_CALL" for edge in ready["edges"])


def test_live_sidecar_buffers_incomplete_trailing_jsonl_record(tmp_path: Path) -> None:
    runtime = tmp_path / "events.jsonl"
    semantic = tmp_path / "semantic.jsonl"
    _write_jsonl(runtime, _runtime_records())
    semantic.write_text(json.dumps(_semantic_record()), encoding="utf-8")
    state = _LiveState("s1", runtime, semantic)

    incomplete = state.snapshot()
    assert incomplete["event_count"] == 2
    assert incomplete["live_evidence_counts"] == {"os_runtime": 2, "specialized": 0}

    with semantic.open("a", encoding="utf-8") as handle:
        handle.write("\n")
    completed = state.snapshot()
    assert completed["event_count"] == 3
    assert completed["live_evidence_counts"] == {"os_runtime": 2, "specialized": 1}


def test_live_sidecar_truncation_resets_provisional_materialization(tmp_path: Path) -> None:
    runtime = tmp_path / "events.jsonl"
    semantic = tmp_path / "semantic.jsonl"
    _write_jsonl(runtime, _runtime_records())
    _write_jsonl(
        semantic,
        [_semantic_record("old", relation="OLD_SPECIALIZED", padding="x" * 4096)],
    )
    state = _LiveState("s1", runtime, semantic)

    old = state.snapshot()
    assert any(edge["relation"] == "OLD_SPECIALIZED" for edge in old["edges"])

    _write_jsonl(semantic, [_semantic_record("new", relation="NEW_SPECIALIZED")])
    refreshed = state.snapshot()
    relations = {edge["relation"] for edge in refreshed["edges"]}
    assert "OLD_SPECIALIZED" not in relations
    assert "NEW_SPECIALIZED" in relations
    assert refreshed["live_evidence_counts"] == {"os_runtime": 2, "specialized": 1}


def test_run_live_exports_sidecar_and_rebuilds_final_graph_from_canonical_merge(
    tmp_path: Path,
) -> None:
    code = r'''import datetime
import json
import os
import pathlib
import time

time.sleep(0.1)
path = pathlib.Path(os.environ["EXECWEAVE_SEMANTIC_SIDECAR"])
record = {
    "event_id": "semantic-child-1",
    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
    "event_type": "agent.tool.requested",
    "relation": "REQUESTED_TOOL_CALL",
    "source": {"id": "tool-call:child", "type": "tool_call", "name": "demo"},
    "target": {"id": "resource:child", "type": "resource", "name": "demo-resource"},
    "attributes": {"causal": False},
}
path.write_text(json.dumps(record) + "\n", encoding="utf-8")
time.sleep(0.15)
'''
    result = run_live(
        [sys.executable, "-c", code],
        watch_root=tmp_path,
        output_dir=tmp_path / "live-v064",
        poll_interval=0.05,
        collect_filesystem=False,
        collect_network=False,
        port=0,
        open_browser=False,
        linger_seconds=0,
    )

    assert result.return_code == 0
    assert result.event_stream.name == "events.jsonl"
    assert result.semantic_sidecar.name == "semantic.jsonl"
    assert result.semantic_sidecar.exists()
    assert result.materialized_event_stream.name == "events.semantic.jsonl"
    assert result.materialized_event_stream.exists()

    graph = json.loads(result.graph.read_text(encoding="utf-8"))
    assert graph["source_path"].endswith("events.semantic.jsonl")
    assert any(edge["relation"] == "REQUESTED_TOOL_CALL" for edge in graph["edges"])


def test_run_live_restores_existing_semantic_sidecar_environment(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", "keep-me")
    result = run_live(
        [sys.executable, "-c", "pass"],
        watch_root=tmp_path,
        output_dir=tmp_path / "live-env",
        collect_filesystem=False,
        collect_network=False,
        port=0,
        open_browser=False,
        linger_seconds=0,
    )
    assert result.return_code == 0
    assert result.materialized_event_stream == result.event_stream
    assert not result.semantic_sidecar.exists()
    assert __import__("os").environ["EXECWEAVE_SEMANTIC_SIDECAR"] == "keep-me"
