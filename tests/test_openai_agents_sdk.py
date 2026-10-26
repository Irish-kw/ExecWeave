"""Offline contract checks for SDK span-to-evidence conversion.

Only fake tracing objects are used: no API keys, networks, shell, or attack code.
"""
from __future__ import annotations

import json
from types import SimpleNamespace as NS

import pytest

from execweave.openai_agents_sdk import AgentsSDKTraceProcessor, install_agents_sdk_tracing


def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("EXECWEAVE_SESSION_ID", "sdk-fixture")
    monkeypatch.setenv("EXECWEAVE_RUN_ID", "sdk-fixture")
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(tmp_path / "semantic.jsonl"))


def _span(sid, kind, parent=None, trace="trace-fixture", error=None, **attrs):
    return NS(
        span_id=sid, trace_id=trace, parent_id=parent, error=error,
        span_data=NS(type=kind, **attrs),
    )


def _records(tmp_path):
    path = tmp_path / "semantic.jsonl"
    return [json.loads(x) for x in path.read_text().splitlines()]


def _run_trace(p, spans):
    trace = NS(trace_id="trace-fixture")
    p.on_trace_start(trace)
    for s in spans:
        p.on_span_start(s)
    for s in reversed(spans):
        p.on_span_end(s)
    p.on_trace_end(trace)


