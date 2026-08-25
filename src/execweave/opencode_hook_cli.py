from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .opencode_adapter import (
    append_semantic_records,
    opencode_plugin_to_semantic_events,
    read_plugin_payload,
)


def _default_sidecar(payload: dict) -> Path:
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        cwd = str(Path.cwd())
    session_id = payload.get("sessionID")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("OpenCode payload has no sessionID for sidecar placement")
    safe = "".join(
        character if character.isalnum() or character in {"-", "_", "."} else "_"
        for character in session_id
    )
    return Path(cwd) / ".execweave" / "semantic" / "opencode" / f"{safe}.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave-opencode-hook",
        description="Capture OpenCode plugin telemetry as local ExecWeave semantic events.",
    )
    parser.add_argument("--sidecar", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = read_plugin_payload()
        sidecar = args.sidecar
        if sidecar is None:
            configured = os.environ.get("EXECWEAVE_SEMANTIC_SIDECAR")
            sidecar = Path(configured) if configured else _default_sidecar(payload)
        append_semantic_records(sidecar, opencode_plugin_to_semantic_events(payload))
    except (OSError, TimeoutError, ValueError) as exc:
        print(f"ExecWeave OpenCode hook warning: {exc}", file=sys.stderr)
        if args.strict:
            return 1
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
