from __future__ import annotations

import http.client
import itertools
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterator

from . import _http_proxy_base as _base
from . import _http_proxy_stage as _stage
from . import model_runtime_full_fidelity as _runtime_ff
from . import openai_compatible_full_fidelity as _openai_ff
from . import stream_assembly as _assembly


def _temp_path(prefix: str, suffix: str) -> tuple[int, Path]:
    fd, name = tempfile.mkstemp(prefix=prefix, suffix=suffix)
    return fd, Path(name)


class _ResponseCapture:
    def __init__(self) -> None:
        fd, self.raw_path = _temp_path(".execweave-http-response-", ".bin")
        self._handle = os.fdopen(fd, "wb")
        self._closed = False

    def write(self, payload: bytes) -> None:
        self._handle.write(payload)

    def finish(self) -> None:
        if self._closed:
            return
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._handle.close()
        self._closed = True

    def cleanup(self) -> None:
        if not self._closed:
            try:
                self._handle.close()
            except OSError:
                pass
            self._closed = True
        self.raw_path.unlink(missing_ok=True)


def _iter_stream_items(
    path: Path,
    *,
    content_type: str | None,
    request: dict[str, Any],
) -> Iterator[Any]:
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    sse = media_type == "text/event-stream"
    streaming = request.get("stream") is True
    if not sse and not streaming and media_type not in {
        "application/x-ndjson",
        "application/ndjson",
    }:
        return
    with path.open("rb") as handle:
        for raw in handle:
            if sse:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    yield json.loads(data)
                except json.JSONDecodeError:
                    yield data
                continue
            if not raw.strip():
                continue
            try:
                yield json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                yield raw.decode("utf-8", errors="replace").strip()


def _write_json_value(handle, encoder: json.JSONEncoder, value: Any) -> None:
    for piece in encoder.iterencode(value):
        handle.write(piece)


