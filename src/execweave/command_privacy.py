"""Deliberately metadata-only argv serialization for recorded OS processes.

An arbitrary Python argument may itself be a secret or full prompt; a denylist
of flag spellings cannot protect it. Keep only executable and script basename
when the script is an unambiguous .py path. Actual child argv is unchanged.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable


def public_command(command: Iterable[str]) -> list[str]:
    argv = list(command)
    if not argv:
        return []
    display = [Path(argv[0]).name]
    if len(argv) > 1 and argv[1].endswith(".py") and not argv[1].startswith("-"):
        display.append(Path(argv[1]).name)
    return display
