from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from .content_evidence import content_observation_event, filter_transport_credentials
from .content_store import ContentReference, FullFidelityContentStore
from .inference_gateway import sanitize_gateway_endpoint

_CONTENT_FIELDS = frozenset({"messages", "response", "model_parameters", "prompt", "input"})
_DROP_METADATA_CONTAINERS = frozenset(
    {"headers", "request_headers", "requester_custom_headers", "proxy_headers"}
)
_SECRET_FRAGMENTS = (
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "client_secret",
    "access_token",
    "refresh_token",
    "password",
)
_URL_KEYS = frozenset(
    {"api_base", "api_base_url", "base_url", "endpoint", "provider_endpoint", "url"}
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
    gateway: str,
    response: dict[str, Any],
    *,
    endpoint: str,
    request_id: str | None,
) -> dict[str, Any]:
    native_id = _request_id(response, request_id)
    return {
        "type": "inference_request",
        "id": f"inference-request:{gateway}:{native_id}",
        "name": native_id,
        "attributes": {"gateway": gateway, "endpoint": sanitize_gateway_endpoint(endpoint)},
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
    provider: str,
    source: dict[str, Any],
    relation: str,
    observed_field: str,
    evidence_source: str,
    attribution: str,
    attributes: dict[str, Any],
) -> dict[str, Any]:
    return content_observation_event(
        timestamp=timestamp,
        provider=provider,
        source=source,
        reference=_store(store, value, content_kind=content_kind),
        relation=relation,
        observed_field=observed_field,
        evidence_source=evidence_source,
        attribution=attribution,
        event_type=f"inference_gateway.{provider}.content.observed",
        attributes=attributes,
    )


def _tool_result_messages(messages: object) -> list[Any]:
    if not isinstance(messages, list):
        return []
    return [
        message
        for message in messages
        if isinstance(message, dict) and message.get("role") in {"tool", "function"}
    ]


def _response_tool_calls(response: object) -> list[Any]:
    if not isinstance(response, dict):
        return []
    calls: list[Any] = []
    choices = response.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
                continue
            nested = choice["message"].get("tool_calls")
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


def _secret_metadata_key(key: str) -> bool:
    lowered = key.lower()
    return (
        lowered in _DROP_METADATA_CONTAINERS
        or lowered == "user_api_key_hash"
        or any(fragment in lowered for fragment in _SECRET_FRAGMENTS)
    )


def _sanitize_metadata(value: Any, *, path: str = "") -> tuple[Any, list[str]]:
    removed: list[str] = []
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, child in value.items():
            key = str(raw_key)
            child_path = f"{path}.{key}" if path else key
            if _secret_metadata_key(key):
                removed.append(child_path)
                continue
            if key.lower() in _URL_KEYS and isinstance(child, str):
                try:
                    result[key] = sanitize_gateway_endpoint(child)
                except ValueError:
                    removed.append(child_path)
                continue
            result[key], nested = _sanitize_metadata(child, path=child_path)
            removed.extend(nested)
        filtered, transport_removed = filter_transport_credentials(result)
        removed.extend(f"{path}.{item}" if path else item for item in transport_removed)
        return filtered, sorted(set(removed))
    if isinstance(value, list):
        result_list: list[Any] = []
        for index, child in enumerate(value):
            sanitized, nested = _sanitize_metadata(child, path=f"{path}[{index}]")
            result_list.append(sanitized)
            removed.extend(nested)
        return result_list, sorted(set(removed))
    return value, removed


def _metadata_event(
    *,
    metadata: dict[str, Any],
    store: FullFidelityContentStore,
    timestamp: str,
    provider: str,
    source: dict[str, Any],
    evidence_source: str,
    attribution: str,
    content_kind: str,
    observed_field: str,
    attributes: dict[str, Any],
) -> dict[str, Any] | None:
    sanitized, removed = _sanitize_metadata(metadata)
    if not isinstance(sanitized, dict) or not sanitized:
        return None
    reference = store.put_json(sanitized, content_kind=content_kind)
    if removed:
        reference = replace(reference, complete_from_source=False)
    return content_observation_event(
        timestamp=timestamp,
        provider=provider,
        source=source,
        reference=reference,
        relation="OBSERVED_PROVIDER_METADATA",
        observed_field=observed_field,
        evidence_source=evidence_source,
        attribution=attribution,
        event_type=f"inference_gateway.{provider}.metadata.observed",
        attributes={
            **attributes,
            "transport_credentials_excluded": removed,
            "metadata_complete_from_source": not removed,
        },
    )


