from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from .content_evidence import content_observation_event
from .content_store import ContentReference, FullFidelityContentStore
from .model_runtime import sanitize_endpoint

_RUNTIMES = frozenset({"ollama", "llamacpp", "vllm", "lmstudio"})
_REQUEST_CONFIG_KEYS = (
    "stream",
    "temperature",
    "top_p",
    "top_k",
    "min_p",
    "max_tokens",
    "max_completion_tokens",
    "num_predict",
    "seed",
    "stop",
    "response_format",
    "tool_choice",
    "parallel_tool_calls",
    "options",
    "format",
    "keep_alive",
    "think",
    "raw",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _request_id(runtime: str, payload: dict[str, Any], explicit: str | None) -> str:
    if isinstance(explicit, str) and explicit:
        return explicit
    native = payload.get("id")
    if isinstance(native, str) and native:
        return native
    seed = {
        "model": payload.get("model"),
        "created_at": payload.get("created_at"),
        "created": payload.get("created"),
        "done_reason": payload.get("done_reason"),
        "usage": payload.get("usage"),
    }
    raw = json.dumps(seed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((runtime + "\0" + raw).encode("utf-8", errors="replace")).hexdigest()[:32]


def _request_entity(
    runtime: str,
    response: dict[str, Any],
    *,
    endpoint: str,
    request_id: str | None,
) -> dict[str, Any]:
    native_id = _request_id(runtime, response, request_id)
    return {
        "type": "inference_request",
        "id": f"inference-request:{runtime}:{native_id}",
        "name": native_id,
        "attributes": {"provider": runtime, "endpoint": sanitize_endpoint(endpoint)},
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
    runtime: str,
    source: dict[str, Any],
    relation: str,
    observed_field: str,
    evidence_source: str,
    attribution: str,
    attributes: dict[str, Any],
) -> dict[str, Any]:
    return content_observation_event(
        timestamp=timestamp,
        provider=runtime,
        source=source,
        reference=_store(store, value, content_kind=content_kind),
        relation=relation,
        observed_field=observed_field,
        evidence_source=evidence_source,
        attribution=attribution,
        event_type=f"model_runtime.{runtime}.content.observed",
        attributes=attributes,
    )


def _metadata_event(
    *,
    store: FullFidelityContentStore,
    metadata: dict[str, Any],
    timestamp: str,
    runtime: str,
    source: dict[str, Any],
    evidence_source: str,
    attribution: str,
    attributes: dict[str, Any],
) -> dict[str, Any]:
    reference = store.put_json(metadata, content_kind=f"model_runtime.{runtime}.provider_metadata")
    reference = replace(reference, complete_from_source=False)
    return content_observation_event(
        timestamp=timestamp,
        provider=runtime,
        source=source,
        reference=reference,
        relation="OBSERVED_PROVIDER_METADATA",
        observed_field="integration_metadata_projection",
        evidence_source=evidence_source,
        attribution=attribution,
        event_type=f"model_runtime.{runtime}.metadata.observed",
        attributes={
            **attributes,
            "metadata_projection": True,
            "metadata_complete_from_source": False,
        },
    )


def _tool_result_messages(messages: object) -> list[Any]:
    if not isinstance(messages, list):
        return []
    return [
        message
        for message in messages
        if isinstance(message, dict) and message.get("role") in {"tool", "function"}
    ]


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
            if not isinstance(item, dict):
                continue
            if item.get("type") in {"message", "assistant_message"}:
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


def _request_config(request: dict[str, Any]) -> dict[str, Any]:
    config: dict[str, Any] = {}
    for key in _REQUEST_CONFIG_KEYS:
        if key in request:
            config[key] = request[key]
    return config


def runtime_response_to_content_events(
    payload: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    runtime: str,
    endpoint: str,
    request_id: str | None = None,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """Store the complete supplied final response without claiming request visibility."""
    if runtime not in _RUNTIMES:
        raise ValueError(f"unsupported model runtime: {runtime}")
    observed_at = timestamp or _now()
    safe_endpoint = sanitize_endpoint(endpoint)
    request = _request_entity(runtime, payload, endpoint=safe_endpoint, request_id=request_id)
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
        "runtime": runtime,
        "source": request,
        "evidence_source": "model_runtime_response",
        "attribution": "model_runtime_api_response",
        "attributes": attrs,
    }
    events = [
        _content_event(
            **common,
            value=payload,
            content_kind=f"model_runtime.{runtime}.response",
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
                content_kind=f"model_runtime.{runtime}.assistant_messages",
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
                content_kind=f"model_runtime.{runtime}.assistant_tool_calls",
                relation="OBSERVED_ASSISTANT_TOOL_CALLS",
                observed_field="response.tool_calls",
            )
        )
    metadata = {
        "runtime": runtime,
        "endpoint": safe_endpoint,
        "request_id": request["name"],
        "resolved_model": payload.get("model"),
    }
    events.append(
        _metadata_event(
            store=store,
            metadata=metadata,
            timestamp=observed_at,
            runtime=runtime,
            source=request,
            evidence_source="model_runtime_response",
            attribution="model_runtime_api_response",
            attributes=attrs,
        )
    )
    return events


def runtime_exchange_to_content_events(
    exchange: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    runtime: str,
    endpoint: str,
    request_id: str | None = None,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """Store caller-supplied request+response evidence; this is not transparent interception."""
    if runtime not in _RUNTIMES:
        raise ValueError(f"unsupported model runtime: {runtime}")
    request_payload = exchange.get("request")
    response_payload = exchange.get("response")
    if not isinstance(request_payload, dict) or not isinstance(response_payload, dict):
        raise ValueError("model runtime exchange requires JSON-object request and response fields")
    observed_at = timestamp or _now()
    safe_endpoint = sanitize_endpoint(endpoint)
    request = _request_entity(
        runtime, response_payload, endpoint=safe_endpoint, request_id=request_id
    )
    attrs = {
        "observation_scope": "caller_supplied_exchange",
        "request_observed": True,
        "caller_supplied_exchange": True,
        "wire_interception_asserted": False,
        "streaming_chunks_observed": False,
    }
    common = {
        "store": store,
        "timestamp": observed_at,
        "runtime": runtime,
        "source": request,
        "evidence_source": "caller_supplied_exchange",
        "attribution": "execweave_model_runtime_cli",
        "attributes": attrs,
    }
    events = [
        _content_event(
            **common,
            value=request_payload,
            content_kind=f"model_runtime.{runtime}.request",
            relation="OBSERVED_INFERENCE_REQUEST",
            observed_field="request",
        )
    ]
    if "messages" in request_payload:
        events.append(
            _content_event(
                **common,
                value=request_payload["messages"],
                content_kind=f"model_runtime.{runtime}.request_messages",
                relation="OBSERVED_INFERENCE_REQUEST_MESSAGES",
                observed_field="request.messages",
            )
        )
        tool_results = _tool_result_messages(request_payload["messages"])
        if tool_results:
            events.append(
                _content_event(
                    **common,
                    value=tool_results,
                    content_kind=f"model_runtime.{runtime}.tool_result_messages",
                    relation="OBSERVED_TOOL_RESULT_MESSAGES",
                    observed_field="request.messages[role=tool|function]",
                )
            )
    if "prompt" in request_payload:
        events.append(
            _content_event(
                **common,
                value=request_payload["prompt"],
                content_kind=f"model_runtime.{runtime}.request_prompt",
                relation="OBSERVED_INFERENCE_REQUEST_PROMPT",
                observed_field="request.prompt",
            )
        )
    if "input" in request_payload:
        events.append(
            _content_event(
                **common,
                value=request_payload["input"],
                content_kind=f"model_runtime.{runtime}.request_input",
                relation="OBSERVED_INFERENCE_REQUEST_INPUT",
                observed_field="request.input",
            )
        )
    if "system" in request_payload:
        events.append(
            _content_event(
                **common,
                value=request_payload["system"],
                content_kind=f"model_runtime.{runtime}.system_context",
                relation="OBSERVED_SYSTEM_CONTEXT",
                observed_field="request.system",
            )
        )
    if "tools" in request_payload:
        events.append(
            _content_event(
                **common,
                value=request_payload["tools"],
                content_kind=f"model_runtime.{runtime}.tool_definitions",
                relation="OBSERVED_TOOL_DEFINITIONS",
                observed_field="request.tools",
            )
        )
    config = _request_config(request_payload)
    if config:
        events.append(
            _content_event(
                **common,
                value=config,
                content_kind=f"model_runtime.{runtime}.request_config",
                relation="OBSERVED_INFERENCE_REQUEST_CONFIG",
                observed_field="request.provider_facing_config",
            )
        )

    for event in runtime_response_to_content_events(
        response_payload,
        store=store,
        runtime=runtime,
        endpoint=safe_endpoint,
        request_id=request_id,
        timestamp=observed_at,
    ):
        if event.get("relation") == "OBSERVED_PROVIDER_METADATA":
            continue
        event["attributes"].update(attrs)
        event["attributes"]["evidence_source"] = "caller_supplied_exchange"
        event["attributes"]["attribution"] = "execweave_model_runtime_cli"
        events.append(event)

    metadata = {
        "runtime": runtime,
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
            runtime=runtime,
            source=request,
            evidence_source="caller_supplied_exchange",
            attribution="execweave_model_runtime_cli",
            attributes=attrs,
        )
    )
    return events


def ollama_response_to_content_events(
    payload: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    endpoint: str = "http://localhost:11434",
    request_id: str | None = None,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    return runtime_response_to_content_events(
        payload,
        store=store,
        runtime="ollama",
        endpoint=endpoint,
        request_id=request_id,
        timestamp=timestamp,
    )


def llamacpp_response_to_content_events(
    payload: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    endpoint: str = "http://localhost:8080",
    request_id: str | None = None,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    return runtime_response_to_content_events(
        payload,
        store=store,
        runtime="llamacpp",
        endpoint=endpoint,
        request_id=request_id,
        timestamp=timestamp,
    )


def vllm_response_to_content_events(
    payload: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    endpoint: str = "http://localhost:8000",
    request_id: str | None = None,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    return runtime_response_to_content_events(
        payload,
        store=store,
        runtime="vllm",
        endpoint=endpoint,
        request_id=request_id,
        timestamp=timestamp,
    )


def lmstudio_response_to_content_events(
    payload: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    endpoint: str = "http://localhost:1234",
    request_id: str | None = None,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    return runtime_response_to_content_events(
        payload,
        store=store,
        runtime="lmstudio",
        endpoint=endpoint,
        request_id=request_id,
        timestamp=timestamp,
    )
