from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .model_runtime import (
    append_model_runtime_records,
    llamacpp_models_to_events,
    lmstudio_models_to_events,
    ollama_ps_to_events,
    vllm_models_to_events,
)

_SEMANTIC_ENV = "EXECWEAVE_SEMANTIC_SIDECAR"
_OLLAMA_DEFAULT_ENDPOINT = "http://127.0.0.1:11434"
_OLLAMA_INFERENCE_PATHS = frozenset(
    {
        "/api/chat",
        "/api/generate",
        "/api/embed",
        "/api/embeddings",
        "/v1/chat/completions",
        "/v1/completions",
        "/v1/embeddings",
        "/v1/responses",
    }
)
_PROBE_INTERVAL_SECONDS = 0.50
_PROBE_TIMEOUT_SECONDS = 0.35
_PROBE_STARTUP_GRACE_SECONDS = 0.10
_POST_PROBE_ATTEMPTS = 6
_POST_PROBE_RETRY_SECONDS = 0.10
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0", "::"}
_PROBE_ERRORS = (HTTPError, URLError, OSError, TimeoutError, ValueError, json.JSONDecodeError)


@dataclass(frozen=True)
class _ProbeSpec:
    runtime: str
    endpoint: str
    path: str


def _command_name(value: str) -> str:
    name = value.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for suffix in (".exe", ".cmd", ".bat", ".ps1"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _is_ollama_serve(command: list[str]) -> bool:
    return (
        len(command) >= 2
        and _command_name(command[0]) == "ollama"
        and command[1].lower() == "serve"
    )


def _is_ollama_run(command: list[str]) -> bool:
    return (
        len(command) >= 2
        and _command_name(command[0]) == "ollama"
        and command[1].lower() == "run"
    )


def _is_llamacpp_server(command: list[str]) -> bool:
    return bool(command) and _command_name(command[0]) == "llama-server"


def _is_vllm_server(command: list[str]) -> bool:
    if len(command) >= 2 and _command_name(command[0]) == "vllm":
        return command[1].lower() == "serve"
    for index, value in enumerate(command[:-1]):
        if value == "-m" and command[index + 1] == "vllm.entrypoints.openai.api_server":
            return True
    return False


def _is_lmstudio_server_start(command: list[str]) -> bool:
    return (
        len(command) >= 3
        and _command_name(command[0]) == "lms"
        and command[1].lower() == "server"
        and command[2].lower() == "start"
    )


def _flag_value(command: list[str], flag: str) -> str | None:
    prefix = f"{flag}="
    for index, value in enumerate(command):
        if value.startswith(prefix):
            return value[len(prefix) :]
        if value == flag and index + 1 < len(command):
            return command[index + 1]
    return None


def _local_endpoint(host: str, port: int) -> str | None:
    if host not in _LOCAL_HOSTS or not (1 <= port <= 65535):
        return None
    probe_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    rendered_host = "[::1]" if probe_host == "::1" else probe_host
    return urlunsplit(("http", f"{rendered_host}:{port}", "", "", ""))


def _server_endpoint(command: list[str], *, default_port: int) -> str | None:
    host = _flag_value(command, "--host") or "127.0.0.1"
    raw_port = _flag_value(command, "--port")
    try:
        port = int(raw_port) if raw_port is not None else default_port
    except ValueError:
        return None
    return _local_endpoint(host, port)


def _ollama_endpoint_from_environment() -> str | None:
    raw = os.environ.get("OLLAMA_HOST", "").strip()
    if not raw:
        return _OLLAMA_DEFAULT_ENDPOINT
    candidate = raw if "://" in raw else f"http://{raw}"
    try:
        parsed = urlsplit(candidate)
        port = parsed.port or 11434
    except ValueError:
        return None
    if parsed.scheme != "http" or parsed.username is not None or parsed.password is not None:
        return None
    hostname = parsed.hostname
    if hostname is None or hostname not in _LOCAL_HOSTS:
        return None
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        return None
    return _local_endpoint(hostname, port)


def _ollama_serve_relay_address() -> tuple[str, int] | None:
    """Return a loopback endpoint ExecWeave can safely own for ``ollama serve``."""
    raw = os.environ.get("OLLAMA_HOST", "").strip()
    if not raw:
        return ("127.0.0.1", 11434)
    candidate = raw if "://" in raw else f"http://{raw}"
    try:
        parsed = urlsplit(candidate)
        port = parsed.port or 11434
    except ValueError:
        return None
    if parsed.scheme != "http" or parsed.username is not None or parsed.password is not None:
        return None
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        return None
    hostname = parsed.hostname
    # Do not silently narrow wildcard/external/IPv6 exposure to IPv4 loopback.
    if hostname not in {"127.0.0.1", "localhost"} or not (1 <= port <= 65535):
        return None
    return ("127.0.0.1", port)


def _allocate_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _record_ollama_inference_exchange(config: Any, **kwargs: Any) -> None:
    """Record inference exchanges while still relaying every Ollama API route."""
    method = str(kwargs.get("method", "")).upper()
    request_path = str(kwargs.get("request_path", ""))
    if method != "POST" or urlsplit(request_path).path not in _OLLAMA_INFERENCE_PATHS:
        return
    from .http_proxy import record_exchange_fail_open

    record_exchange_fail_open(config, **kwargs)


def _lmstudio_post_probe_spec(command: list[str]) -> _ProbeSpec | None:
    if not _is_lmstudio_server_start(command):
        return None
    raw_port = _flag_value(command, "--port")
    if raw_port is None:
        return None
    host = _flag_value(command, "--bind") or os.environ.get("LMS_SERVER_HOST", "").strip()
    host = host or "127.0.0.1"
    try:
        port = int(raw_port)
    except ValueError:
        return None
    endpoint = _local_endpoint(host, port)
    return _ProbeSpec("lmstudio", endpoint, "/v1/models") if endpoint else None


def _probe_spec(command: list[str]) -> _ProbeSpec | None:
    if _is_ollama_serve(command):
        endpoint = _ollama_endpoint_from_environment()
        return _ProbeSpec("ollama", endpoint, "/api/ps") if endpoint else None
    if _is_llamacpp_server(command):
        endpoint = _server_endpoint(command, default_port=8080)
        return _ProbeSpec("llamacpp", endpoint, "/v1/models") if endpoint else None
    if _is_vllm_server(command):
        endpoint = _server_endpoint(command, default_port=8000)
        return _ProbeSpec("vllm", endpoint, "/v1/models") if endpoint else None
    return None


def _get_json(url: str, *, timeout: float) -> dict[str, object]:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("model runtime probe did not return a JSON object")
    return payload


def _probe_records(spec: _ProbeSpec, payload: dict[str, object]) -> list[dict[str, object]]:
    if spec.runtime == "ollama":
        return ollama_ps_to_events(payload, endpoint=spec.endpoint)
    if spec.runtime == "llamacpp":
        return llamacpp_models_to_events(payload, endpoint=spec.endpoint)
    if spec.runtime == "vllm":
        return vllm_models_to_events(payload, endpoint=spec.endpoint)
    if spec.runtime == "lmstudio":
        return lmstudio_models_to_events(payload, endpoint=spec.endpoint)
    return []


def _record_identity(record: dict[str, object]) -> str:
    target = record.get("target")
    if isinstance(target, dict):
        target_id = target.get("id")
        if isinstance(target_id, str) and target_id:
            return f"{record.get('relation')}:{target_id}"
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _record_fingerprint(record: dict[str, object]) -> str:
    stable = {
        "event_type": record.get("event_type"),
        "relation": record.get("relation"),
        "source": record.get("source"),
        "target": record.get("target"),
        "attributes": record.get("attributes"),
    }
    return json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _run_model_probe(
    *,
    spec: _ProbeSpec,
    sidecar: Path,
    stop_event: threading.Event,
) -> None:
    if stop_event.wait(_PROBE_STARTUP_GRACE_SECONDS):
        return
    previous: dict[str, str] = {}
    url = f"{spec.endpoint.rstrip('/')}{spec.path}"
    while not stop_event.is_set():
        try:
            payload = _get_json(url, timeout=_PROBE_TIMEOUT_SECONDS)
            records = _probe_records(spec, payload)
            current = {
                _record_identity(record): _record_fingerprint(record)
                for record in records
            }
            changed = [
                record
                for record in records
                if current[_record_identity(record)]
                != previous.get(_record_identity(record))
            ]
            if changed:
                append_model_runtime_records(sidecar, changed)
            previous = current
        except _PROBE_ERRORS:
            pass
        stop_event.wait(_PROBE_INTERVAL_SECONDS)


def _run_ollama_probe(
    *,
    endpoint: str,
    sidecar: Path,
    stop_event: threading.Event,
) -> None:
    _run_model_probe(
        spec=_ProbeSpec("ollama", endpoint, "/api/ps"),
        sidecar=sidecar,
        stop_event=stop_event,
    )


def prepare_post_command_specialized_probe(command: list[str]) -> _ProbeSpec | None:
    """Prepare an attribution-safe post-command probe for short-lived launch CLIs."""
    spec = _lmstudio_post_probe_spec(command)
    if spec is None:
        return None
    try:
        _get_json(
            f"{spec.endpoint.rstrip('/')}{spec.path}",
            timeout=_PROBE_TIMEOUT_SECONDS,
        )
    except _PROBE_ERRORS:
        return spec
    return None


def run_post_command_specialized_probe(
    spec: _ProbeSpec | None,
    *,
    return_code: int,
) -> None:
    """Materialize a prepared short-lived launcher probe after successful exit."""
    configured_sidecar = os.environ.get(_SEMANTIC_ENV)
    if spec is None or return_code != 0 or not configured_sidecar:
        return
    url = f"{spec.endpoint.rstrip('/')}{spec.path}"
    for attempt in range(_POST_PROBE_ATTEMPTS):
        try:
            payload = _get_json(url, timeout=_PROBE_TIMEOUT_SECONDS)
            records = _probe_records(spec, payload)
            if records:
                append_model_runtime_records(
                    Path(configured_sidecar).expanduser().resolve(),
                    records,
                )
            return
        except _PROBE_ERRORS:
            if attempt + 1 < _POST_PROBE_ATTEMPTS:
                time.sleep(_POST_PROBE_RETRY_SECONDS)


@contextmanager
def auto_specialized_launch(
    command: list[str],
    *,
    server_relay: bool = False,
) -> Iterator[dict[str, str]]:
    """Prepare child launch wiring for supported transparent local integrations.

    ``server_relay`` is deliberately opt-in so direct library callers preserve the
    existing contract. RuntimeCollector enables it for a real managed server run.
    """
    environment = dict(os.environ)
    configured_sidecar = os.environ.get(_SEMANTIC_ENV)
    wants_run_relay = _is_ollama_run(command)
    wants_serve_relay = server_relay and _is_ollama_serve(command)
    if not configured_sidecar or not (wants_run_relay or wants_serve_relay):
        yield environment
        return

    from .http_proxy import ExecWeaveHTTPProxyServer, ProxyConfig

    sidecar = Path(configured_sidecar).expanduser().resolve()

    if wants_run_relay:
        upstream = _ollama_endpoint_from_environment()
        if upstream is None:
            yield environment
            return
        try:
            server = ExecWeaveHTTPProxyServer(
                ("127.0.0.1", 0),
                ProxyConfig(upstream=upstream, sidecar=sidecar, mode="ollama"),
                recorder=_record_ollama_inference_exchange,
            )
        except OSError:
            yield environment
            return
        thread = threading.Thread(
            target=server.serve_forever,
            kwargs={"poll_interval": 0.05},
            name="execweave-ollama-run-relay",
            daemon=True,
        )
        thread.start()
        host, port = server.server_address[:2]
        environment["OLLAMA_HOST"] = f"http://{host}:{port}"
        try:
            yield environment
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2.0)
        return

    listen_address = _ollama_serve_relay_address()
    if listen_address is None:
        yield environment
        return
    listen_host, listen_port = listen_address
    internal_port = _allocate_loopback_port()
    upstream = f"http://127.0.0.1:{internal_port}"
    server: ExecWeaveHTTPProxyServer | None = None
    last_bind_error: OSError | None = None
    for attempt in range(5):
        try:
            server = ExecWeaveHTTPProxyServer(
                (listen_host, listen_port),
                ProxyConfig(upstream=upstream, sidecar=sidecar, mode="ollama"),
                recorder=_record_ollama_inference_exchange,
            )
            break
        except OSError as exc:
            last_bind_error = exc
            if attempt < 4:
                time.sleep(0.05)
    if server is None:
        public_endpoint = f"http://{listen_host}:{listen_port}"
        raise RuntimeError(
            "ExecWeave could not reserve the Ollama endpoint "
            f"{public_endpoint} for transparent conversation capture. "
            "Stop any existing Ollama server using that endpoint or set "
            "OLLAMA_HOST to a free loopback port before starting "
            "`execweave live -- ollama serve`."
        ) from last_bind_error
    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.05},
        name="execweave-ollama-serve-relay",
        daemon=True,
    )
    thread.start()
    environment["OLLAMA_HOST"] = upstream
    print(
        "ExecWeave Ollama relay: "
        f"http://{listen_host}:{listen_port} -> {upstream}",
        file=sys.stderr,
    )
    try:
        yield environment
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


@contextmanager
def auto_specialized_probe(command: list[str]) -> Iterator[None]:
    """Run supported local specialized probes without affecting command execution."""
    configured_sidecar = os.environ.get(_SEMANTIC_ENV)
    spec = _probe_spec(command)
    if not configured_sidecar or spec is None:
        yield
        return

    sidecar = Path(configured_sidecar).expanduser().resolve()
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_run_model_probe,
        kwargs={"spec": spec, "sidecar": sidecar, "stop_event": stop_event},
        name=f"execweave-{spec.runtime}-live-probe",
        daemon=True,
    )
    thread.start()
    try:
        yield
    finally:
        stop_event.set()
        thread.join(
            timeout=max(
                1.0,
                _PROBE_STARTUP_GRACE_SECONDS
                + _PROBE_TIMEOUT_SECONDS
                + _PROBE_INTERVAL_SECONDS
                + 0.2,
            )
        )
