from __future__ import annotations

import json
from pathlib import Path

from execweave.codex_rollout_structures import enrich_codex_rollout_structures


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _execution(started: int, ended: int) -> dict:
    return {
        "started_at_unix_ms": started,
        "started_seq": 1,
        "ended_at_unix_ms": ended,
        "ended_seq": 2,
        "status": "completed",
    }


def _bundle(tmp_path: Path) -> Path:
    root = tmp_path / "trace-root"
    bundle = root / "trace-structures"
    payloads = bundle / "payloads"
    payloads.mkdir(parents=True)
    started = 1_788_000_000_000
    ended = started + 10_000

    _write(payloads / "compact-request.json", {"input": ["full history"]})
    _write(payloads / "compact-response.json", {"summary": "replacement summary"})

    state = {
        "trace_id": "trace-structures",
        "rollout_id": "rollout-structures",
        "started_at_unix_ms": started,
        "ended_at_unix_ms": ended,
        "root_thread_id": "root-thread",
        "threads": {
            "root-thread": {
                "thread_id": "root-thread",
                "agent_path": "/root",
                "nickname": "root",
                "origin": {"type": "root"},
                "execution": _execution(started, ended),
            }
        },
        "codex_turns": {
            "turn-1": {
                "codex_turn_id": "turn-1",
                "thread_id": "root-thread",
                "execution": _execution(started + 100, started + 9000),
                "input_item_ids": ["input-1"],
            }
        },
        "conversation_items": {
            "input-1": {
                "item_id": "input-1",
                "thread_id": "root-thread",
                "codex_turn_id": "turn-1",
                "first_seen_at_unix_ms": started + 100,
                "role": "user",
                "kind": "message",
            },
            "marker-1": {
                "item_id": "marker-1",
                "thread_id": "root-thread",
                "codex_turn_id": "turn-1",
                "first_seen_at_unix_ms": started + 4000,
                "role": "system",
                "kind": "compaction_marker",
            },
            "replacement-1": {
                "item_id": "replacement-1",
                "thread_id": "root-thread",
                "codex_turn_id": "turn-1",
                "first_seen_at_unix_ms": started + 5000,
                "role": "user",
                "kind": "message",
            },
        },
        "inference_calls": {
            "inf-1": {
                "inference_call_id": "inf-1",
                "thread_id": "root-thread",
                "codex_turn_id": "turn-1",
                "execution": _execution(started + 1000, started + 2000),
                "model": "gpt-5.6-codex",
            }
        },
        "tool_calls": {
            "tool-1": {
                "tool_call_id": "tool-1",
                "thread_id": "root-thread",
                "started_by_codex_turn_id": "turn-1",
                "execution": _execution(started + 2100, started + 3000),
                "kind": {"type": "exec_command"},
            }
        },
        "code_cells": {
            "cell-1": {
                "code_cell_id": "cell-1",
                "thread_id": "root-thread",
                "codex_turn_id": "turn-1",
                "execution": _execution(started + 3100, started + 3500),
            }
        },
        "terminal_operations": {
            "op-1": {
                "operation_id": "op-1",
                "terminal_id": "terminal-1",
                "tool_call_id": "tool-1",
                "kind": "exec_command",
                "execution": _execution(started + 2100, started + 3000),
            }
        },
        "terminal_sessions": {
            "terminal-1": {
                "terminal_id": "terminal-1",
                "thread_id": "root-thread",
                "created_by_operation_id": "op-1",
                "operation_ids": ["op-1"],
                "execution": _execution(started + 2100, started + 8000),
            }
        },
        "compactions": {
            "compact-1": {
                "compaction_id": "compact-1",
                "thread_id": "root-thread",
                "codex_turn_id": "turn-1",
                "installed_at_unix_ms": started + 6000,
                "marker_item_id": "marker-1",
                "request_ids": ["compact-request-1"],
                "input_item_ids": ["input-1"],
                "replacement_item_ids": ["replacement-1"],
            }
        },
        "compaction_requests": {
            "compact-request-1": {
                "compaction_request_id": "compact-request-1",
                "compaction_id": "compact-1",
                "thread_id": "root-thread",
                "codex_turn_id": "turn-1",
                "execution": _execution(started + 4000, started + 5500),
                "model": "gpt-5.6-codex",
                "provider_name": "openai",
                "raw_request_payload_id": "compact-request-payload",
                "raw_response_payload_id": "compact-response-payload",
            }
        },
        "raw_payloads": {
            "compact-request-payload": {
                "path": "payloads/compact-request.json",
                "kind": {"type": "compaction_request"},
            },
            "compact-response-payload": {
                "path": "payloads/compact-response.json",
                "kind": {"type": "compaction_response"},
            },
        },
    }
    _write(bundle / "state.json", state)
    return root


