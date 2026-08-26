from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .model_runtime import append_model_runtime_records, ollama_ps_to_events

_SEMANTIC_ENV = "EXECWEAVE_SEMANTIC_SIDECAR"
_OLLAMA_DEFAULT_ENDPOINT = "http://127.0.0.1:11434"
_PROBE_INTERVAL_SECONDS = 0.50
_PROBE_TIMEOUT_SECONDS = 0.35


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


def _ollama_endpoint_from_environment() -> str | None:
    raw = os.environ.get("OLLAMA_HOST", "").strip()
    if not raw:
        return _OLLAMA_DEFAULT_ENDPOINT
    candidate = raw if "://" in raw else f"http://{raw}"
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme != "http" or parsed.username is not None or parsed.password is not None:
        return None
    hostname = parsed.hostname
    if hostname not in {"127.0.0.1", "localhost", "::1", "0.0.0.0", "::"}:
        return None
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        return None
    if port is not None and not (1 <= port <= 65535):
        return None

    if hostname in {"0.0.0.0", "::"}:
        hostname = "127.0.0.1"
    if hostname == "::1":
        host = "[::1]"
    else:
        host = hostname
    if port is not None:
        host = f"{host}:{port}"
    return urlunsplit(("http", host, "", "", ""))


def _get_json(url: str, *, timeout: float) -> dict[str, object]:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Ollama probe did not return a JSON object")
    return payload


def _model_snapshot_signatures(
    payload: dict[str, object],
) -> tuple[dict[str, str], list[dict[str, object]]]:
    models = payload.get("models")
    if not isinstance(models, list):
        raise ValueError("Ollama /api/ps response requires models")
    signatures: dict[str, str] = {}
    valid_items: list[dict[str, object]] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        name = item.get("model") or item.get("name")
        if not isinstance(name, str) or not name:
            continue
        signatures[name] = json.dumps(
            item,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        valid_items.append(item)
    return signatures, valid_items


def _run_ollama_probe(
    *,
    endpoint: str,
    sidecar: Path,
    stop_event: threading.Event,
) -> None:
    previous_signatures: dict[str, str] = {}
    url = f"{endpoint.rstrip('/')}/api/ps"
    while not stop_event.is_set():
        try:
            payload = _get_json(url, timeout=_PROBE_TIMEOUT_SECONDS)
            current_signatures, items = _model_snapshot_signatures(payload)
            changed = [
                item
                for item in items
                if current_signatures[str(item.get("model") or item.get("name"))]
                != previous_signatures.get(str(item.get("model") or item.get("name")))
            ]
            if changed:
                records = ollama_ps_to_events({"models": changed}, endpoint=endpoint)
                append_model_runtime_records(sidecar, records)
            previous_signatures = current_signatures
        except (HTTPError, URLError, OSError, TimeoutError, ValueError, json.JSONDecodeError):
            pass
        stop_event.wait(_PROBE_INTERVAL_SECONDS)


@contextmanager
def auto_specialized_probe(command: list[str]) -> Iterator[None]:
    """Run supported local specialized probes without affecting command execution.

    The probe is deliberately opt-in by execution context: it only activates when
    a caller has supplied ExecWeave's per-run semantic sidecar environment variable.
    All probe failures are fail-open and never change the wrapped command's result.
    """
    configured_sidecar = os.environ.get(_SEMANTIC_ENV)
    endpoint = _ollama_endpoint_from_environment() if _is_ollama_serve(command) else None
    if not configured_sidecar or endpoint is None:
        yield
        return

    sidecar = Path(configured_sidecar).expanduser().resolve()
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_run_ollama_probe,
        kwargs={"endpoint": endpoint, "sidecar": sidecar, "stop_event": stop_event},
        name="execweave-ollama-live-probe",
        daemon=True,
    )
    thread.start()
    try:
        yield
    finally:
        stop_event.set()
        thread.join(timeout=max(1.0, _PROBE_TIMEOUT_SECONDS + _PROBE_INTERVAL_SECONDS + 0.2))
