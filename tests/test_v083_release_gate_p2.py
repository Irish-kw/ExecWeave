from __future__ import annotations

from pathlib import Path

from execweave.anthropic import response_to_events as anthropic_response_to_events
from execweave.anthropic_full_fidelity import response_to_content_events as anthropic_content_events
from execweave.content_store import FullFidelityContentStore
from execweave.inference_gateway import (
    openrouter_generation_to_events,
    openrouter_response_to_events,
)
from execweave.openai_compatible import response_to_events as openai_response_to_events
from execweave.openai_compatible_full_fidelity import (
    response_to_content_events as openai_content_events,
)


def _relation(events: list[dict], relation: str) -> dict:
    return next(event for event in events if event["relation"] == relation)


def test_same_raw_model_name_does_not_join_unrelated_provider_domains() -> None:
    model = "shared-model-name"
    anthropic = anthropic_response_to_events(
        {"id": "anth-1", "model": model},
        endpoint="https://api.anthropic.com/v1/messages",
        timestamp="2026-08-31T00:00:00Z",
    )
    openai = openai_response_to_events(
        {"id": "oai-1", "model": model},
        endpoint="https://proxy-a.example/v1",
        provider_name="proxy-a",
        timestamp="2026-08-31T00:00:00Z",
    )
    gateway = openrouter_response_to_events(
        {"id": "gw-1", "model": model},
        endpoint="https://openrouter.ai/api/v1",
        timestamp="2026-08-31T00:00:00Z",
    )

    ids = {
        _relation(anthropic, "USED_MODEL")["target"]["id"],
        _relation(openai, "USED_MODEL")["target"]["id"],
        _relation(gateway, "ROUTED_TO_MODEL")["target"]["id"],
    }
    assert len(ids) == 3
    assert all(not model_id.startswith("model:catalog:") for model_id in ids)


def test_openai_compatible_and_gateway_model_identity_is_endpoint_scoped() -> None:
    payload = {"id": "req-1", "model": "same-model"}
    openai_a = openai_response_to_events(
        payload,
        endpoint="https://proxy-a.example/v1",
        timestamp="2026-08-31T00:00:00Z",
    )
    openai_b = openai_response_to_events(
        payload,
        endpoint="https://proxy-b.example/v1",
        timestamp="2026-08-31T00:00:00Z",
    )
    assert (
        _relation(openai_a, "USED_MODEL")["target"]["id"]
        != _relation(openai_b, "USED_MODEL")["target"]["id"]
    )

    gateway_a = openrouter_response_to_events(
        payload,
        endpoint="https://gateway-a.example/v1",
        timestamp="2026-08-31T00:00:00Z",
    )
    gateway_b = openrouter_response_to_events(
        payload,
        endpoint="https://gateway-b.example/v1",
        timestamp="2026-08-31T00:00:00Z",
    )
    assert (
        _relation(gateway_a, "ROUTED_TO_MODEL")["target"]["id"]
        != _relation(gateway_b, "ROUTED_TO_MODEL")["target"]["id"]
    )


def test_openrouter_response_and_generation_reconcile_model_within_same_endpoint() -> None:
    endpoint = "https://openrouter.ai/api/v1"
    response = openrouter_response_to_events(
        {"id": "gen-1", "model": "provider/model"},
        endpoint=endpoint,
        timestamp="2026-08-31T00:00:00Z",
    )
    generation = openrouter_generation_to_events(
        {"data": {"id": "gen-1", "model": "provider/model"}},
        endpoint=endpoint,
        timestamp="2026-08-31T00:00:01Z",
    )
    assert (
        _relation(response, "ROUTED_TO_MODEL")["target"]["id"]
        == _relation(generation, "ROUTED_TO_MODEL")["target"]["id"]
    )


def test_anthropic_idless_occurrences_are_distinct_but_semantic_and_content_align(
    tmp_path: Path,
) -> None:
    payload = {"model": "claude-test", "role": "assistant", "usage": {"input_tokens": 1}}
    endpoint = "https://api.anthropic.com/v1/messages"
    first_at = "2026-08-31T00:00:00Z"
    second_at = "2026-08-31T00:00:01Z"

    first = anthropic_response_to_events(payload, endpoint=endpoint, timestamp=first_at)
    second = anthropic_response_to_events(payload, endpoint=endpoint, timestamp=second_at)
    first_request = _relation(first, "SERVED_INFERENCE")["target"]
    second_request = _relation(second, "SERVED_INFERENCE")["target"]
    assert first_request["id"] != second_request["id"]
    assert first_request["attributes"]["request_id_source"] == "execweave_observation"

    content = anthropic_content_events(
        payload,
        store=FullFidelityContentStore(tmp_path / "anthropic"),
        endpoint=endpoint,
        timestamp=first_at,
    )
    content_request = _relation(content, "OBSERVED_INFERENCE_RESPONSE")["source"]
    assert content_request["id"] == first_request["id"]
    assert content_request["attributes"]["request_id_source"] == "execweave_observation"


def test_openai_compatible_idless_occurrences_are_distinct_but_semantic_and_content_align(
    tmp_path: Path,
) -> None:
    payload = {"model": "model-test", "usage": {"total_tokens": 1}}
    endpoint = "https://proxy.example/v1"
    first_at = "2026-08-31T00:00:00Z"
    second_at = "2026-08-31T00:00:01Z"

    first = openai_response_to_events(payload, endpoint=endpoint, timestamp=first_at)
    second = openai_response_to_events(payload, endpoint=endpoint, timestamp=second_at)
    first_request = _relation(first, "SERVED_INFERENCE")["target"]
    second_request = _relation(second, "SERVED_INFERENCE")["target"]
    assert first_request["id"] != second_request["id"]
    assert first_request["attributes"]["request_id_source"] == "execweave_observation"

    content = openai_content_events(
        payload,
        store=FullFidelityContentStore(tmp_path / "openai"),
        endpoint=endpoint,
        timestamp=first_at,
    )
    content_request = _relation(content, "OBSERVED_INFERENCE_RESPONSE")["source"]
    assert content_request["id"] == first_request["id"]
    assert content_request["attributes"]["request_id_source"] == "execweave_observation"
