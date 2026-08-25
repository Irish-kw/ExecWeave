from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from .model_runtime import (
    append_model_runtime_records,
    llamacpp_metrics_to_events,
    llamacpp_models_to_events,
    llamacpp_response_to_events,
    lmstudio_models_to_events,
    lmstudio_response_to_events,
    ollama_ps_to_events,
    ollama_response_to_events,
    sanitize_endpoint,
    vllm_models_to_events,
    vllm_response_to_events,
)

_RUNTIMES = ("ollama", "llamacpp", "vllm", "lmstudio")


def _sidecar(value: Path | None) -> Path:
    if value is not None:
        return value
    configured = os.environ.get("EXECWEAVE_SEMANTIC_SIDECAR")
    if configured:
        return Path(configured)
    raise ValueError("--sidecar or EXECWEAVE_SEMANTIC_SIDECAR is required")


def _read_json_stdin() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        raise ValueError("stdin is empty")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"stdin is invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("stdin must contain one JSON object")
    return payload


def _get_json(url: str, timeout: float) -> dict:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{url} did not return a JSON object")
    return payload


def _get_text(url: str, timeout: float) -> str:
    request = Request(url, headers={"Accept": "text/plain"})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave-model-runtime",
        description="Capture local model-runtime metadata without prompt or response content.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    event = sub.add_parser("event", help="Convert one final provider response into inference metadata events.")
    event.add_argument("--runtime", choices=_RUNTIMES, required=True)
    event.add_argument("--endpoint", default=None)
    event.add_argument("--request-id", default=None)
    event.add_argument("--sidecar", type=Path, default=None)

    probe = sub.add_parser("probe", help="Snapshot model-runtime catalog and optional aggregate metrics.")
    probe.add_argument("--runtime", choices=_RUNTIMES, required=True)
    probe.add_argument("--endpoint", default=None)
    probe.add_argument("--sidecar", type=Path, default=None)
    probe.add_argument(
        "--metrics",
        action="store_true",
        help="Also collect llama.cpp /metrics when enabled server-side.",
    )
    probe.add_argument("--timeout", type=float, default=3.0)
    return parser


def _default_endpoint(runtime: str) -> str:
    return {
        "ollama": "http://localhost:11434",
        "llamacpp": "http://localhost:8080",
        "vllm": "http://localhost:8000",
        "lmstudio": "http://localhost:1234",
    }[runtime]


def _event_command(args: argparse.Namespace) -> int:
    payload = _read_json_stdin()
    endpoint = sanitize_endpoint(args.endpoint or _default_endpoint(args.runtime))
    converters = {
        "ollama": ollama_response_to_events,
        "llamacpp": llamacpp_response_to_events,
        "vllm": vllm_response_to_events,
        "lmstudio": lmstudio_response_to_events,
    }
    records = converters[args.runtime](
        payload,
        endpoint=endpoint,
        request_id=args.request_id,
    )
    output = append_model_runtime_records(_sidecar(args.sidecar), records)
    print(json.dumps({"records": len(records), "sidecar": str(output)}, sort_keys=True))
    return 0


def _probe_command(args: argparse.Namespace) -> int:
    endpoint = sanitize_endpoint(args.endpoint or _default_endpoint(args.runtime))
    records = []
    if args.runtime == "ollama":
        payload = _get_json(f"{endpoint}/api/ps", args.timeout)
        records.extend(ollama_ps_to_events(payload, endpoint=endpoint))
    else:
        payload = _get_json(f"{endpoint}/v1/models", args.timeout)
        converters = {
            "llamacpp": llamacpp_models_to_events,
            "vllm": vllm_models_to_events,
            "lmstudio": lmstudio_models_to_events,
        }
        records.extend(converters[args.runtime](payload, endpoint=endpoint))
        if args.runtime == "llamacpp" and args.metrics:
            metrics = _get_text(f"{endpoint}/metrics", args.timeout)
            records.extend(llamacpp_metrics_to_events(metrics, endpoint=endpoint))
    output = append_model_runtime_records(_sidecar(args.sidecar), records)
    print(json.dumps({"records": len(records), "sidecar": str(output)}, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "event":
            return _event_command(args)
        return _probe_command(args)
    except (OSError, URLError, TimeoutError, ValueError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
