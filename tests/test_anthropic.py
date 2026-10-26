from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from execweave.anthropic import response_to_events, sanitize_anthropic_endpoint
from execweave.anthropic_cli import main as anthropic_cli_main
from execweave.anthropic_full_fidelity import exchange_to_content_events, response_to_content_events
from execweave.content_store import FullFidelityContentStore


def _event(events: list[dict], relation: str) -> dict:
    return next(item for item in events if item["relation"] == relation)


def _read_ref(root: Path, event: dict):
    path = root / event["attributes"]["content_path"]
    raw = path.read_text(encoding="utf-8")
    return json.loads(raw) if event["attributes"]["content_media_type"] == "application/json" else raw


def test_summary_usage_endpoint_identity_and_model_relations():
    payload = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-4-5",
        "stop_reason": "tool_use",
        "usage": {
            "input_tokens": 12,
            "output_tokens": 7,
            "cache_read_input_tokens": 5,
            "cache_creation_input_tokens": 3,
            "service_tier": "standard",
        },
    }
    events = response_to_events(
        payload,
        endpoint="https://user:secret@api.anthropic.com/v1/messages?key=NOPE#frag",
        requested_model="claude-sonnet-4",
        timestamp="2026-08-27T00:00:00Z",
    )
    assert {item["relation"] for item in events} == {
        "SERVED_INFERENCE",
        "REQUESTED_MODEL",
        "USED_MODEL",
    }
    assert events[0]["source"]["attributes"]["endpoint"] == "https://api.anthropic.com/v1/messages"
    assert events[0]["attributes"]["prompt_tokens"] == 12
    assert events[0]["attributes"]["completion_tokens"] == 7
    assert events[0]["attributes"]["cached_prompt_tokens"] == 5
    assert events[0]["attributes"]["cache_creation_prompt_tokens"] == 3
    assert events[0]["attributes"]["stop_reason"] == "tool_use"
    assert events[0]["attributes"]["causal"] is False
    assert events[0]["attributes"]["inferred"] is False
    other = response_to_events(payload, endpoint="https://other.example/v1/messages")
    assert events[0]["target"]["id"] != other[0]["target"]["id"]
    assert sanitize_anthropic_endpoint(
        "http://user:pass@[::1]:8000/v1/messages/?x=1#f"
    ) == "http://[::1]:8000/v1/messages"


def test_response_only_preserves_content_tool_use_and_reasoning_without_request_claim(
    tmp_path: Path,
):
    payload = {
        "id": "msg_2",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-4-5",
        "content": [
            {"type": "thinking", "thinking": "PRIVATE_REASONING", "signature": "sig"},
            {"type": "text", "text": "PRIVATE_FINAL"},
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "lookup",
                "input": {"api_key": "CONTENT_NOT_REDACTED"},
            },
        ],
        "stop_reason": "tool_use",
    }
    events = response_to_content_events(
        payload,
        store=FullFidelityContentStore(tmp_path),
        endpoint="https://user:secret@api.anthropic.com/v1/messages?token=SECRET",
        timestamp="2026-08-27T00:00:00Z",
    )
    response = _event(events, "OBSERVED_INFERENCE_RESPONSE")
    assert _read_ref(tmp_path, response) == payload
    assert _read_ref(tmp_path, _event(events, "OBSERVED_ASSISTANT_CONTENT_BLOCKS")) == payload[
        "content"
    ]
    assert "CONTENT_NOT_REDACTED" in json.dumps(
        _read_ref(tmp_path, _event(events, "OBSERVED_ASSISTANT_TOOL_CALLS"))
    )
    assert "PRIVATE_REASONING" in json.dumps(
        _read_ref(tmp_path, _event(events, "OBSERVED_ASSISTANT_REASONING_BLOCKS"))
    )
    assert response["attributes"]["request_observed"] is False
    assert response["attributes"]["caller_supplied_exchange"] is False
    assert response["attributes"]["wire_interception_asserted"] is False
    metadata = _read_ref(tmp_path, _event(events, "OBSERVED_PROVIDER_METADATA"))
    assert metadata["endpoint"] == "https://api.anthropic.com/v1/messages"
    assert "SECRET" not in json.dumps(metadata)