def gateway_response_to_content_events(
    payload: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    gateway_name: str,
    endpoint: str,
    request_id: str | None = None,
    timestamp: str | None = None,
    provider_name: str | None = None,
    deployment_id: str | None = None,
) -> list[dict[str, Any]]:
    """Store the complete response supplied to ExecWeave, without claiming request visibility."""
    observed_at = timestamp or _now()
    safe_endpoint = sanitize_gateway_endpoint(endpoint)
    request = _request_entity(gateway_name, payload, endpoint=safe_endpoint, request_id=request_id)
    attrs = {
        "observation_scope": "response_only",
        "request_observed": False,
        "caller_supplied_exchange": False,
    }
    events = [
        _content_event(
            store=store,
            value=payload,
            content_kind=f"inference_gateway.{gateway_name}.response",
            timestamp=observed_at,
            provider=gateway_name,
            source=request,
            relation="OBSERVED_INFERENCE_RESPONSE",
            observed_field="response",
            evidence_source="gateway_response",
            attribution="gateway_api_response",
            attributes=attrs,
        )
    ]
    tool_calls = _response_tool_calls(payload)
    if tool_calls:
        events.append(
            _content_event(
                store=store,
                value=tool_calls,
                content_kind=f"inference_gateway.{gateway_name}.assistant_tool_calls",
                timestamp=observed_at,
                provider=gateway_name,
                source=request,
                relation="OBSERVED_ASSISTANT_TOOL_CALLS",
                observed_field="response.tool_calls",
                evidence_source="gateway_response",
                attribution="gateway_api_response",
                attributes=attrs,
            )
        )
    metadata: dict[str, Any] = {
        "gateway": gateway_name,
        "endpoint": safe_endpoint,
        "request_id": request["name"],
    }
    if provider_name:
        metadata["provider_name"] = provider_name
    if deployment_id:
        metadata["deployment_id"] = deployment_id
    metadata_event = _metadata_event(
        metadata=metadata,
        store=store,
        timestamp=observed_at,
        provider=gateway_name,
        source=request,
        evidence_source="gateway_response",
        attribution="gateway_api_response",
        content_kind=f"inference_gateway.{gateway_name}.provider_metadata",
        observed_field="integration_metadata",
        attributes=attrs,
    )
    if metadata_event is not None:
        events.append(metadata_event)
    return events


def openrouter_response_to_content_events(
    payload: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    endpoint: str = "https://openrouter.ai/api/v1",
    request_id: str | None = None,
    timestamp: str | None = None,
    provider_name: str | None = None,
    deployment_id: str | None = None,
) -> list[dict[str, Any]]:
    return gateway_response_to_content_events(
        payload,
        store=store,
        gateway_name="openrouter",
        endpoint=endpoint,
        request_id=request_id,
        timestamp=timestamp,
        provider_name=provider_name,
        deployment_id=deployment_id,
    )