def test_codex_reduced_structures_become_first_class_graph_edges(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    sidecar = tmp_path / "run" / "semantic.jsonl"

    result = enrich_codex_rollout_structures(trace_root=root, semantic_sidecar=sidecar)

    assert result.status == "imported"
    assert result.bundle_count == 1
    assert result.turn_count == 1
    assert result.terminal_session_count == 1
    assert result.compaction_count == 1
    assert result.compaction_request_count == 1

    events = [json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()]
    relations = {event["relation"] for event in events}
    assert {
        "STARTED_AGENT_TURN",
        "TRIGGERED_AGENT_TURN",
        "OBSERVED_IN_AGENT_TURN",
        "ISSUED_INFERENCE_IN_TURN",
        "STARTED_TOOL_CALL_IN_TURN",
        "EXECUTED_CODE_CELL_IN_TURN",
        "OWNED_TERMINAL_SESSION",
        "CREATED_TERMINAL_SESSION",
        "HAS_TERMINAL_OPERATION",
        "INSTALLED_COMPACTION",
        "INSTALLED_COMPACTION_IN_TURN",
        "MARKED_BY_CONVERSATION_ITEM",
        "INPUT_TO_COMPACTION",
        "INSTALLED_REPLACEMENT_ITEM",
        "COMPUTED_BY_COMPACTION_REQUEST",
        "MADE_COMPACTION_REQUEST",
        "REQUESTED_COMPACTION_IN_TURN",
        "HAS_COMPACTION_REQUEST_PAYLOAD",
        "HAS_COMPACTION_RESPONSE_PAYLOAD",
    }.issubset(relations)

    turn = next(event for event in events if event["relation"] == "STARTED_AGENT_TURN")
    assert turn["source"]["id"] == "agent:codex:rollout:rollout-structures:thread:root-thread"
    assert turn["target"]["id"] == "agent-turn:codex:rollout-structures:turn-1"

    session = next(event for event in events if event["relation"] == "OWNED_TERMINAL_SESSION")
    assert session["target"]["id"] == "terminal-session:codex:rollout-structures:terminal-1"
    assert session["attributes"]["terminal_lifetime_distinct_from_operation"] is True

    compact = next(event for event in events if event["relation"] == "INSTALLED_COMPACTION")
    assert compact["target"]["id"] == "compaction:codex:rollout-structures:compact-1"
    assert compact["attributes"]["history_replacement_checkpoint"] is True

    payload_events = [
        event
        for event in events
        if event["relation"] in {"HAS_COMPACTION_REQUEST_PAYLOAD", "HAS_COMPACTION_RESPONSE_PAYLOAD"}
    ]
    assert len(payload_events) == 2
    for event in payload_events:
        assert "full history" not in json.dumps(event)
        assert (sidecar.parent / event["attributes"]["content_path"]).is_file()


def test_codex_structure_enricher_is_noop_without_reduced_state(tmp_path: Path) -> None:
    result = enrich_codex_rollout_structures(
        trace_root=tmp_path / "missing",
        semantic_sidecar=tmp_path / "run" / "semantic.jsonl",
    )
    assert result.status == "no_reduced_state"
    assert result.semantic_event_count == 0
