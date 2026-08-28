from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .agent_trace import opencode_agent_trace_events
from .content_store import FullFidelityContentStore
from .opencode_adapter import append_semantic_records, opencode_plugin_to_semantic_events, read_plugin_payload
from .opencode_full_fidelity import opencode_plugin_to_content_events


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _default_sidecar(payload: dict) -> Path:
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        cwd = str(Path.cwd())
    session_id = payload.get("sessionID")
    scope = session_id if isinstance(session_id, str) and session_id else "unscoped"
    safe = "".join(character if character.isalnum() or character in {"-", "_", "."} else "_" for character in scope)
    return Path(cwd) / ".execweave" / "semantic" / "opencode" / f"{safe}.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave-opencode-hook",
        description="Capture OpenCode plugin telemetry as local ExecWeave semantic events.",
    )
    parser.add_argument("--sidecar", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--auto", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.auto and not os.environ.get("EXECWEAVE_SEMANTIC_SIDECAR"):
        print("{}")
        return 0
    try:
        payload = read_plugin_payload()
        sidecar = args.sidecar
        if sidecar is None:
            configured = os.environ.get("EXECWEAVE_SEMANTIC_SIDECAR")
            sidecar = Path(configured) if configured else _default_sidecar(payload)
        sidecar = Path(sidecar).expanduser().resolve()
        observed_at = _now()
        store = FullFidelityContentStore(sidecar.parent)
        append_semantic_records(
            sidecar,
            opencode_plugin_to_semantic_events(payload, timestamp=observed_at),
        )
        append_semantic_records(
            sidecar,
            opencode_plugin_to_content_events(
                payload,
                store=store,
                timestamp=observed_at,
            ),
        )
        append_semantic_records(
            sidecar,
            opencode_agent_trace_events(
                payload,
                store=store,
                timestamp=observed_at,
            ),
        )
    except (OSError, RuntimeError, TimeoutError, TypeError, ValueError) as exc:
        print(f"ExecWeave OpenCode hook warning: {exc}", file=sys.stderr)
        if args.strict:
            return 1
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