def openrouter_exchange_to_content_events(
    exchange: dict[str, Any],
    *,
    store: FullFidelityContentStore,
    endpoint: str = "https://openrouter.ai/api/v1",
    request_id: str | None = None,
    timestamp: str | None = None,
    provider_name: str | None = None,
    deployment_id: str | None = None,
) -> list[dict[str, Any]]:
    """Store caller-supplied request+response evidence; this is not wire interception."""
    request_payload = exchange.get("request")
    response_payload = exchange.get("response")
    if not isinstance(request_payload, dict) or not isinstance(response_payload, dict):
        raise ValueError("OpenRouter exchange requires JSON-object request and response fields")
    observed_at = timestamp or _now()
    safe_endpoint = sanitize_gateway_endpoint(endpoint)
    request = _request_entity(
        "openrouter", response_payload, endpoint=safe_endpoint, request_id=request_id
    )
    attrs = {
        "observation_scope": "caller_supplied_exchange",
        "request_observed": True,
        "caller_supplied_exchange": True,
        "wire_interception_asserted": False,
    }
    common = {
        "store": store,
        "timestamp": observed_at,
        "provider": "openrouter",
        "source": request,
        "evidence_source": "caller_supplied_exchange",
        "attribution": "execweave_gateway_cli",
        "attributes": attrs,
    }
    events = [
        _content_event(
            **common,
            value=request_payload,
            content_kind="inference_gateway.openrouter.request",
            relation="OBSERVED_INFERENCE_REQUEST",
            observed_field="request",
        )
    ]
    if "messages" in request_payload:
        events.append(
            _content_event(
                **common,
                value=request_payload["messages"],
                content_kind="inference_gateway.openrouter.request_messages",
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
                    content_kind="inference_gateway.openrouter.tool_result_messages",
                    relation="OBSERVED_TOOL_RESULT_MESSAGES",
                    observed_field="request.messages[role=tool|function]",
                )
            )
    if "tools" in request_payload:
        events.append(
            _content_event(
                **common,
                value=request_payload["tools"],
                content_kind="inference_gateway.openrouter.tool_definitions",
                relation="OBSERVED_TOOL_DEFINITIONS",
                observed_field="request.tools",
            )
        )
    for event in gateway_response_to_content_events(
        response_payload,
        store=store,
        gateway_name="openrouter",
        endpoint=safe_endpoint,
        request_id=request_id,
        timestamp=observed_at,
        provider_name=provider_name,
        deployment_id=deployment_id,
    ):
        if event.get("relation") == "OBSERVED_PROVIDER_METADATA":
            continue
        event["attributes"].update(attrs)
        event["attributes"]["evidence_source"] = "caller_supplied_exchange"
        event["attributes"]["attribution"] = "execweave_gateway_cli"
        events.append(event)
    metadata: dict[str, Any] = {
        "gateway": "openrouter",
        "endpoint": safe_endpoint,
        "request_id": request["name"],
        "requested_model": request_payload.get("model"),
        "resolved_model": response_payload.get("model"),
    }
    if provider_name:
        metadata["provider_name"] = provider_name
    if deployment_id:
        metadata["deployment_id"] = deployment_id
    metadata_event = _metadata_event(
        metadata=metadata,
        store=store,
        timestamp=observed_at,
        provider="openrouter",
        source=request,
        evidence_source="caller_supplied_exchange",
        attribution="execweave_gateway_cli",
        content_kind="inference_gateway.openrouter.provider_metadata",
        observed_field="integration_metadata",
        attributes=attrs,
    )
    if metadata_event is not None:
        events.append(metadata_event)
    return events


def _litellm_tools(
    callback_kwargs: dict[str, Any], standard: dict[str, Any]
) -> list[tuple[str, Any]]:
    values: list[tuple[str, Any]] = []
    if "tools" in callback_kwargs:
        values.append(("kwargs.tools", callback_kwargs["tools"]))
    optional = callback_kwargs.get("optional_params")
    if isinstance(optional, dict) and "tools" in optional:
        values.append(("kwargs.optional_params.tools", optional["tools"]))
    model_parameters = standard.get("model_parameters")
    if isinstance(model_parameters, dict) and "tools" in model_parameters:
        values.append(("standard_logging_object.model_parameters.tools", model_parameters["tools"]))
    return values


