"""Regression cases distilled from the Windows audit; no user data is committed."""
from __future__ import annotations

import io
import json
from copy import deepcopy

import pytest

from execweave.acceptance_output import prepare_acceptance_output
from execweave.codex_adapter import read_hook_payload
from execweave.conversation_records_common import history_message_key
from execweave.finalization import REQUIRED_EXPORTS, record_finalization
from execweave.graph import GraphAccumulator
from execweave.session_summary import SessionSummary
from execweave.viewer_background_files import collapse_python_cache_files, is_python_cache


@pytest.mark.parametrize("attributes,state", [
    ({"return_code": 0}, "succeeded"), ({"return_code": 1}, "failed"),
    ({"return_code": 130}, "failed"),
    ({"return_code": 130, "interrupted": True}, "interrupted"),
    ({"return_code": 0, "collector_failed": True}, "collector_failed"),
    ({"return_code": None}, "unknown"), ({"return_code": True}, "unknown"),
])
def test_terminal_outcome_is_not_recorder_status(attributes, state):
    summary = SessionSummary()
    summary.observe({"event_type": "session.finished", "attributes": attributes})
    assert summary.outcome["state"] == state
    assert summary.outcome["recorder_finished"] is True


def test_counts_include_model_runtime_sidecar_and_true_zero(tmp_path):
    accumulator = GraphAccumulator(session_id="run", source_path=tmp_path / "events.jsonl")
    for kind, attributes in [
        ("session.started", {"execweave_version": "0.8.32", "python_executable": "python"}),
        ("filesystem.modified", {}), ("MODEL_RESPONSE", {"backend": "semantic"}),
        ("model_runtime.ollama.model.loaded", {"backend": "model_runtime", "attribution": "semantic_sidecar"}),
    ]:
        accumulator.apply({"session_id": "run", "event_type": kind, "attributes": attributes})
    result = accumulator.to_dict()
    assert result["evidence_counts"] == {"os_runtime": 2, "specialized": 2}
    assert result["runtime_environment"]["python_executable"] == "python"
    assert result["session_outcome"]["state"] == "unknown"
    assert GraphAccumulator(session_id="empty", source_path=tmp_path / "empty").to_dict()["evidence_counts"] == {"os_runtime": 0, "specialized": 0}


def test_repeated_ollama_prompt_local_ordinals_are_not_same_occurrence():
    first = {"occurrence_id": "request:1", "ordinal": 0, "kind": "user_message", "text": "again"}
    second = {**first, "occurrence_id": "request:2"}
    assert history_message_key(first) != history_message_key(second)
    assert history_message_key(first) == history_message_key({**first, "timestamp": "later observation"})


@pytest.mark.parametrize("name,expected", [
    (r"file:C:\app\__pycache__\x.pyc.1234", True),
    ("file:/app/__pycache__/x.pyc.1234", True),
    ("file:/app/x.pyc", True), ("file:/app/result.csv", False),
    ("file:/app/notes__pycache__.txt", False),
])
def test_cache_detection_uses_full_identity_path(name, expected):
    assert is_python_cache({"id": name, "type": "file", "name": "basename"}) is expected


def test_cache_projection_preserves_all_evidence_and_mixed_semantics():
    files = [{"id": f"file:/app/__pycache__/{i}.pyc", "type": "file", "name": f"{i}.pyc"} for i in range(20)]
    nodes = [{"id": "process:p", "type": "process"}, *files, {"id": "file:important", "type": "file", "name": "result.csv"}]
    edges = [{"id": f"edge:{i}", "source": "process:p", "target": f["id"], "relation": "WROTE", "count": 1,
              "event_ids": [f"event:{i}"], "causal": bool(i % 2), "inferred": False} for i, f in enumerate(files)]
    before = deepcopy((nodes, edges))
    result, projected, expansion = collapse_python_cache_files(nodes, edges, None)
    assert (nodes, edges) == before
    assert len(result) == 3 and len(projected) == 1
    assert expansion["nodes"] == files and expansion["edges"] == edges
    assert projected[0]["count"] == 20
    assert len(projected[0]["event_ids"]) == 20
    assert projected[0]["causal"] is None
    assert any(n["id"] == "file:important" for n in result)


