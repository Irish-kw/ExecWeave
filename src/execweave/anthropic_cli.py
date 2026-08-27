from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .anthropic import append_anthropic_records, response_to_events, sanitize_anthropic_endpoint
from .anthropic_full_fidelity import exchange_to_content_events, response_to_content_events
from .content_store import FullFidelityContentStore


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave-anthropic",
        description=(
            "Capture explicit Anthropic Messages API evidence plus complete content exposed "
            "by the selected integration point."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    event = sub.add_parser(
        "event",
        help="Capture one supplied final Messages API response; response-only evidence.",
    )
    event.add_argument("--endpoint", required=True)
    event.add_argument("--request-id", default=None)
    event.add_argument("--sidecar", type=Path, default=None)
    exchange = sub.add_parser(
        "exchange",
        help="Capture caller-supplied request+response JSON; does not assert interception.",
    )
    exchange.add_argument("--endpoint", required=True)
    exchange.add_argument("--request-id", default=None)
    exchange.add_argument("--sidecar", type=Path, default=None)
    return parser


def _append_full_fidelity_fail_open(sidecar: Path, records_factory) -> int:
    try:
        records = records_factory(FullFidelityContentStore(sidecar.parent))
        append_anthropic_records(sidecar, records)
        return len(records)
    except (OSError, RuntimeError, TimeoutError, TypeError, ValueError) as exc:
        print(f"ExecWeave Anthropic full-fidelity warning: {exc}", file=sys.stderr)
        return 0


def _event_command(args: argparse.Namespace) -> int:
    payload = _read_json_stdin()
    endpoint = sanitize_anthropic_endpoint(args.endpoint)
    sidecar = _sidecar(args.sidecar).expanduser().resolve()
    observed_at = _now()
    records = response_to_events(
        payload,
        endpoint=endpoint,
        request_id=args.request_id,
        timestamp=observed_at,
    )
    output = append_anthropic_records(sidecar, records)
    full_records = _append_full_fidelity_fail_open(
        sidecar,
        lambda store: response_to_content_events(
            payload,
            store=store,
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
    endpoint = sanitize_anthropic_endpoint(args.endpoint)
    sidecar = _sidecar(args.sidecar).expanduser().resolve()
    observed_at = _now()
    requested_model = request_payload.get("model")
    if not isinstance(requested_model, str) or not requested_model:
        requested_model = None
    records = response_to_events(
        response_payload,
        endpoint=endpoint,
        requested_model=requested_model,
        request_id=args.request_id,
        timestamp=observed_at,
    )
    output = append_anthropic_records(sidecar, records)
    full_records = _append_full_fidelity_fail_open(
        sidecar,
        lambda store: exchange_to_content_events(
            exchange,
            store=store,
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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "event":
            return _event_command(args)
        return _exchange_command(args)
    except (OSError, TimeoutError, ValueError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
