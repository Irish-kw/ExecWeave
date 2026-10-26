from __future__ import annotations

import json
from pathlib import Path

from execweave.codex_rollout_trace import (
    CODEX_ROLLOUT_TRACE_ROOT_ENV,
    codex_rollout_trace_environment,
    import_codex_rollout_traces,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _bundle(tmp_path: Path) -> tuple[Path, Path]:
    trace_root = tmp_path / "trace-root"
    bundle = trace_root / "trace-test-root-thread"
    payloads = bundle / "payloads"
    payloads.mkdir(parents=True)

    started = 1_788_000_000_000
    ended = started + 10_000
    _write_json(
        bundle / "manifest.json",
        {
            "schema_version": 1,
            "trace_id": "trace-test",
            "rollout_id": "rollout-test",
            "root_thread_id": "root-thread",
            "started_at_unix_ms": started,
            "raw_event_log": "trace.jsonl",
            "payloads_dir": "payloads",
        },
    )
    (bundle / "trace.jsonl").write_text(
        '{"seq":1,"event":"thread_started"}\n{"seq":2,"event":"rollout_ended"}\n',
        encoding="utf-8",
    )

    payload_values = {
        "inference-request": {"input": [{"role": "user", "content": "guess a number"}]},
        "inference-response": {"output": [{"type": "reasoning"}, {"type": "message"}]},
        "tool-invocation": {
            "name": "send_message",
            "arguments": {"agent_path": "/root/agent_b", "message": "mine is 0.731"},
        },
        "tool-result": {"status": "delivered"},
        "agent-message": {"message": "mine is 0.731"},
        "terminal-runtime": {"stdout": "731\n", "stderr": "", "exit_code": 0},
        "orphan": {"future_codex_payload": True},
    }
    raw_payloads = {}
    kinds = {
        "inference-request": {"type": "inference_request"},
        "inference-response": {"type": "inference_response"},
        "tool-invocation": {"type": "tool_invocation"},
        "tool-result": {"type": "tool_result"},
        "agent-message": {"type": "agent_result"},
        "terminal-runtime": {"type": "terminal_runtime_event"},
        "orphan": {"type": "protocol_event"},
    }
    for raw_id, value in payload_values.items():
        path = payloads / f"{raw_id}.json"
        _write_json(path, value)
        raw_payloads[raw_id] = {
            "raw_payload_id": raw_id,
            "kind": kinds[raw_id],
            "path": f"payloads/{raw_id}.json",
        }

    root_execution = {
        "started_at_unix_ms": started,
        "started_seq": 1,
        "ended_at_unix_ms": ended,
        "ended_seq": 20,
        "status": "completed",
    }
    child_execution = {
        "started_at_unix_ms": started + 1000,
        "started_seq": 3,
        "ended_at_unix_ms": ended - 1000,
        "ended_seq": 18,
        "status": "completed",
    }
    state = {
        "schema_version": 1,
        "trace_id": "trace-test",
        "rollout_id": "rollout-test",
        "started_at_unix_ms": started,
        "ended_at_unix_ms": ended,
        "status": "completed",
        "root_thread_id": "root-thread",
        "threads": {
            "root-thread": {
                "thread_id": "root-thread",
                "agent_path": "/root",
                "nickname": "root",
                "origin": {"type": "root"},
                "execution": root_execution,
                "default_model": "gpt-5.6-codex",
                "conversation_item_ids": ["reason-1"],
            },
            "child-thread": {
                "thread_id": "child-thread",
                "agent_path": "/root/agent_b",
                "nickname": "agent_b",
                "origin": {
                    "type": "spawned",
                    "parent_thread_id": "root-thread",
                    "spawn_edge_id": "edge-spawn",
                    "task_name": "agent_b",
                    "agent_role": "worker",
                },
                "execution": child_execution,
                "default_model": "gpt-5.6-codex",
                "conversation_item_ids": ["message-1"],
            },
        },
        "codex_turns": {},
        "conversation_items": {
            "reason-1": {
                "item_id": "reason-1",
                "thread_id": "root-thread",
                "codex_turn_id": "turn-root",
                "first_seen_at_unix_ms": started + 2000,
                "role": "assistant",
                "channel": "analysis",
                "kind": "reasoning",
                "agent_message": None,
                "body": {
                    "parts": [
                        {"type": "text", "text": "private reasoning text"},
                        {"type": "summary", "text": "reasoning summary"},
                        {
                            "type": "encoded",
                            "label": "encrypted_content",
                            "value": "opaque-ciphertext",
                        },
                    ]
                },
                "call_id": None,
                "produced_by": [{"type": "inference", "inference_call_id": "inf-1"}],
            },
            "message-1": {
                "item_id": "message-1",
                "thread_id": "child-thread",
                "codex_turn_id": "turn-child",
                "first_seen_at_unix_ms": started + 4000,
                "role": "user",
                "channel": None,
                "kind": "message",
                "agent_message": {"author": "/root", "recipient": "/root/agent_b"},
                "body": {"parts": [{"type": "text", "text": "mine is 0.731"}]},
                "call_id": None,
                "produced_by": [{"type": "interaction_edge", "edge_id": "edge-message"}],
            },
        },
        "inference_calls": {
            "inf-1": {
                "inference_call_id": "inf-1",
                "thread_id": "root-thread",
                "codex_turn_id": "turn-root",
                "execution": {
                    "started_at_unix_ms": started + 1500,
                    "started_seq": 4,
                    "ended_at_unix_ms": started + 3500,
                    "ended_seq": 9,
                    "status": "completed",
                },
                "model": "gpt-5.6-codex",
                "provider_name": "openai",
                "response_id": "resp-1",
                "upstream_request_id": "req-1",
                "request_item_ids": [],
                "response_item_ids": ["reason-1"],
                "tool_call_ids_started_by_response": ["tool-1"],
                "usage": {
                    "input_tokens": 100,
                    "cached_input_tokens": 10,
                    "cache_write_input_tokens": 0,
                    "output_tokens": 20,
                    "reasoning_output_tokens": 12,
                },
                "raw_request_payload_id": "inference-request",
                "raw_response_payload_id": "inference-response",
            }
        },
        "code_cells": {
            "cell-1": {
                "code_cell_id": "cell-1",
                "model_visible_call_id": "exec-call",
                "thread_id": "root-thread",
                "codex_turn_id": "turn-root",
                "source_item_id": "reason-1",
                "output_item_ids": [],
                "runtime_cell_id": "runtime-cell-1",
                "execution": {
                    "started_at_unix_ms": started + 5000,
                    "started_seq": 11,
                    "ended_at_unix_ms": started + 6000,
                    "ended_seq": 13,
                    "status": "completed",
                },
                "runtime_status": "completed",
                "initial_response_at_unix_ms": started + 5500,
                "initial_response_seq": 12,
                "yielded_at_unix_ms": None,
                "yielded_seq": None,
                "source_js": "const n = 0.731;",
                "nested_tool_call_ids": ["tool-1"],
                "wait_tool_call_ids": [],
            }
        },
        "tool_calls": {
            "tool-1": {
                "tool_call_id": "tool-1",
                "mcp_call_id": None,
                "model_visible_call_id": "call-1",
                "code_mode_runtime_tool_id": None,
                "thread_id": "root-thread",
                "started_by_codex_turn_id": "turn-root",
                "execution": {
                    "started_at_unix_ms": started + 3000,
                    "started_seq": 7,
                    "ended_at_unix_ms": started + 4500,
                    "ended_seq": 10,
                    "status": "completed",
                },
                "requester": {"type": "model"},
                "kind": {"type": "send_message"},
                "model_visible_call_item_ids": [],
                "model_visible_output_item_ids": [],
                "terminal_operation_id": "terminal-op-1",
                "summary": {
                    "type": "agent",
                    "target_agent_path": "/root/agent_b",
                    "task_name": None,
                    "message_preview": "mine is 0.731",
                },
                "raw_invocation_payload_id": "tool-invocation",
                "raw_result_payload_id": "tool-result",
                "raw_runtime_payload_ids": ["terminal-runtime"],
            }
        },
        "terminal_sessions": {},
        "terminal_operations": {
            "terminal-op-1": {
                "operation_id": "terminal-op-1",
                "terminal_id": "terminal-1",
                "tool_call_id": "tool-1",
                "kind": "exec_command",
                "execution": {
                    "started_at_unix_ms": started + 3000,
                    "started_seq": 7,
                    "ended_at_unix_ms": started + 4500,
                    "ended_seq": 10,
                    "status": "completed",
                },
                "request": {
                    "type": "exec_command",
                    "command": ["printf", "731"],
                    "display_command": "printf 731",
                    "cwd": "/repo",
                    "yield_time_ms": None,
                    "max_output_tokens": None,
                },
                "result": {
                    "exit_code": 0,
                    "stdout": "731",
                    "stderr": "",
                    "formatted_output": "731",
                    "original_token_count": 1,
                    "chunk_id": None,
                },
                "model_observations": [],
                "raw_payload_ids": ["terminal-runtime"],
            }
        },
        "compactions": {},
        "compaction_requests": {},
        "interaction_edges": {
            "edge-message": {
                "edge_id": "edge-message",
                "kind": "send_message",
                "source": {"type": "tool_call", "tool_call_id": "tool-1"},
                "target": {"type": "conversation_item", "item_id": "message-1"},
                "started_at_unix_ms": started + 3000,
                "ended_at_unix_ms": started + 4000,
                "carried_item_ids": ["message-1"],
                "carried_raw_payload_ids": ["agent-message"],
            }
        },
        "raw_payloads": raw_payloads,
    }
    _write_json(bundle / "state.json", state)
    return trace_root, bundle


def test_codex_rollout_trace_environment_is_run_scoped(tmp_path: Path) -> None:
    environment = codex_rollout_trace_environment(tmp_path / "run")
    assert environment == {
        CODEX_ROLLOUT_TRACE_ROOT_ENV: str((tmp_path / "run" / "codex-rollout-trace").resolve())
    }


def test_rollout_import_preserves_agent_messages_reasoning_and_raw_payloads(
    tmp_path: Path,
) -> None:
    trace_root, _ = _bundle(tmp_path)
    sidecar = tmp_path / "run" / "semantic.jsonl"

    result = import_codex_rollout_traces(
        trace_root=trace_root,
        semantic_sidecar=sidecar,
        codex_executable="codex-not-needed-because-state-exists",
    )

    assert result.status == "imported"
    assert result.bundle_count == 1
    assert result.reduced_bundle_count == 1
    assert result.reasoning_text_count == 1
    assert result.reasoning_summary_count == 1
    assert result.encoded_reasoning_count == 1
    assert result.agent_message_count == 1
    assert result.interaction_edge_count == 1
    assert result.tool_call_count == 1
    assert result.inference_call_count == 1
    assert result.terminal_operation_count == 1
    assert result.code_cell_count == 1
    assert result.raw_payload_count == 7

    events = [
        json.loads(line)
        for line in sidecar.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    relations = {event["relation"] for event in events}
    assert "SPAWNED_AGENT" in relations
    assert "SENT_AGENT_MESSAGE" in relations
    assert "DELIVERED_AGENT_MESSAGE" in relations
    assert "HAS_AGENT_MESSAGE_PAYLOAD" in relations
    assert "PRODUCED_REASONING_TEXT" in relations
    assert "PRODUCED_REASONING_SUMMARY" in relations
    assert "PRODUCED_ENCODED_REASONING" in relations
    assert "HAS_INFERENCE_REQUEST_PAYLOAD" in relations
    assert "HAS_INFERENCE_RESPONSE_PAYLOAD" in relations
    assert "HAS_TOOL_INPUT" in relations
    assert "HAS_TOOL_OUTPUT" in relations
    assert "HAS_TOOL_RUNTIME_PAYLOAD" in relations
    assert "STARTED_TERMINAL_OPERATION" in relations
    assert "HAS_TERMINAL_REQUEST" in relations
    assert "HAS_TERMINAL_RESULT" in relations
    assert "EXECUTED_CODE_CELL" in relations
    assert "HAS_CODE_CELL_SOURCE" in relations
    assert "HAS_RAW_CODEX_PAYLOAD" in relations

    direct = [
        event
        for event in events
        if event["relation"] == "SENT_AGENT_MESSAGE"
        and event["source"]["type"] == "agent"
        and event["target"]["type"] == "agent"
    ]
    assert len(direct) == 1
    assert direct[0]["source"]["name"] == "/root"
    assert direct[0]["target"]["name"] == "/root/agent_b"
    assert direct[0]["attributes"]["normalized_agent_to_agent"] is True

    plaintext = next(event for event in events if event["relation"] == "PRODUCED_REASONING_TEXT")
    encoded = next(event for event in events if event["relation"] == "PRODUCED_ENCODED_REASONING")
    assert plaintext["attributes"]["reasoning_representation"] == "plaintext"
    assert encoded["attributes"]["reasoning_representation"] == "encoded"
    assert encoded["attributes"]["reasoning_readable"] is False

    content_paths = [
        sidecar.parent / event["attributes"]["content_path"]
        for event in events
        if isinstance(event.get("attributes"), dict) and event["attributes"].get("content_path")
    ]
    assert content_paths
    assert all(path.is_file() for path in content_paths)


def test_rollout_import_is_fail_open_when_no_trace_exists(tmp_path: Path) -> None:
    result = import_codex_rollout_traces(
        trace_root=tmp_path / "missing",
        semantic_sidecar=tmp_path / "run" / "semantic.jsonl",
    )
    assert result.status == "no_trace_bundles"
    assert result.bundle_count == 0
