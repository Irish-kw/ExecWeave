from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import time
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SEMANTIC_ENV = "EXECWEAVE_SEMANTIC_SIDECAR"
_AUTO_FLAG = "--auto"
_STRICT_FLAG = "--strict"
_INTERRUPT_EVENT = "Interrupt"
_INTERRUPT_LOCK_BUDGET_SECONDS = 0.15
_HOOKS_REFERENCE = "https://learn.chatgpt.com/docs/hooks"


def _arguments(argv: Sequence[str] | None) -> list[str]:
    return list(sys.argv[1:] if argv is None else argv)


def _load_capture_main():
    # Keep the globally installed passive hook cheap and isolated from the capture
    # stack. Inactive Codex sessions must not import telemetry code at all.
    from .codex_hook_cli import main as capture_main

    return capture_main


def _automatic_capture_enabled() -> bool:
    configured = os.environ.get(_SEMANTIC_ENV, "")
    return bool(configured.strip())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _interrupt_record(payload: dict[str, Any], *, timestamp: str) -> dict[str, Any]:
    session_id = payload.get("session_id")
    turn_id = payload.get("turn_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("Codex Interrupt payload requires session_id")
    if not isinstance(turn_id, str) or not turn_id:
        raise ValueError("Codex Interrupt payload requires turn_id")

    stable = json.dumps(
        {
            "session_id": session_id,
            "turn_id": turn_id,
            "hook_event_name": _INTERRUPT_EVENT,
            "timestamp": timestamp,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    observation_id = hashlib.sha256(stable.encode("utf-8")).hexdigest()[:24]
    attributes: dict[str, Any] = {
        "backend": "semantic",
        "provider": "codex",
        "evidence_source": "provider_hook",
        "attribution": "codex_official_hook_contract",
        "causal": False,
        "inferred": False,
        "official_hook_contract": True,
        "official_hook_reference": _HOOKS_REFERENCE,
        "codex_hook_event_name": _INTERRUPT_EVENT,
        "codex_session_id": session_id,
        "codex_turn_id": turn_id,
    }
    for key in ("cwd", "model", "permission_mode"):
        value = payload.get(key)
        if isinstance(value, (str, int, float, bool)) and value != "":
            attributes[f"codex_{key}"] = value

    return {
        "timestamp": timestamp,
        "event_type": "semantic.codex.turn.interrupted",
        "relation": "OBSERVED_TURN_INTERRUPT",
        "source": {
            "type": "agent",
            "id": "agent:OpenAI Codex",
            "name": "OpenAI Codex",
            "attributes": {},
        },
        "target": {
            "type": "agent_turn_interrupt",
            "id": f"agent-turn-interrupt:codex:{observation_id}",
            "name": f"Codex turn interrupt {turn_id}",
            "attributes": {
                "provider": "codex",
                "session_id": session_id,
                "turn_id": turn_id,
                "interrupt_semantics": "provider_interrupt_hook_observation",
            },
        },
        "attributes": attributes,
    }


def _append_interrupt_fast(sidecar: Path, payload: dict[str, Any]) -> None:
    """Persist Interrupt without importing the normal capture stack.

    Codex gives Interrupt only one second by default and at most three seconds.
    The ordinary semantic writer can wait up to five seconds for its lock, which is
    correct for normal lifecycle hooks but incompatible with Interrupt. This path
    therefore uses a tiny bounded lock budget and drops only this best-effort
    observation when another writer owns the sidecar lock. It never blocks Codex.
    """

    output = sidecar.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    record = _interrupt_record(payload, timestamp=_now())
    blob = json.dumps(
        record, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ) + "\n"
    lock_dir = output.with_name(output.name + ".lock")
    deadline = time.monotonic() + _INTERRUPT_LOCK_BUDGET_SECONDS
    while True:
        try:
            lock_dir.mkdir()
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                return
            time.sleep(0.005)
    try:
        with output.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(blob)
            handle.flush()
    finally:
        try:
            lock_dir.rmdir()
        except OSError:
            pass


def _active_auto_payload() -> tuple[str, dict[str, Any] | None]:
    raw = sys.stdin.read()
    if not isinstance(raw, str):
        return "", None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw, None
    return raw, payload if isinstance(payload, dict) else None


def main(argv: Sequence[str] | None = None) -> int:
    """Fail-open boundary for the globally installed Codex hook command.

    ExecWeave intentionally leaves the Codex hook configuration installed so a run
    launched through ExecWeave can inherit its semantic sidecar automatically. A
    normal Codex session has no run-bound sidecar, so ``--auto`` is a completely
    inert success path.

    Active Interrupt hooks use a minimal stdlib-only writer because Codex allows at
    most three seconds for Interrupt and defaults to one second. Other active hooks
    enter the full capture stack. Passive ``--auto`` hooks still normalize telemetry
    failures to success so observation can never break the Codex UI.
    """

    args = _arguments(argv)
    automatic = _AUTO_FLAG in args
    strict = _STRICT_FLAG in args

    if automatic and not _automatic_capture_enabled():
        return 0

    if automatic and not strict:
        raw, payload = _active_auto_payload()
        if payload is not None and payload.get("hook_event_name") == _INTERRUPT_EVENT:
            try:
                configured = os.environ.get(_SEMANTIC_ENV, "").strip()
                if configured:
                    _append_interrupt_fast(Path(configured), payload)
            except BaseException:  # noqa: BLE001 - Interrupt telemetry must never delay Codex
                pass
            return 0
        sys.stdin = io.StringIO(raw)

    if not automatic or strict:
        return _load_capture_main()(args)

    try:
        _load_capture_main()(args)
    except BaseException:  # noqa: BLE001 - the passive hook must never block Codex
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
