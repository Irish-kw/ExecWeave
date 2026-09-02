from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from .agent_topology import (
    EVIDENCE_CROSS_AGENT_ROUTING,
    PATH_EXECWEAVE_DERIVED,
    PATH_PROVIDER_DECLARED,
    THREAD_ID_EXECWEAVE_DERIVED,
    THREAD_ID_PROVIDER_NATIVE,
)

_MAX_IDENTITY_SCAN_LINES = 64
_MAX_PREVIEW_MESSAGES = 80
_MAX_PREVIEW_TEXT_CHARS = 6000


def _canonical_absolute_path(value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        path = Path(value).expanduser()
        if not path.is_absolute():
            return None
        return path.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return None


def _codex_sessions_root() -> Path:
    configured = os.environ.get("CODEX_HOME")
    home = Path(configured).expanduser() if configured else Path.home() / ".codex"
    return (home / "sessions").resolve(strict=False)


def _inside_codex_sessions(path: Path) -> bool:
    try:
        path.relative_to(_codex_sessions_root())
    except ValueError:
        return False
    return True


def _history_base_end_ordinal(payload: dict[str, Any]) -> int:
    history_base = payload.get("history_base")
    if not isinstance(history_base, dict):
        return 0
    value = history_base.get("end_ordinal_exclusive")
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _session_meta_identity(payload: dict[str, Any]) -> dict[str, Any] | None:
    thread_id = payload.get("id") or payload.get("session_id")
    if not isinstance(thread_id, str) or not thread_id:
        return None
    source = payload.get("source")
    spawn: dict[str, Any] = {}
    if isinstance(source, dict):
        subagent = source.get("subagent")
        if isinstance(subagent, dict):
            candidate = subagent.get("thread_spawn")
            if isinstance(candidate, dict):
                spawn = candidate
    agent_path = payload.get("agent_path") or spawn.get("agent_path")
    nickname = payload.get("agent_nickname") or spawn.get("agent_nickname")
    parent_thread_id = payload.get("parent_thread_id") or spawn.get("parent_thread_id")
    history_start = payload.get("subagent_history_start_ordinal")
    return {
        "thread_id": thread_id,
        "parent_thread_id": parent_thread_id if isinstance(parent_thread_id, str) else None,
        "agent_path": agent_path if isinstance(agent_path, str) else None,
        "agent_nickname": nickname if isinstance(nickname, str) else None,
        "history_base_end_ordinal": _history_base_end_ordinal(payload),
        "subagent_history_start_ordinal": (
            history_start
            if isinstance(history_start, int) and not isinstance(history_start, bool) and history_start >= 0
            else None
        ),
    }


def _sanitize_path_leaf(value: str) -> str | None:
    leaf = " ".join(value.replace("\\", "-").replace("/", "-").split())
    return leaf or None


def _resolved_agent_path(identity: dict[str, Any]) -> tuple[str | None, str]:
    """Prefer Codex's own path; otherwise /root/<nickname> when a parent exists.

    Windows Codex sessions in the field have been observed to publish nickname and
    parent_thread_id without agent_path. The dashboard child-round splitter addresses
    messages by recipient === path, so a missing path drops every later fold.
    """
    declared = identity.get("agent_path")
    if isinstance(declared, str) and declared:
        return declared, PATH_PROVIDER_DECLARED
    if identity.get("parent_thread_id") is None:
        return "/root", PATH_EXECWEAVE_DERIVED
    nickname = identity.get("agent_nickname")
    if not isinstance(nickname, str):
        return None, PATH_EXECWEAVE_DERIVED
    leaf = _sanitize_path_leaf(nickname)
    if leaf is None:
        return None, PATH_EXECWEAVE_DERIVED
    return f"/root/{leaf}", PATH_EXECWEAVE_DERIVED


def codex_rollout_identity(path: str | Path) -> dict[str, Any] | None:
    """Read only leading Codex session metadata needed for exact thread identity."""
    source = Path(path).expanduser().resolve(strict=False)
    try:
        with source.open("r", encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                if index >= _MAX_IDENTITY_SCAN_LINES:
                    break
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    return None
                if record.get("type") != "session_meta":
                    continue
                payload = record.get("payload")
                return _session_meta_identity(payload) if isinstance(payload, dict) else None
    except (OSError, RuntimeError, UnicodeError):
        return None
    return None