def test_metagpt_accepts_only_current_live_run_directory(tmp_path, monkeypatch):
    active = tmp_path / "active"
    active.mkdir()
    (active / "events.jsonl").write_text("recording")
    with pytest.raises(FileExistsError):
        prepare_acceptance_output(active)
    monkeypatch.setenv("EXECWEAVE_SESSION_ID", "run")
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(active / "semantic.jsonl"))
    assert prepare_acceptance_output(active) == active
    (active / "summary.json").write_text("previous run")
    with pytest.raises(FileExistsError):
        prepare_acceptance_output(active)
    assert prepare_acceptance_output(tmp_path / "new").is_dir()


def test_hook_transport_does_not_decode_using_windows_terminal_codepage():
    raw = json.dumps({"hook_event_name": "PostToolUse", "tool_response": "中文完整回覆"}, ensure_ascii=False).encode("utf-8")
    stream = io.TextIOWrapper(io.BytesIO(raw), encoding="ascii", errors="strict")
    assert read_hook_payload(stream)["tool_response"] == "中文完整回覆"


def test_bad_tool_input_does_not_erase_good_result(tmp_path, monkeypatch):
    from execweave.codex_hook_cli import main

    sidecar = tmp_path / "semantic.jsonl"
    payload = {"hook_event_name": "PostToolUse", "session_id": "run", "tool_use_id": "call-1", "tool_name": "echo",
               "tool_input": "\ud800", "tool_response": "完整回覆"}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    assert main(["--sidecar", str(sidecar), "--strict"]) == 1
    records = [json.loads(line) for line in sidecar.read_text().splitlines()]
    assert any(record["relation"] == "CONTENT_CAPTURE_FAILED" for record in records)
    outputs = [record for record in records if record["relation"] == "HAS_TOOL_OUTPUT"]
    assert len(outputs) == 1
    reference = outputs[0]["target"]["attributes"]
    assert (tmp_path / reference["path"]).read_text(encoding="utf-8") == "完整回覆"


def test_export_manifest_never_calls_missing_viewer_complete(tmp_path):
    with pytest.raises(RuntimeError, match="incomplete"):
        record_finalization(tmp_path, state="complete")
    payload = json.loads((tmp_path / "finalization.json").read_text())
    assert payload["state"] == "incomplete"
    assert set(payload["missing"]) == set(REQUIRED_EXPORTS)
    for name in REQUIRED_EXPORTS:
        (tmp_path / name).write_text("artifact", encoding="utf-8")
    result = record_finalization(tmp_path, state="complete")
    assert result["state"] == "complete" and result["missing"] == []
    assert all(len(value["sha256"]) == 64 for value in result["artifacts"].values())


def test_live_collector_error_still_exports_valid_terminal_evidence(tmp_path, monkeypatch):
    pytest.importorskip("watchdog")
    from execweave import live_core
    from execweave.schema import Entity, RuntimeEvent

    class BrokenCollector:
        def __init__(self, *, session_id, sink, **kwargs):
            self.session_id, self.sink = session_id, sink

        def run(self, command):
            self.sink.emit(RuntimeEvent.create(session_id=self.session_id, event_type="session.started", relation="STARTED_SESSION",
                           source=Entity(type="agent", id="agent:test"), target=Entity(type="session", id=f"session:{self.session_id}")))
            self.sink.emit(RuntimeEvent.create(session_id=self.session_id, event_type="session.finished", relation="FINISHED_SESSION",
                           source=Entity(type="session", id=f"session:{self.session_id}"), attributes={"return_code": 1, "collector_failed": True}))
            raise RuntimeError("collector failure after terminal evidence")

    monkeypatch.setattr(live_core, "create_collector", lambda **kwargs: BrokenCollector(**kwargs))
    with pytest.raises(RuntimeError, match="collector failure"):
        live_core.run_live(["synthetic"], watch_root=tmp_path, output_dir=tmp_path / "run", open_browser=False, linger_seconds=0)
    for name in REQUIRED_EXPORTS:
        assert (tmp_path / "run" / name).is_file()
    result = json.loads((tmp_path / "run" / "graph.json").read_text())
    assert result["session_outcome"]["state"] == "collector_failed"
    manifest = json.loads((tmp_path / "run" / "finalization.json").read_text())
    assert manifest["state"] == "complete" and manifest["error_type"] == "RuntimeError"


