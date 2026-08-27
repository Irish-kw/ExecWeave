from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from .anthropic import _endpoint_digest, sanitize_anthropic_endpoint
from .content_evidence import content_observation_event
from .content_store import ContentReference, FullFidelityContentStore

_REQUEST_CONTENT_KEYS = frozenset({"messages", "system", "tools"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _request_id(payload: dict[str, Any], explicit: str | None) -> str:
    if isinstance(explicit, str) and explicit:
        return explicit
    native = payload.get("id")
    if isinstance(native, str) and native:
        return native
    seed = {
        key: payload.get(key)
        for key in ("model", "type", "role", "stop_reason", "usage")
    }
    raw = json.dumps(seed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:32]


def _request_entity(
    response: dict[str, Any],
    *,
    endpoint: str,
    request_id: str | None,
) -> dict[str, Any]:
    native_id = _request_id(response, request_id)
    safe = sanitize_anthropic_endpoint(endpoint)
    return {
        "type": "inference_request",
        "id": f"inference-request:anthropic:{_endpoint_digest(safe)}:{native_id}",
        "name": native_id,
        "attributes": {
            "protocol": "anthropic_messages",
            "provider_name": "anthropic",
            "endpoint": safe,
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
    source: dict[str, Any],
    relation: str,
    observed_field: str,
    evidence_source: str,
    attribution: str,
    attributes: dict[str, Any],
) -> dict[str, Any]:
    return content_observation_event(
        timestamp=timestamp,
        provider="anthropic",
        source=source,
        reference=_store(store, value, content_kind=content_kind),
        relation=relation,
        observed_field=observed_field,
        evidence_source=evidence_source,
        attribution=attribution,
        event_type="anthropic.content.observed",
        attributes=attributes,
    )


def _metadata_event(
    *,
    store: FullFidelityContentStore,
    metadata: dict[str, Any],
    timestamp: str,
    source: dict[str, Any],
    evidence_source: str,
    attribution: str,
    attributes: dict[str, Any],
) -> dict[str, Any]:
    reference = store.put_json(metadata, content_kind="anthropic.provider_metadata")
    reference = replace(reference, complete_from_source=False)
    return content_observation_event(
        timestamp=timestamp,
        provider="anthropic",
        source=source,
        reference=reference,
        relation="OBSERVED_PROVIDER_METADATA",
        observed_field="integration_metadata_projection",
        evidence_source=evidence_source,
        attribution=attribution,
        event_type="anthropic.metadata.observed",
        attributes={
            **attributes,
            "metadata_projection": True,
            "metadata_complete_from_source": False,
        },
    )


def _content_blocks(response: object) -> list[Any]:
    if not isinstance(response, dict):
        return []
    content = response.get("content")
    return list(content) if isinstance(content, list) else []


def _blocks_of_type(value: Any, types: set[str]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            if item.get("type") in types:
                found.append(item)
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return found


def response_to_content_events(
    payload: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    endpoint: str,
    request_id: str | None = None,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """Store one supplied Anthropic final response without claiming unseen request evidence."""
    observed_at = timestamp or _now()
    safe = sanitize_anthropic_endpoint(endpoint)
    request = _request_entity(payload, endpoint=safe, request_id=request_id)
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
        "source": request,
        "evidence_source": "anthropic_response",
        "attribution": "direct_api_response",
        "attributes": attrs,
    }
    events = [
        _content_event(
            **common,
            value=payload,
            content_kind="anthropic.response",
            relation="OBSERVED_INFERENCE_RESPONSE",
            observed_field="response",
        )
    ]
    blocks = _content_blocks(payload)
    if blocks:
        events.append(
            _content_event(
                **common,
                value=blocks,
                content_kind="anthropic.assistant_content_blocks",
                relation="OBSERVED_ASSISTANT_CONTENT_BLOCKS",
                observed_field="response.content",
            )
        )
    tool_uses = _blocks_of_type(blocks, {"tool_use"})
    if tool_uses:
        events.append(
            _content_event(
                **common,
                value=tool_uses,
                content_kind="anthropic.assistant_tool_uses",
                relation="OBSERVED_ASSISTANT_TOOL_CALLS",
                observed_field="response.content[type=tool_use]",
            )
        )
    reasoning = _blocks_of_type(blocks, {"thinking", "redacted_thinking"})
    if reasoning:
        events.append(
            _content_event(
                **common,
                value=reasoning,
                content_kind="anthropic.assistant_reasoning_blocks",
                relation="OBSERVED_ASSISTANT_REASONING_BLOCKS",
                observed_field="response.content[type=thinking|redacted_thinking]",
            )
        )
    events.append(
        _metadata_event(
            store=store,
            metadata={
                "protocol": "anthropic_messages",
                "provider_name": "anthropic",
                "endpoint": safe,
                "request_id": request["name"],
                "resolved_model": payload.get("model"),
                "stop_reason": payload.get("stop_reason"),
                "stop_sequence": payload.get("stop_sequence"),
            },
            timestamp=observed_at,
            source=request,
            evidence_source="anthropic_response",
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
    request_id: str | None = None,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """Store caller-supplied Anthropic request+response evidence; not wire interception."""
    request_payload = exchange.get("request")
    response_payload = exchange.get("response")
    if not isinstance(request_payload, dict) or not isinstance(response_payload, dict):
        raise ValueError("Anthropic exchange requires JSON-object request and response fields")
    stream_chunks = exchange.get("stream_chunks")
    if stream_chunks is not None and not isinstance(stream_chunks, list):
        raise ValueError("Anthropic stream_chunks must be a JSON array when supplied")

    observed_at = timestamp or _now()
    safe = sanitize_anthropic_endpoint(endpoint)
    request = _request_entity(response_payload, endpoint=safe, request_id=request_id)
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
        "source": request,
        "evidence_source": "caller_supplied_exchange",
        "attribution": "execweave_anthropic_cli",
        "attributes": attrs,
    }
    events = [
        _content_event(
            **common,
            value=request_payload,
            content_kind="anthropic.request",
            relation="OBSERVED_INFERENCE_REQUEST",
            observed_field="request",
        )
    ]
    if "messages" in request_payload:
        events.append(
            _content_event(
                **common,
                value=request_payload["messages"],
                content_kind="anthropic.request_messages",
                relation="OBSERVED_INFERENCE_REQUEST_MESSAGES",
                observed_field="request.messages",
            )
        )
        tool_results = _blocks_of_type(request_payload["messages"], {"tool_result"})
        if tool_results:
            events.append(
                _content_event(
                    **common,
                    value=tool_results,
                    content_kind="anthropic.tool_results",
                    relation="OBSERVED_TOOL_RESULT_MESSAGES",
                    observed_field="request.messages.content[type=tool_result]",
                )
            )
    if "system" in request_payload:
        events.append(
            _content_event(
                **common,
                value=request_payload["system"],
                content_kind="anthropic.system_context",
                relation="OBSERVED_SYSTEM_CONTEXT",
                observed_field="request.system",
            )
        )
    if "tools" in request_payload:
        events.append(
            _content_event(
                **common,
                value=request_payload["tools"],
                content_kind="anthropic.tools",
                relation="OBSERVED_TOOL_DEFINITIONS",
                observed_field="request.tools",
            )
        )
    config = {
        key: value
        for key, value in request_payload.items()
        if key not in _REQUEST_CONTENT_KEYS
    }
    if config:
        events.append(
            _content_event(
                **common,
                value=config,
                content_kind="anthropic.request_config",
                relation="OBSERVED_PROVIDER_REQUEST_CONFIG",
                observed_field="request.provider_facing_config",
            )
        )
    if stream_chunks is not None:
        events.append(
            _content_event(
                **common,
                value=stream_chunks,
                content_kind="anthropic.stream_chunks",
                relation="OBSERVED_INFERENCE_STREAM_CHUNKS",
                observed_field="stream_chunks",
            )
        )

    for event in response_to_content_events(
        response_payload,
        store=store,
        endpoint=safe,
        request_id=request_id,
        timestamp=observed_at,
    ):
        if event.get("relation") == "OBSERVED_PROVIDER_METADATA":
            continue
        event["attributes"].update(attrs)
        event["attributes"]["evidence_source"] = "caller_supplied_exchange"
        event["attributes"]["attribution"] = "execweave_anthropic_cli"
        events.append(event)

    events.append(
        _metadata_event(
            store=store,
            metadata={
                "protocol": "anthropic_messages",
                "provider_name": "anthropic",
                "endpoint": safe,
                "request_id": request["name"],
                "requested_model": request_payload.get("model"),
                "resolved_model": response_payload.get("model"),
                "stop_reason": response_payload.get("stop_reason"),
                "stop_sequence": response_payload.get("stop_sequence"),
            },
            timestamp=observed_at,
            source=request,
            evidence_source="caller_supplied_exchange",
            attribution="execweave_anthropic_cli",
            attributes=attrs,
        )
    )
    return events
