from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from execweave.content_store import FullFidelityContentStore
from execweave.model_runtime_cli import main as model_runtime_cli_main
from execweave.model_runtime_full_fidelity import (
    runtime_exchange_to_content_events,
    runtime_response_to_content_events,
)


def _read_ref(root: Path, event: dict) -> object:
    path = event["attributes"]["content_path"]
    raw = (root / path).read_text(encoding="utf-8")
    media = event["attributes"]["content_media_type"]
    return json.loads(raw) if media == "application/json" else raw


def _event(events: list[dict], relation: str) -> dict:
    return next(item for item in events if item["relation"] == relation)


def test_ollama_event_stores_complete_response_and_tool_calls(tmp_path: Path) -> None:
    payload = {
        "model": "qwen3:4b",
        "message": {
            "role": "assistant",
            "content": "PRIVATE_FINAL",
            "thinking": "PROVIDER_EXPOSED_THOUGHT",
            "tool_calls": [
                {
                    "function": {
                        "name": "lookup",
                        "arguments": {"api_key": "CONTENT_NOT_REDACTED"},
                    }
                }
            ],
        },
        "done": True,
        "done_reason": "stop",
    }
    events = runtime_response_to_content_events(
        payload,
        store=FullFidelityContentStore(tmp_path),
        runtime="ollama",
        endpoint="http://user:secret@localhost:11434?token=SECRET#frag",
        timestamp="2026-08-27T00:00:00Z",
    )
    response = _event(events, "OBSERVED_INFERENCE_RESPONSE")
    assert _read_ref(tmp_path, response) == payload
    assert "CONTENT_NOT_REDACTED" in json.dumps(
        _read_ref(tmp_path, _event(events, "OBSERVED_ASSISTANT_TOOL_CALLS"))
    )
    assert response["attributes"]["request_observed"] is False
    assert response["attributes"]["streaming_chunks_observed"] is False
    assert response["attributes"]["causal"] is False
    assert response["attributes"]["inferred"] is False
    metadata = _read_ref(tmp_path, _event(events, "OBSERVED_PROVIDER_METADATA"))
    assert metadata["endpoint"] == "http://localhost:11434"
    assert "SECRET" not in json.dumps(metadata)


@pytest.mark.parametrize("runtime", ["ollama", "llamacpp", "vllm", "lmstudio"])
def test_runtime_exchange_preserves_request_content_and_evidence_boundary(
    runtime: str,
    tmp_path: Path,
) -> None:
    exchange = {
        "request": {
            "model": "local-model",
            "system": "SYSTEM_CONTEXT",
            "messages": [
                {"role": "user", "content": "PRIVATE_PROMPT"},
                {
                    "role": "tool",
                    "tool_call_id": "call-1",
                    "content": {"authorization": "TOOL_CONTENT_NOT_REDACTED"},
                },
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "parameters": {
                            "type": "object",
                            "properties": {"api_key": {"type": "string"}},
                        },
                    },
                }
            ],
            "temperature": 0.2,
            "tool_choice": "auto",
            "options": {"seed": 7},
        },
        "response": {
            "id": "resp-1",
            "model": "local-model",
            "choices": [
                {
                    "message": {
                        "content": "PRIVATE_RESPONSE",
                        "tool_calls": [
                            {
                                "id": "call-2",
                                "type": "function",
                                "function": {"name": "lookup", "arguments": "{\"x\":1}"},
                            }
                        ],
                    }
                }
            ],
        },
    }
    events = runtime_exchange_to_content_events(
        exchange,
        store=FullFidelityContentStore(tmp_path),
        runtime=runtime,
        endpoint="http://user:secret@localhost:8000/v1?token=NOPE#frag",
        timestamp="2026-08-27T00:00:00Z",
    )
    assert _read_ref(tmp_path, _event(events, "OBSERVED_INFERENCE_REQUEST")) == exchange["request"]
    assert _read_ref(tmp_path, _event(events, "OBSERVED_SYSTEM_CONTEXT")) == "SYSTEM_CONTEXT"
    assert "TOOL_CONTENT_NOT_REDACTED" in json.dumps(
        _read_ref(tmp_path, _event(events, "OBSERVED_TOOL_RESULT_MESSAGES"))
    )
    assert "api_key" in json.dumps(_read_ref(tmp_path, _event(events, "OBSERVED_TOOL_DEFINITIONS")))
    config = _read_ref(tmp_path, _event(events, "OBSERVED_INFERENCE_REQUEST_CONFIG"))
    assert config["temperature"] == 0.2
    assert config["tool_choice"] == "auto"
    assert config["options"] == {"seed": 7}
    response = _event(events, "OBSERVED_INFERENCE_RESPONSE")
    assert _read_ref(tmp_path, response) == exchange["response"]
    assert response["attributes"]["caller_supplied_exchange"] is True
    assert response["attributes"]["wire_interception_asserted"] is False
    assert response["attributes"]["causal"] is False
    assert response["attributes"]["inferred"] is False
    metadata = _read_ref(tmp_path, _event(events, "OBSERVED_PROVIDER_METADATA"))
    assert metadata["endpoint"] == "http://localhost:8000/v1"