def litellm_callback_to_content_events(
    callback_kwargs: dict[str, Any],
    response_obj: Any,
    *,
    store: FullFidelityContentStore,
    endpoint: str = "http://localhost:4000",
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """Store complete content exposed by LiteLLM's success callback, fail-open at caller."""
    standard = callback_kwargs.get("standard_logging_object")
    if not isinstance(standard, dict):
        raise ValueError("LiteLLM callback requires standard_logging_object")
    call_id = standard.get("id")
    if not isinstance(call_id, str) or not call_id:
        raise ValueError("LiteLLM standard logging payload requires id")
    observed_at = timestamp or _now()
    safe_endpoint = sanitize_gateway_endpoint(endpoint)
    response = response_obj if isinstance(response_obj, dict) else None
    identity = response or {
        "id": call_id,
        "model": standard.get("model"),
        "usage": {"total_tokens": standard.get("total_tokens")},
    }
    request = _request_entity("litellm", identity, endpoint=safe_endpoint, request_id=call_id)
    attrs = {
        "observation_scope": "litellm_success_callback",
        "automatic_callback_observation": True,
        "wire_interception_asserted": False,
    }
    common = {
        "store": store,
        "timestamp": observed_at,
        "provider": "litellm",
        "source": request,
        "evidence_source": "litellm_callback",
        "attribution": "litellm_success_callback",
        "attributes": attrs,
    }
    events: list[dict[str, Any]] = []
    for field in ("prompt", "input"):
        value = callback_kwargs.get(field)
        observed_field = f"kwargs.{field}"
        if value is None:
            value = standard.get(field)
            observed_field = f"standard_logging_object.{field}"
        if value is not None:
            events.append(
                _content_event(
                    **common,
                    value=value,
                    content_kind=f"inference_gateway.litellm.request_{field}",
                    relation=(
                        "OBSERVED_INFERENCE_REQUEST_PROMPT"
                        if field == "prompt"
                        else "OBSERVED_INFERENCE_REQUEST_INPUT"
                    ),
                    observed_field=observed_field,
                )
            )
    messages = callback_kwargs.get("messages")
    message_field = "kwargs.messages"
    if messages is None:
        messages = standard.get("messages")
        message_field = "standard_logging_object.messages"
    if messages is not None:
        events.append(
            _content_event(
                **common,
                value=messages,
                content_kind="inference_gateway.litellm.request_messages",
                relation="OBSERVED_INFERENCE_REQUEST_MESSAGES",
                observed_field=message_field,
            )
        )
        tool_results = _tool_result_messages(messages)
        if tool_results:
            events.append(
                _content_event(
                    **common,
                    value=tool_results,
                    content_kind="inference_gateway.litellm.tool_result_messages",
                    relation="OBSERVED_TOOL_RESULT_MESSAGES",
                    observed_field=f"{message_field}[role=tool|function]",
                )
            )
    for observed_field, tools in _litellm_tools(callback_kwargs, standard):
        events.append(
            _content_event(
                **common,
                value=tools,
                content_kind="inference_gateway.litellm.tool_definitions",
                relation="OBSERVED_TOOL_DEFINITIONS",
                observed_field=observed_field,
            )
        )
    for observed_field, config in (
        ("kwargs.optional_params", callback_kwargs.get("optional_params")),
        ("standard_logging_object.model_parameters", standard.get("model_parameters")),
    ):
        if not isinstance(config, dict):
            continue
        event = _metadata_event(
            metadata=config,
            store=store,
            timestamp=observed_at,
            provider="litellm",
            source=request,
            evidence_source="litellm_callback",
            attribution="litellm_success_callback",
            content_kind="inference_gateway.litellm.provider_request_config",
            observed_field=observed_field,
            attributes={**attrs, "provider_facing_request_config": True},
        )
        if event is not None:
            event["relation"] = "OBSERVED_PROVIDER_REQUEST_CONFIG"
            events.append(event)
    if response is not None:
        events.append(
            _content_event(
                **common,
                value=response,
                content_kind="inference_gateway.litellm.response_object",
                relation="OBSERVED_INFERENCE_RESPONSE",
                observed_field="response_obj",
            )
        )
        tool_calls = _response_tool_calls(response)
        if tool_calls:
            events.append(
                _content_event(
                    **common,
                    value=tool_calls,
                    content_kind="inference_gateway.litellm.assistant_tool_calls",
                    relation="OBSERVED_ASSISTANT_TOOL_CALLS",
                    observed_field="response_obj.tool_calls",
                )
            )
    if standard.get("response") is not None:
        events.append(
            _content_event(
                **common,
                value=standard["response"],
                content_kind="inference_gateway.litellm.standard_logging_response",
                relation="OBSERVED_STANDARD_LOGGING_RESPONSE",
                observed_field="standard_logging_object.response",
            )
        )
    metadata = {key: value for key, value in standard.items() if key not in _CONTENT_FIELDS}
    if callback_kwargs.get("litellm_params") is not None:
        metadata["callback_litellm_params"] = callback_kwargs["litellm_params"]
    metadata["gateway_endpoint"] = safe_endpoint
    event = _metadata_event(
        metadata=metadata,
        store=store,
        timestamp=observed_at,
        provider="litellm",
        source=request,
        evidence_source="litellm_callback",
        attribution="litellm_success_callback",
        content_kind="inference_gateway.litellm.provider_metadata",
        observed_field="standard_logging_object.metadata_projection",
        attributes=attrs,
    )
    if event is not None:
        events.append(event)
    return events
