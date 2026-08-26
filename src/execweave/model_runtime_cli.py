from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from .content_store import FullFidelityContentStore
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
from .model_runtime_full_fidelity import (
    runtime_exchange_to_content_events,
    runtime_response_to_content_events,
)

_RUNTIMES = ("ollama", "llamacpp", "vllm", "lmstudio")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
        description=(
            "Capture local model-runtime semantic metadata plus complete content exposed by the "
            "selected integration point."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    event = sub.add_parser(
        "event",
        help="Capture one supplied final provider response; this is response-only evidence.",
    )
    event.add_argument("--runtime", choices=_RUNTIMES, required=True)
    event.add_argument("--endpoint", default=None)
    event.add_argument("--request-id", default=None)
    event.add_argument("--sidecar", type=Path, default=None)

    exchange = sub.add_parser(
        "exchange",
        help=(
            "Capture caller-supplied request+response JSON; this does not assert transparent "
            "interception."
        ),
    )
    exchange.add_argument("--runtime", choices=_RUNTIMES, required=True)
    exchange.add_argument("--endpoint", default=None)
    exchange.add_argument("--request-id", default=None)
    exchange.add_argument("--sidecar", type=Path, default=None)

    probe = sub.add_parser(
        "probe", help="Snapshot model-runtime catalog and optional aggregate metrics."
    )
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


def _response_converter(runtime: str):
    return {
        "ollama": ollama_response_to_events,
        "llamacpp": llamacpp_response_to_events,
        "vllm": vllm_response_to_events,
        "lmstudio": lmstudio_response_to_events,
    }[runtime]


def _append_full_fidelity_fail_open(sidecar: Path, records_factory) -> int:
    try:
        records = records_factory(FullFidelityContentStore(sidecar.parent))
        append_model_runtime_records(sidecar, records)
        return len(records)
    except (OSError, RuntimeError, TimeoutError, TypeError, ValueError) as exc:
        print(f"ExecWeave model runtime full-fidelity warning: {exc}", file=sys.stderr)
        return 0


def _event_command(args: argparse.Namespace) -> int:
    payload = _read_json_stdin()
    endpoint = sanitize_endpoint(args.endpoint or _default_endpoint(args.runtime))
    sidecar = _sidecar(args.sidecar).expanduser().resolve()
    observed_at = _now()
    records = _response_converter(args.runtime)(
        payload,
        endpoint=endpoint,
        request_id=args.request_id,
        timestamp=observed_at,
    )
    output = append_model_runtime_records(sidecar, records)
    full_records = _append_full_fidelity_fail_open(
        sidecar,
        lambda store: runtime_response_to_content_events(
            payload,
            store=store,
            runtime=args.runtime,
            endpoint=endpoint,
            request_id=args.request_id,
            timestamp=observed_at,
        ),
    )
    print(
        json.dumps(
            {
                "full_fidelity_records": full_records,
                "records": len(records),
                "sidecar": str(output),
            },
            sort_keys=True,
        )
    )
    return 0


def _exchange_command(args: argparse.Namespace) -> int:
    exchange = _read_json_stdin()
    request_payload = exchange.get("request")
    response_payload = exchange.get("response")
    if not isinstance(request_payload, dict) or not isinstance(response_payload, dict):
        raise ValueError("exchange stdin requires JSON-object request and response fields")
    endpoint = sanitize_endpoint(args.endpoint or _default_endpoint(args.runtime))
    sidecar = _sidecar(args.sidecar).expanduser().resolve()
    observed_at = _now()
    records = _response_converter(args.runtime)(
        response_payload,
        endpoint=endpoint,
        request_id=args.request_id,
        timestamp=observed_at,
    )
    output = append_model_runtime_records(sidecar, records)
    full_records = _append_full_fidelity_fail_open(
        sidecar,
        lambda store: runtime_exchange_to_content_events(
            exchange,
            store=store,
            runtime=args.runtime,
            endpoint=endpoint,
            request_id=args.request_id,
            timestamp=observed_at,
        ),
    )
    print(
        json.dumps(
            {
                "full_fidelity_records": full_records,
                "records": len(records),
                "sidecar": str(output),
            },
            sort_keys=True,
        )
    )
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
        if args.command == "exchange":
            return _exchange_command(args)
        return _probe_command(args)
    except (OSError, URLError, TimeoutError, ValueError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