def test_model_runtime_cli_event_and_exchange_write_content_refs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    event_sidecar = tmp_path / "runtime-event.jsonl"
    response = {
        "model": "qwen3:4b",
        "message": {"role": "assistant", "content": "EVENT_FINAL"},
        "done": True,
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(response)))
    assert model_runtime_cli_main(
        ["event", "--runtime", "ollama", "--sidecar", str(event_sidecar)]
    ) == 0
    event_records = [
        json.loads(line) for line in event_sidecar.read_text(encoding="utf-8").splitlines()
    ]
    response_edge = next(
        record for record in event_records if record["relation"] == "OBSERVED_INFERENCE_RESPONSE"
    )
    assert response_edge["attributes"]["request_observed"] is False
    assert "EVENT_FINAL" not in event_sidecar.read_text(encoding="utf-8")

    exchange_sidecar = tmp_path / "runtime-exchange.jsonl"
    exchange = {
        "request": {"model": "local-model", "messages": [{"role": "user", "content": "PROMPT"}]},
        "response": {
            "id": "chatcmpl-1",
            "model": "local-model",
            "choices": [{"message": {"content": "FINAL"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(exchange)))
    assert model_runtime_cli_main(
        ["exchange", "--runtime", "vllm", "--sidecar", str(exchange_sidecar)]
    ) == 0
    exchange_records = [
        json.loads(line) for line in exchange_sidecar.read_text(encoding="utf-8").splitlines()
    ]
    assert any(record["relation"] == "OBSERVED_INFERENCE_REQUEST" for record in exchange_records)
    assert any(record["relation"] == "OBSERVED_INFERENCE_RESPONSE" for record in exchange_records)
    assert "PROMPT" not in exchange_sidecar.read_text(encoding="utf-8")
    assert (tmp_path / "content" / "sha256").is_dir()


def test_full_fidelity_store_failure_keeps_semantic_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sidecar = tmp_path / "runtime.jsonl"

    class BrokenStore:
        def __init__(self, root: Path) -> None:
            raise OSError(f"broken store: {root}")

    monkeypatch.setattr("execweave.model_runtime_cli.FullFidelityContentStore", BrokenStore)
    response = {
        "model": "qwen3:4b",
        "message": {"role": "assistant", "content": "PRIVATE_RESPONSE"},
        "prompt_eval_count": 1,
        "eval_count": 2,
        "done": True,
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(response)))
    assert model_runtime_cli_main(
        ["event", "--runtime", "ollama", "--sidecar", str(sidecar)]
    ) == 0
    records = [json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()]
    assert {record["relation"] for record in records} == {"SERVED_INFERENCE", "USED_MODEL"}
    assert not any(record["attributes"].get("backend") == "semantic" for record in records)
