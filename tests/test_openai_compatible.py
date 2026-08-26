from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from execweave.content_store import FullFidelityContentStore
from execweave.openai_compatible import (
    response_to_events,
    sanitize_openai_compatible_endpoint,
)
from execweave.openai_compatible_cli import main as openai_compatible_cli_main
from execweave.openai_compatible_full_fidelity import (
    exchange_to_content_events,
    response_to_content_events,
)


def _read_ref(root: Path, event: dict) -> object:
    path = event["attributes"]["content_path"]
    raw = (root / path).read_text(encoding="utf-8")
    media = event["attributes"]["content_media_type"]
    return json.loads(raw) if media == "application/json" else raw


def _event(events: list[dict], relation: str) -> dict:
    return next(item for item in events if item["relation"] == relation)


def test_summary_preserves_direct_api_semantics_and_sanitizes_endpoint() -> None:
    payload = {
        "id": "resp-1",
        "model": "vendor/actual-model",
        "usage": {
            "input_tokens": 5,
            "output_tokens": 7,
            "total_tokens": 12,
            "input_tokens_details": {"cached_tokens": 2},
            "output_tokens_details": {"reasoning_tokens": 1},
        },
    }
    events = response_to_events(
        payload,
        endpoint="https://user:secret@api.example/v1?token=SECRET#frag",
        provider_name="example-provider",
        requested_model="vendor/requested-model",
        timestamp="2026-08-27T00:00:00Z",
    )

    assert {event["relation"] for event in events} == {
        "SERVED_INFERENCE",
        "REQUESTED_MODEL",
        "USED_MODEL",
    }
    assert events[0]["source"]["attributes"]["endpoint"] == "https://api.example/v1"
    assert all(event["attributes"]["backend"] == "openai_compatible_api" for event in events)
    assert all(event["attributes"]["causal"] is False for event in events)
    assert all(event["attributes"]["inferred"] is False for event in events)
    assert events[0]["attributes"]["prompt_tokens"] == 5
    assert events[0]["attributes"]["completion_tokens"] == 7
    assert events[0]["attributes"]["cached_prompt_tokens"] == 2
    assert events[0]["attributes"]["reasoning_tokens"] == 1
    assert sanitize_openai_compatible_endpoint(
        "http://user:pass@[::1]:8000/v1/?secret=NOPE#frag"
    ) == "http://[::1]:8000/v1"


def test_response_only_stores_complete_response_without_request_claim(tmp_path: Path) -> None:
    payload = {
        "id": "resp-2",
        "model": "vendor/model",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "PRIVATE_RESPONSE",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "lookup",
                                "arguments": '{"api_key":"CONTENT_NOT_REDACTED"}',
                            },
                        }
                    ],
                }
            }
        ],
    }
    events = response_to_content_events(
        payload,
        store=FullFidelityContentStore(tmp_path),
        endpoint="https://user:secret@api.example/v1?token=SECRET#frag",
        provider_name="example-provider",
        timestamp="2026-08-27T00:00:00Z",
    )

    response = _event(events, "OBSERVED_INFERENCE_RESPONSE")
    assert _read_ref(tmp_path, response) == payload
    assert "CONTENT_NOT_REDACTED" in json.dumps(
        _read_ref(tmp_path, _event(events, "OBSERVED_ASSISTANT_TOOL_CALLS"))
    )
    assert _read_ref(tmp_path, _event(events, "OBSERVED_ASSISTANT_MESSAGES"))[0][
        "content"
    ] == "PRIVATE_RESPONSE"
    assert response["attributes"]["request_observed"] is False
    assert response["attributes"]["caller_supplied_exchange"] is False
    assert response["attributes"]["wire_interception_asserted"] is False
    assert response["attributes"]["streaming_chunks_observed"] is False
    assert response["attributes"]["causal"] is False
    assert response["attributes"]["inferred"] is False

    metadata_event = _event(events, "OBSERVED_PROVIDER_METADATA")
    metadata = _read_ref(tmp_path, metadata_event)
    assert metadata["endpoint"] == "https://api.example/v1"
    assert metadata["provider_name"] == "example-provider"
    assert metadata_event["attributes"]["metadata_projection"] is True
    assert metadata_event["attributes"]["content_complete_from_source"] is False
    assert "SECRET" not in json.dumps(metadata)


