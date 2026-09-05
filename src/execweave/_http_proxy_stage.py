from __future__ import annotations

from typing import Any

from . import _http_proxy_base as _base
from . import model_runtime_full_fidelity as _runtime_ff
from . import openai_compatible_full_fidelity as _openai_ff
from ._http_proxy_base import *  # noqa: F403


# OpenAI-compatible request config is request-side evidence too. Without this relation
# in the phase set it was emitted only after the response arrived, then duplicated by
# the two-stage proxy capture.
_base._REQUEST_RELATIONS = frozenset(
    set(_base._REQUEST_RELATIONS) | {"OBSERVED_PROVIDER_REQUEST_CONFIG"}
)
_ORIGINAL_RECORD_EXCHANGE = _base.record_exchange_fail_open


def _request_events_openai(
    config: ProxyConfig,  # noqa: F405
    request: dict[str, Any],
    store,
    exchange_id: str,
) -> list[dict[str, Any]]:
    observed_at = _openai_ff._now()
    safe_endpoint = _openai_ff.sanitize_openai_compatible_endpoint(config.upstream)
    source = _openai_ff._request_entity(
        {},
        endpoint=safe_endpoint,
        provider_name=config.provider_name,
        request_id=exchange_id,
        observed_at=observed_at,
    )
    common = {
        "store": store,
        "timestamp": observed_at,
        "provider_name": config.provider_name,
        "source": source,
        "evidence_source": "localhost_http_proxy",
        "attribution": "execweave_http_proxy",
        "attributes": {},
    }
    events = [
        _openai_ff._content_event(
            **common,
            value=request,
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
        if key in request:
            events.append(
                _openai_ff._content_event(
                    **common,
                    value=request[key],
                    content_kind=f"openai_compatible.request_{key}",
                    relation=relation,
                    observed_field=f"request.{key}",
                )
            )
    for key in ("system", "instructions"):
        if key in request:
            events.append(
                _openai_ff._content_event(
                    **common,
                    value=request[key],
                    content_kind=f"openai_compatible.{key}_context",
                    relation="OBSERVED_SYSTEM_CONTEXT",
                    observed_field=f"request.{key}",
                )
            )
    for key in ("tools", "functions"):
        if key in request:
            events.append(
                _openai_ff._content_event(
                    **common,
                    value=request[key],
                    content_kind=f"openai_compatible.{key}",
                    relation="OBSERVED_TOOL_DEFINITIONS",
                    observed_field=f"request.{key}",
                )
            )
    tool_results = _openai_ff._tool_results(request)
    if tool_results:
        events.append(
            _openai_ff._content_event(
                **common,
                value=tool_results,
                content_kind="openai_compatible.tool_results",
                relation="OBSERVED_TOOL_RESULT_MESSAGES",
                observed_field="request.tool_results",
            )
        )
    request_config = {
        key: value for key, value in request.items() if key not in _openai_ff._REQUEST_CONTENT_KEYS
    }
    if request_config:
        events.append(
            _openai_ff._content_event(
                **common,
                value=request_config,
                content_kind="openai_compatible.request_config",
                relation="OBSERVED_PROVIDER_REQUEST_CONFIG",
                observed_field="request.provider_facing_config",
            )
        )
    return events


def _request_events_ollama(
    config: ProxyConfig,  # noqa: F405
    request: dict[str, Any],
    store,
    exchange_id: str,
) -> list[dict[str, Any]]:
    observed_at = _runtime_ff._now()
    safe_endpoint = _runtime_ff.sanitize_endpoint(config.upstream)
    source = _runtime_ff._request_entity(
        "ollama", {}, endpoint=safe_endpoint, request_id=exchange_id
    )
    common = {
        "store": store,
        "timestamp": observed_at,
        "runtime": "ollama",
        "source": source,
        "evidence_source": "localhost_http_proxy",
        "attribution": "execweave_http_proxy",
        "attributes": {},
    }
    events = [
        _runtime_ff._content_event(
            **common,
            value=request,
            content_kind="model_runtime.ollama.request",
            relation="OBSERVED_INFERENCE_REQUEST",
            observed_field="request",
        )
    ]
    if "messages" in request:
        events.append(
            _runtime_ff._content_event(
                **common,
                value=request["messages"],
                content_kind="model_runtime.ollama.request_messages",
                relation="OBSERVED_INFERENCE_REQUEST_MESSAGES",
                observed_field="request.messages",
            )
        )
        tool_results = _runtime_ff._tool_result_messages(request["messages"])
        if tool_results:
            events.append(
                _runtime_ff._content_event(
                    **common,
                    value=tool_results,
                    content_kind="model_runtime.ollama.tool_result_messages",
                    relation="OBSERVED_TOOL_RESULT_MESSAGES",
                    observed_field="request.messages[role=tool|function]",
                )
            )
    if "prompt" in request:
        events.append(
            _runtime_ff._content_event(
                **common,
                value=request["prompt"],
                content_kind="model_runtime.ollama.request_prompt",
                relation="OBSERVED_INFERENCE_REQUEST_PROMPT",
                observed_field="request.prompt",
            )
        )
    if "input" in request:
        events.append(
            _runtime_ff._content_event(
                **common,
                value=request["input"],
                content_kind="model_runtime.ollama.request_input",
                relation="OBSERVED_INFERENCE_REQUEST_INPUT",
                observed_field="request.input",
            )
        )
    if "system" in request:
        events.append(
            _runtime_ff._content_event(
                **common,
                value=request["system"],
                content_kind="model_runtime.ollama.system_context",
                relation="OBSERVED_SYSTEM_CONTEXT",
                observed_field="request.system",
            )
        )
    if "tools" in request:
        events.append(
            _runtime_ff._content_event(
                **common,
                value=request["tools"],
                content_kind="model_runtime.ollama.tool_definitions",
                relation="OBSERVED_TOOL_DEFINITIONS",
                observed_field="request.tools",
            )
        )
    request_config = _runtime_ff._request_config(request)
    if request_config:
        events.append(
            _runtime_ff._content_event(
                **common,
                value=request_config,
                content_kind="model_runtime.ollama.request_config",
                relation="OBSERVED_INFERENCE_REQUEST_CONFIG",
                observed_field="request.provider_facing_config",
            )
        )
    return events


def _stamp_phase(
    events: list[dict[str, Any]],
    *,
    config: ProxyConfig,  # noqa: F405
    method: str,
    request_path: str,
    status: int | None,
    phase: str,
) -> None:
    for event in events:
        attrs = event.setdefault("attributes", {})
        attrs.update(
            {
                "observation_scope": "localhost_http_proxy",
                "caller_supplied_exchange": False,
                "wire_interception_asserted": True,
                "transport_relay_observed": True,
                "evidence_source": "localhost_http_proxy",
                "attribution": "execweave_http_proxy",
                "proxy_method": method,
                "proxy_request_path": request_path,
                "proxy_status": status,
                "proxy_upstream": _base.sanitize_upstream(config.upstream),
                "causal": False,
                "inferred": False,
                "capture_phase": phase,
                "response_observed": phase == "response",
            }
        )


def _record_request_phase(
    config: ProxyConfig,  # noqa: F405
    *,
    exchange_id: str,
    request_body: bytes,
    request_content_type: str | None,
    method: str,
    request_path: str,
    status: int | None,
) -> bool:
    request = _base._json(request_body)
    if not isinstance(request, dict):
        request = {}
    if not any(key in request for key in ("messages", "prompt", "input")):
        return False
    store = _base.FullFidelityContentStore(config.sidecar.parent)
    if config.mode == "ollama":
        events = _request_events_ollama(config, request, store, exchange_id)
        provider = "ollama"
    else:
        events = _request_events_openai(config, request, store, exchange_id)
        provider = config.provider_name
    _stamp_phase(
        events,
        config=config,
        method=method,
        request_path=request_path,
        status=status,
        phase="request",
    )
    source = events[0]["source"]
    source.setdefault("attributes", {})["observed_at"] = events[0]["timestamp"]
    events.append(
        _base._raw_event(
            store,
            source,
            provider,
            request_body,
            kind="http_proxy.request_body_raw",
            relation="OBSERVED_INFERENCE_REQUEST_RAW",
            field="request.body.raw",
            media_type=request_content_type,
        )
    )
    _base.append_openai_compatible_records(config.sidecar, events)
    return True


def _record_response_phase(
    config: ProxyConfig,  # noqa: F405
    *,
    exchange_id: str,
    request_body: bytes,
    response_body: bytes,
    response_content_type: str | None,
    method: str,
    request_path: str,
    status: int | None,
) -> bool:
    request = _base._json(request_body)
    if not isinstance(request, dict):
        request = {}
    chunks = _base._stream_items(response_body, response_content_type, request)
    assembled = (
        _base.assemble_stream(
            chunks,
            wire_format=_base.OLLAMA_NDJSON
            if config.mode == "ollama"
            else _base.OPENAI_CHAT_DELTA,
        )
        if chunks
        else None
    )
    response = assembled.response if assembled is not None else _base._json(response_body)
    if not isinstance(response, dict):
        response = {}
    store = _base.FullFidelityContentStore(config.sidecar.parent)
    if config.mode == "ollama":
        events = _runtime_ff.runtime_response_to_content_events(
            response,
            store=store,
            runtime="ollama",
            endpoint=config.upstream,
            request_id=exchange_id,
        )
        provider = "ollama"
    else:
        events = _openai_ff.response_to_content_events(
            response,
            store=store,
            endpoint=config.upstream,
            provider_name=config.provider_name,
            request_id=exchange_id,
        )
        provider = config.provider_name
    _stamp_phase(
        events,
        config=config,
        method=method,
        request_path=request_path,
        status=status,
        phase="response",
    )
    for event in events:
        attrs = event.setdefault("attributes", {})
        if assembled is not None:
            attrs.update(assembled.attributes())
            attrs["stream_tool_arguments_parse_cleanly"] = _base.arguments_parse_cleanly(response)
            if assembled.notes:
                attrs["stream_assembly_notes"] = assembled.notes
    source = events[0]["source"]
    source.setdefault("attributes", {})["observed_at"] = events[0]["timestamp"]
    events.append(
        _base._raw_event(
            store,
            source,
            provider,
            response_body,
            kind="http_proxy.response_body_raw",
            relation="OBSERVED_INFERENCE_RESPONSE_RAW",
            field="response.body.raw",
            media_type=response_content_type,
        )
    )
    if chunks and not _base._has_relation(events, "OBSERVED_INFERENCE_STREAM_CHUNKS"):
        kind = (
            "http_proxy.ollama_stream_chunks"
            if config.mode == "ollama"
            else "http_proxy.stream_chunks"
        )
        reference = store.put_json(chunks, content_kind=kind)
        events.append(
            _base.content_observation_event(
                timestamp=events[0]["timestamp"],
                provider=provider,
                source=source,
                reference=reference,
                relation="OBSERVED_INFERENCE_STREAM_CHUNKS",
                observed_field="response.stream_chunks",
                evidence_source="localhost_http_proxy",
                attribution="execweave_http_proxy",
                event_type="http_proxy.content.observed",
                attributes={"causal": False, "inferred": False},
            )
        )
    calls = (
        []
        if _base._has_relation(events, "OBSERVED_ASSISTANT_TOOL_CALLS")
        else _base.assembled_tool_calls(response)
        if assembled is not None
        else _base._tool_calls(response)
    )
    if calls:
        reference = store.put_json(calls, content_kind="http_proxy.response_tool_calls")
        events.append(
            _base.content_observation_event(
                timestamp=events[0]["timestamp"],
                provider=provider,
                source=source,
                reference=reference,
                relation="OBSERVED_ASSISTANT_TOOL_CALLS",
                observed_field="response.tool_calls",
                evidence_source="localhost_http_proxy",
                attribution="execweave_http_proxy",
                event_type="http_proxy.content.observed",
                attributes={"causal": False, "inferred": False},
            )
        )
    _base.append_openai_compatible_records(config.sidecar, events)
    return True


def record_exchange_fail_open(
    config: ProxyConfig,  # noqa: F405
    *,
    exchange_id: str,
    request_body: bytes,
    request_content_type: str | None,
    response_body: bytes,
    response_content_type: str | None,
    method: str,
    request_path: str,
    status: int | None,
    request_only: bool = False,
    request_recorded: bool = False,
) -> bool:
    try:
        if request_only:
            return _record_request_phase(
                config,
                exchange_id=exchange_id,
                request_body=request_body,
                request_content_type=request_content_type,
                method=method,
                request_path=request_path,
                status=status,
            )
        if request_recorded:
            return _record_response_phase(
                config,
                exchange_id=exchange_id,
                request_body=request_body,
                response_body=response_body,
                response_content_type=response_content_type,
                method=method,
                request_path=request_path,
                status=status,
            )
        return _ORIGINAL_RECORD_EXCHANGE(
            config,
            exchange_id=exchange_id,
            request_body=request_body,
            request_content_type=request_content_type,
            response_body=response_body,
            response_content_type=response_content_type,
            method=method,
            request_path=request_path,
            status=status,
            request_only=False,
            request_recorded=False,
        )
    except Exception as exc:
        print(f"ExecWeave HTTP proxy capture warning: {exc}", file=_base.sys.stderr)
        return False


def create_proxy_server(
    *,
    listen_host: str,
    listen_port: int,
    config: ProxyConfig,  # noqa: F405
    recorder=None,
):
    """Create a proxy with the staged recorder as the actual runtime default.

    The base function's default argument was bound before this acceptance layer replaced
    the recorder. Passing it explicitly is required so the handler's identity check
    enters request-phase capture before it waits for model response headers.
    """
    actual = record_exchange_fail_open if recorder is None else recorder
    return _base.create_proxy_server(
        listen_host=listen_host,
        listen_port=listen_port,
        config=config,
        recorder=actual,
    )


# Handler methods were defined in the base module, so patch its global too. This keeps
# identity checks inside _relay aligned with the recorder explicitly passed above.
_base.record_exchange_fail_open = record_exchange_fail_open


def __getattr__(name: str):
    return getattr(_base, name)
