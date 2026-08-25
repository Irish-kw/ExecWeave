from __future__ import annotations

import json
from pathlib import Path

from execweave.inference_gateway import (
    append_gateway_records,
    openrouter_generation_to_events,
    openrouter_response_to_events,
    sanitize_gateway_endpoint,
)


def test_openrouter_response_preserves_requested_and_resolved_model_without_content() -> None:
    payload = {
        "id": "gen-1",
        "model": "anthropic/claude-sonnet-4.6",
        "choices": [{"message": {"content": "PRIVATE_RESPONSE"}}],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "total_tokens": 120,
            "cost": 0.0123,
            "prompt_tokens_details": {"cached_tokens": 70, "cache_write_tokens": 5},
            "completion_tokens_details": {"reasoning_tokens": 9},
        },
    }
    events = openrouter_response_to_events(
        payload,
        requested_model="openrouter/auto",
        provider_name="Anthropic",
    )
    rendered = json.dumps(events)
    relations = {event["relation"] for event in events}
    assert relations == {
        "SERVED_INFERENCE",
        "REQUESTED_MODEL",
        "ROUTED_TO_MODEL",
        "ROUTED_TO_PROVIDER",
    }
    assert "openrouter/auto" in rendered
    assert "anthropic/claude-sonnet-4.6" in rendered
    assert "PRIVATE_RESPONSE" not in rendered
    request = next(event["target"] for event in events if event["relation"] == "SERVED_INFERENCE")
    assert request["attributes"]["cost_usd"] == 0.0123
    assert request["attributes"]["cached_prompt_tokens"] == 70
    assert request["attributes"]["reasoning_tokens"] == 9


def test_openrouter_generation_metadata_is_whitelisted() -> None:
    payload = {
        "data": {
            "id": "gen-2",
            "model": "openai/gpt-5.6-sol",
            "provider_name": "OpenAI",
            "latency": 0.5,
            "generation_time": 1.2,
            "total_cost": 0.02,
            "tokens_prompt": 30,
            "tokens_completion": 40,
            "prompt": "PRIVATE_PROMPT",
            "completion": "PRIVATE_COMPLETION",
        }
    }
    events = openrouter_generation_to_events(payload)
    rendered = json.dumps(events)
    assert "PRIVATE_PROMPT" not in rendered
    assert "PRIVATE_COMPLETION" not in rendered
    assert any(event["relation"] == "ROUTED_TO_PROVIDER" for event in events)
    assert any(event["relation"] == "ROUTED_TO_MODEL" for event in events)


def test_gateway_endpoint_sanitization_strips_credentials_query_fragment() -> None:
    assert (
        sanitize_gateway_endpoint("https://user:secret@openrouter.ai/api/v1/?x=1#frag")
        == "https://openrouter.ai/api/v1"
    )


def test_gateway_sidecar_io(tmp_path: Path) -> None:
    records = openrouter_response_to_events(
        {"id": "gen-3", "model": "openai/gpt-5.6-sol", "usage": {"total_tokens": 5}},
        requested_model="openai/gpt-5.6-sol",
    )
    output = append_gateway_records(tmp_path / "gateway.jsonl", records)
    lines = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 3
    assert all(line["attributes"]["backend"] == "inference_gateway" for line in lines)
