from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .claude_adapter import append_semantic_records, claude_hook_to_semantic_events, read_hook_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave-claude-hook",
        description="Capture Claude Code hook input as local ExecWeave semantic telemetry.",
    )
    parser.add_argument(
        "--sidecar",
        type=Path,
        default=None,
        help=(
            "Semantic JSONL output path. Defaults to EXECWEAVE_SEMANTIC_SIDECAR. "
            "The hook never writes into the runtime event stream directly."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero on telemetry errors. Default is fail-open so tracing cannot block Claude.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    sidecar = args.sidecar
    if sidecar is None:
        configured = os.environ.get("EXECWEAVE_SEMANTIC_SIDECAR")
        if configured:
            sidecar = Path(configured)

    try:
        if sidecar is None:
            raise ValueError(
                "semantic sidecar path is not configured; use --sidecar or "
                "EXECWEAVE_SEMANTIC_SIDECAR"
            )
        payload = read_hook_payload()
        records = claude_hook_to_semantic_events(payload)
        append_semantic_records(sidecar, records)
    except (OSError, TimeoutError, ValueError) as exc:
        print(f"ExecWeave Claude hook warning: {exc}", file=sys.stderr)
        return 1 if args.strict else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
