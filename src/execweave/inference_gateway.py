from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sanitize_gateway_endpoint(endpoint: str) -> str:
    split = urlsplit(endpoint)
    if split.scheme not in {"http", "https"} or not split.hostname:
        raise ValueError("inference gateway endpoint must be an http(s) URL")
    host = split.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if split.port is not None:
        host = f"{host}:{split.port}"
    path = split.path.rstrip("/")
    return urlunsplit((split.scheme, host, path, "", ""))


def _entity(
    entity_type: str,
    entity_id: str,
    *,
    name: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {"type": entity_type, "id": entity_id, "name": name, "attributes": attributes or {}}


def _gateway_entity(gateway: str, endpoint: str) -> dict[str, Any]:
    safe_endpoint = sanitize_gateway_endpoint(endpoint)
    digest = hashlib.sha256(safe_endpoint.encode("utf-8")).hexdigest()[:24]
    return _entity(
        "inference_gateway",
        f"inference-gateway:{gateway}:{digest}",
        name=gateway,
        attributes={"gateway": gateway, "endpoint": safe_endpoint},
    )


def _model_entity(model: str) -> dict[str, Any]:
    return _entity(
        "model",
        f"model:catalog:{model}",
        name=model,
        attributes={"catalog_id": model},
    )


def _provider_entity(provider: str) -> dict[str, Any]:
    slug = hashlib.sha256(provider.encode("utf-8", errors="replace")).hexdigest()[:24]
    return _entity(
        "inference_provider",
        f"inference-provider:{slug}",
        name=provider,
        attributes={"provider_name": provider},
    )


def _deployment_entity(gateway: str, deployment: str) -> dict[str, Any]:
    slug = hashlib.sha256(deployment.encode("utf-8", errors="replace")).hexdigest()[:24]
    return _entity(
        "inference_deployment",
        f"inference-deployment:{gateway}:{slug}",
        name=deployment,
        attributes={"gateway": gateway, "deployment_id": deployment},
    )


def _event(
    *,
    timestamp: str,
    event_type: str,
    relation: str,
    source: dict[str, Any],
    target: dict[str, Any],
    gateway: str,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged = {
        "backend": "inference_gateway",
        "attribution": "gateway_api",
        "evidence_source": "gateway_response",
        "gateway": gateway,
        "causal": False,
    }
    if attributes:
        merged.update(attributes)
    return {
        "timestamp": timestamp,
        "event_type": event_type,
        "relation": relation,
        "source": source,
        "target": target,
        "attributes": merged,
    }


def _request_id(payload: dict[str, Any], explicit: str | None) -> str:
    if explicit:
        return explicit
    native = payload.get("id")
    if isinstance(native, str) and native:
        return native
    seed = {
        "model": payload.get("model"),
        "created": payload.get("created"),
        "usage": payload.get("usage"),
    }
    raw = json.dumps(seed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:32]


def _copy_int(mapping: dict[str, Any], source: str, target: str, attrs: dict[str, Any]) -> None:
    value = mapping.get(source)
    if isinstance(value, int) and not isinstance(value, bool) and target not in attrs:
        attrs[target] = value


def _usage_attributes(payload: dict[str, Any]) -> dict[str, Any]:
    attrs: dict[str, Any] = {"protocol": "openai_compatible"}
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return attrs
    for source, target in (
        ("prompt_tokens", "prompt_tokens"),
        ("input_tokens", "prompt_tokens"),
        ("completion_tokens", "completion_tokens"),
        ("output_tokens", "completion_tokens"),
        ("total_tokens", "total_tokens"),
    ):
        _copy_int(usage, source, target, attrs)
    cost = usage.get("cost")
    if isinstance(cost, (int, float)) and not isinstance(cost, bool):
        attrs["cost_usd"] = float(cost)
    for detail_key in ("prompt_tokens_details", "input_tokens_details"):
        details = usage.get(detail_key)
        if not isinstance(details, dict):
            continue
        for source, target in (
            ("cached_tokens", "cached_prompt_tokens"),
            ("cache_write_tokens", "cache_write_tokens"),
        ):
            _copy_int(details, source, target, attrs)
    for detail_key in ("completion_tokens_details", "output_tokens_details"):
        details = usage.get(detail_key)
        if isinstance(details, dict):
            _copy_int(details, "reasoning_tokens", "reasoning_tokens", attrs)
    for source, target in (
        ("cache_creation_input_tokens", "cache_write_tokens"),
        ("cache_read_input_tokens", "cached_prompt_tokens"),
    ):
        _copy_int(usage, source, target, attrs)
    return attrs


def gateway_response_to_events(
    payload: dict[str, Any],
    *,
    gateway_name: str,
    endpoint: str,
    requested_model: str | None = None,
    resolved_model: str | None = None,
    provider_name: str | None = None,
    deployment_id: str | None = None,
    request_id: str | None = None,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    observed_at = timestamp or _now()
    gateway = _gateway_entity(gateway_name, endpoint)
    native_id = _request_id(payload, request_id)
    response_model = payload.get("model")
    resolved = resolved_model
    if not isinstance(resolved, str) or not resolved:
        resolved = response_model if isinstance(response_model, str) and response_model else None

    attrs = _usage_attributes(payload)
    if isinstance(requested_model, str) and requested_model:
        attrs["requested_model"] = requested_model
    if isinstance(resolved, str) and resolved:
        attrs["resolved_model"] = resolved
    if isinstance(provider_name, str) and provider_name:
        attrs["provider_name"] = provider_name
    if isinstance(deployment_id, str) and deployment_id:
        attrs["deployment_id"] = deployment_id

    request = _entity(
        "inference_request",
        f"inference-request:{gateway_name}:{native_id}",
        name=native_id,
        attributes={"gateway": gateway_name, **attrs},
    )
    events = [
        _event(
            timestamp=observed_at,
            event_type=f"inference_gateway.{gateway_name}.response.observed",
            relation="SERVED_INFERENCE",
            source=gateway,
            target=request,
            gateway=gateway_name,
            attributes=attrs,
        )
    ]
    if isinstance(requested_model, str) and requested_model:
        events.append(
            _event(
                timestamp=observed_at,
                event_type=f"inference_gateway.{gateway_name}.model.requested",
                relation="REQUESTED_MODEL",
                source=request,
                target=_model_entity(requested_model),
                gateway=gateway_name,
                attributes=attrs,
            )
        )
    if isinstance(resolved, str) and resolved:
        events.append(
            _event(
                timestamp=observed_at,
                event_type=f"inference_gateway.{gateway_name}.model.resolved",
                relation="ROUTED_TO_MODEL",
                source=request,
                target=_model_entity(resolved),
                gateway=gateway_name,
                attributes=attrs,
            )
        )
    if isinstance(provider_name, str) and provider_name:
        events.append(
            _event(
                timestamp=observed_at,
                event_type=f"inference_gateway.{gateway_name}.provider.resolved",
                relation="ROUTED_TO_PROVIDER",
                source=request,
                target=_provider_entity(provider_name),
                gateway=gateway_name,
                attributes=attrs,
            )
        )
    if isinstance(deployment_id, str) and deployment_id:
        events.append(
            _event(
                timestamp=observed_at,
                event_type=f"inference_gateway.{gateway_name}.deployment.resolved",
                relation="ROUTED_TO_DEPLOYMENT",
                source=request,
                target=_deployment_entity(gateway_name, deployment_id),
                gateway=gateway_name,
                attributes=attrs,
            )
        )
    return events


def openrouter_response_to_events(
    payload: dict[str, Any],
    *,
    requested_model: str | None = None,
    resolved_model: str | None = None,
    provider_name: str | None = None,
    deployment_id: str | None = None,
    endpoint: str = "https://openrouter.ai/api/v1",
    request_id: str | None = None,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    return gateway_response_to_events(
        payload,
        gateway_name="openrouter",
        endpoint=endpoint,
        requested_model=requested_model,
        resolved_model=resolved_model,
        provider_name=provider_name,
        deployment_id=deployment_id,
        request_id=request_id,
        timestamp=timestamp,
    )


def litellm_response_to_events(
    payload: dict[str, Any],
    *,
    requested_model: str | None = None,
    resolved_model: str | None = None,
    provider_name: str | None = None,
    deployment_id: str | None = None,
    endpoint: str = "http://localhost:4000",
    request_id: str | None = None,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    return gateway_response_to_events(
        payload,
        gateway_name="litellm",
        endpoint=endpoint,
        requested_model=requested_model,
        resolved_model=resolved_model,
        provider_name=provider_name,
        deployment_id=deployment_id,
        request_id=request_id,
        timestamp=timestamp,
    )


def openrouter_generation_to_events(
    payload: dict[str, Any],
    *,
    endpoint: str = "https://openrouter.ai/api/v1",
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        raise ValueError("OpenRouter generation payload must be a JSON object")
    generation_id = data.get("id")
    if not isinstance(generation_id, str) or not generation_id:
        raise ValueError("OpenRouter generation metadata requires id")
    observed_at = timestamp or _now()
    gateway = _gateway_entity("openrouter", endpoint)

    attrs: dict[str, Any] = {"protocol": "openrouter_generation"}
    for key in (
        "latency",
        "generation_time",
        "total_cost",
        "tokens_prompt",
        "tokens_completion",
        "native_tokens_prompt",
        "native_tokens_completion",
    ):
        value = data.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            attrs[key] = value
    for key in ("streamed", "cancelled"):
        value = data.get(key)
        if isinstance(value, bool):
            attrs[key] = value

    request = _entity(
        "inference_request",
        f"inference-request:openrouter:{generation_id}",
        name=generation_id,
        attributes={"gateway": "openrouter", **attrs},
    )
    events = [
        _event(
            timestamp=observed_at,
            event_type="inference_gateway.openrouter.generation.observed",
            relation="REPORTED_GENERATION_METADATA",
            source=gateway,
            target=request,
            gateway="openrouter",
            attributes=attrs,
        )
    ]

    model = data.get("model") or data.get("model_name")
    if isinstance(model, str) and model:
        events.append(
            _event(
                timestamp=observed_at,
                event_type="inference_gateway.openrouter.model.resolved",
                relation="ROUTED_TO_MODEL",
                source=request,
                target=_model_entity(model),
                gateway="openrouter",
                attributes=attrs,
            )
        )
    provider = data.get("provider_name") or data.get("provider")
    if isinstance(provider, str) and provider:
        events.append(
            _event(
                timestamp=observed_at,
                event_type="inference_gateway.openrouter.provider.resolved",
                relation="ROUTED_TO_PROVIDER",
                source=request,
                target=_provider_entity(provider),
                gateway="openrouter",
                attributes=attrs,
            )
        )
    return events


def append_gateway_records(path: str | Path, records: list[dict[str, Any]]) -> Path:
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        return output
    blob = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for record in records
    )
    lock_dir = output.with_name(output.name + ".lock")
    deadline = time.monotonic() + 5.0
    while True:
        try:
            lock_dir.mkdir()
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timed out waiting for inference gateway sidecar lock: {lock_dir}")
            time.sleep(0.01)
    try:
        with output.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(blob)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        try:
            lock_dir.rmdir()
        except OSError:
            pass
    return output
