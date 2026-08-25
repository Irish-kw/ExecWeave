from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .inference_gateway import append_gateway_records
from .inference_identity import gateway_runtime_identity_event

_GATEWAYS = ("openrouter", "litellm")
_RUNTIMES = ("ollama", "llamacpp", "vllm", "lmstudio")


def _sidecar(value: Path | None) -> Path:
    if value is not None:
        return value
    configured = os.environ.get("EXECWEAVE_SEMANTIC_SIDECAR")
    if configured:
        return Path(configured)
    raise ValueError("--sidecar or EXECWEAVE_SEMANTIC_SIDECAR is required")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave-inference-link",
        description=(
            "Link gateway and model-runtime request nodes only when an explicit shared request "
            "identity is available."
        ),
    )
    parser.add_argument("--gateway", choices=_GATEWAYS, required=True)
    parser.add_argument("--gateway-request-id", required=True)
    parser.add_argument("--runtime", choices=_RUNTIMES, required=True)
    parser.add_argument("--runtime-request-id", required=True)
    parser.add_argument("--shared-request-id", required=True)
    parser.add_argument("--sidecar", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        record = gateway_runtime_identity_event(
            gateway=args.gateway,
            gateway_request_id=args.gateway_request_id,
            runtime=args.runtime,
            runtime_request_id=args.runtime_request_id,
            shared_request_id=args.shared_request_id,
        )
        output = append_gateway_records(_sidecar(args.sidecar), [record])
    except (OSError, TimeoutError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({"records": 1, "sidecar": str(output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