def test_ollama_full_archive_roundtrip_preserves_125_equal_text_exchanges(tmp_path):
    from execweave.content_store import FullFidelityContentStore
    from execweave.conversation_records import write_conversation_records
    from execweave.model_runtime_full_fidelity import runtime_exchange_to_content_events

    store = FullFidelityContentStore(tmp_path)
    accumulator = GraphAccumulator(session_id="long-run", source_path=tmp_path / "events.jsonl")
    accumulator.apply({"event_id": "start", "event_type": "session.started", "session_id": "long-run",
                       "relation": "STARTED_SESSION", "source": {"id": "agent:Ollama", "name": "Ollama", "type": "agent",
                       "attributes": {"agent_role": "root"}}, "target": {"id": "session:long-run", "type": "session"}})
    for i in range(125):
        exchange = {"request": {"model": "test", "messages": [{"role": "user", "content": "same question"}]},
                    "response": {"model": "test", "message": {"role": "assistant", "content": "same reply"}, "done": True}}
        events = runtime_exchange_to_content_events(exchange, store=store, runtime="ollama",
                 endpoint="http://localhost:11434", request_id=f"round-{i}", timestamp=f"2026-09-17T00:{i//60:02}:{i%60:02}Z")
        for j, event in enumerate(events):
            event.update(event_id=f"{i}-{j}", session_id="long-run")
            accumulator.apply(event)
    json_path, _ = write_conversation_records(accumulator.to_dict(), tmp_path)
    entries = json.loads(json_path.read_text(encoding="utf-8"))["entries"]
    previews = [entry["conversation_preview"] for entry in entries if entry.get("conversation_preview")]
    assert len(previews) == 1
    preview = previews[0]
    assert preview["message_count"] == 250 and not preview["messages_truncated"]
    messages = preview["messages"]
    assert len(messages) == 250
    assert {m["occurrence_id"] for m in messages} == {f"inference-request:ollama:round-{i}" for i in range(125)}
    for i in range(125):
        prompt, response = messages[2*i:2*i+2]
        assert prompt["text"] == "same question" and prompt["content_role"] == "ollama_request_surface"
        assert response["text"] == "same reply" and response["content_role"] == "ollama_response_surface"
        assert prompt["occurrence_id"] == response["occurrence_id"] == f"inference-request:ollama:round-{i}"


def test_collector_error_remains_primary_when_export_diagnostic_fails(tmp_path, monkeypatch):
    pytest.importorskip("watchdog")
    from execweave import live_core
    from execweave.schema import Entity, RuntimeEvent

    class BrokenCollector:
        def __init__(self, *, session_id, sink, **kwargs):
            self.session_id, self.sink = session_id, sink

        def run(self, command):
            self.sink.emit(RuntimeEvent.create(
                session_id=self.session_id,
                event_type="session.started",
                relation="STARTED_SESSION",
                source=Entity(type="agent", id="agent:test"),
                target=Entity(type="session", id=f"session:{self.session_id}"),
            ))
            self.sink.emit(RuntimeEvent.create(
                session_id=self.session_id,
                event_type="session.finished",
                relation="FINISHED_SESSION",
                source=Entity(type="session", id=f"session:{self.session_id}"),
                attributes={"return_code": 1, "collector_failed": True},
            ))
            raise RuntimeError("primary collector failure")

    def fail_conversation_export(*args, **kwargs):
        raise ValueError("secondary conversation export failure")

    monkeypatch.setattr(live_core, "create_collector", lambda **kwargs: BrokenCollector(**kwargs))
    monkeypatch.setattr(live_core, "write_conversation_records", fail_conversation_export)
    with pytest.raises(RuntimeError, match="primary collector failure") as raised:
        live_core.run_live(
            ["synthetic"],
            watch_root=tmp_path,
            output_dir=tmp_path / "run",
            open_browser=False,
            linger_seconds=0,
        )

    assert isinstance(raised.value.__cause__, ValueError)
    assert "secondary conversation export failure" in str(raised.value.__cause__)
    manifest = json.loads((tmp_path / "run" / "finalization.json").read_text())
    assert manifest["state"] == "failed"
    assert manifest["error_type"] == "RuntimeError"
