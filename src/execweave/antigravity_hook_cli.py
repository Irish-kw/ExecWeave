from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .antigravity_adapter import (
    antigravity_hook_to_semantic_events,
    append_semantic_records,
    read_hook_payload,
)
from .antigravity_full_fidelity import antigravity_hook_to_content_events
from .content_store import FullFidelityContentStore


def _handler(event: str) -> dict[str, Any]:
    return {
        "type": "command",
        "command": f"execweave-antigravity-hook --auto --event {event}",
        "timeout": 30,
    }


def antigravity_hook_config() -> dict[str, Any]:
    """Return a passive Antigravity hooks.json fragment.

    ExecWeave intentionally avoids PreToolUse because its response can alter the
    user's permission decision. PostToolUse is observational and returns ``{}``.
    """
    return {
        "execweave-observability": {
            "enabled": True,
            "PostToolUse": [
                {
                    "matcher": "*",
                    "hooks": [_handler("PostToolUse")],
                }
            ],
            "PreInvocation": [_handler("PreInvocation")],
            "PostInvocation": [_handler("PostInvocation")],
        }
    }


def _default_sidecar(payload: dict[str, Any]) -> Path:
    roots = payload.get("workspacePaths")
    if not isinstance(roots, list) or not roots or not isinstance(roots[0], str):
        raise ValueError("Antigravity hook payload has no workspacePaths for sidecar placement")
    conversation = payload.get("conversationId")
    if not isinstance(conversation, str) or not conversation:
        raise ValueError("Antigravity hook payload has no conversationId for sidecar placement")
    safe = "".join(
        character if character.isalnum() or character in {"-", "_", "."} else "_"
        for character in conversation
    )
    return Path(roots[0]) / ".execweave" / "semantic" / "antigravity" / f"{safe}.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="execweave-antigravity-hook",
        description="Capture Google Antigravity hook input as local ExecWeave semantic telemetry.",
    )
    parser.add_argument("--sidecar", type=Path, default=None)
    parser.add_argument(
        "--event",
        choices=["PostToolUse", "PreInvocation", "PostInvocation"],
        default=None,
    )
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--auto", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--print-config", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.print_config:
        print(json.dumps(antigravity_hook_config(), indent=2, sort_keys=True))
        return 0
    if args.auto and not os.environ.get("EXECWEAVE_SEMANTIC_SIDECAR"):
        print("{}")
        return 0
    if args.event is None:
        print("ExecWeave Antigravity hook warning: --event is required", file=sys.stderr)
        return 1 if args.strict else 0

    try:
        payload = read_hook_payload()
        sidecar = args.sidecar
        if sidecar is None:
            configured = os.environ.get("EXECWEAVE_SEMANTIC_SIDECAR")
            sidecar = Path(configured) if configured else _default_sidecar(payload)
        sidecar = Path(sidecar).expanduser().resolve()

        summary = antigravity_hook_to_semantic_events(payload, hook_event=args.event)
        append_semantic_records(sidecar, summary)
        store = FullFidelityContentStore(sidecar.parent)
        content = antigravity_hook_to_content_events(
            payload,
            hook_event=args.event,
            store=store,
        )
        append_semantic_records(sidecar, content)
    except (OSError, RuntimeError, TimeoutError, TypeError, ValueError) as exc:
        print(f"ExecWeave Antigravity hook warning: {exc}", file=sys.stderr)
        if args.strict:
            return 1
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
