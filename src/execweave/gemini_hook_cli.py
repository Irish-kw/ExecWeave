from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .content_store import FullFidelityContentStore
from .gemini_adapter import append_semantic_records, gemini_hook_to_semantic_events, read_hook_payload
from .gemini_full_fidelity import gemini_hook_to_content_events


def _handler(command: str) -> dict[str, Any]:
    return {
        "name": "execweave-gemini-telemetry",
        "type": "command",
        "command": command,
        "timeout": 5000,
    }


def gemini_hook_config(command: str = "execweave-gemini-hook") -> dict[str, Any]:
    handler = _handler(command)
    tool_group = {"matcher": ".*", "hooks": [handler]}
    plain_group = {"hooks": [handler]}
    return {
        "hooks": {
            "SessionStart": [plain_group],
            "SessionEnd": [plain_group],
            "BeforeAgent": [plain_group],
            "AfterAgent": [plain_group],
            "BeforeModel": [plain_group],
            "AfterModel": [plain_group],
            "BeforeToolSelection": [plain_group],
            "BeforeTool": [tool_group],
            "AfterTool": [tool_group],
            "PreCompress": [plain_group],
            "Notification": [plain_group],
        }
    }


def _default_sidecar(payload: dict[str, Any]) -> Path:
    cwd = payload.get("cwd")
    session_id = payload.get("session_id")
    if not isinstance(cwd, str) or not cwd:
        raise ValueError("Gemini hook payload has no cwd for automatic sidecar placement")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("Gemini hook payload has no session_id for automatic sidecar placement")
    safe_session = "".join(
        character if character.isalnum() or character in {"-", "_", "."} else "_"
        for character in session_id
    )
    return Path(cwd) / ".execweave" / "semantic" / "gemini" / f"{safe_session}.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave-gemini-hook",
        description="Capture Gemini CLI hook input as local ExecWeave semantic telemetry.",
    )
    parser.add_argument("--sidecar", type=Path, default=None)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero on telemetry errors. Default is fail-open.",
    )
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="Print a Gemini CLI settings.json hooks fragment and exit.",
    )
    parser.add_argument("--command", default="execweave-gemini-hook")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.print_config:
        print(json.dumps(gemini_hook_config(args.command), indent=2, sort_keys=True))
        return 0

    try:
        payload = read_hook_payload()
        sidecar = args.sidecar
        if sidecar is None:
            configured = os.environ.get("EXECWEAVE_SEMANTIC_SIDECAR")
            sidecar = Path(configured) if configured else _default_sidecar(payload)
        sidecar = Path(sidecar).expanduser().resolve()

        provider_timestamp = payload.get("timestamp")
        observed_at = (
            provider_timestamp
            if isinstance(provider_timestamp, str) and provider_timestamp
            else None
        )
        summary_records = gemini_hook_to_semantic_events(payload, timestamp=observed_at)
        append_semantic_records(sidecar, summary_records)

        content_store = FullFidelityContentStore(sidecar.parent)
        content_records = gemini_hook_to_content_events(
            payload,
            store=content_store,
            timestamp=observed_at,
        )
        append_semantic_records(sidecar, content_records)
    except (OSError, RuntimeError, TimeoutError, TypeError, ValueError) as exc:
        print(f"ExecWeave Gemini hook warning: {exc}", file=sys.stderr)
        if args.strict:
            return 1
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