def test_exchange_preserves_request_content_stream_and_responses_api_tools(tmp_path: Path) -> None:
    exchange = {
        "request": {
            "model": "vendor/requested-model",
            "instructions": "SYSTEM_CONTEXT",
            "input": [
                {"role": "user", "content": "PRIVATE_PROMPT"},
                {
                    "type": "function_call_output",
                    "call_id": "call-1",
                    "output": {"authorization": "TOOL_CONTENT_NOT_REDACTED"},
                },
            ],
            "tools": [
                {
                    "type": "function",
                    "name": "lookup",
                    "parameters": {
                        "type": "object",
                        "properties": {"api_key": {"type": "string"}},
                    },
                }
            ],
            "temperature": 0.2,
            "api_key": "REQUEST_BODY_CONTENT_NOT_REDACTED",
        },
        "response": {
            "id": "resp-3",
            "model": "vendor/actual-model",
            "output": [
                {"type": "message", "role": "assistant", "content": "FINAL"},
                {
                    "type": "function_call",
                    "call_id": "call-2",
                    "name": "lookup",
                    "arguments": '{"x":1}',
                },
            ],
        },
        "stream_chunks": [
            {"id": "chunk-1", "choices": [{"delta": {"content": "partial"}}]},
            {"id": "chunk-2", "choices": [{"delta": {"content": " response"}}]},
        ],
    }
    events = exchange_to_content_events(
        exchange,
        store=FullFidelityContentStore(tmp_path),
        endpoint="http://user:secret@localhost:8000/v1?token=NOPE#frag",
        provider_name="local-server",
        timestamp="2026-08-27T00:00:00Z",
    )

    assert _read_ref(tmp_path, _event(events, "OBSERVED_INFERENCE_REQUEST")) == exchange[
        "request"
    ]
    assert _read_ref(tmp_path, _event(events, "OBSERVED_SYSTEM_CONTEXT")) == "SYSTEM_CONTEXT"
    assert "TOOL_CONTENT_NOT_REDACTED" in json.dumps(
        _read_ref(tmp_path, _event(events, "OBSERVED_TOOL_RESULT_MESSAGES"))
    )
    assert "api_key" in json.dumps(_read_ref(tmp_path, _event(events, "OBSERVED_TOOL_DEFINITIONS")))
    config = _read_ref(tmp_path, _event(events, "OBSERVED_PROVIDER_REQUEST_CONFIG"))
    assert config["temperature"] == 0.2
    assert config["api_key"] == "REQUEST_BODY_CONTENT_NOT_REDACTED"
    assert _read_ref(tmp_path, _event(events, "OBSERVED_INFERENCE_STREAM_CHUNKS")) == exchange[
        "stream_chunks"
    ]
    assert "call-2" in json.dumps(
        _read_ref(tmp_path, _event(events, "OBSERVED_ASSISTANT_TOOL_CALLS"))
    )
    response = _event(events, "OBSERVED_INFERENCE_RESPONSE")
    assert _read_ref(tmp_path, response) == exchange["response"]
    assert response["attributes"]["request_observed"] is True
    assert response["attributes"]["caller_supplied_exchange"] is True
    assert response["attributes"]["wire_interception_asserted"] is False
    assert response["attributes"]["streaming_chunks_observed"] is True
    assert response["attributes"]["causal"] is False
    assert response["attributes"]["inferred"] is False

    metadata = _read_ref(tmp_path, _event(events, "OBSERVED_PROVIDER_METADATA"))
    assert metadata["endpoint"] == "http://localhost:8000/v1"
    assert metadata["requested_model"] == "vendor/requested-model"
    assert metadata["resolved_model"] == "vendor/actual-model"
    assert "NOPE" not in json.dumps(metadata)


def test_cli_writes_refs_without_leaking_content_or_endpoint_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sidecar = tmp_path / "direct-api.jsonl"
    exchange = {
        "request": {
            "model": "vendor/requested-model",
            "messages": [
                {"role": "user", "content": "PRIVATE_PROMPT"},
                {"role": "tool", "content": "PRIVATE_TOOL_RESULT"},
            ],
            "tools": [{"type": "function", "function": {"name": "lookup"}}],
        },
        "response": {
            "id": "resp-cli",
            "model": "vendor/actual-model",
            "choices": [{"message": {"content": "PRIVATE_FINAL"}}],
        },
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(exchange)))
    assert openai_compatible_cli_main(
        [
            "exchange",
            "--endpoint",
            "http://user:secret@localhost:8000/v1?token=SECRET#frag",
            "--provider-name",
            "local-server",
            "--sidecar",
            str(sidecar),
        ]
    ) == 0

    text = sidecar.read_text(encoding="utf-8")
    for private in (
        "PRIVATE_PROMPT",
        "PRIVATE_TOOL_RESULT",
        "PRIVATE_FINAL",
        "user:secret",
        "token=SECRET",
    ):
        assert private not in text
    records = [json.loads(line) for line in text.splitlines()]
    summary_relations = {
        record["relation"]
        for record in records
        if record["attributes"].get("backend") == "openai_compatible_api"
    }
    assert summary_relations == {"SERVED_INFERENCE", "REQUESTED_MODEL", "USED_MODEL"}
    semantic_relations = {
        record["relation"]
        for record in records
        if record["attributes"].get("backend") == "semantic"
    }
    assert {"OBSERVED_INFERENCE_REQUEST", "OBSERVED_INFERENCE_RESPONSE"}.issubset(
        semantic_relations
    )
    assert (tmp_path / "content" / "sha256").is_dir()


def test_content_store_failure_keeps_summary_fail_open(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sidecar = tmp_path / "direct-api.jsonl"

    class BrokenStore:
        def __init__(self, root: Path) -> None:
            raise OSError(f"broken store: {root}")

    monkeypatch.setattr("execweave.openai_compatible_cli.FullFidelityContentStore", BrokenStore)
    response = {
        "id": "resp-fail-open",
        "model": "vendor/model",
        "choices": [{"message": {"content": "PRIVATE_RESPONSE"}}],
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(response)))
    assert openai_compatible_cli_main(
        [
            "event",
            "--endpoint",
            "https://api.example/v1",
            "--sidecar",
            str(sidecar),
        ]
    ) == 0

    records = [json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()]
    assert {record["relation"] for record in records} == {"SERVED_INFERENCE", "USED_MODEL"}
    assert not any(record["attributes"].get("backend") == "semantic" for record in records)
