"""v0.8.39 SDK correlation hints must not be confused with OS verification."""
from __future__ import annotations

import json
import os
import threading
from types import SimpleNamespace as NS

from execweave.openai_agents_sdk import AgentsSDKTraceProcessor


def test_function_callbacks_expose_only_self_reported_host_context(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EXECWEAVE_SESSION_ID", "sdk-hint")
    monkeypatch.setenv("EXECWEAVE_RUN_ID", "sdk-hint")
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(tmp_path / "semantic.jsonl"))
    processor = AgentsSDKTraceProcessor(capture_mode="metadata_only")
    trace = NS(trace_id="trace-hint")
    agent = NS(trace_id="trace-hint", span_id="agent", parent_id=None,
               span_data=NS(type="agent", name="Worker", tools=["ping"]), error=None)
    func = NS(trace_id="trace-hint", span_id="function", parent_id="agent",
              span_data=NS(type="function", name="ping", input="{}", output="pong"),
              error=None)
    processor.on_trace_start(trace)
    processor.on_span_start(agent)
    processor.on_span_start(func)
    processor.on_span_end(func)
    processor.on_span_end(agent)
    processor.on_trace_end(trace)

    rows = [json.loads(x) for x in
            (tmp_path / "semantic.jsonl").read_text(encoding="utf-8").splitlines()]
    tools = [r for r in rows if r["event_type"] in {"TOOL_CALL", "TOOL_RESULT"}]
    assert len(tools) == 2
    for event in tools:
        a = event["attributes"]
        assert a["sdk_host_pid"] == os.getpid()
        assert a["sdk_callback_tid"] == threading.get_native_id()
        assert a["sdk_host_pid_source"] == "sdk_callback_self_report"
        assert a["process_effect_verified"] is False
        assert a["effect_attestation"] == "not_provided"
        assert a["sdk_trace_id"] == "trace-hint"
        assert a["sdk_span_id"] == "function"
    assert not any(r.get("relation") == "SPAWNED" for r in rows)
    assert not (tmp_path / "content").exists()
