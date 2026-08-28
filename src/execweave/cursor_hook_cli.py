from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent_trace import cursor_agent_trace_events
from .content_store import FullFidelityContentStore
from .cursor_adapter import append_semantic_records, cursor_hook_to_semantic_events, read_hook_payload
from .cursor_delegation import cursor_delegation_events
from .cursor_full_fidelity import cursor_hook_to_content_events

_HOOKS = (
    "sessionStart", "sessionEnd", "preToolUse", "postToolUse", "postToolUseFailure",
    "subagentStart", "subagentStop", "beforeShellExecution", "afterShellExecution",
    "beforeMCPExecution", "afterMCPExecution", "beforeReadFile", "afterFileEdit",
    "beforeSubmitPrompt", "preCompact", "stop", "afterAgentResponse", "afterAgentThought",
    "beforeTabFileRead", "afterTabFileEdit",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def cursor_hook_config(command: str = "execweave-cursor-hook") -> dict[str, Any]:
    return {"version": 1, "hooks": {name: [{"command": command}] for name in _HOOKS}}


def _default_sidecar(payload: dict[str, Any]) -> Path:
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        roots = payload.get("workspace_roots")
        if isinstance(roots, list) and roots and isinstance(roots[0], str):
            cwd = roots[0]
    if not isinstance(cwd, str) or not cwd:
        raise ValueError("Cursor hook payload has no cwd/workspace root for sidecar placement")
    scope = next(
        (payload[key] for key in ("conversation_id", "session_id", "generation_id")
         if isinstance(payload.get(key), str) and payload[key]),
        None,
    )
    if scope is None:
        raise ValueError("Cursor hook payload has no conversation/session identifier")
    safe_scope = "".join(c if c.isalnum() or c in "-_." else "_" for c in scope)
    return Path(cwd) / ".execweave" / "semantic" / "cursor" / f"{safe_scope}.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave-cursor-hook",
        description="Capture Cursor hook input as local ExecWeave semantic telemetry.",
    )
    parser.add_argument("--sidecar", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--auto", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--print-config", action="store_true")
    parser.add_argument("--command", default="execweave-cursor-hook")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.print_config:
        print(json.dumps(cursor_hook_config(args.command), indent=2, sort_keys=True))
        return 0
    if args.auto and not os.environ.get("EXECWEAVE_SEMANTIC_SIDECAR"):
        print("{}")
        return 0
    try:
        payload = read_hook_payload()
        sidecar = args.sidecar
        if sidecar is None:
            configured = os.environ.get("EXECWEAVE_SEMANTIC_SIDECAR")
            sidecar = Path(configured) if configured else _default_sidecar(payload)
        sidecar = Path(sidecar).expanduser().resolve()
        observed_at = _now()
        store = FullFidelityContentStore(sidecar.parent)
        append_semantic_records(
            sidecar,
            cursor_hook_to_semantic_events(payload, timestamp=observed_at),
        )
        append_semantic_records(
            sidecar,
            cursor_hook_to_content_events(
                payload,
                store=store,
                timestamp=observed_at,
            ),
        )
        append_semantic_records(
            sidecar,
            cursor_agent_trace_events(
                payload,
                store=store,
                timestamp=observed_at,
            ),
        )
        append_semantic_records(
            sidecar,
            cursor_delegation_events(
                payload,
                store=store,
                timestamp=observed_at,
            ),
        )
    except (OSError, RuntimeError, TimeoutError, TypeError, ValueError) as exc:
        print(f"ExecWeave Cursor hook warning: {exc}", file=sys.stderr)
        if args.strict:
            return 1
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
