from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _looks_like_path(value: str) -> bool:
    return (
        Path(value).is_absolute()
        or value.startswith((".", "~"))
        or "/" in value
        or "\\" in value
    )


def _cursor_desktop_candidates() -> list[Path]:
    home = Path.home()
    if sys.platform == "darwin":
        return [
            home / "Applications" / "Cursor.app" / "Contents" / "MacOS" / "Cursor",
            Path("/Applications/Cursor.app/Contents/MacOS/Cursor"),
        ]
    if os.name == "nt":
        candidates: list[Path] = []
        local_app_data = os.environ.get("LOCALAPPDATA")
        program_files = os.environ.get("ProgramFiles")
        program_files_x86 = os.environ.get("ProgramFiles(x86)")
        if local_app_data:
            candidates.append(Path(local_app_data) / "Programs" / "cursor" / "Cursor.exe")
        if program_files:
            candidates.append(Path(program_files) / "cursor" / "Cursor.exe")
        if program_files_x86:
            candidates.append(Path(program_files_x86) / "cursor" / "Cursor.exe")
        return candidates
    return []


def _resolve_cursor_desktop() -> str | None:
    for candidate in _cursor_desktop_candidates():
        if candidate.is_file():
            return str(candidate.resolve())
    return None


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
        if resolved is None and executable.lower() == "cursor":
            resolved = _resolve_cursor_desktop()
        if resolved is None and executable.lower() == "antigravity":
            resolved = shutil.which("agy", path=path)
        if resolved is None:
            detail = ""
            if executable.lower() == "cursor":
                detail = (
                    "; ExecWeave also checked the standard Cursor desktop-app install paths"
                )
            elif executable.lower() == "antigravity":
                detail = "; the current Antigravity CLI executable is 'agy'"
            raise FileNotFoundError(
                f"command executable {executable!r} was not found on PATH{detail}; "
                "install it or make its launcher available on PATH"
            )

    if os.name != "nt" and not os.access(resolved, os.X_OK):
        raise PermissionError(f"command executable is not executable: {resolved!r}")
    return resolved


def resolve_launch_command(command: list[str], *, path: str | None = None) -> list[str]:
    """Resolve a user-facing command into an argv safe for ``subprocess``.

    ExecWeave launches commands without ``shell=True``. Normal executables use PATH
    lookup. On Windows, PATHEXT keeps npm-style ``.cmd``/``.bat`` launchers working.

    ``cursor`` additionally falls back to the standard macOS/Windows desktop app
    binaries when no CLI launcher exists on PATH. ``antigravity`` is accepted as a
    friendly alias for Google's current Antigravity CLI executable, ``agy``.

    An explicitly supplied PowerShell ``.ps1`` file is launched through pwsh or
    Windows PowerShell because CreateProcess cannot execute a PowerShell script by
    itself. The caller's original command remains the evidence-facing value; this
    function only returns the argv used to start the child process.
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
