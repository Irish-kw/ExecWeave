from __future__ import annotations

import http.client
import ipaddress
import json
import sys
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import SplitResult, urlsplit, urlunsplit

from .content_evidence import content_observation_event
from .content_store import FullFidelityContentStore
from .model_runtime_full_fidelity import runtime_exchange_to_content_events
from .openai_compatible import append_openai_compatible_records
from .openai_compatible_full_fidelity import exchange_to_content_events

_HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)


@dataclass(frozen=True)
class ProxyConfig:
    upstream: str
    sidecar: Path
    mode: str = "openai-compatible"
    provider_name: str = "openai-compatible"
    timeout_seconds: float = 120.0


def _parse_upstream(value: str) -> SplitResult:
    split = urlsplit(value)
    if split.scheme != "http" or not split.hostname:
        raise ValueError("proxy upstream must be one explicit http:// URL")
    if split.username is not None or split.password is not None:
        raise ValueError("proxy upstream URL must not contain credentials")
    if split.query or split.fragment:
        raise ValueError("proxy upstream URL must not contain query or fragment components")
    return split


def sanitize_upstream(value: str) -> str:
    split = _parse_upstream(value)
    host = split.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if split.port is not None:
        host = f"{host}:{split.port}"
    return urlunsplit(("http", host, split.path.rstrip("/"), "", ""))


def validate_listen_host(host: str) -> None:
    if host == "localhost":
        return
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError("proxy listen host must be localhost or a loopback IP address") from exc
    if not address.is_loopback:
        raise ValueError("proxy listen host must be localhost or a loopback IP address")


def _target_path(upstream: SplitResult, incoming: str) -> str:
    split = urlsplit(incoming)
    if split.scheme or split.netloc or not split.path.startswith("/"):
        raise ValueError("absolute-form proxy targets are not accepted")
    base = upstream.path.rstrip("/")
    path = f"{base}{split.path}" if base else split.path
    return urlunsplit(("", "", path, split.query, ""))


