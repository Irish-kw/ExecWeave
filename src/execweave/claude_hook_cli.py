from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent_trace import provider_agent_trace_visibility_event
from .claude_adapter import append_semantic_records, claude_hook_to_semantic_events, read_hook_payload
from .claude_delegation import claude_delegation_events
from .claude_hook_contract import (
    PASSIVE_CLAUDE_HOOK_EVENTS,
    claude_official_full_fidelity_events,
    claude_official_hook_semantic_events,
)
from .claude_model_observer import append_claude_transcript_model_events
from .content_store import FullFidelityContentStore


def _hook_handler(command: str) -> dict[str, str]:
    return {"type": "command", "command": command}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


_MATCH_ALL_EVENTS = frozenset(
    {
        "PreToolUse",
        "PermissionRequest",
        "PostToolUse",
        "PostToolUseFailure",
        "PermissionDenied",
    }
)


def claude_hook_config(command: str = "execweave-claude-hook") -> dict[str, Any]:
    """Return a passive Claude Code observer config grounded in the official hook contract.

    WorktreeCreate is intentionally excluded because configuring it replaces Claude
    Code's default worktree creation. FileChanged is excluded because its matcher
    defines the literal file watch list and therefore cannot be enabled generically.
    """

    handler = _hook_handler(command)
    tool_group = {"matcher": "*", "hooks": [handler]}
    plain_group = {"hooks": [handler]}
    hooks: dict[str, Any] = {}
    for event in sorted(PASSIVE_CLAUDE_HOOK_EVENTS):
        hooks[event] = [tool_group if event in _MATCH_ALL_EVENTS else plain_group]
    if set(hooks) != set(PASSIVE_CLAUDE_HOOK_EVENTS):
        raise RuntimeError("Claude hook config drifted from the passive official event set")
    return {"hooks": hooks}


def _default_sidecar(payload: dict[str, Any]) -> Path:
    cwd = payload.get("cwd")
    session_id = payload.get("session_id")
    if not isinstance(cwd, str) or not cwd:
        raise ValueError("Claude hook payload has no cwd for automatic sidecar placement")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("Claude hook payload has no session_id for automatic sidecar placement")
    safe_session = "".join(
        character if character.isalnum() or character in {"-", "_", "."} else "_"
        for character in session_id
    )
    return Path(cwd) / ".execweave" / "semantic" / "claude" / f"{safe_session}.jsonl"


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
            "Semantic JSONL output path. Defaults to EXECWEAVE_SEMANTIC_SIDECAR, then "
            "<cwd>/.execweave/semantic/claude/<Claude-session-id>.jsonl."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero on telemetry errors. Default is fail-open so tracing cannot block Claude.",
    )
    parser.add_argument("--auto", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="Print a passive Claude Code settings fragment grounded in the official hook contract.",
    )
    parser.add_argument(
        "--command",
        default="execweave-claude-hook",
        help="Hook command embedded by --print-config (default: execweave-claude-hook).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.print_config:
        print(json.dumps(claude_hook_config(args.command), indent=2, sort_keys=True))
        return 0
    if args.auto and not os.environ.get("EXECWEAVE_SEMANTIC_SIDECAR"):
        return 0

    try:
        payload = read_hook_payload()
        sidecar = args.sidecar
        if sidecar is None:
            configured = os.environ.get("EXECWEAVE_SEMANTIC_SIDECAR")
            sidecar = Path(configured) if configured else _default_sidecar(payload)
        sidecar = Path(sidecar).expanduser().resolve()
        observed_at = _now()
        records = claude_hook_to_semantic_events(payload, timestamp=observed_at)
        records.extend(
            claude_official_hook_semantic_events(
                payload,
                timestamp=observed_at,
            )
        )
        if payload.get("hook_event_name") == "SessionStart":
            records.append(
                provider_agent_trace_visibility_event(
                    "claude",
                    timestamp=observed_at,
                    attribution="claude_hook",
                    evidence_source="provider_hook",
                )
            )
        content_store = FullFidelityContentStore(sidecar.parent)
        content_records = claude_official_full_fidelity_events(
            payload,
            store=content_store,
            timestamp=observed_at,
        )
        records.extend(content_records)
        records.extend(
            claude_delegation_events(
                payload,
                content_events=content_records,
                timestamp=observed_at,
            )
        )
        append_semantic_records(sidecar, records)
        append_claude_transcript_model_events(
            payload,
            sidecar=sidecar,
            timestamp=observed_at,
        )
    except (OSError, RuntimeError, TimeoutError, TypeError, ValueError) as exc:
        print(f"ExecWeave Claude hook warning: {exc}", file=sys.stderr)
        return 1 if args.strict else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
