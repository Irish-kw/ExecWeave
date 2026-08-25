from __future__ import annotations

import os
import shutil
from pathlib import Path


def _looks_like_path(value: str) -> bool:
    return (
        Path(value).is_absolute()
        or value.startswith((".", "~"))
        or "/" in value
        or "\\" in value
    )


def _resolve_executable(executable: str, *, path: str | None = None) -> str:
    if not executable.strip():
        raise ValueError("command executable must not be empty")

    if _looks_like_path(executable):
        candidate = Path(executable).expanduser()
        if not candidate.is_file():
            raise FileNotFoundError(f"command executable not found: {executable!r}")
        resolved = str(candidate.resolve())
    else:
        resolved = shutil.which(executable, path=path)
        if resolved is None:
            raise FileNotFoundError(
                f"command executable {executable!r} was not found on PATH; "
                "install it or make its launcher available on PATH"
            )

    if os.name != "nt" and not os.access(resolved, os.X_OK):
        raise PermissionError(f"command executable is not executable: {resolved!r}")
    return resolved


def resolve_launch_command(command: list[str], *, path: str | None = None) -> list[str]:
    """Resolve a shell-visible command into an argv safe for ``subprocess``.

    ExecWeave launches commands without ``shell=True``. On POSIX, ``shutil.which``
    mirrors PATH lookup for normal executables and shebang scripts. On Windows it
    also honors PATHEXT, which is required for npm-style ``.cmd``/``.bat`` shims
    such as Codex, Cursor, Claude, Gemini, and OpenCode launchers.

    An explicitly supplied PowerShell ``.ps1`` file is launched through pwsh or
    Windows PowerShell because CreateProcess cannot execute a PowerShell script by
    itself. The caller's original command should remain the evidence-facing value;
    this function only returns the argv used to start the child process.
    """
    if not command:
        raise ValueError("command must not be empty")

    resolved = _resolve_executable(command[0], path=path)
    arguments = list(command[1:])

    if os.name == "nt" and Path(resolved).suffix.lower() == ".ps1":
        search_path = path if path is not None else os.environ.get("PATH")
        powershell = shutil.which("pwsh.exe", path=search_path) or shutil.which(
            "powershell.exe", path=search_path
        )
        if powershell is None:
            raise FileNotFoundError(
                "PowerShell script requested, but neither pwsh.exe nor powershell.exe "
                "was found on PATH"
            )
        return [powershell, "-NoLogo", "-NoProfile", "-File", resolved, *arguments]

    return [resolved, *arguments]
