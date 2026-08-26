from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from execweave.content_store import FullFidelityContentStore
from execweave.inference_gateway_cli import main as gateway_cli_main
from execweave.inference_gateway_full_fidelity import (
    litellm_callback_to_content_events,
    openrouter_exchange_to_content_events,
    openrouter_response_to_content_events,
)
from execweave.litellm_callback import ExecWeaveLiteLLMCallback
from execweave.live import run_live


def _read_ref(root: Path, event: dict) -> object:
    path = event["attributes"]["content_path"]
    raw = (root / path).read_text(encoding="utf-8")
    media = event["attributes"]["content_media_type"]
    return json.loads(raw) if media == "application/json" else raw


def _event(events: list[dict], relation: str) -> dict:
    return next(item for item in events if item["relation"] == relation)


def test_openrouter_event_stores_complete_response_and_tool_calls(tmp_path: Path) -> None:
    payload = {
        "id": "gen-1",
        "model": "anthropic/claude-sonnet-4.6",
        "choices": [
            {
                "message": {
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
        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
    }
    events = openrouter_response_to_content_events(
        payload,
        store=FullFidelityContentStore(tmp_path),
        endpoint="https://user:secret@openrouter.ai/api/v1?token=SECRET#frag",
        timestamp="2026-08-26T00:00:00Z",
    )

    response = _event(events, "OBSERVED_INFERENCE_RESPONSE")
    assert _read_ref(tmp_path, response) == payload
    assert "CONTENT_NOT_REDACTED" in json.dumps(
        _read_ref(tmp_path, _event(events, "OBSERVED_ASSISTANT_TOOL_CALLS"))
    )
    assert response["attributes"]["request_observed"] is False
    assert response["attributes"]["causal"] is False
    assert response["attributes"]["inferred"] is False
    metadata = _read_ref(tmp_path, _event(events, "OBSERVED_PROVIDER_METADATA"))
    assert metadata["endpoint"] == "https://openrouter.ai/api/v1"
    assert "SECRET" not in json.dumps(metadata)


def test_openrouter_exchange_preserves_request_tools_results_without_false_attribution(
    tmp_path: Path,
) -> None:
    exchange = {
        "request": {
            "model": "openrouter/auto",
            "messages": [
                {"role": "system", "content": "SYSTEM"},
                {"role": "user", "content": "PROMPT"},
                {
                    "role": "tool",
                    "tool_call_id": "call-1",
                    "content": {"authorization": "CONTENT_VALUE_MUST_REMAIN"},
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
            "tool_choice": "auto",
            "temperature": 0.1,
        },
        "response": {
            "id": "gen-2",
            "model": "openai/gpt-5.6-sol",
            "choices": [{"message": {"content": "FINAL"}}],
        },
    }
    events = openrouter_exchange_to_content_events(
        exchange,
        store=FullFidelityContentStore(tmp_path),
        endpoint="https://openrouter.ai/api/v1?secret=NOPE",
        timestamp="2026-08-26T00:00:00Z",
    )

    assert [event["relation"] for event in events].count("OBSERVED_PROVIDER_METADATA") == 1
    assert _read_ref(tmp_path, _event(events, "OBSERVED_INFERENCE_REQUEST")) == exchange["request"]
    assert "api_key" in json.dumps(_read_ref(tmp_path, _event(events, "OBSERVED_TOOL_DEFINITIONS")))
    assert "CONTENT_VALUE_MUST_REMAIN" in json.dumps(
        _read_ref(tmp_path, _event(events, "OBSERVED_TOOL_RESULT_MESSAGES"))
    )
    response = _event(events, "OBSERVED_INFERENCE_RESPONSE")
    assert _read_ref(tmp_path, response) == exchange["response"]
    assert response["attributes"]["caller_supplied_exchange"] is True
    assert response["attributes"]["wire_interception_asserted"] is False
    assert response["attributes"]["causal"] is False
    assert response["attributes"]["inferred"] is False


def _standard_payload() -> dict[str, object]:
    return {
        "id": "call-123",
        "status": "success",
        "call_type": "acompletion",
        "model_group": "assistant",
        "model": "azure/gpt-5",
        "model_id": "deployment-west",
        "prompt_tokens": 12,
        "completion_tokens": 8,
        "total_tokens": 20,
        "response_cost": 0.0042,
        "response_time": 0.75,
        "cache_hit": True,
        "api_base": "https://user:secret@private-provider.example/v1?token=SECRET",
        "messages": [
            {"role": "system", "content": "PRIVATE_SYSTEM_PROMPT"},
            {"role": "user", "content": "PRIVATE_PROMPT"},
            {
                "role": "tool",
                "tool_call_id": "call-a",
                "content": {"authorization": "TOOL_CONTENT_NOT_REDACTED"},
            },
        ],
        "prompt": "DIRECT_PRIVATE_PROMPT",
        "input": [{"type": "input_text", "text": "PRIVATE_INPUT"}],
        "response": {"choices": [{"message": {"content": "STANDARD_PRIVATE_RESPONSE"}}]},
        "metadata": {
            "request_id": "safe-id",
            "user_api_key_hash": "PRIVATE_KEY_HASH",
            "requester_custom_headers": {"x-secret": "PRIVATE_HEADER"},
        },
        "model_parameters": {
            "system": "PRIVATE_SYSTEM_CONFIG",
            "temperature": 0.1,
            "api_key": "MODEL_PARAM_SECRET",
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
        },
    }


def test_litellm_full_exchange_preserves_content_and_filters_metadata(tmp_path: Path) -> None:
    standard = _standard_payload()
    kwargs = {
        "standard_logging_object": standard,
        "messages": standard["messages"],
        "optional_params": {
            "temperature": 0.1,
            "tool_choice": "auto",
            "api_key": "OPTIONAL_SECRET",
            "tools": standard["model_parameters"]["tools"],
        },
        "litellm_params": {
            "api_key": "LITELLM_SECRET",
            "api_base": "https://user:pass@provider.example/v1?token=NOPE",
            "metadata": {"trace_id": "trace-safe", "authorization": "BEARER"},
        },
    }
    response = {
        "id": "resp-1",
        "model": "azure/gpt-5",
        "choices": [
            {
                "message": {
                    "content": "PRIVATE_RESPONSE_OBJECT",
                    "tool_calls": [
                        {
                            "id": "call-b",
                            "type": "function",
                            "function": {"name": "lookup", "arguments": '{"x":1}'},
                        }
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
    }
    events = litellm_callback_to_content_events(
        kwargs,
        response,
        store=FullFidelityContentStore(tmp_path),
        endpoint="http://user:secret@localhost:4000?token=SECRET",
        timestamp="2026-08-26T00:00:00Z",
    )

    assert _read_ref(tmp_path, _event(events, "OBSERVED_INFERENCE_REQUEST_PROMPT")) == standard[
        "prompt"
    ]
    assert _read_ref(tmp_path, _event(events, "OBSERVED_INFERENCE_REQUEST_INPUT")) == standard[
        "input"
    ]
    assert "TOOL_CONTENT_NOT_REDACTED" in json.dumps(
        _read_ref(tmp_path, _event(events, "OBSERVED_INFERENCE_REQUEST_MESSAGES"))
    )
    assert "api_key" in json.dumps(_read_ref(tmp_path, _event(events, "OBSERVED_TOOL_DEFINITIONS")))
    assert _read_ref(tmp_path, _event(events, "OBSERVED_INFERENCE_RESPONSE")) == response
    assert "call-b" in json.dumps(_read_ref(tmp_path, _event(events, "OBSERVED_ASSISTANT_TOOL_CALLS")))
    assert "STANDARD_PRIVATE_RESPONSE" in json.dumps(
        _read_ref(tmp_path, _event(events, "OBSERVED_STANDARD_LOGGING_RESPONSE"))
    )

    metadata_events = [
        event
        for event in events
        if event["relation"] in {"OBSERVED_PROVIDER_METADATA", "OBSERVED_PROVIDER_REQUEST_CONFIG"}
    ]
    all_metadata = "\n".join(
        json.dumps(_read_ref(tmp_path, event), sort_keys=True) for event in metadata_events
    )
    for secret in (
        "PRIVATE_KEY_HASH",
        "PRIVATE_HEADER",
        "MODEL_PARAM_SECRET",
        "OPTIONAL_SECRET",
        "LITELLM_SECRET",
        "BEARER",
    ):
        assert secret not in all_metadata
    assert "https://provider.example/v1" in all_metadata
    assert "trace-safe" in all_metadata
    assert "PRIVATE_SYSTEM_CONFIG" in all_metadata
    assert all(event["attributes"]["causal"] is False for event in events)
    assert all(event["attributes"]["inferred"] is False for event in events)


def test_litellm_callback_noop_and_content_store_failure_are_fail_open(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("EXECWEAVE_SEMANTIC_SIDECAR", raising=False)
    callback = ExecWeaveLiteLLMCallback()
    callback.log_success_event(
        {"standard_logging_object": _standard_payload()},
        {"id": "r", "private": "PRIVATE_RESPONSE"},
        None,
        datetime.now(timezone.utc),
    )
    assert list(tmp_path.iterdir()) == []

    sidecar = tmp_path / "semantic.jsonl"
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(sidecar))

    class BrokenStore:
        def __init__(self, root: Path) -> None:
            raise OSError(f"broken store: {root}")

    monkeypatch.setattr("execweave.litellm_callback.FullFidelityContentStore", BrokenStore)
    callback.log_success_event(
        {"standard_logging_object": _standard_payload()},
        {"id": "resp", "model": "azure/gpt-5"},
        None,
        datetime.now(timezone.utc),
    )
    records = [json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()]
    relations = {record["relation"] for record in records}
    assert {"SERVED_INFERENCE", "REQUESTED_MODEL", "ROUTED_TO_MODEL", "ROUTED_TO_DEPLOYMENT"}.issubset(
        relations
    )
    assert not any(record["attributes"].get("backend") == "semantic" for record in records)


def test_openrouter_cli_exchange_and_event_write_content_refs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sidecar = tmp_path / "gateway.jsonl"
    exchange = {
        "request": {
            "model": "openrouter/auto",
            "messages": [{"role": "user", "content": "PROMPT"}],
        },
        "response": {
            "id": "gen-cli",
            "model": "openai/gpt-5.6-sol",
            "choices": [{"message": {"content": "FINAL"}}],
        },
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(exchange)))
    assert gateway_cli_main(
        ["exchange", "--gateway", "openrouter", "--sidecar", str(sidecar)]
    ) == 0
    records = [json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()]
    assert any(record["relation"] == "OBSERVED_INFERENCE_REQUEST" for record in records)
    assert any(record["relation"] == "OBSERVED_INFERENCE_RESPONSE" for record in records)
    assert "PROMPT" not in sidecar.read_text(encoding="utf-8")
    assert (tmp_path / "content" / "sha256").is_dir()

    event_sidecar = tmp_path / "gateway-event.jsonl"
    response = {
        "id": "gen-event",
        "model": "openai/gpt-5.6-sol",
        "choices": [{"message": {"content": "EVENT_FINAL"}}],
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(response)))
    assert gateway_cli_main(
        ["event", "--gateway", "openrouter", "--sidecar", str(event_sidecar)]
    ) == 0
    event_records = [
        json.loads(line) for line in event_sidecar.read_text(encoding="utf-8").splitlines()
    ]
    response_edge = next(
        record for record in event_records if record["relation"] == "OBSERVED_INFERENCE_RESPONSE"
    )
    assert response_edge["attributes"]["request_observed"] is False


def test_run_live_materializes_litellm_content_reference_nodes(tmp_path: Path) -> None:
    code = r'''
from datetime import datetime, timezone
from execweave.litellm_callback import execweave_litellm_callback

execweave_litellm_callback.log_success_event(
    {
        "standard_logging_object": {
            "id": "live-full-call-1",
            "call_type": "acompletion",
            "model_group": "assistant",
            "model": "openai/gpt-5",
            "model_id": "deployment-live",
            "prompt_tokens": 4,
            "completion_tokens": 2,
            "total_tokens": 6,
            "messages": [{"role": "user", "content": "LIVE_FULL_PROMPT"}],
        }
    },
    {
        "id": "live-full-response-1",
        "model": "openai/gpt-5",
        "choices": [{"message": {"content": "LIVE_FULL_RESPONSE"}}],
    },
    None,
    datetime.now(timezone.utc),
)
'''
    result = run_live(
        [sys.executable, "-c", code],
        watch_root=tmp_path,
        output_dir=tmp_path / "litellm-live-full",
        poll_interval=0.03,
        collect_filesystem=False,
        collect_network=False,
        port=0,
        open_browser=False,
        linger_seconds=0,
    )
    assert result.return_code == 0

    sidecar_records = [
        json.loads(line)
        for line in result.semantic_sidecar.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    prompt_record = next(
        record
        for record in sidecar_records
        if record["relation"] == "OBSERVED_INFERENCE_REQUEST_MESSAGES"
    )
    prompt_path = result.semantic_sidecar.parent / prompt_record["attributes"]["content_path"]
    assert "LIVE_FULL_PROMPT" in prompt_path.read_text(encoding="utf-8")

    graph = json.loads(result.graph.read_text(encoding="utf-8"))
    observed_nodes = [node for node in graph["nodes"] if node["type"] == "observed_content"]
    assert observed_nodes
    assert any(
        node["attributes"].get("content_kind") == "inference_gateway.litellm.request_messages"
        and node["attributes"].get("path") == prompt_record["attributes"]["content_path"]
        for node in observed_nodes
    )
