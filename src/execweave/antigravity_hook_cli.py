from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .antigravity_adapter import (
    antigravity_hook_to_semantic_events,
    append_semantic_records,
    read_hook_payload,
)
from .antigravity_full_fidelity import antigravity_hook_to_content_events
from .antigravity_trace_capability import antigravity_agent_trace_visibility_event
from .content_store import FullFidelityContentStore
from .conversation_archive import antigravity_conversation_archive_events

_CAPTURE_ERRORS = (OSError, RuntimeError, TimeoutError, TypeError, ValueError)

ANTIGRAVITY_OFFICIAL_HOOK_EVENTS = (
    "PreToolUse",
    "PostToolUse",
    "PreInvocation",
    "PostInvocation",
    "Stop",
)
ANTIGRAVITY_PASSIVE_HOOK_EVENTS = (
    "PostToolUse",
    "PreInvocation",
    "PostInvocation",
    "Stop",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _handler(event: str) -> dict[str, Any]:
    return {
        "type": "command",
        "command": f"execweave-antigravity-hook --auto --event {event}",
        "timeout": 30,
    }


def _passive_response(event: str | None) -> dict[str, str]:
    if event == "Stop":
        return {"decision": "stop"}
    return {}


def antigravity_hook_config() -> dict[str, Any]:
    """Return a passive Antigravity hooks.json fragment.

    PreToolUse is deliberately excluded because its required response participates
    in Antigravity's permission gating. The remaining hooks are observational;
    Stop explicitly returns a non-``continue`` decision so ExecWeave never keeps
    an execution loop alive.
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
            "Stop": [_handler("Stop")],
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
        choices=list(ANTIGRAVITY_PASSIVE_HOOK_EVENTS),
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
        print(json.dumps(_passive_response(args.event), sort_keys=True))
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
    except _CAPTURE_ERRORS as exc:
        print(f"ExecWeave Antigravity hook warning [setup]: {exc}", file=sys.stderr)
        print(json.dumps(_passive_response(args.event), sort_keys=True))
        return 1 if args.strict else 0

    observed_at = _now()
    # Match Codex: each capture stage is independent so a metadata/content
    # failure cannot skip the provider-declared transcript snapshot.
    try:
        summary = antigravity_hook_to_semantic_events(
            payload,
            hook_event=args.event,
            timestamp=observed_at,
        )
        if args.event == "PreInvocation":
            summary.append(
                antigravity_agent_trace_visibility_event(
                    timestamp=observed_at,
                    attribution="antigravity_hook",
                    evidence_source="provider_hook",
                )
            )
        append_semantic_records(sidecar, summary)
    except _CAPTURE_ERRORS as exc:
        print(f"ExecWeave Antigravity hook warning [summary_capture]: {exc}", file=sys.stderr)
        if args.strict:
            print(json.dumps(_passive_response(args.event), sort_keys=True))
            return 1

    try:
        store = FullFidelityContentStore(sidecar.parent)
    except _CAPTURE_ERRORS as exc:
        print(f"ExecWeave Antigravity hook warning [content_store]: {exc}", file=sys.stderr)
        print(json.dumps(_passive_response(args.event), sort_keys=True))
        return 1 if args.strict else 0

    try:
        content = antigravity_hook_to_content_events(
            payload,
            hook_event=args.event,
            store=store,
            timestamp=observed_at,
        )
        append_semantic_records(sidecar, content)
    except _CAPTURE_ERRORS as exc:
        print(f"ExecWeave Antigravity hook warning [content_capture]: {exc}", file=sys.stderr)
        if args.strict:
            print(json.dumps(_passive_response(args.event), sort_keys=True))
            return 1

    if args.event in {"PreInvocation", "PostInvocation", "Stop"}:
        try:
            archived = antigravity_conversation_archive_events(
                payload,
                store=store,
                timestamp=observed_at,
            )
            append_semantic_records(sidecar, archived)
        except _CAPTURE_ERRORS as exc:
            print(
                f"ExecWeave Antigravity hook warning [conversation_archive]: {exc}",
                file=sys.stderr,
            )
            if args.strict:
                print(json.dumps(_passive_response(args.event), sort_keys=True))
                return 1

    print(json.dumps(_passive_response(args.event), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
