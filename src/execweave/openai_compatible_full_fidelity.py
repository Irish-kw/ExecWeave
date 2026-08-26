from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from .content_evidence import content_observation_event
from .content_store import ContentReference, FullFidelityContentStore
from .openai_compatible import sanitize_openai_compatible_endpoint

_REQUEST_CONTENT_KEYS = frozenset(
    {"messages", "prompt", "input", "system", "instructions", "tools", "functions"}
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _request_id(payload: dict[str, Any], explicit: str | None) -> str:
    if isinstance(explicit, str) and explicit:
        return explicit
    native = payload.get("id")
    if isinstance(native, str) and native:
        return native
    seed = {key: payload.get(key) for key in ("model", "created", "usage")}
    raw = json.dumps(seed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:32]


def _request_entity(
    response: dict[str, Any],
    *,
    endpoint: str,
    provider_name: str,
    request_id: str | None,
) -> dict[str, Any]:
    native_id = _request_id(response, request_id)
    return {
        "type": "inference_request",
        "id": f"inference-request:openai-compatible:{native_id}",
        "name": native_id,
        "attributes": {
            "protocol": "openai_compatible",
            "provider_name": provider_name,
            "endpoint": sanitize_openai_compatible_endpoint(endpoint),
        },
    }


def _store(
    store: FullFidelityContentStore,
    value: Any,
    *,
    content_kind: str,
) -> ContentReference:
    if isinstance(value, str):
        return store.put_text(value, content_kind=content_kind)
    return store.put_json(value, content_kind=content_kind)


def _content_event(
    *,
    store: FullFidelityContentStore,
    value: Any,
    content_kind: str,
    timestamp: str,
    provider_name: str,
    source: dict[str, Any],
    relation: str,
    observed_field: str,
    evidence_source: str,
    attribution: str,
    attributes: dict[str, Any],
) -> dict[str, Any]:
    return content_observation_event(
        timestamp=timestamp,
        provider=provider_name,
        source=source,
        reference=_store(store, value, content_kind=content_kind),
        relation=relation,
        observed_field=observed_field,
        evidence_source=evidence_source,
        attribution=attribution,
        event_type="openai_compatible.content.observed",
        attributes=attributes,
    )


def _metadata_event(
    *,
    store: FullFidelityContentStore,
    metadata: dict[str, Any],
    timestamp: str,
    provider_name: str,
    source: dict[str, Any],
    evidence_source: str,
    attribution: str,
    attributes: dict[str, Any],
) -> dict[str, Any]:
    reference = store.put_json(metadata, content_kind="openai_compatible.provider_metadata")
    reference = replace(reference, complete_from_source=False)
    return content_observation_event(
        timestamp=timestamp,
        provider=provider_name,
        source=source,
        reference=reference,
        relation="OBSERVED_PROVIDER_METADATA",
        observed_field="integration_metadata_projection",
        evidence_source=evidence_source,
        attribution=attribution,
        event_type="openai_compatible.metadata.observed",
        attributes={
            **attributes,
            "metadata_projection": True,
            "metadata_complete_from_source": False,
        },
    )


def _assistant_messages(response: object) -> list[Any]:
    if not isinstance(response, dict):
        return []
    messages: list[Any] = []
    native = response.get("message")
    if isinstance(native, dict):
        messages.append(native)
    choices = response.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if isinstance(choice, dict) and isinstance(choice.get("message"), dict):
                messages.append(choice["message"])
    output = response.get("output")
    if isinstance(output, list):
        for item in output:
            if isinstance(item, dict) and item.get("type") in {"message", "assistant_message"}:
                messages.append(item)
    return messages


def _response_tool_calls(response: object) -> list[Any]:
    if not isinstance(response, dict):
        return []
    calls: list[Any] = []
    direct = response.get("tool_calls")
    if isinstance(direct, list):
        calls.extend(direct)
    for message in _assistant_messages(response):
        if isinstance(message, dict):
            nested = message.get("tool_calls")
            if isinstance(nested, list):
                calls.extend(nested)
    output = response.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") in {"function_call", "tool_call", "tool_use"}:
                calls.append(item)
            nested = item.get("tool_calls")
            if isinstance(nested, list):
                calls.extend(nested)
    return calls


def _tool_results(request: dict[str, Any]) -> list[Any]:
    results: list[Any] = []
    messages = request.get("messages")
    if isinstance(messages, list):
        results.extend(
            item
            for item in messages
            if isinstance(item, dict) and item.get("role") in {"tool", "function"}
        )
    input_value = request.get("input")
    if isinstance(input_value, list):
        results.extend(
            item
            for item in input_value
            if isinstance(item, dict)
            and item.get("type") in {"function_call_output", "tool_result", "tool_output"}
        )
    return results


def response_to_content_events(
    payload: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    endpoint: str,
    provider_name: str = "openai-compatible",
    request_id: str | None = None,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """Store the complete supplied final response without claiming request visibility."""
    observed_at = timestamp or _now()
    safe_endpoint = sanitize_openai_compatible_endpoint(endpoint)
    request = _request_entity(
        payload,
        endpoint=safe_endpoint,
        provider_name=provider_name,
        request_id=request_id,
    )
    attrs = {
        "observation_scope": "response_only",
        "request_observed": False,
        "caller_supplied_exchange": False,
        "wire_interception_asserted": False,
        "streaming_chunks_observed": False,
    }
    common = {
        "store": store,
        "timestamp": observed_at,
        "provider_name": provider_name,
        "source": request,
        "evidence_source": "openai_compatible_response",
        "attribution": "direct_api_response",
        "attributes": attrs,
    }
    events = [
        _content_event(
            **common,
            value=payload,
            content_kind="openai_compatible.response",
            relation="OBSERVED_INFERENCE_RESPONSE",
            observed_field="response",
        )
    ]
    assistant_messages = _assistant_messages(payload)
    if assistant_messages:
        events.append(
            _content_event(
                **common,
                value=assistant_messages,
                content_kind="openai_compatible.assistant_messages",
                relation="OBSERVED_ASSISTANT_MESSAGES",
                observed_field="response.assistant_messages",
            )
        )
    tool_calls = _response_tool_calls(payload)
    if tool_calls:
        events.append(
            _content_event(
                **common,
                value=tool_calls,
                content_kind="openai_compatible.assistant_tool_calls",
                relation="OBSERVED_ASSISTANT_TOOL_CALLS",
                observed_field="response.tool_calls",
            )
        )
    metadata = {
        "protocol": "openai_compatible",
        "provider_name": provider_name,
        "endpoint": safe_endpoint,
        "request_id": request["name"],
        "resolved_model": payload.get("model"),
    }
    events.append(
        _metadata_event(
            store=store,
            metadata=metadata,
            timestamp=observed_at,
            provider_name=provider_name,
            source=request,
            evidence_source="openai_compatible_response",
            attribution="direct_api_response",
            attributes=attrs,
        )
    )
    return events


def exchange_to_content_events(
    exchange: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    endpoint: str,
    provider_name: str = "openai-compatible",
    request_id: str | None = None,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """Store caller-supplied request+response evidence; this is not wire interception."""
    request_payload = exchange.get("request")
    response_payload = exchange.get("response")
    if not isinstance(request_payload, dict) or not isinstance(response_payload, dict):
        raise ValueError(
            "OpenAI-compatible exchange requires JSON-object request and response fields"
        )
    stream_chunks = exchange.get("stream_chunks")
    if stream_chunks is not None and not isinstance(stream_chunks, list):
        raise ValueError("OpenAI-compatible stream_chunks must be a JSON array when supplied")

    observed_at = timestamp or _now()
    safe_endpoint = sanitize_openai_compatible_endpoint(endpoint)
    request = _request_entity(
        response_payload,
        endpoint=safe_endpoint,
        provider_name=provider_name,
        request_id=request_id,
    )
    attrs = {
        "observation_scope": "caller_supplied_exchange",
        "request_observed": True,
        "caller_supplied_exchange": True,
        "wire_interception_asserted": False,
        "streaming_chunks_observed": stream_chunks is not None,
    }
    common = {
        "store": store,
        "timestamp": observed_at,
        "provider_name": provider_name,
        "source": request,
        "evidence_source": "caller_supplied_exchange",
        "attribution": "execweave_openai_compatible_cli",
        "attributes": attrs,
    }
    events = [
        _content_event(
            **common,
            value=request_payload,
            content_kind="openai_compatible.request",
            relation="OBSERVED_INFERENCE_REQUEST",
            observed_field="request",
        )
    ]
    for key, relation in (
        ("messages", "OBSERVED_INFERENCE_REQUEST_MESSAGES"),
        ("prompt", "OBSERVED_INFERENCE_REQUEST_PROMPT"),
        ("input", "OBSERVED_INFERENCE_REQUEST_INPUT"),
    ):
        if key in request_payload:
            events.append(
                _content_event(
                    **common,
                    value=request_payload[key],
                    content_kind=f"openai_compatible.request_{key}",
                    relation=relation,
                    observed_field=f"request.{key}",
                )
            )
    for key in ("system", "instructions"):
        if key in request_payload:
            events.append(
                _content_event(
                    **common,
                    value=request_payload[key],
                    content_kind=f"openai_compatible.{key}_context",
                    relation="OBSERVED_SYSTEM_CONTEXT",
                    observed_field=f"request.{key}",
                )
            )
    for key in ("tools", "functions"):
        if key in request_payload:
            events.append(
                _content_event(
                    **common,
                    value=request_payload[key],
                    content_kind=f"openai_compatible.{key}",
                    relation="OBSERVED_TOOL_DEFINITIONS",
                    observed_field=f"request.{key}",
                )
            )
    tool_results = _tool_results(request_payload)
    if tool_results:
        events.append(
            _content_event(
                **common,
                value=tool_results,
                content_kind="openai_compatible.tool_results",
                relation="OBSERVED_TOOL_RESULT_MESSAGES",
                observed_field="request.tool_results",
            )
        )
    config = {
        key: value for key, value in request_payload.items() if key not in _REQUEST_CONTENT_KEYS
    }
    if config:
        events.append(
            _content_event(
                **common,
                value=config,
                content_kind="openai_compatible.request_config",
                relation="OBSERVED_PROVIDER_REQUEST_CONFIG",
                observed_field="request.provider_facing_config",
            )
        )
    if stream_chunks is not None:
        events.append(
            _content_event(
                **common,
                value=stream_chunks,
                content_kind="openai_compatible.stream_chunks",
                relation="OBSERVED_INFERENCE_STREAM_CHUNKS",
                observed_field="stream_chunks",
            )
        )

    for event in response_to_content_events(
        response_payload,
        store=store,
        endpoint=safe_endpoint,
        provider_name=provider_name,
        request_id=request_id,
        timestamp=observed_at,
    ):
        if event.get("relation") == "OBSERVED_PROVIDER_METADATA":
            continue
        event["attributes"].update(attrs)
        event["attributes"]["evidence_source"] = "caller_supplied_exchange"
        event["attributes"]["attribution"] = "execweave_openai_compatible_cli"
        events.append(event)

    metadata = {
        "protocol": "openai_compatible",
        "provider_name": provider_name,
        "endpoint": safe_endpoint,
        "request_id": request["name"],
        "requested_model": request_payload.get("model"),
        "resolved_model": response_payload.get("model"),
    }
    events.append(
        _metadata_event(
            store=store,
            metadata=metadata,
            timestamp=observed_at,
            provider_name=provider_name,
            source=request,
            evidence_source="caller_supplied_exchange",
            attribution="execweave_openai_compatible_cli",
            attributes=attrs,
        )
    )
    return events
