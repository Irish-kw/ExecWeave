from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent_trace import provider_agent_trace_visibility_event
from .codex_adapter import (
    append_semantic_records,
    codex_hook_to_semantic_events,
    read_hook_payload,
)
from .codex_full_fidelity import (
    codex_hook_to_content_events,
    codex_hook_to_metadata_events,
)
from .codex_hook_lifecycle import (
    OFFICIAL_CODEX_HOOK_EVENTS,
    codex_official_hook_lifecycle_events,
)
from .content_store import FullFidelityContentStore
from .conversation_archive import codex_conversation_archive_events

_CAPTURE_ERRORS = (OSError, RuntimeError, TimeoutError, TypeError, ValueError)


def _hook_handler(command: str) -> dict[str, str]:
    return {"type": "command", "command": command}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _codex_trace_visibility_event(timestamp: str) -> dict[str, Any]:
    return provider_agent_trace_visibility_event(
        "codex",
        timestamp=timestamp,
        source={
            "type": "agent",
            "id": "agent:OpenAI Codex",
            "name": "OpenAI Codex",
            "attributes": {"provider": "codex"},
        },
        attribution="codex_hook",
        evidence_source="provider_hook",
    )


def codex_hook_config(command: str = "execweave-codex-hook") -> dict[str, Any]:
    handler = _hook_handler(command)
    tool_group = {"matcher": "*", "hooks": [handler]}
    plain_group = {"hooks": [handler]}
    hooks: dict[str, Any] = {}
    for event in (
        "PreToolUse",
        "PermissionRequest",
        "PostToolUse",
    ):
        hooks[event] = [tool_group]
    for event in (
        "PreCompact",
        "PostCompact",
        "SessionStart",
        "SessionEnd",
        "UserPromptSubmit",
        "SubagentStart",
        "SubagentStop",
        "Stop",
    ):
        hooks[event] = [plain_group]
    if set(hooks) != set(OFFICIAL_CODEX_HOOK_EVENTS):
        raise RuntimeError("Codex hook config drifted from the documented official event set")
    return {"hooks": hooks}


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


def _capture_warning(stage: str, exc: BaseException) -> None:
    print(f"ExecWeave Codex hook warning [{stage}]: {exc}", file=sys.stderr)


def _append_stage(
    sidecar: Path,
    records: list[dict[str, Any]],
    *,
    stage: str,
    failures: list[str],
) -> None:
    try:
        append_semantic_records(sidecar, records)
    except _CAPTURE_ERRORS as exc:
        failures.append(stage)
        _capture_warning(stage, exc)


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
        help=(
            "Return non-zero on telemetry errors after attempting every independent "
            "capture stage. Default is fail-open so tracing cannot block Codex."
        ),
    )
    parser.add_argument("--auto", action="store_true", help=argparse.SUPPRESS)
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
    except _CAPTURE_ERRORS as exc:
        _capture_warning("setup", exc)
        return 1 if args.strict else 0

    observed_at = _now()
    failures: list[str] = []

    # Every stage below is independent. In particular, optional full-fidelity content
    # capture must never prevent a provider-declared transcript from being archived.
    try:
        summary_records = codex_hook_to_semantic_events(payload, timestamp=observed_at)
        summary_records.extend(
            codex_official_hook_lifecycle_events(payload, timestamp=observed_at)
        )
        if payload.get("hook_event_name") == "SessionStart":
            summary_records.append(_codex_trace_visibility_event(observed_at))
    except _CAPTURE_ERRORS as exc:
        failures.append("summary_capture")
        _capture_warning("summary_capture", exc)
    else:
        _append_stage(
            sidecar,
            summary_records,
            stage="summary_append",
            failures=failures,
        )

    # The content store is itself optional telemetry infrastructure. If it is
    # unavailable, the lifecycle/summary stream above must still survive.
    try:
        content_store = FullFidelityContentStore(sidecar.parent)
    except _CAPTURE_ERRORS as exc:
        failures.append("content_store")
        _capture_warning("content_store", exc)
        return 1 if args.strict and failures else 0

    # Provider hook metadata is persisted separately from optional content values. A
    # failure while storing a final response/tool payload therefore cannot erase the
    # already-observed agent_transcript_path that is needed to diagnose the run.
    try:
        metadata_records = codex_hook_to_metadata_events(
            payload,
            store=content_store,
            timestamp=observed_at,
        )
    except _CAPTURE_ERRORS as exc:
        failures.append("metadata_capture")
        _capture_warning("metadata_capture", exc)
    else:
        _append_stage(
            sidecar,
            metadata_records,
            stage="metadata_append",
            failures=failures,
        )

    try:
        content_records = codex_hook_to_content_events(
            payload,
            store=content_store,
            timestamp=observed_at,
            include_metadata=False,
        )
    except _CAPTURE_ERRORS as exc:
        failures.append("content_capture")
        _capture_warning("content_capture", exc)
    else:
        _append_stage(
            sidecar,
            content_records,
            stage="content_append",
            failures=failures,
        )

    try:
        archive_records = codex_conversation_archive_events(
            payload,
            store=content_store,
            timestamp=observed_at,
        )
    except _CAPTURE_ERRORS as exc:
        failures.append("conversation_archive")
        _capture_warning("conversation_archive", exc)
    else:
        _append_stage(
            sidecar,
            archive_records,
            stage="archive_append",
            failures=failures,
        )

    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
