from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .content_store import FullFidelityContentStore
from .inference_gateway import (
    append_gateway_records,
    litellm_response_to_events,
    sanitize_gateway_endpoint,
)
from .inference_gateway_full_fidelity import litellm_callback_to_content_events

try:
    from litellm.integrations.custom_logger import CustomLogger as _LiteLLMCustomLogger
except ImportError:  # ExecWeave does not require LiteLLM unless this callback is loaded by it.
    class _LiteLLMCustomLogger:  # type: ignore[no-redef]
        pass


_SEMANTIC_ENV = "EXECWEAVE_SEMANTIC_SIDECAR"
_ENDPOINT_ENV = "EXECWEAVE_LITELLM_ENDPOINT"
_DEFAULT_ENDPOINT = "http://localhost:4000"


def _mapping(value: object) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        return dumped if isinstance(dumped, dict) else None
    as_dict = getattr(value, "dict", None)
    if callable(as_dict):
        dumped = as_dict()
        return dumped if isinstance(dumped, dict) else None
    return None


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _number(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _timestamp(value: object) -> str | None:
    if isinstance(value, datetime):
        observed = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return observed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat().replace(
                "+00:00", "Z"
            )
        except (OSError, OverflowError, ValueError):
            return None
    return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _gateway_endpoint() -> str:
    candidate = os.environ.get(_ENDPOINT_ENV) or os.environ.get("PROXY_BASE_URL") or _DEFAULT_ENDPOINT
    try:
        return sanitize_gateway_endpoint(candidate)
    except ValueError:
        return _DEFAULT_ENDPOINT


def standard_logging_to_events(
    payload: dict[str, Any],
    *,
    endpoint: str | None = None,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    """Convert LiteLLM StandardLoggingPayload into privacy-safe gateway evidence.

    The semantic summary intentionally stays limited to routing, usage, cost, cache, and
    latency fields. Full request/response evidence is appended separately by the callback.
    """
    call_id = _text(payload.get("id"))
    if call_id is None:
        raise ValueError("LiteLLM standard logging payload requires id")

    model = _text(payload.get("model"))
    model_group = _text(payload.get("model_group"))
    deployment_id = _text(payload.get("model_id"))

    usage: dict[str, Any] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = payload.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            usage[key] = value
    response_cost = _number(payload.get("response_cost"))
    if response_cost is not None:
        usage["cost"] = response_cost

    response_payload: dict[str, Any] = {"id": call_id, "usage": usage}
    if model is not None:
        response_payload["model"] = model

    records = litellm_response_to_events(
        response_payload,
        requested_model=model_group,
        resolved_model=model,
        deployment_id=deployment_id,
        endpoint=sanitize_gateway_endpoint(endpoint or _gateway_endpoint()),
        request_id=call_id,
        timestamp=timestamp or _timestamp(payload.get("endTime")),
    )

    extra: dict[str, Any] = {"litellm_standard_logging": True}
    call_type = _text(payload.get("call_type"))
    if call_type is not None:
        extra["call_type"] = call_type
    response_time = _number(payload.get("response_time"))
    if response_time is not None:
        extra["response_time_seconds"] = float(response_time)
    cache_hit = payload.get("cache_hit")
    if isinstance(cache_hit, bool):
        extra["cache_hit"] = cache_hit

    for record in records:
        attributes = record.get("attributes")
        if isinstance(attributes, dict):
            attributes.update(extra)
        target = record.get("target")
        if record.get("relation") == "SERVED_INFERENCE" and isinstance(target, dict):
            target_attributes = target.get("attributes")
            if isinstance(target_attributes, dict):
                target_attributes.update(extra)
    return records


class ExecWeaveLiteLLMCallback(_LiteLLMCustomLogger):
    """LiteLLM callback that appends semantic summary then full source-exposed evidence."""

    def _emit(self, kwargs: object, response_obj: object, end_time: object = None) -> None:
        sidecar_value = os.environ.get(_SEMANTIC_ENV)
        if not sidecar_value:
            return
        sidecar = Path(sidecar_value).expanduser().resolve()
        try:
            callback_kwargs = _mapping(kwargs)
            if callback_kwargs is None:
                return
            standard = _mapping(callback_kwargs.get("standard_logging_object"))
            if standard is None:
                return
            callback_kwargs = {**callback_kwargs, "standard_logging_object": standard}
            observed_at = _timestamp(end_time) or _now()
            records = standard_logging_to_events(standard, timestamp=observed_at)
            append_gateway_records(sidecar, records)
        except Exception:
            # Observability must never alter the LiteLLM request outcome.
            return

        try:
            mapped_response = _mapping(response_obj)
            full_response: object = mapped_response if mapped_response is not None else response_obj
            content_records = litellm_callback_to_content_events(
                callback_kwargs,
                full_response,
                store=FullFidelityContentStore(sidecar.parent),
                endpoint=_gateway_endpoint(),
                timestamp=observed_at,
            )
            for record in content_records:
                attributes = record.get("attributes")
                if isinstance(attributes, dict):
                    attributes.setdefault("gateway", "litellm")
            append_gateway_records(sidecar, content_records)
        except Exception:
            # Keep the already-written semantic summary if full-fidelity storage fails.
            return

    def log_success_event(
        self,
        kwargs: object,
        response_obj: object,
        start_time: object,
        end_time: object,
    ) -> None:
        del start_time
        self._emit(kwargs, response_obj, end_time)

    async def async_log_success_event(
        self,
        kwargs: object,
        response_obj: object,
        start_time: object,
        end_time: object,
    ) -> None:
        del start_time
        await asyncio.to_thread(self._emit, kwargs, response_obj, end_time)


execweave_litellm_callback = ExecWeaveLiteLLMCallback()
