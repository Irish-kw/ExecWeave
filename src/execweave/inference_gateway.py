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


def _usage_attributes(payload: dict[str, Any]) -> dict[str, Any]:
    attrs: dict[str, Any] = {"protocol": "openai_compatible"}
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return attrs
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            attrs[key] = value
    cost = usage.get("cost")
    if isinstance(cost, (int, float)) and not isinstance(cost, bool):
        attrs["cost_usd"] = float(cost)
    prompt_details = usage.get("prompt_tokens_details")
    if isinstance(prompt_details, dict):
        for source, target in (
            ("cached_tokens", "cached_prompt_tokens"),
            ("cache_write_tokens", "cache_write_tokens"),
        ):
            value = prompt_details.get(source)
            if isinstance(value, int) and not isinstance(value, bool):
                attrs[target] = value
    completion_details = usage.get("completion_tokens_details")
    if isinstance(completion_details, dict):
        reasoning = completion_details.get("reasoning_tokens")
        if isinstance(reasoning, int) and not isinstance(reasoning, bool):
            attrs["reasoning_tokens"] = reasoning
    return attrs


def openrouter_response_to_events(
    payload: dict[str, Any],
    *,
    requested_model: str | None = None,
    provider_name: str | None = None,
    endpoint: str = "https://openrouter.ai/api/v1",
    request_id: str | None = None,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    observed_at = timestamp or _now()
    gateway = _gateway_entity("openrouter", endpoint)
    native_id = _request_id(payload, request_id)
    resolved_model = payload.get("model")
    attrs = _usage_attributes(payload)
    if isinstance(requested_model, str) and requested_model:
        attrs["requested_model"] = requested_model
    if isinstance(resolved_model, str) and resolved_model:
        attrs["resolved_model"] = resolved_model
    if isinstance(provider_name, str) and provider_name:
        attrs["provider_name"] = provider_name
    request = _entity(
        "inference_request",
        f"inference-request:openrouter:{native_id}",
        name=native_id,
        attributes={"gateway": "openrouter", **attrs},
    )
    events = [
        _event(
            timestamp=observed_at,
            event_type="inference_gateway.openrouter.response.observed",
            relation="SERVED_INFERENCE",
            source=gateway,
            target=request,
            gateway="openrouter",
            attributes=attrs,
        )
    ]
    if isinstance(requested_model, str) and requested_model:
        events.append(
            _event(
                timestamp=observed_at,
                event_type="inference_gateway.openrouter.model.requested",
                relation="REQUESTED_MODEL",
                source=request,
                target=_model_entity(requested_model),
                gateway="openrouter",
                attributes=attrs,
            )
        )
    if isinstance(resolved_model, str) and resolved_model:
        events.append(
            _event(
                timestamp=observed_at,
                event_type="inference_gateway.openrouter.model.resolved",
                relation="ROUTED_TO_MODEL",
                source=request,
                target=_model_entity(resolved_model),
                gateway="openrouter",
                attributes=attrs,
            )
        )
    if isinstance(provider_name, str) and provider_name:
        events.append(
            _event(
                timestamp=observed_at,
                event_type="inference_gateway.openrouter.provider.resolved",
                relation="ROUTED_TO_PROVIDER",
                source=request,
                target=_provider_entity(provider_name),
                gateway="openrouter",
                attributes=attrs,
            )
        )
    return events


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
