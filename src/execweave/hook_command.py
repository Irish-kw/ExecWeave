"""Rootless hooks tied to the installing interpreter, not an agent's PATH."""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

_MODULES = {
    "claude": "execweave.claude_hook_cli",
    "codex": "execweave.codex_hook_entry",
    "antigravity": "execweave.antigravity_hook_cli",
    "cursor": "execweave.cursor_hook_cli",
    "opencode": "execweave.opencode_hook_cli",
}


def hook_argv(provider: str) -> list[str]:
    # Do NOT resolve symlinks: a venv's python symlink must retain its venv path.
    return [str(Path(sys.executable).absolute()), "-I", "-m", _MODULES[provider], "--auto"]


def hook_command(provider: str) -> str:
    parts = hook_argv(provider)
    return subprocess.list2cmdline(parts) if os.name == "nt" else shlex.join(parts)


def hook_markers(marker: str) -> tuple[str, ...]:
    provider = marker.removeprefix("execweave-").removesuffix("-hook")
    module = _MODULES.get(provider)
    return (marker, module) if module else (marker,)
