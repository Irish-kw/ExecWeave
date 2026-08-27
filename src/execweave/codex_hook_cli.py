from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .codex_adapter import (
    append_semantic_records,
    codex_hook_to_semantic_events,
    read_hook_payload,
)
from .codex_full_fidelity import codex_hook_to_content_events
from .content_store import FullFidelityContentStore


def _hook_handler(command: str) -> dict[str, str]:
    return {"type": "command", "command": command}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def codex_hook_config(command: str = "execweave-codex-hook") -> dict[str, Any]:
    handler = _hook_handler(command)
    tool_group = {"matcher": "*", "hooks": [handler]}
    plain_group = {"hooks": [handler]}
    return {
        "hooks": {
            "PreToolUse": [tool_group],
            "PermissionRequest": [tool_group],
            "PostToolUse": [tool_group],
            "PreCompact": [plain_group],
            "PostCompact": [plain_group],
            "SessionStart": [plain_group],
            "SessionEnd": [plain_group],
            "UserPromptSubmit": [plain_group],
            "SubagentStart": [plain_group],
            "SubagentStop": [plain_group],
            "Stop": [plain_group],
            "Interrupt": [plain_group],
        }
    }


def _default_sidecar(payload: dict[str, Any]) -> Path:
    cwd = payload.get("cwd")
    session_id = payload.get("session_id")
    if not isinstance(cwd, str) or not cwd:
        raise ValueError("Codex hook payload has no cwd for automatic sidecar placement")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("Codex hook payload has no session_id for automatic sidecar placement")
    safe_session = "".join(
        character if character.isalnum() or character in {"-", "_", "."} else "_"
        for character in session_id
    )
    return Path(cwd) / ".execweave" / "semantic" / "codex" / f"{safe_session}.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave-codex-hook",
        description="Capture OpenAI Codex lifecycle hook input as local ExecWeave semantic telemetry.",
    )
    parser.add_argument(
        "--sidecar",
        type=Path,
        default=None,
        help=(
            "Semantic JSONL output path. Defaults to EXECWEAVE_SEMANTIC_SIDECAR, then "
            "<cwd>/.execweave/semantic/codex/<Codex-session-id>.jsonl."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero on telemetry errors. Default is fail-open so tracing cannot block Codex.",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="Print a Codex hooks.json fragment for the supported ExecWeave lifecycle hooks and exit.",
    )
    parser.add_argument(
        "--command",
        default="execweave-codex-hook",
        help="Hook command embedded by --print-config (default: execweave-codex-hook).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.print_config:
        print(json.dumps(codex_hook_config(args.command), indent=2, sort_keys=True))
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
        summary_records = codex_hook_to_semantic_events(payload, timestamp=observed_at)
        append_semantic_records(sidecar, summary_records)

        content_store = FullFidelityContentStore(sidecar.parent)
        content_records = codex_hook_to_content_events(
            payload,
            store=content_store,
            timestamp=observed_at,
        )
        append_semantic_records(sidecar, content_records)
    except (OSError, RuntimeError, TimeoutError, TypeError, ValueError) as exc:
        print(f"ExecWeave Codex hook warning: {exc}", file=sys.stderr)
        return 1 if args.strict else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
