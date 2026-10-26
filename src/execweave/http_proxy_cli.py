from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .http_proxy import ProxyConfig, create_proxy_server, sanitize_upstream, validate_listen_host


def _sidecar(value: Path | None) -> Path:
    if value is not None:
        return value.expanduser().resolve()
    configured = os.environ.get("EXECWEAVE_SEMANTIC_SIDECAR")
    if configured:
        return Path(configured).expanduser().resolve()
    raise ValueError("--sidecar or EXECWEAVE_SEMANTIC_SIDECAR is required")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave-http-proxy",
        description=(
            "Run a loopback-only HTTP relay that records full-fidelity Ollama or "
            "OpenAI-compatible inference traffic. HTTPS CONNECT/TLS MITM is not supported."
        ),
    )
    parser.add_argument("--upstream", required=True, help="Fixed http:// upstream base URL.")
    parser.add_argument(
        "--mode",
        choices=("ollama", "openai-compatible"),
        default="openai-compatible",
    )
    parser.add_argument("--provider-name", default="openai-compatible")
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=4319)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--sidecar", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        validate_listen_host(args.listen_host)
        upstream = sanitize_upstream(args.upstream)
        if args.timeout <= 0:
            raise ValueError("--timeout must be greater than zero")
        sidecar = _sidecar(args.sidecar)
        config = ProxyConfig(
            upstream=upstream,
            sidecar=sidecar,
            mode=args.mode,
            provider_name=args.provider_name,
            timeout_seconds=args.timeout,
        )
        server = create_proxy_server(
            listen_host=args.listen_host,
            listen_port=args.listen_port,
            config=config,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
        return 2

    host, port = server.server_address[:2]
    print(
        f"ExecWeave HTTP proxy: http://{host}:{port}/ -> {upstream} "
        f"[{args.mode}]",
        file=sys.stderr,
    )
    print(f"ExecWeave sidecar: {sidecar}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
