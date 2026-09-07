from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from . import _http_proxy_base as _base
from . import _http_proxy_stage as _stage
from . import model_runtime as _runtime_semantic
from . import openai_compatible as _openai_semantic
from ._http_proxy_stage import *  # noqa: F403


_ORIGINAL_REQUEST_EVENTS_OLLAMA = _stage._request_events_ollama
_ORIGINAL_REQUEST_EVENTS_OPENAI = _stage._request_events_openai


def _requested_model_event(
    *,
    config: Any,
    source: dict[str, Any],
    model: str,
    timestamp: str,
) -> dict[str, Any]:
    """Represent the model named by an observed proxy request without guessing usage.

    The request phase has direct wire evidence for the provider-facing ``model`` field.
    Recording it as REQUESTED_MODEL gives the viewer a request-specific model identity
    even when a runtime probe only reports LOADED_MODEL state.  It deliberately does
    not claim USED_MODEL: loaded state and actual request usage are different facts.
    """

    if config.mode == "ollama":
        provider = "ollama"
        target = _runtime_semantic._model_entity("ollama", model)
    else:
        provider = str(config.provider_name or "openai-compatible")
        target = _openai_semantic._model_entity(provider, config.upstream, model)
    return {
        "timestamp": timestamp,
        "event_type": "http_proxy.model.requested",
        "relation": "REQUESTED_MODEL",
        "source": source,
        "target": target,
        "attributes": {
            "backend": "semantic",
            "provider": provider,
            "evidence_source": "localhost_http_proxy",
            "attribution": "execweave_http_proxy",
            "causal": False,
            "inferred": False,
        },
    }


def _append_requested_model(
    events: list[dict[str, Any]],
    *,
    config: Any,
    request: dict[str, Any],
) -> list[dict[str, Any]]:
    model = request.get("model")
    if not isinstance(model, str) or not model.strip():
        return events
    if any(event.get("relation") == "REQUESTED_MODEL" for event in events):
        return events
    if not events:
        return events
    source = events[0].get("source")
    timestamp = events[0].get("timestamp")
    if not isinstance(source, dict) or not isinstance(timestamp, str) or not timestamp:
        return events
    events.append(
        _requested_model_event(
            config=config,
            source=source,
            model=model.strip(),
            timestamp=timestamp,
        )
    )
    return events


def _request_events_ollama(
    config: Any,
    request: dict[str, Any],
    store: Any,
    exchange_id: str,
) -> list[dict[str, Any]]:
    events = _ORIGINAL_REQUEST_EVENTS_OLLAMA(config, request, store, exchange_id)
    return _append_requested_model(events, config=config, request=request)


def _request_events_openai(
    config: Any,
    request: dict[str, Any],
    store: Any,
    exchange_id: str,
) -> list[dict[str, Any]]:
    events = _ORIGINAL_REQUEST_EVENTS_OPENAI(config, request, store, exchange_id)
    return _append_requested_model(events, config=config, request=request)


# The staged recorder resolves these module globals at request time.  Patch only the
# proxy request-event seam so full-fidelity APIs outside the localhost relay keep their
# historical event surface.  The resulting model edge is raw evidence, not a viewer
# fallback, and therefore remains available for audit/model-switch chronology.
_stage._request_events_ollama = _request_events_ollama
_stage._request_events_openai = _request_events_openai


def _safe_http_reason(message: str | None) -> str | None:
    """Return a single-line HTTP reason phrase that BaseHTTPRequestHandler can encode."""
    if message is None:
        return None
    single_line = " ".join(str(message).splitlines())
    return single_line.encode("latin-1", errors="replace").decode("latin-1")


def _uses_bounded_two_phase_capture(handler: Any) -> bool:
    """Whether this request must publish request evidence before response completion.

    The normal proxy recorder is intrinsically two-phase.  Managed ``ollama serve``
    uses one production-only filtering callback so non-inference routes such as
    ``/api/tags`` keep their historical no-capture behavior.  That callback forwards
    inference exchanges to the same staged recorder, so recognized inference routes
    must use the bounded two-phase relay too; otherwise the base handler waits for the
    full response and Task A evidence (including REQUESTED_MODEL) arrives too late or
    not at all.
    """

    recorder = handler.server.recorder
    if recorder is _base.record_exchange_fail_open:
        return True
    try:
        from .auto_specialized import (
            _OLLAMA_INFERENCE_PATHS,
            _record_ollama_inference_exchange,
        )
    except ImportError:
        return False
    return (
        recorder is _record_ollama_inference_exchange
        and str(handler.command or "").upper() == "POST"
        and urlsplit(str(handler.path or "")).path in _OLLAMA_INFERENCE_PATHS
    )


class ExecWeaveHTTPProxyHandler(_base.ExecWeaveHTTPProxyHandler):
    """Security-equivalent handler used by the staged acceptance relay."""

    def send_error(
        self,
        code: int,
        message: str | None = None,
        explain: str | None = None,
    ) -> None:
        # BaseHTTPRequestHandler writes the status line as latin-1. Windows socket
        # errors can be localized (for example WinError 10061 in Chinese), so a raw
        # exception string here can turn a recoverable 502 into UnicodeEncodeError
        # and an EOF at the client. Preserve the diagnostic shape but fail closed to
        # an encodable, single-line reason phrase.
        super().send_error(code, _safe_http_reason(message), explain)

    def do_CONNECT(self) -> None:
        self.send_error(405, "CONNECT is disabled; ExecWeave does not perform TLS MITM")

    def _relay(self) -> None:
        # The product default uses file-backed response capture so raw full-fidelity
        # evidence does not require retaining the entire provider response in RAM.
        # The managed Ollama inference filter is also two-phase on its recognized
        # routes; unrelated custom recorder callbacks keep the historical one-call API.
        if _uses_bounded_two_phase_capture(self):
            from ._http_proxy_bounded import relay_default

            relay_default(self)
            return
        super()._relay()


# The base server resolves this module global when each server instance is created.
# Point it at the handler whose CONNECT refusal is visible to the release red-line
# guard, so the checked implementation and the runtime implementation are the same.
_base.ExecWeaveHTTPProxyHandler = ExecWeaveHTTPProxyHandler


def __getattr__(name: str):
    return getattr(_stage, name)