def test_exchange_preserves_system_tools_tool_results_config_and_stream(tmp_path: Path):
    exchange = {
        "request": {
            "model": "claude-sonnet-4",
            "max_tokens": 1024,
            "system": [{"type": "text", "text": "PRIVATE_SYSTEM"}],
            "messages": [
                {"role": "user", "content": "PRIVATE_PROMPT"},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_1",
                            "content": {"authorization": "TOOL_CONTENT_NOT_REDACTED"},
                        }
                    ],
                },
            ],
            "tools": [
                {"name": "lookup", "description": "lookup", "input_schema": {"type": "object"}}
            ],
            "thinking": {"type": "enabled", "budget_tokens": 256},
            "metadata": {"user_id": "local-user"},
        },
        "response": {
            "id": "msg_3",
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-4-5",
            "content": [{"type": "text", "text": "PRIVATE_FINAL"}],
            "stop_reason": "end_turn",
        },
        "stream_chunks": [
            {"type": "message_start", "message": {"id": "msg_3"}},
            {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "PRIVATE"}},
        ],
    }
    events = exchange_to_content_events(
        exchange,
        store=FullFidelityContentStore(tmp_path),
        endpoint="https://api.anthropic.com/v1/messages",
        timestamp="2026-08-27T00:00:00Z",
    )
    assert _read_ref(tmp_path, _event(events, "OBSERVED_INFERENCE_REQUEST")) == exchange[
        "request"
    ]
    assert _read_ref(tmp_path, _event(events, "OBSERVED_SYSTEM_CONTEXT")) == exchange["request"][
        "system"
    ]
    assert _read_ref(tmp_path, _event(events, "OBSERVED_TOOL_DEFINITIONS")) == exchange[
        "request"
    ]["tools"]
    assert "TOOL_CONTENT_NOT_REDACTED" in json.dumps(
        _read_ref(tmp_path, _event(events, "OBSERVED_TOOL_RESULT_MESSAGES"))
    )
    config = _read_ref(tmp_path, _event(events, "OBSERVED_PROVIDER_REQUEST_CONFIG"))
    assert config["max_tokens"] == 1024
    assert config["thinking"]["budget_tokens"] == 256
    assert _read_ref(tmp_path, _event(events, "OBSERVED_INFERENCE_STREAM_CHUNKS")) == exchange[
        "stream_chunks"
    ]
    response = _event(events, "OBSERVED_INFERENCE_RESPONSE")
    assert response["attributes"]["request_observed"] is True
    assert response["attributes"]["caller_supplied_exchange"] is True
    assert response["attributes"]["streaming_chunks_observed"] is True


def test_cli_sidecar_has_refs_not_private_content_and_full_fidelity_failure_is_fail_open(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    sidecar = tmp_path / "anthropic.jsonl"
    exchange = {
        "request": {
            "model": "claude-sonnet-4",
            "max_tokens": 64,
            "messages": [{"role": "user", "content": "PRIVATE_PROMPT"}],
        },
        "response": {
            "id": "msg_cli",
            "model": "claude-sonnet-4-5",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "PRIVATE_FINAL"}],
        },
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(exchange)))
    assert (
        anthropic_cli_main(
            [
                "exchange",
                "--endpoint",
                "https://user:secret@api.anthropic.com/v1/messages?token=SECRET",
                "--sidecar",
                str(sidecar),
            ]
        )
        == 0
    )
    text = sidecar.read_text(encoding="utf-8")
    for private in ("PRIVATE_PROMPT", "PRIVATE_FINAL", "user:secret", "token=SECRET"):
        assert private not in text
    records = [json.loads(line) for line in text.splitlines()]
    assert {
        r["relation"] for r in records if r["attributes"].get("backend") == "anthropic_api"
    } == {"SERVED_INFERENCE", "REQUESTED_MODEL", "USED_MODEL"}
    assert any(r["relation"] == "OBSERVED_INFERENCE_REQUEST" for r in records)

    fail_sidecar = tmp_path / "fail.jsonl"

    class BrokenStore:
        def __init__(self, root: Path) -> None:
            raise OSError(f"broken: {root}")

    monkeypatch.setattr("execweave.anthropic_cli.FullFidelityContentStore", BrokenStore)
    response = {
        "id": "msg_fail",
        "model": "claude-sonnet-4-5",
        "content": [{"type": "text", "text": "PRIVATE"}],
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(response)))
    assert (
        anthropic_cli_main(
            [
                "event",
                "--endpoint",
                "https://api.anthropic.com/v1/messages",
                "--sidecar",
                str(fail_sidecar),
            ]
        )
        == 0
    )
    failed_records = [json.loads(line) for line in fail_sidecar.read_text().splitlines()]
    assert {r["relation"] for r in failed_records} == {"SERVED_INFERENCE", "USED_MODEL"}
    assert not any(r["attributes"].get("backend") == "semantic" for r in failed_records)