def _assemble_stream_to_file(
    raw_path: Path,
    *,
    content_type: str | None,
    request: dict[str, Any],
    mode: str,
) -> tuple[_assembly.AssembledStream | None, Path | None]:
    items = _iter_stream_items(raw_path, content_type=content_type, request=request)
    try:
        first = next(items)
    except StopIteration:
        return None, None

    fd, chunks_path = _temp_path(".execweave-http-chunks-", ".json")
    handle = os.fdopen(fd, "w", encoding="utf-8", newline="")
    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    chunk_count = 0
    malformed = 0
    terminated = False
    try:
        handle.write("[")
        if mode == "ollama":
            response: dict[str, Any] = {}
            message_content: list[str] = []
            message_thinking: list[str] = []
            generate_parts: list[str] = []
            tool_calls: list[Any] = []
            role: str | None = None
            saw_message = False
            saw_generate = False
            choices = None
            envelope = None
            usage = None
        else:
            response = {}
            message_content = []
            message_thinking = []
            generate_parts = []
            tool_calls = []
            role = None
            saw_message = False
            saw_generate = False
            choices: dict[int, _assembly._ChoiceAccumulator] | None = {}
            envelope: dict[str, Any] | None = {}
            usage: Any = None

        for item in itertools.chain((first,), items):
            if chunk_count:
                handle.write(",")
            _write_json_value(handle, encoder, item)
            chunk_count += 1
            if not isinstance(item, dict):
                malformed += 1
                continue
            if mode == "ollama":
                for key in ("model", "created_at"):
                    value = item.get(key)
                    if key not in response and value is not None:
                        response[key] = value
                message = item.get("message")
                if isinstance(message, dict):
                    saw_message = True
                    frame_role = message.get("role")
                    if isinstance(frame_role, str) and frame_role and role is None:
                        role = frame_role
                    content = message.get("content")
                    if isinstance(content, str):
                        message_content.append(content)
                    thinking = message.get("thinking")
                    if isinstance(thinking, str):
                        message_thinking.append(thinking)
                    calls = message.get("tool_calls")
                    if isinstance(calls, list):
                        tool_calls.extend(calls)
                generated = item.get("response")
                if isinstance(generated, str):
                    saw_generate = True
                    generate_parts.append(generated)
                if item.get("done") is True:
                    terminated = True
                    for key, value in item.items():
                        if key not in {"message", "response", "model", "created_at"}:
                            response[key] = value
                continue

            assert choices is not None and envelope is not None
            for key in ("id", "model", "system_fingerprint", "created"):
                value = item.get(key)
                if key not in envelope and value is not None:
                    envelope[key] = value
            frame_usage = item.get("usage")
            if isinstance(frame_usage, dict) and frame_usage:
                usage = frame_usage
            raw_choices = item.get("choices")
            if not isinstance(raw_choices, list):
                continue
            for position, raw_choice in enumerate(raw_choices):
                if not isinstance(raw_choice, dict):
                    continue
                raw_index = raw_choice.get("index")
                index = raw_index if isinstance(raw_index, int) else position
                choice = choices.setdefault(index, _assembly._ChoiceAccumulator(index=index))
                delta = raw_choice.get("delta")
                if isinstance(delta, dict):
                    choice.absorb_delta(delta)
                finish_reason = raw_choice.get("finish_reason")
                if finish_reason is not None:
                    choice.finish_reason = finish_reason
                    terminated = True

        handle.write("]")
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()

        if mode == "ollama":
            if saw_message:
                message_payload: dict[str, Any] = {
                    "role": role or "assistant",
                    "content": "".join(message_content),
                }
                if message_thinking:
                    message_payload["thinking"] = "".join(message_thinking)
                if tool_calls:
                    message_payload["tool_calls"] = tool_calls
                response["message"] = message_payload
            if saw_generate:
                response["response"] = "".join(generate_parts)
            response.setdefault("done", terminated)
            wire_format = _assembly.OLLAMA_NDJSON
        else:
            assert choices is not None and envelope is not None
            response = dict(envelope)
            response["object"] = "chat.completion"
            response["choices"] = [choices[index].to_dict() for index in sorted(choices)]
            if usage is not None:
                response["usage"] = usage
            wire_format = _assembly.OPENAI_CHAT_DELTA

        availability, notes = _assembly._availability(
            terminated=terminated,
            malformed=malformed,
        )
        return (
            _assembly.AssembledStream(
                response=response,
                wire_format=wire_format,
                chunk_count=chunk_count,
                malformed_chunks=malformed,
                terminated=terminated,
                availability=availability,
                notes=notes,
            ),
            chunks_path,
        )
    except Exception:
        try:
            handle.close()
        except OSError:
            pass
        chunks_path.unlink(missing_ok=True)
        raise


