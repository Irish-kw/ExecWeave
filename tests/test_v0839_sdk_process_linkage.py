"""v0.8.39: SDK-to-native process correlations abstain unless unique and bounded."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from execweave.correlation import _sdk_native_spawn_correlations, correlate_tool_process
from execweave.evidence_grade import grade_edge
from execweave.graph import build_execution_graph
from execweave.schema import SCHEMA_VERSION
from execweave.validate import validate_event_stream


def _entity(kind: str, ident: str, **attrs) -> dict:
    return {"type": kind, "id": ident, "name": ident, "attributes": attrs}


def _event(event_id: str, ts: str, event_type: str, relation: str,
           source=None, target=None, **attrs) -> dict:
    return {
        "schema_version": SCHEMA_VERSION, "event_id": event_id,
        "session_id": "s1", "timestamp": ts, "sequence": None,
        "event_type": event_type, "relation": relation,
        "source": source, "target": target, "attributes": attrs,
    }


def _fixture() -> list[dict]:
    session = _entity("session", "session:s1")
    agent = _entity("agent", "agent:test")
    tool = _entity("tool", "tool:create")
    sdk = {
        "framework": "openai-agents-sdk",
        "backend": "semantic",
        "evidence_source": "agents_sdk_tracing_callback",
        "sdk_trace_id": "trace_test", "sdk_span_id": "span_1",
        "tool_call_id": "tool-call:1", "sdk_host_pid": 100,
        "sdk_callback_tid": 101, "sdk_host_pid_source": "sdk_callback_self_report",
    }
    return [
        _event("start", "2026-10-17T02:00:00Z",
               "session.started", "STARTED_SESSION", agent, session, backend="strace"),
        _event("call", "2026-10-17T02:00:01Z",
               "TOOL_CALL", "REQUESTS_TOOL_CALL", agent, tool, **sdk),
        _event("spawn", "2026-10-17T02:00:01.300Z",
               "process.started", "SPAWNED",
               _entity("process", "process:s1:100", pid=100),
               _entity("process", "process:s1:200", pid=200),
               backend="strace", attribution="syscall",
               causal=True, spawn_origin_tid=101),
        _event("end", "2026-10-17T02:00:01.500Z",
               "TOOL_RESULT", "TOOL_CALL_RETURNS", agent, tool, **sdk),
        _event("finish", "2026-10-17T02:00:05Z",
               "session.finished", "FINISHED_SESSION", session, backend="strace"),
    ]


def _links(events: list[dict]) -> list[dict]:
    return _sdk_native_spawn_correlations(
        events, session_id="s1", max_window_ms=3000
    )[0]


def test_unique_sdk_host_pid_and_native_spawn_is_only_inferred(tmp_path: Path) -> None:
    events = _fixture()
    derived = _links(events)
    assert len(derived) == 1
    link = derived[0]
    assert link["source"]["id"] == "tool-call:1"
    assert link["target"]["id"] == "process:s1:200"
    assert link["attributes"]["inferred"] is True
    assert link["attributes"]["causal"] is False
    assert link["attributes"]["process_effect_verified"] is False
    assert link["attributes"]["same_callback_and_spawn_tid"] is True
    assert set(link["attributes"]["supporting_event_ids"]) == {"call", "end", "spawn"}

    start, body, end = events[0], events[1:-1], events[-1]
    for i, event in enumerate([start, *body, end], start=1):
        event["sequence"] = i
    raw = tmp_path / "raw.jsonl"
    output = tmp_path / "output.jsonl"
    raw.write_text("".join(json.dumps(e) + "\n" for e in events))
    assert validate_event_stream(raw, require_complete_session=True).valid
    result = correlate_tool_process(raw, output)
    assert result.correlated_tool_calls == 1
    assert validate_event_stream(output, require_complete_session=True).valid
    graph = build_execution_graph(output).to_dict()
    edge = next(e for e in graph["edges"] if
                e["relation"] == "CORRELATED_WITH_PROCESS" and
                e["source"] == "tool-call:1" and e["target"] == "process:s1:200")
    assert edge["inferred"] is True
    assert edge["causal"] is False
    assert grade_edge(edge).grade == "D"


def test_concurrent_sdk_spans_claiming_same_spawn_abstain() -> None:
    events = _fixture()
    second_start = deepcopy(events[1])
    second_end = deepcopy(events[3])
    second_start["event_id"] = "call2"
    second_end["event_id"] = "end2"
    for item in (second_start, second_end):
        item["attributes"]["tool_call_id"] = "tool-call:2"
        item["attributes"]["sdk_span_id"] = "span_2"
    events.extend([second_start, second_end])
    derived, considered, _, ambiguous, joined = _sdk_native_spawn_correlations(
        events, session_id="s1", max_window_ms=3000
    )
    assert considered == 2
    assert ambiguous == 2
    assert joined == 0
    assert derived == []


@pytest.mark.parametrize("change", [
    "wrong_pid", "wrong_end_pid", "missing_result", "outside_window",
    "two_spawns", "duplicate_call", "not_native", "wrong_sdk_identity",
    "tool_claim_only",
])
def test_absence_or_ambiguity_must_not_create_link(change: str) -> None:
    events = _fixture()
    if change == "wrong_pid":
        events[1]["attributes"]["sdk_host_pid"] = 999
        events[3]["attributes"]["sdk_host_pid"] = 999
    elif change == "wrong_end_pid":
        events[3]["attributes"]["sdk_host_pid"] = 999
    elif change == "missing_result":
        events.pop(3)
    elif change == "outside_window":
        events[2]["timestamp"] = "2026-10-17T02:00:04Z"
        events[3]["timestamp"] = "2026-10-17T02:00:04.500Z"
    elif change == "two_spawns":
        second = deepcopy(events[2])
        second["event_id"] = "spawn2"
        second["target"] = _entity("process", "process:s1:201", pid=201)
        events.append(second)
    elif change == "duplicate_call":
        events.append(deepcopy(events[1]))
    elif change == "not_native":
        events[2]["attributes"]["backend"] = "semantic"
    elif change == "wrong_sdk_identity":
        events[3]["attributes"]["sdk_span_id"] = "wrong"
    elif change == "tool_claim_only":
        events.pop(2)
    assert _links(events) == []


def test_failed_tool_result_does_not_fabricate_os_effect() -> None:
    events = _fixture()
    events.pop(2)
    events[2]["event_type"] = "TOOL_FAILURE"
    events[2]["relation"] = "TOOL_CALL_FAILED"
    events[2]["attributes"]["effect_attestation"] = "not_provided"
    assert _links(events) == []
