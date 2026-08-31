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


def sanitize_anthropic_endpoint(endpoint: str) -> str:
    split = urlsplit(endpoint)
    if split.scheme not in {"http", "https"} or not split.hostname:
        raise ValueError("Anthropic endpoint must be an http(s) URL")
    host = split.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if split.port is not None:
        host = f"{host}:{split.port}"
    return urlunsplit((split.scheme, host, split.path.rstrip("/"), "", ""))


def _endpoint_digest(endpoint: str) -> str:
    safe = sanitize_anthropic_endpoint(endpoint)
    return hashlib.sha256(safe.encode("utf-8")).hexdigest()[:24]


def _entity(
    entity_type: str,
    entity_id: str,
    *,
    name: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {"type": entity_type, "id": entity_id, "name": name, "attributes": attributes or {}}


def _api_entity(endpoint: str) -> dict[str, Any]:
    safe = sanitize_anthropic_endpoint(endpoint)
    return _entity(
        "inference_api",
        f"inference-api:anthropic:{_endpoint_digest(safe)}",
        name="anthropic",
        attributes={
            "protocol": "anthropic_messages",
            "provider_name": "anthropic",
            "endpoint": safe,
        },
    )


def _model_entity(model: str) -> dict[str, Any]:
    return _entity(
        "model",
        f"model:anthropic:{model}",
        name=model,
        attributes={
            "catalog_id": model,
            "provider_name": "anthropic",
            "identity_scope": "provider:anthropic",
        },
    )


def _request_identity(
    payload: dict[str, Any],
    explicit: str | None,
    *,
    endpoint_scope: str,
    observed_at: str,
) -> tuple[str, str]:
    if isinstance(explicit, str) and explicit:
        return explicit, "provided"
    native = payload.get("id")
    if isinstance(native, str) and native:
        return native, "provider_native"
    seed = {
        key: payload.get(key)
        for key in ("model", "type", "role", "stop_reason", "usage")
    }
    raw = json.dumps(seed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    occurrence = "\0".join(("anthropic", endpoint_scope, observed_at, raw))
    digest = hashlib.sha256(occurrence.encode("utf-8", errors="replace")).hexdigest()[:32]
    return digest, "execweave_observation"


def _usage_attributes(payload: dict[str, Any]) -> dict[str, Any]:
    attrs: dict[str, Any] = {"protocol": "anthropic_messages"}
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return attrs
    mapping = (
        ("input_tokens", "prompt_tokens"),
        ("output_tokens", "completion_tokens"),
        ("cache_read_input_tokens", "cached_prompt_tokens"),
        ("cache_creation_input_tokens", "cache_creation_prompt_tokens"),
    )
    for source, target in mapping:
        value = usage.get(source)
        if isinstance(value, int) and not isinstance(value, bool):
            attrs[target] = value
    service_tier = usage.get("service_tier")
    if isinstance(service_tier, str) and service_tier:
        attrs["service_tier"] = service_tier
    server_tool_use = usage.get("server_tool_use")
    if isinstance(server_tool_use, dict):
        attrs["server_tool_use"] = server_tool_use
    return attrs


def response_to_events(
    payload: dict[str, Any],
    *,
    endpoint: str,
    requested_model: str | None = None,
    request_id: str | None = None,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    observed_at = timestamp or _now()
    safe = sanitize_anthropic_endpoint(endpoint)
    endpoint_scope = _endpoint_digest(safe)
    native_id, request_id_source = _request_identity(
        payload,
        request_id,
        endpoint_scope=endpoint_scope,
        observed_at=observed_at,
    )
    attrs = _usage_attributes(payload)
    attrs.update(
        {
            "backend": "anthropic_api",
            "attribution": "direct_api_response",
            "evidence_source": "anthropic_response",
            "provider_name": "anthropic",
            "endpoint_scope": endpoint_scope,
            "request_id_source": request_id_source,
            "causal": False,
            "inferred": False,
        }
    )
    for key in ("stop_reason", "stop_sequence", "type", "role"):
        value = payload.get(key)
        if value is not None:
            attrs[key] = value
    request = _entity(
        "inference_request",
        f"inference-request:anthropic:{endpoint_scope}:{native_id}",
        name=native_id,
        attributes={
            "provider_name": "anthropic",
            "endpoint_scope": endpoint_scope,
            "request_id_source": request_id_source,
            **_usage_attributes(payload),
        },
    )
    events = [
        {
            "timestamp": observed_at,
            "event_type": "anthropic.response.observed",
            "relation": "SERVED_INFERENCE",
            "source": _api_entity(safe),
            "target": request,
            "attributes": attrs,
        }
    ]
    if isinstance(requested_model, str) and requested_model:
        events.append(
            {
                "timestamp": observed_at,
                "event_type": "anthropic.model.requested",
                "relation": "REQUESTED_MODEL",
                "source": request,
                "target": _model_entity(requested_model),
                "attributes": attrs,
            }
        )
    resolved_model = payload.get("model")
    if isinstance(resolved_model, str) and resolved_model:
        events.append(
            {
                "timestamp": observed_at,
                "event_type": "anthropic.model.used",
                "relation": "USED_MODEL",
                "source": request,
                "target": _model_entity(resolved_model),
                "attributes": attrs,
            }
        )
    return events


def append_anthropic_records(path: str | Path, records: list[dict[str, Any]]) -> Path:
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
                raise TimeoutError(
                    f"timed out waiting for Anthropic sidecar lock: {lock_dir}"
                )
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