def test_semantic_spans_and_coverage(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    p = AgentsSDKTraceProcessor(capture_mode="metadata_only")
    spans = [
        _span("a1", "agent", name="Tool_Selector", tools=["execute_command", "query_NVD"]),
        _span("m1", "generation", parent="a1", model="gpt-test",
              input=[{"role": "user", "content": "PRIVATE_PROMPT"}],
              output=[{"content": "PRIVATE_RESPONSE"}]),
        _span("f1", "function", parent="a1", name="query_NVD",
              input="PRIVATE_ARGUMENTS", output="PRIVATE_RESULT"),
    ]
    _run_trace(p, spans)
    records = _records(tmp_path)
    kinds = [r["event_type"] for r in records]
    for event_type in ("AGENT_CREATED", "AGENT_STARTED", "AGENT_STOPPED",
                       "MODEL_REQUEST", "MODEL_RESPONSE", "TOOL_CALL", "TOOL_RESULT"):
        assert event_type in kinds
    coverage = [r for r in records if r["relation"] == "OBSERVATION_COVERAGE"]
    assert len(coverage) == 1
    assert coverage[0]["attributes"]["span_counts"] == {
        "agent": 1, "generation": 1, "function": 1
    }
    assert coverage[0]["attributes"]["unclosed_spans"] == 0
    assert coverage[0]["attributes"]["runtime_effects_verified"] is False
    raw = (tmp_path / "semantic.jsonl").read_text()
    assert not any(s in raw for s in ("PRIVATE_PROMPT", "PRIVATE_RESPONSE",
                                       "PRIVATE_ARGUMENTS", "PRIVATE_RESULT"))
    assert p.callback_errors == 0


def test_content_policy_redacts_hidden_and_credential_fields(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    p = AgentsSDKTraceProcessor(capture_mode="prompt_and_response")
    spans = [
        _span("a1", "agent", name="Executor"),
        _span("m1", "generation", parent="a1", model="gpt-test",
              input=[{"content": "VISIBLE_PROMPT", "api_key": "SECRET_KEY",
                      "reasoning": "INTERNAL_CHAIN"}],
              output=[{"content": "VISIBLE_RESPONSE", "token": "SECRET_TOKEN"}]),
        _span("f1", "function", parent="a1", name="safe_test_tool",
              input={"hello": "TOOL_ARG", "password": "SECRET_PASSWORD"},
              output={"result": "TOOL_RESULT"}),
    ]
    _run_trace(p, spans)
    root = tmp_path / "content"
    payload = " ".join(x.read_text() for x in root.rglob("*") if x.is_file())
    assert all(x in payload for x in ("VISIBLE_PROMPT", "VISIBLE_RESPONSE",
                                       "TOOL_ARG", "TOOL_RESULT"))
    assert all(x not in payload for x in ("SECRET_KEY", "SECRET_TOKEN",
                                         "INTERNAL_CHAIN", "SECRET_PASSWORD"))
    raw = (tmp_path / "semantic.jsonl").read_text()
    assert "SECRET_KEY" not in raw


def test_handoff_does_not_invent_received_event(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    p = AgentsSDKTraceProcessor()
    _run_trace(p, [
        _span("a1", "agent", name="Planner"),
        _span("h1", "handoff", parent="a1", from_agent="Planner", to_agent="Executor"),
    ])
    events = _records(tmp_path)
    assert sum(r["event_type"] == "MESSAGE_SENT" for r in events) == 1
    assert not any(r["event_type"] == "MESSAGE_RECEIVED" for r in events)
    sent = next(r for r in events if r["event_type"] == "MESSAGE_SENT")
    assert sent["attributes"]["receive_observed"] is False


def test_sdk_reported_tool_result_not_runtime_proof(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    p = AgentsSDKTraceProcessor()
    _run_trace(p, [
        _span("a1", "agent", name="Executor"),
        _span("t1", "function", parent="a1", name="remote_tool", output="completed"),
    ])
    result = next(r for r in _records(tmp_path) if r["event_type"] == "TOOL_RESULT")
    assert result["attributes"]["process_effect_verified"] is False
    assert result["attributes"]["effect_attestation"] == "not_provided"


def test_failed_spans_and_unattributed_activity(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    p = AgentsSDKTraceProcessor()
    _run_trace(p, [
        _span("orphan", "function", name="unknown_tool", error={"message": "SECRET_ERROR"}),
        _span("a1", "agent", name="Worker"),
        _span("m1", "generation", parent="a1", model="gpt-test",
              error={"message": "SECRET_ERROR"}),
    ])
    events = _records(tmp_path)
    assert any(e["event_type"] == "TOOL_FAILURE" for e in events)
    assert any(e["event_type"] == "MODEL_FAILURE" for e in events)
    coverage = next(e for e in events if e["relation"] == "OBSERVATION_COVERAGE")
    assert coverage["attributes"]["unattributed_spans"] == 1
    assert "SECRET_ERROR" not in (tmp_path / "semantic.jsonl").read_text()


def test_repeated_end_does_not_duplicate_and_missing_start_is_reported(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    p = AgentsSDKTraceProcessor()
    trace = NS(trace_id="trace-fixture")
    p.on_trace_start(trace)
    agent = _span("a1", "agent", name="Worker")
    p.on_span_start(agent)
    p.on_span_start(agent)
    p.on_span_end(agent)
    p.on_span_end(agent)
    p.on_span_end(_span("unknown", "function", name="missing"))
    p.on_trace_end(trace)
    events = _records(tmp_path)
    # AdapterContext emits AGENT_STARTED also for a distinct OS-process
    # correlation. That link is not a second SDK AgentSpan start.
    assert sum(e["relation"] == "AGENT_STARTED" for e in events) == 1
    assert sum(e["relation"] == "CORRELATED_WITH_PROCESS" for e in events) == 1
    assert sum(e["event_type"] == "AGENT_STOPPED" for e in events) == 1
    coverage = next(e for e in events if e["relation"] == "OBSERVATION_COVERAGE")
    assert coverage["attributes"]["span_counts"]["end_without_start"] == 1


def test_no_run_is_no_op(tmp_path, monkeypatch):
    monkeypatch.delenv("EXECWEAVE_SESSION_ID", raising=False)
    monkeypatch.delenv("EXECWEAVE_SEMANTIC_SIDECAR", raising=False)
    p = AgentsSDKTraceProcessor()
    _run_trace(p, [_span("a1", "agent", name="Worker")])
    assert not (tmp_path / "semantic.jsonl").exists()


def test_callback_errors_do_not_interrupt_sdk_and_are_counted(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    p = AgentsSDKTraceProcessor()
    p.on_span_start(NS(trace_id="trace-fixture", span_id="bad"))
    assert p.callback_errors == 1
    p.on_trace_end(NS(trace_id="trace-fixture"))
    report = next(e for e in _records(tmp_path) if e["relation"] == "OBSERVATION_COVERAGE")
    assert report["attributes"]["callback_errors"] == 1


def test_installer_requires_optional_sdk_or_registers_safely(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    try:
        import agents.tracing as sdk
    except ImportError:
        with pytest.raises(ImportError):
            install_agents_sdk_tracing()
    else:
        attached = []
        monkeypatch.setattr(sdk, "add_trace_processor", attached.append)
        processor = install_agents_sdk_tracing()
        assert attached == [processor]
        assert isinstance(processor, sdk.TracingProcessor)


def test_response_span_maps_to_model_events_without_exposing_payload(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    p = AgentsSDKTraceProcessor(capture_mode="prompt_and_response")
    response = NS(
        model="gpt-test", model_dump=lambda **_: {
            "model": "gpt-test", "output": [{"type": "reasoning", "text": "SECRET_THOUGHT"},
                                            {"type": "message", "text": "VISIBLE_REPLY"}],
        }
    )
    _run_trace(p, [
        _span("a1", "agent", name="Agent"),
        _span("response-1", "response", parent="a1",
              input="VISIBLE_QUESTION", response=response),
    ])
    records = _records(tmp_path)
    assert any(e["event_type"] == "MODEL_REQUEST" for e in records)
    assert any(e["event_type"] == "MODEL_RESPONSE" for e in records)
    result = next(e for e in records if e["event_type"] == "MODEL_RESPONSE")
    assert result["attributes"]["sdk_reported_model"] == "gpt-test"
    assert result["attributes"]["model_identity_resolved_at_end"] is False
    payload = " ".join(f.read_text() for f in (tmp_path / "content").rglob("*") if f.is_file())
    assert "VISIBLE_QUESTION" in payload
    assert "VISIBLE_REPLY" in payload
    assert "SECRET_THOUGHT" not in payload


def test_nested_task_turn_parent_chain_preserves_actual_agent_owner(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    p = AgentsSDKTraceProcessor(capture_mode="metadata_only")
    _run_trace(p, [
        _span("task-1", "task", name="Runner invocation"),
        _span("agent-1", "agent", parent="task-1", name="Selector"),
        _span("turn-1", "turn", parent="agent-1", agent_name="Selector", turn=1),
        _span("tool-1", "function", parent="turn-1", name="status"),
        _span("model-1", "response", parent="turn-1"),
    ])
    events = _records(tmp_path)
    for event_type in ("TOOL_CALL", "TOOL_RESULT", "MODEL_REQUEST", "MODEL_RESPONSE"):
        matches = [row for row in events if row["event_type"] == event_type]
        assert len(matches) == 1
        assert matches[0]["attributes"]["requesting_agent_id"] is not None
        assert matches[0]["attributes"]["requesting_agent_id"].endswith(":Selector")
    coverage = next(row for row in events if row["relation"] == "OBSERVATION_COVERAGE")
    assert coverage["attributes"]["unattributed_spans"] == 1  # task alone has no Agent owner


def test_cyclic_or_absent_sdk_parent_cannot_invent_an_agent(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    p = AgentsSDKTraceProcessor(capture_mode="metadata_only")
    _run_trace(p, [
        _span("cycle-1", "turn", parent="cycle-2", agent_name="Unverified", turn=1),
        _span("cycle-2", "task", parent="cycle-1", name="Loop"),
        _span("orphan-tool", "function", parent="cycle-1", name="status"),
    ])
    events = _records(tmp_path)
    tool = next(row for row in events if row["event_type"] == "TOOL_CALL")
    assert tool["attributes"]["requesting_agent_id"] is None
    assert not any(row["event_type"] == "AGENT_CREATED" for row in events)


def test_sdk_response_model_may_be_known_only_after_span_end(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    p = AgentsSDKTraceProcessor()
    trace = NS(trace_id="trace-fixture")
    p.on_trace_start(trace)
    agent = _span("a1", "agent", name="Worker")
    response = _span("r1", "response", parent="a1", response=None)
    p.on_span_start(agent)
    p.on_span_start(response)
    response.span_data.response = NS(model="actual-model")
    p.on_span_end(response)
    p.on_span_end(agent)
    p.on_trace_end(trace)
    events = _records(tmp_path)
    request = next(e for e in events if e["event_type"] == "MODEL_REQUEST")
    result = next(e for e in events if e["event_type"] == "MODEL_RESPONSE")
    assert request["target"]["name"] == "unknown"
    assert result["target"]["name"] == "actual-model"
    assert result["attributes"]["sdk_initial_model"] == "unknown"
    assert result["attributes"]["model_identity_resolved_at_end"] is True


def test_runner_task_turn_recorded_as_observed_without_success(tmp_path, monkeypatch):
    import hashlib

    _env(monkeypatch, tmp_path)
    p = AgentsSDKTraceProcessor()
    trace = NS(trace_id="trace-fixture", group_id="PRIVATE-GROUP-REF")
    p.on_trace_start(trace)
    agent = _span("a1", "agent", name="Worker")
    task = _span("t1", "task", parent="a1", name="Runner")
    turn = _span("u1", "turn", parent="t1", turn=2, agent_name="Worker")
    for value in (agent, task, turn):
        p.on_span_start(value)
    for value in (turn, task, agent):
        p.on_span_end(value)
    p.on_trace_end(trace)
    events = _records(tmp_path)
    assert sum(x["event_type"] == "TASK_CREATED" for x in events) >= 2
    assert any(x["relation"] == "SDK_TASK_STARTED" for x in events)
    assert any(x["relation"] == "SDK_TASK_SPAN_ENDED" for x in events)
    assert any(x["relation"] == "SDK_TURN_STARTED" for x in events)
    assert any(x["relation"] == "SDK_TURN_ENDED" for x in events)
    assert not any(x["event_type"] == "TASK_COMPLETED" for x in events)
    raw = (tmp_path / "semantic.jsonl").read_text()
    assert "PRIVATE-GROUP-REF" not in raw
    assert hashlib.sha256(b"PRIVATE-GROUP-REF").hexdigest() in raw


def test_responses_input_arrives_at_end_and_captures_truthful_source_time(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    p = AgentsSDKTraceProcessor(capture_mode="prompt_and_response")
    trace = NS(trace_id="trace-fixture")
    p.on_trace_start(trace)
    agent = _span("a1", "agent", name="Worker")
    response = _span("r1", "response", parent="a1", input=None, response=None)
    p.on_span_start(agent)
    p.on_span_start(response)
    response.span_data.input = [{"role": "user", "content": "LATE_VISIBLE_PROMPT"}]
    response.span_data.response = NS(
        model="gpt-test",
        model_dump=lambda **_: {"output": [{"type": "message", "text": "LATE_RESPONSE"}]},
    )
    p.on_span_end(response)
    p.on_span_end(agent)
    p.on_trace_end(trace)
    events = _records(tmp_path)
    requests = [e for e in events if e["event_type"] == "MODEL_REQUEST"]
    assert len(requests) == 2
    assert requests[0]["attributes"]["input_observed_at_start"] is False
    assert requests[0]["attributes"]["content_available"] is False
    assert requests[1]["attributes"]["late_request_content"] is True
    assert requests[1]["attributes"]["content_observed_at"] == "sdk_span_end"
    assert requests[1]["attributes"]["request_timestamp_not_inferred"] is True
    payload = " ".join(x.read_text() for x in (tmp_path / "content").rglob("*") if x.is_file())
    assert "LATE_VISIBLE_PROMPT" in payload
    assert "LATE_RESPONSE" in payload


def test_metadata_only_never_promotes_late_prompt_to_content(tmp_path, monkeypatch):
    _env(monkeypatch, tmp_path)
    p = AgentsSDKTraceProcessor(capture_mode="metadata_only")
    trace = NS(trace_id="trace-fixture")
    p.on_trace_start(trace)
    response = _span("r1", "response", input=None, response=None)
    p.on_span_start(response)
    response.span_data.input = "PRIVATE_LATE_PROMPT"
    p.on_span_end(response)
    p.on_trace_end(trace)
    events = _records(tmp_path)
    assert sum(x["event_type"] == "MODEL_REQUEST" for x in events) == 1
    assert "PRIVATE_LATE_PROMPT" not in (tmp_path / "semantic.jsonl").read_text()
    assert not (tmp_path / "content").exists()
