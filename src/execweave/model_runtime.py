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


def _entity(
    entity_type: str,
    entity_id: str,
    *,
    name: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {"type": entity_type, "id": entity_id, "name": name, "attributes": attributes or {}}


def _event(
    *,
    timestamp: str,
    event_type: str,
    relation: str,
    source: dict[str, Any],
    target: dict[str, Any],
    runtime: str,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged = {
        "backend": "model_runtime",
        "attribution": "provider_api",
        "evidence_source": "model_runtime_api",
        "provider": runtime,
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


def sanitize_endpoint(endpoint: str) -> str:
    split = urlsplit(endpoint)
    if split.scheme not in {"http", "https"} or not split.hostname:
        raise ValueError("model runtime endpoint must be an http(s) URL")
    host = split.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if split.port is not None:
        host = f"{host}:{split.port}"
    path = split.path.rstrip("/")
    return urlunsplit((split.scheme, host, path, "", ""))


def _runtime_entity(runtime: str, endpoint: str) -> dict[str, Any]:
    safe_endpoint = sanitize_endpoint(endpoint)
    digest = hashlib.sha256(safe_endpoint.encode("utf-8")).hexdigest()[:24]
    return _entity(
        "model_runtime",
        f"model-runtime:{runtime}:{digest}",
        name=runtime,
        attributes={"provider": runtime, "endpoint": safe_endpoint},
    )


def _model_entity(runtime: str, model: str) -> dict[str, Any]:
    return _entity(
        "model",
        f"model:{runtime}:{model}",
        name=model,
        attributes={"provider": runtime},
    )


def _request_id(runtime: str, payload: dict[str, Any], explicit: str | None) -> str:
    if explicit:
        return explicit
    native = payload.get("id")
    if isinstance(native, str) and native:
        return native
    seed = {
        "model": payload.get("model"),
        "created_at": payload.get("created_at"),
        "created": payload.get("created"),
        "done_reason": payload.get("done_reason"),
        "total_duration": payload.get("total_duration"),
        "prompt_eval_count": payload.get("prompt_eval_count"),
        "eval_count": payload.get("eval_count"),
    }
    raw = json.dumps(seed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256((runtime + "\0" + raw).encode("utf-8", errors="replace")).hexdigest()[:32]


def _inference_entities(
    runtime: str,
    payload: dict[str, Any],
    *,
    endpoint: str,
    request_id: str | None,
    timestamp: str,
    attributes: dict[str, Any],
) -> list[dict[str, Any]]:
    runtime_entity = _runtime_entity(runtime, endpoint)
    request_native_id = _request_id(runtime, payload, request_id)
    request = _entity(
        "inference_request",
        f"inference-request:{runtime}:{request_native_id}",
        name=request_native_id,
        attributes={"provider": runtime, **attributes},
    )
    events = [
        _event(
            timestamp=timestamp,
            event_type=f"model_runtime.{runtime}.inference.observed",
            relation="SERVED_INFERENCE",
            source=runtime_entity,
            target=request,
            runtime=runtime,
            attributes=attributes,
        )
    ]
    model = payload.get("model")
    if isinstance(model, str) and model:
        events.append(
            _event(
                timestamp=timestamp,
                event_type=f"model_runtime.{runtime}.model.used",
                relation="USED_MODEL",
                source=request,
                target=_model_entity(runtime, model),
                runtime=runtime,
                attributes=attributes,
            )
        )
    return events


def ollama_response_to_events(
    payload: dict[str, Any],
    *,
    endpoint: str = "http://localhost:11434",
    request_id: str | None = None,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(payload.get("model"), str) or not payload.get("model"):
        raise ValueError("Ollama response requires model")
    attrs: dict[str, Any] = {"protocol": "ollama_native"}
    mapping = {
        "done_reason": "finish_reason",
        "total_duration": "total_duration_ns",
        "load_duration": "load_duration_ns",
        "prompt_eval_count": "prompt_tokens",
        "prompt_eval_duration": "prompt_eval_duration_ns",
        "eval_count": "completion_tokens",
        "eval_duration": "completion_duration_ns",
    }
    for source, target in mapping.items():
        value = payload.get(source)
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            attrs[target] = value
    return _inference_entities(
        "ollama",
        payload,
        endpoint=endpoint,
        request_id=request_id,
        timestamp=timestamp or _now(),
        attributes=attrs,
    )


def llamacpp_response_to_events(
    payload: dict[str, Any],
    *,
    endpoint: str = "http://localhost:8080",
    request_id: str | None = None,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    attrs: dict[str, Any] = {"protocol": "openai_compatible"}
    usage = payload.get("usage")
    if isinstance(usage, dict):
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                attrs[key] = value
        details = usage.get("prompt_tokens_details")
        if isinstance(details, dict):
            cached = details.get("cached_tokens")
            if isinstance(cached, int) and not isinstance(cached, bool):
                attrs["cached_prompt_tokens"] = cached
    timings = payload.get("timings")
    if isinstance(timings, dict):
        for key in (
            "cache_n",
            "prompt_n",
            "prompt_ms",
            "prompt_per_token_ms",
            "prompt_per_second",
            "predicted_n",
            "predicted_ms",
            "predicted_per_token_ms",
            "predicted_per_second",
        ):
            value = timings.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                attrs[f"timing_{key}"] = value
    return _inference_entities(
        "llamacpp",
        payload,
        endpoint=endpoint,
        request_id=request_id,
        timestamp=timestamp or _now(),
        attributes=attrs,
    )


def ollama_ps_to_events(
    payload: dict[str, Any],
    *,
    endpoint: str = "http://localhost:11434",
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    models = payload.get("models")
    if not isinstance(models, list):
        raise ValueError("Ollama /api/ps response requires models")
    observed_at = timestamp or _now()
    runtime = _runtime_entity("ollama", endpoint)
    events: list[dict[str, Any]] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        name = item.get("model") or item.get("name")
        if not isinstance(name, str) or not name:
            continue
        attrs: dict[str, Any] = {}
        for key in ("size", "size_vram", "context_length", "expires_at", "digest"):
            value = item.get(key)
            if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                attrs[key] = value
        details = item.get("details")
        if isinstance(details, dict):
            for key in ("format", "family", "parameter_size", "quantization_level"):
                value = details.get(key)
                if isinstance(value, str) and value:
                    attrs[key] = value
        events.append(
            _event(
                timestamp=observed_at,
                event_type="model_runtime.ollama.model.loaded",
                relation="LOADED_MODEL",
                source=runtime,
                target=_model_entity("ollama", name),
                runtime="ollama",
                attributes=attrs,
            )
        )
    return events


def llamacpp_models_to_events(
    payload: dict[str, Any],
    *,
    endpoint: str = "http://localhost:8080",
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("llama.cpp /v1/models response requires data")
    observed_at = timestamp or _now()
    runtime = _runtime_entity("llamacpp", endpoint)
    events: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        if not isinstance(model_id, str) or not model_id:
            continue
        attrs: dict[str, Any] = {}
        owned_by = item.get("owned_by")
        if isinstance(owned_by, str) and owned_by:
            attrs["owned_by"] = owned_by
        meta = item.get("meta")
        if isinstance(meta, dict):
            for key in ("vocab_type", "n_vocab", "n_ctx_train", "n_embd", "n_params", "size"):
                value = meta.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    attrs[key] = value
        events.append(
            _event(
                timestamp=observed_at,
                event_type="model_runtime.llamacpp.model.served",
                relation="SERVES_MODEL",
                source=runtime,
                target=_model_entity("llamacpp", model_id),
                runtime="llamacpp",
                attributes=attrs,
            )
        )
    return events


def llamacpp_metrics_to_events(
    metrics_text: str,
    *,
    endpoint: str = "http://localhost:8080",
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    values: dict[str, float] = {}
    for raw_line in metrics_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "{" in line:
            continue
        parts = line.split()
        if len(parts) != 2 or not parts[0].startswith("llamacpp:"):
            continue
        try:
            values[parts[0]] = float(parts[1])
        except ValueError:
            continue
    if not values:
        return []
    observed_at = timestamp or _now()
    runtime = _runtime_entity("llamacpp", endpoint)
    raw = json.dumps(values, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256((observed_at + "\0" + raw).encode("utf-8")).hexdigest()[:24]
    snapshot = _entity(
        "model_runtime_snapshot",
        f"model-runtime-snapshot:llamacpp:{digest}",
        name="llama.cpp metrics",
        attributes={"provider": "llamacpp", "metrics": values},
    )
    return [
        _event(
            timestamp=observed_at,
            event_type="model_runtime.llamacpp.metrics.observed",
            relation="REPORTED_METRICS",
            source=runtime,
            target=snapshot,
            runtime="llamacpp",
            attributes={"metric_count": len(values)},
        )
    ]


def append_model_runtime_records(path: str | Path, records: list[dict[str, Any]]) -> Path:
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
                raise TimeoutError(f"timed out waiting for model runtime sidecar lock: {lock_dir}")
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
