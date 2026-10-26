from __future__ import annotations

import json

from execweave.inference_gateway import (
    litellm_response_to_events,
    openrouter_generation_to_events,
    openrouter_response_to_events,
)
from execweave.model_runtime import vllm_response_to_events


def _request(events: list[dict]) -> dict:
    return next(event["target"] for event in events if event["relation"] == "SERVED_INFERENCE")


def _deployment(events: list[dict]) -> dict:
    return next(
        event["target"] for event in events if event["relation"] == "ROUTED_TO_DEPLOYMENT"
    )


def test_vllm_native_request_id_is_scoped_by_endpoint() -> None:
    payload = {"id": "req-shared", "model": "org/model", "usage": {"total_tokens": 1}}
    first = _request(vllm_response_to_events(payload, endpoint="http://localhost:8000"))
    second = _request(vllm_response_to_events(payload, endpoint="http://localhost:8001"))
    assert first["id"] != second["id"]
    assert first["attributes"]["request_id_source"] == "provider_native"
    assert second["attributes"]["request_id_source"] == "provider_native"
    assert first["attributes"]["endpoint_scope"] != second["attributes"]["endpoint_scope"]


def test_litellm_request_and_deployment_ids_are_scoped_by_endpoint() -> None:
    payload = {"id": "resp-shared", "model": "proxy/model", "usage": {"total_tokens": 1}}
    first_events = litellm_response_to_events(
        payload,
        endpoint="http://localhost:4000",
        deployment_id="deployment-west",
    )
    second_events = litellm_response_to_events(
        payload,
        endpoint="http://localhost:4001",
        deployment_id="deployment-west",
    )
    assert _request(first_events)["id"] != _request(second_events)["id"]
    assert _deployment(first_events)["id"] != _deployment(second_events)["id"]


def test_openrouter_response_and_generation_reconcile_only_within_same_endpoint() -> None:
    endpoint = "https://openrouter.ai/api/v1"
    response = _request(
        openrouter_response_to_events(
            {"id": "gen-shared", "model": "openai/gpt", "usage": {"total_tokens": 1}},
            endpoint=endpoint,
        )
    )
    generation_events = openrouter_generation_to_events(
        {"data": {"id": "gen-shared", "model": "openai/gpt"}},
        endpoint=endpoint,
    )
    generation = next(
        event["target"]
        for event in generation_events
        if event["relation"] == "REPORTED_GENERATION_METADATA"
    )
    assert response["id"] == generation["id"]

    other_generation_events = openrouter_generation_to_events(
        {"data": {"id": "gen-shared", "model": "openai/gpt"}},
        endpoint="https://proxy.example.test/openrouter/v1",
    )
    other_generation = next(
        event["target"]
        for event in other_generation_events
        if event["relation"] == "REPORTED_GENERATION_METADATA"
    )
    assert response["id"] != other_generation["id"]


def test_idless_model_runtime_observations_are_occurrence_scoped() -> None:
    payload = {"model": "org/model", "usage": {"total_tokens": 1}}
    first = _request(
        vllm_response_to_events(
            payload,
            endpoint="http://localhost:8000",
            timestamp="2026-08-31T10:00:00Z",
        )
    )
    replay = _request(
        vllm_response_to_events(
            payload,
            endpoint="http://localhost:8000",
            timestamp="2026-08-31T10:00:00Z",
        )
    )
    second = _request(
        vllm_response_to_events(
            payload,
            endpoint="http://localhost:8000",
            timestamp="2026-08-31T10:00:01Z",
        )
    )
    assert first["id"] == replay["id"]
    assert first["id"] != second["id"]
    assert first["attributes"]["request_id_source"] == "execweave_observation"


def test_idless_gateway_observations_are_occurrence_scoped() -> None:
    payload = {"model": "proxy/model", "usage": {"total_tokens": 1}}
    first = _request(
        litellm_response_to_events(
            payload,
            endpoint="http://localhost:4000",
            timestamp="2026-08-31T10:00:00Z",
        )
    )
    replay = _request(
        litellm_response_to_events(
            payload,
            endpoint="http://localhost:4000",
            timestamp="2026-08-31T10:00:00Z",
        )
    )
    second = _request(
        litellm_response_to_events(
            payload,
            endpoint="http://localhost:4000",
            timestamp="2026-08-31T10:00:01Z",
        )
    )
    assert first["id"] == replay["id"]
    assert first["id"] != second["id"]
    assert first["attributes"]["request_id_source"] == "execweave_observation"


def test_endpoint_scope_uses_sanitized_endpoint_only() -> None:
    payload = {"id": "req-safe", "model": "org/model", "usage": {"total_tokens": 1}}
    private_events = vllm_response_to_events(
        payload,
        endpoint="http://user:supersecret@localhost:8000/v1/?token=private#fragment",
    )
    clean_events = vllm_response_to_events(payload, endpoint="http://localhost:8000/v1")
    assert _request(private_events)["id"] == _request(clean_events)["id"]
    rendered = json.dumps(private_events)
    assert "supersecret" not in rendered
    assert "token=private" not in rendered
    assert "user:" not in rendered
