from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .content_store import FullFidelityContentStore
from .inference_gateway import (
    append_gateway_records,
    litellm_response_to_events,
    openrouter_generation_to_events,
    openrouter_response_to_events,
    sanitize_gateway_endpoint,
)
from .inference_gateway_full_fidelity import (
    openrouter_exchange_to_content_events,
    openrouter_response_to_content_events,
)

_GATEWAYS = ("openrouter", "litellm")


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


def _default_endpoint(gateway: str) -> str:
    return {
        "openrouter": "https://openrouter.ai/api/v1",
        "litellm": "http://localhost:4000",
    }[gateway]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave-inference-gateway",
        description=(
            "Capture inference gateway semantic metadata plus complete content exposed by the "
            "selected integration point."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    event = sub.add_parser(
        "event",
        help="Capture one final gateway response; this is response-only evidence.",
    )
    event.add_argument("--gateway", choices=_GATEWAYS, required=True)
    event.add_argument("--endpoint", default=None)
    event.add_argument("--requested-model", default=None)
    event.add_argument("--resolved-model", default=None)
    event.add_argument("--provider-name", default=None)
    event.add_argument("--deployment-id", default=None)
    event.add_argument("--request-id", default=None)
    event.add_argument("--sidecar", type=Path, default=None)

    exchange = sub.add_parser(
        "exchange",
        help=(
            "Capture caller-supplied OpenRouter request+response JSON; this is not wire "
            "interception."
        ),
    )
    exchange.add_argument("--gateway", choices=["openrouter"], required=True)
    exchange.add_argument("--endpoint", default=None)
    exchange.add_argument("--provider-name", default=None)
    exchange.add_argument("--deployment-id", default=None)
    exchange.add_argument("--request-id", default=None)
    exchange.add_argument("--sidecar", type=Path, default=None)

    generation = sub.add_parser(
        "generation",
        help="Convert OpenRouter generation metadata into routing/performance events.",
    )
    generation.add_argument("--gateway", choices=["openrouter"], required=True)
    generation.add_argument("--endpoint", default=None)
    generation.add_argument("--sidecar", type=Path, default=None)
    return parser


def _append_full_fidelity_fail_open(sidecar: Path, records_factory) -> int:
    try:
        records = records_factory(FullFidelityContentStore(sidecar.parent))
        append_gateway_records(sidecar, records)
        return len(records)
    except (OSError, RuntimeError, TimeoutError, TypeError, ValueError) as exc:
        print(f"ExecWeave inference gateway full-fidelity warning: {exc}", file=sys.stderr)
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = _read_json_stdin()
        endpoint = sanitize_gateway_endpoint(args.endpoint or _default_endpoint(args.gateway))
        sidecar = _sidecar(args.sidecar).expanduser().resolve()
        observed_at = _now()
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
                timestamp=observed_at,
            )
            output = append_gateway_records(sidecar, records)
            full_records = 0
            if args.gateway == "openrouter":
                full_records = _append_full_fidelity_fail_open(
                    sidecar,
                    lambda store: openrouter_response_to_content_events(
                        payload,
                        store=store,
                        endpoint=endpoint,
                        request_id=args.request_id,
                        timestamp=observed_at,
                        provider_name=args.provider_name,
                        deployment_id=args.deployment_id,
                    ),
                )
        elif args.command == "exchange":
            request_payload = payload.get("request")
            response_payload = payload.get("response")
            if not isinstance(request_payload, dict) or not isinstance(response_payload, dict):
                raise ValueError("exchange stdin requires JSON-object request and response fields")
            requested_model = request_payload.get("model")
            if not isinstance(requested_model, str) or not requested_model:
                requested_model = None
            records = openrouter_response_to_events(
                response_payload,
                requested_model=requested_model,
                provider_name=args.provider_name,
                deployment_id=args.deployment_id,
                endpoint=endpoint,
                request_id=args.request_id,
                timestamp=observed_at,
            )
            output = append_gateway_records(sidecar, records)
            full_records = _append_full_fidelity_fail_open(
                sidecar,
                lambda store: openrouter_exchange_to_content_events(
                    payload,
                    store=store,
                    endpoint=endpoint,
                    request_id=args.request_id,
                    timestamp=observed_at,
                    provider_name=args.provider_name,
                    deployment_id=args.deployment_id,
                ),
            )
        else:
            records = openrouter_generation_to_events(
                payload,
                endpoint=endpoint,
                timestamp=observed_at,
            )
            output = append_gateway_records(sidecar, records)
            full_records = 0
    except (OSError, TimeoutError, ValueError) as exc:
        parser.error(str(exc))
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


if __name__ == "__main__":
    raise SystemExit(main())
