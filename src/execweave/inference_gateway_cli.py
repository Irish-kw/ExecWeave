from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .inference_gateway import (
    append_gateway_records,
    litellm_response_to_events,
    openrouter_generation_to_events,
    openrouter_response_to_events,
    sanitize_gateway_endpoint,
)

_GATEWAYS = ("openrouter", "litellm")


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


def _default_endpoint(gateway: str) -> str:
    return {
        "openrouter": "https://openrouter.ai/api/v1",
        "litellm": "http://localhost:4000",
    }[gateway]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave-inference-gateway",
        description="Capture inference gateway routing/usage metadata without prompt or response content.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    event = sub.add_parser("event", help="Convert one final gateway response into metadata events.")
    event.add_argument("--gateway", choices=_GATEWAYS, required=True)
    event.add_argument("--endpoint", default=None)
    event.add_argument("--requested-model", default=None)
    event.add_argument("--resolved-model", default=None)
    event.add_argument("--provider-name", default=None)
    event.add_argument("--deployment-id", default=None)
    event.add_argument("--request-id", default=None)
    event.add_argument("--sidecar", type=Path, default=None)

    generation = sub.add_parser(
        "generation",
        help="Convert OpenRouter generation metadata into routing/performance events.",
    )
    generation.add_argument("--gateway", choices=["openrouter"], required=True)
    generation.add_argument("--endpoint", default=None)
    generation.add_argument("--sidecar", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = _read_json_stdin()
        endpoint = sanitize_gateway_endpoint(args.endpoint or _default_endpoint(args.gateway))
        if args.command == "event":
            converters = {
                "openrouter": openrouter_response_to_events,
                "litellm": litellm_response_to_events,
            }
            records = converters[args.gateway](
                payload,
                requested_model=args.requested_model,
                resolved_model=args.resolved_model,
                provider_name=args.provider_name,
                deployment_id=args.deployment_id,
                endpoint=endpoint,
                request_id=args.request_id,
            )
        else:
            records = openrouter_generation_to_events(payload, endpoint=endpoint)
        output = append_gateway_records(_sidecar(args.sidecar), records)
    except (OSError, TimeoutError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({"records": len(records), "sidecar": str(output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
