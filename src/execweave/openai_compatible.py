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


def sanitize_openai_compatible_endpoint(endpoint: str) -> str:
    split = urlsplit(endpoint)
    if split.scheme not in {"http", "https"} or not split.hostname:
        raise ValueError("OpenAI-compatible endpoint must be an http(s) URL")
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


def _endpoint_digest(endpoint: str) -> str:
    safe_endpoint = sanitize_openai_compatible_endpoint(endpoint)
    return hashlib.sha256(safe_endpoint.encode("utf-8")).hexdigest()[:24]


def _api_entity(provider_name: str, endpoint: str) -> dict[str, Any]:
    safe_endpoint = sanitize_openai_compatible_endpoint(endpoint)
    digest = _endpoint_digest(safe_endpoint)
    return _entity(
        "inference_api",
        f"inference-api:openai-compatible:{digest}",
        name=provider_name,
        attributes={
            "protocol": "openai_compatible",
            "provider_name": provider_name,
            "endpoint": safe_endpoint,
        },
    )


def _model_entity(provider_name: str, endpoint: str, model: str) -> dict[str, Any]:
    endpoint_scope = _endpoint_digest(endpoint)
    return _entity(
        "model",
        f"model:openai-compatible:{endpoint_scope}:{model}",
        name=model,
        attributes={
            "catalog_id": model,
            "provider_name": provider_name,
            "endpoint_scope": endpoint_scope,
            "identity_scope": "openai_compatible_endpoint",
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
        "model": payload.get("model"),
        "created": payload.get("created"),
        "usage": payload.get("usage"),
    }
    raw = json.dumps(seed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    occurrence = "\0".join(("openai-compatible", endpoint_scope, observed_at, raw))
    digest = hashlib.sha256(occurrence.encode("utf-8", errors="replace")).hexdigest()[:32]
    return digest, "execweave_observation"


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
    for detail_key in ("prompt_tokens_details", "input_tokens_details"):
        details = usage.get(detail_key)
        if isinstance(details, dict):
            _copy_int(details, "cached_tokens", "cached_prompt_tokens", attrs)
    for detail_key in ("completion_tokens_details", "output_tokens_details"):
        details = usage.get(detail_key)
        if isinstance(details, dict):
            _copy_int(details, "reasoning_tokens", "reasoning_tokens", attrs)
    return attrs


def response_to_events(
    payload: dict[str, Any],
    *,
    endpoint: str,
    provider_name: str = "openai-compatible",
    requested_model: str | None = None,
    request_id: str | None = None,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    observed_at = timestamp or _now()
    safe_endpoint = sanitize_openai_compatible_endpoint(endpoint)
    endpoint_scope = _endpoint_digest(safe_endpoint)
    api = _api_entity(provider_name, safe_endpoint)
    native_id, request_id_source = _request_identity(
        payload,
        request_id,
        endpoint_scope=endpoint_scope,
        observed_at=observed_at,
    )
    attrs = _usage_attributes(payload)
    attrs.update(
        {
            "backend": "openai_compatible_api",
            "attribution": "direct_api_response",
            "evidence_source": "openai_compatible_response",
            "provider_name": provider_name,
            "endpoint_scope": endpoint_scope,
            "request_id_source": request_id_source,
            "causal": False,
            "inferred": False,
        }
    )
    request = _entity(
        "inference_request",
        f"inference-request:openai-compatible:{endpoint_scope}:{native_id}",
        name=native_id,
        attributes={
            "provider_name": provider_name,
            "endpoint_scope": endpoint_scope,
            "request_id_source": request_id_source,
            **_usage_attributes(payload),
        },
    )
    events = [
        {
            "timestamp": observed_at,
            "event_type": "openai_compatible.response.observed",
            "relation": "SERVED_INFERENCE",
            "source": api,
            "target": request,
            "attributes": attrs,
        }
    ]
    if isinstance(requested_model, str) and requested_model:
        events.append(
            {
                "timestamp": observed_at,
                "event_type": "openai_compatible.model.requested",
                "relation": "REQUESTED_MODEL",
                "source": request,
                "target": _model_entity(provider_name, safe_endpoint, requested_model),
                "attributes": attrs,
            }
        )
    resolved_model = payload.get("model")
    if isinstance(resolved_model, str) and resolved_model:
        events.append(
            {
                "timestamp": observed_at,
                "event_type": "openai_compatible.model.used",
                "relation": "USED_MODEL",
                "source": request,
                "target": _model_entity(provider_name, safe_endpoint, resolved_model),
                "attributes": attrs,
            }
        )
    return events


def append_openai_compatible_records(
    path: str | Path, records: list[dict[str, Any]]
) -> Path:
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
                    f"timed out waiting for OpenAI-compatible sidecar lock: {lock_dir}"
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