def _json(payload: bytes) -> Any | None:
    try:
        return json.loads(payload.decode("utf-8")) if payload else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _stream_items(payload: bytes, content_type: str | None, request: Any) -> list[Any]:
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    if media_type == "text/event-stream":
        values: list[Any] = []
        for raw in payload.splitlines():
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                values.append(json.loads(data))
            except json.JSONDecodeError:
                values.append(data)
        return values
    streaming = isinstance(request, dict) and request.get("stream") is True
    if not streaming and media_type not in {"application/x-ndjson", "application/ndjson"}:
        return []
    values = []
    for raw in payload.splitlines():
        if not raw.strip():
            continue
        try:
            values.append(json.loads(raw.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError):
            values.append(raw.decode("utf-8", errors="replace"))
    return values


def _tool_calls(value: Any) -> list[Any]:
    calls: list[Any] = []

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            nested = item.get("tool_calls")
            if isinstance(nested, list):
                calls.extend(nested)
            if item.get("type") in {"function_call", "tool_call", "tool_use"}:
                calls.append(item)
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return calls


def _raw_event(
    store: FullFidelityContentStore,
    source: dict[str, Any],
    provider: str,
    body: bytes,
    *,
    kind: str,
    relation: str,
    field: str,
    media_type: str | None,
) -> dict[str, Any]:
    reference = store.put_bytes(
        body,
        content_kind=kind,
        media_type=media_type or "application/octet-stream",
        representation="raw_bytes",
    )
    return content_observation_event(
        timestamp=source.get("attributes", {}).get("observed_at", ""),
        provider=provider,
        source=source,
        reference=reference,
        relation=relation,
        observed_field=field,
        evidence_source="localhost_http_proxy",
        attribution="execweave_http_proxy",
        event_type="http_proxy.content.observed",
        attributes={"transport_relay_observed": True, "causal": False, "inferred": False},
    )


def record_exchange_fail_open(
    config: ProxyConfig,
    *,
    exchange_id: str,
    request_body: bytes,
    request_content_type: str | None,
    response_body: bytes,
    response_content_type: str | None,
    method: str,
    request_path: str,
    status: int,
) -> None:
    try:
        request = _json(request_body)
        if not isinstance(request, dict):
            request = {}
        chunks = _stream_items(response_body, response_content_type, request)
        response = chunks[-1] if chunks and isinstance(chunks[-1], dict) else _json(response_body)
        if not isinstance(response, dict):
            response = {}
        store = FullFidelityContentStore(config.sidecar.parent)
        if config.mode == "ollama":
            events = runtime_exchange_to_content_events(
                {"request": request, "response": response},
                store=store,
                runtime="ollama",
                endpoint=config.upstream,
                request_id=exchange_id,
            )
            provider = "ollama"
        else:
            exchange = {"request": request, "response": response}
            if chunks:
                exchange["stream_chunks"] = chunks
            events = exchange_to_content_events(
                exchange,
                store=store,
                endpoint=config.upstream,
                provider_name=config.provider_name,
                request_id=exchange_id,
            )
            provider = config.provider_name
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
                    "proxy_upstream": sanitize_upstream(config.upstream),
                    "causal": False,
                    "inferred": False,
                }
            )
        source = events[0]["source"]
        source.setdefault("attributes", {})["observed_at"] = events[0]["timestamp"]
        events.extend(
            [
                _raw_event(
                    store,
                    source,
                    provider,
                    request_body,
                    kind="http_proxy.request_body_raw",
                    relation="OBSERVED_INFERENCE_REQUEST_RAW",
                    field="request.body.raw",
                    media_type=request_content_type,
                ),
                _raw_event(
                    store,
                    source,
                    provider,
                    response_body,
                    kind="http_proxy.response_body_raw",
                    relation="OBSERVED_INFERENCE_RESPONSE_RAW",
                    field="response.body.raw",
                    media_type=response_content_type,
                ),
            ]
        )
        if chunks and config.mode == "ollama":
            reference = store.put_json(chunks, content_kind="http_proxy.ollama_stream_chunks")
            events.append(
                content_observation_event(
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
        calls = _tool_calls(chunks if chunks else response)
        if calls:
            reference = store.put_json(calls, content_kind="http_proxy.response_tool_calls")
            events.append(
                content_observation_event(
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
        append_openai_compatible_records(config.sidecar, events)
    except Exception as exc:
        print(f"ExecWeave HTTP proxy capture warning: {exc}", file=sys.stderr)


class ExecWeaveHTTPProxyServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        config: ProxyConfig,
        recorder: Callable[..., None] = record_exchange_fail_open,
    ) -> None:
        validate_listen_host(address[0])
        if config.mode not in {"ollama", "openai-compatible"}:
            raise ValueError("proxy mode must be ollama or openai-compatible")
        self.proxy_config = config
        self.upstream = _parse_upstream(config.upstream)
        self.recorder = recorder
        super().__init__(address, ExecWeaveHTTPProxyHandler)


class ExecWeaveHTTPProxyHandler(BaseHTTPRequestHandler):
    server: ExecWeaveHTTPProxyServer
    protocol_version = "HTTP/1.0"

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_CONNECT(self) -> None:
        self.send_error(405, "CONNECT is disabled; ExecWeave does not perform TLS MITM")

    def do_GET(self) -> None:
        self._relay()

    def do_HEAD(self) -> None:
        self._relay()

    def do_OPTIONS(self) -> None:
        self._relay()

    def do_POST(self) -> None:
        self._relay()

    def do_PUT(self) -> None:
        self._relay()

    def do_PATCH(self) -> None:
        self._relay()

    def do_DELETE(self) -> None:
        self._relay()

    def _read_body(self) -> bytes:
        transfer = self.headers.get("Transfer-Encoding", "").lower()
        if transfer:
            if transfer != "chunked":
                raise ValueError("unsupported request Transfer-Encoding")
            chunks: list[bytes] = []
            while True:
                line = self.rfile.readline()
                size = int(line.split(b";", 1)[0].strip(), 16)
                if size == 0:
                    while self.rfile.readline() not in {b"\r\n", b"\n", b""}:
                        pass
                    return b"".join(chunks)
                chunks.append(self.rfile.read(size))
                if self.rfile.read(2) != b"\r\n":
                    raise ValueError("invalid chunk terminator")
        length = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(length)

    def _headers(self, body: bytes) -> dict[str, str]:
        result = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in _HOP_BY_HOP | {"host", "content-length"}
        }
        if body:
            result["Content-Length"] = str(len(body))
        return result

    def _relay(self) -> None:
        try:
            target = _target_path(self.server.upstream, self.path)
            body = self._read_body()
        except (TypeError, ValueError) as exc:
            self.send_error(400, str(exc))
            return
        upstream = self.server.upstream
        connection = http.client.HTTPConnection(
            upstream.hostname,
            upstream.port or 80,
            timeout=self.server.proxy_config.timeout_seconds,
        )
        response_body = bytearray()
        response_type: str | None = None
        started = False
        try:
            connection.request(self.command, target, body=body or None, headers=self._headers(body))
            response = connection.getresponse()
            response_type = response.getheader("Content-Type")
            self.send_response(response.status, response.reason)
            started = True
            for key, value in response.getheaders():
                if key.lower() not in _HOP_BY_HOP | {"content-length", "connection"}:
                    self.send_header(key, value)
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                while chunk := response.read(65536):
                    response_body.extend(chunk)
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except (OSError, http.client.HTTPException) as exc:
            if not started:
                self.send_error(502, f"upstream HTTP relay failed: {exc}")
            return
        finally:
            connection.close()
        try:
            self.server.recorder(
                self.server.proxy_config,
                exchange_id=uuid.uuid4().hex,
                method=self.command,
                request_path=target,
                request_body=body,
                request_content_type=self.headers.get("Content-Type"),
                status=response.status,
                response_body=bytes(response_body),
                response_content_type=response_type,
            )
        except Exception as exc:
            print(f"ExecWeave HTTP proxy recorder warning: {exc}", file=sys.stderr)


def create_proxy_server(
    *,
    listen_host: str,
    listen_port: int,
    config: ProxyConfig,
    recorder: Callable[..., None] = record_exchange_fail_open,
) -> ExecWeaveHTTPProxyServer:
    if not 0 <= listen_port <= 65535:
        raise ValueError("proxy listen port must be between 0 and 65535")
    return ExecWeaveHTTPProxyServer((listen_host, listen_port), config, recorder)