def _load_response(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _content_event_from_file(
    *,
    store: _base.FullFidelityContentStore,
    source: dict[str, Any],
    provider: str,
    path: Path,
    content_kind: str,
    media_type: str,
    representation: str,
    relation: str,
    observed_field: str,
    transport: bool = False,
) -> dict[str, Any]:
    reference = store.put_file(
        path,
        content_kind=content_kind,
        media_type=media_type,
        representation=representation,
    )
    return _base.content_observation_event(
        timestamp=source.get("attributes", {}).get("observed_at", ""),
        provider=provider,
        source=source,
        reference=reference,
        relation=relation,
        observed_field=observed_field,
        evidence_source="localhost_http_proxy",
        attribution="execweave_http_proxy",
        event_type="http_proxy.content.observed",
        attributes=(
            {"transport_relay_observed": True, "causal": False, "inferred": False}
            if transport
            else {"causal": False, "inferred": False}
        ),
    )


def _record_capture(
    config: _base.ProxyConfig,
    *,
    exchange_id: str,
    request_body: bytes,
    response_content_type: str | None,
    method: str,
    request_path: str,
    status: int | None,
    capture: _ResponseCapture,
) -> bool:
    chunks_path: Path | None = None
    try:
        request = _base._json(request_body)
        if not isinstance(request, dict):
            request = {}
        assembled, chunks_path = _assemble_stream_to_file(
            capture.raw_path,
            content_type=response_content_type,
            request=request,
            mode=config.mode,
        )
        response = assembled.response if assembled is not None else _load_response(capture.raw_path)
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
        _stage._stamp_phase(
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
            _content_event_from_file(
                store=store,
                source=source,
                provider=provider,
                path=capture.raw_path,
                content_kind="http_proxy.response_body_raw",
                media_type=response_content_type or "application/octet-stream",
                representation="raw_bytes",
                relation="OBSERVED_INFERENCE_RESPONSE_RAW",
                observed_field="response.body.raw",
                transport=True,
            )
        )
        if chunks_path is not None and assembled is not None:
            kind = (
                "http_proxy.ollama_stream_chunks"
                if config.mode == "ollama"
                else "http_proxy.stream_chunks"
            )
            events.append(
                _content_event_from_file(
                    store=store,
                    source=source,
                    provider=provider,
                    path=chunks_path,
                    content_kind=kind,
                    media_type="application/json",
                    representation="parsed_json_canonical",
                    relation="OBSERVED_INFERENCE_STREAM_CHUNKS",
                    observed_field="response.stream_chunks",
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
    except Exception as exc:
        print(f"ExecWeave HTTP proxy capture warning: {exc}", file=_base.sys.stderr)
        return False
    finally:
        if chunks_path is not None:
            chunks_path.unlink(missing_ok=True)


def relay_default(handler: _base.ExecWeaveHTTPProxyHandler) -> None:
    try:
        target = _base._target_path(handler.server.upstream, handler.path)
        body = handler._read_body()
    except (TypeError, ValueError) as exc:
        handler.send_error(400, str(exc))
        return
    upstream = handler.server.upstream
    connection = http.client.HTTPConnection(
        upstream.hostname,
        upstream.port or 80,
        timeout=handler.server.proxy_config.timeout_seconds,
    )
    response_body = bytearray()
    capture: _ResponseCapture | None = None
    response_type: str | None = None
    status: int | None = None
    started = False
    exchange_id = _base.uuid.uuid4().hex
    request_recorded = False
    try:
        connection.request(handler.command, target, body=body or None, headers=handler._headers(body))
        request_recorded = _base.record_exchange_fail_open(
            handler.server.proxy_config,
            exchange_id=exchange_id,
            method=handler.command,
            request_path=target,
            request_body=body,
            request_content_type=handler.headers.get("Content-Type"),
            status=None,
            response_body=b"",
            response_content_type=None,
            request_only=True,
        )
        response = connection.getresponse()
        status = response.status
        response_type = response.getheader("Content-Type")
        handler.send_response(response.status, response.reason)
        started = True
        for key, value in response.getheaders():
            if key.lower() not in _base._HOP_BY_HOP | {"content-length", "connection"}:
                handler.send_header(key, value)
        handler.send_header("Connection", "close")
        handler.end_headers()
        if handler.command != "HEAD":
            if request_recorded:
                capture = _ResponseCapture()
            while chunk := response.read1(65536):
                if capture is not None:
                    capture.write(chunk)
                else:
                    response_body.extend(chunk)
                handler.wfile.write(chunk)
                handler.wfile.flush()
    except (OSError, http.client.HTTPException) as exc:
        if capture is not None:
            capture.cleanup()
        if not started:
            handler.send_error(502, f"upstream HTTP relay failed: {exc}")
        return
    finally:
        connection.close()
    try:
        if capture is not None:
            capture.finish()
            _record_capture(
                handler.server.proxy_config,
                exchange_id=exchange_id,
                request_body=body,
                response_content_type=response_type,
                method=handler.command,
                request_path=target,
                status=status,
                capture=capture,
            )
        else:
            handler.server.recorder(
                handler.server.proxy_config,
                exchange_id=exchange_id,
                method=handler.command,
                request_path=target,
                request_body=body,
                request_content_type=handler.headers.get("Content-Type"),
                status=status,
                response_body=bytes(response_body),
                response_content_type=response_type,
                request_recorded=request_recorded,
            )
    except Exception as exc:
        print(f"ExecWeave HTTP proxy recorder warning: {exc}", file=_base.sys.stderr)
    finally:
        if capture is not None:
            capture.cleanup()
