"""User-facing runtime regressions; raw evidence stays authoritative."""
from __future__ import annotations

import json
from pathlib import Path

from execweave.framework_adapters import AdapterContext, CAMELAdapter, ContentCapturePolicy
from execweave.graph import GraphAccumulator
from execweave.investigation_index import build_investigation_index
from execweave.sink import JsonlSink
from execweave.strace_backend import StraceParser, TraceRecord
from execweave.viewer_run_assessment import RUN_ASSESSMENT_JS


def test_process_exit_is_materialized_without_reclassifying_session(tmp_path: Path) -> None:
    acc = GraphAccumulator(session_id="s", source_path=tmp_path / "events.jsonl")
    process = {"id": "process:s:51", "type": "process", "name": "51",
               "attributes": {"pid": 51}}
    events = [
        {"event_id": "start", "schema_version": "0.2", "session_id": "s",
         "timestamp": "2026-10-12T00:00:00Z", "event_type": "process.started",
         "relation": "LAUNCHED", "source": {"id": "session:s", "type": "session"},
         "target": process, "attributes": {}},
        {"event_id": "exec", "schema_version": "0.2", "session_id": "s",
         "timestamp": "2026-10-12T00:00:01Z", "event_type": "process.exec",
         "relation": "EXECUTED",
         "source": {**process, "name": "python · 51"},
         "target": {"id": "executable:python", "type": "executable", "name": "python"},
         "attributes": {}},
        {"event_id": "exited", "schema_version": "0.2", "session_id": "s",
         "timestamp": "2026-10-12T00:00:02Z", "event_type": "process.exited",
         "relation": "EXITED", "source": process, "attributes": {"exit_code": 3}},
    ]
    for event in events:
        acc.apply(event)
    graph = acc.to_dict()
    node = next(n for n in graph["nodes"] if n["id"] == process["id"])
    assert node["name"] == "python · 51"
    assert node["attributes"]["exit_code"] == 3
    assert node["attributes"]["return_code"] == 3
    assert node["attributes"]["exit_observed"] is True
    assert node["attributes"]["exit_observed_at"] == "2026-10-12T00:00:02Z"
    assert "exit_code" not in next(n for n in graph["nodes"] if n["id"] == "session:s")["attributes"]


def test_strace_exec_labels_pid_without_saving_arguments(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    parser = StraceParser(session_id="s", sink=JsonlSink(path), watch_root=tmp_path,
                          command=["python", "custom.py"])
    parser.parse([
        TraceRecord(1720000000.0, 66,
                    'execve("/usr/bin/python3", ["python3", "--secret", "DO_NOT_STORE"], 0x0) = 0'),
        TraceRecord(1720000000.2, 66, "+++ exited with 3 +++"),
    ])
    raw = path.read_text(encoding="utf-8")
    assert "DO_NOT_STORE" not in raw
    events = [json.loads(line) for line in raw.splitlines()]
    exec_event = next(e for e in events if e["event_type"] == "process.exec")
    assert exec_event["source"]["name"] == "python3 · 66"
    assert exec_event["attributes"]["argument_count"] == 3
    assert next(e for e in events if e["event_type"] == "process.exited")["attributes"]["exit_code"] == 3


def test_git_ignore_is_created_only_for_execweave_directory(tmp_path: Path) -> None:
    secret_run = tmp_path / ".execweave" / "runs" / "s" / "events.jsonl"
    JsonlSink(secret_run)
    assert (tmp_path / ".execweave" / ".gitignore").read_text(encoding="utf-8") == "*\\n"
    other = tmp_path / "ordinary" / "events.jsonl"
    JsonlSink(other)
    assert not (other.parent / ".gitignore").exists()
    existing = tmp_path / ".execweave" / ".gitignore"
    existing.write_text("# custom\\n", encoding="utf-8")
    JsonlSink(tmp_path / ".execweave" / "runs" / "two" / "events.jsonl")
    assert existing.read_text(encoding="utf-8") == "# custom\\n"


def test_custom_framework_canonical_occurrences_are_indexed(tmp_path: Path) -> None:
    ctx = AdapterContext(framework="handoff", run_id="s", session_id="s",
                         sidecar=tmp_path / "semantic.jsonl", content_root=tmp_path,
                         capture_policy=ContentCapturePolicy("metadata_only"))
    class HandoffAdapter(CAMELAdapter):
        framework_name = "handoff"

    adapter = HandoffAdapter(ctx)
    sender = adapter.agent_created("eng", name="Engineer", role="engineer")
    receiver = adapter.agent_created("rev", name="Reviewer", role="reviewer")
    adapter.message("m2", sender, receiver, content="Review.")
    events = [json.loads(line) for line in (tmp_path / "semantic.jsonl").read_text(encoding="utf-8").splitlines()]
    acc = GraphAccumulator(session_id="s", source_path=tmp_path / "events.jsonl")
    for idx, e in enumerate(events):
        acc.apply({**e, "session_id": "s", "sequence": idx})
    report = build_investigation_index(acc.to_dict(), tmp_path)
    assert any(row["framework"] == "handoff" and row["phases"] == ["sent"]
               for row in report["messages"])
    assert report["inspection"]["invalid_records"] == 0


def test_handoff_reapplied_after_viewer_redraw() -> None:
    assert "new MutationObserver(schedule)" in RUN_ASSESSMENT_JS
    assert "attributeFilter:['class','data-warning']" in RUN_ASSESSMENT_JS
    assert "markedNodes.forEach" in RUN_ASSESSMENT_JS
    assert "markedEdges.forEach" in RUN_ASSESSMENT_JS
    assert "execweave-process-exit-alert" in RUN_ASSESSMENT_JS
