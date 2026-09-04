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


def _cursor_desktop_from_launcher(launcher: str | None) -> str | None:
    """Resolve Cursor.exe beside a Windows VS Code-style PATH shim."""
    if not launcher or os.name != "nt":
        return None
    path = Path(launcher).expanduser()
    bin_dir = path.parent
    app_dir = bin_dir.parent
    resources_dir = app_dir.parent
    install_root = resources_dir.parent
    if (
        bin_dir.name.lower() != "bin"
        or app_dir.name.lower() != "app"
        or resources_dir.name.lower() != "resources"
    ):
        return None
    candidate = install_root / "Cursor.exe"
    if candidate.is_file():
        return str(candidate.resolve())
    return None


def _resolve_cursor_desktop(*, path_launcher: str | None = None) -> str | None:
    derived = _cursor_desktop_from_launcher(path_launcher)
    if derived is not None:
        return derived
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
        path_launcher = shutil.which(executable, path=path)
        if executable.lower() == "cursor" and os.name == "nt":
            resolved = _resolve_cursor_desktop(path_launcher=path_launcher) or path_launcher
        else:
            resolved = path_launcher
            if resolved is None and executable.lower() == "cursor":
                resolved = _resolve_cursor_desktop()
        if resolved is None and executable.lower() == "antigravity":
            resolved = shutil.which("agy", path=path)
        if resolved is None:
            detail = ""
            if executable.lower() == "cursor":
                detail = (
                    "; ExecWeave also checked the Cursor desktop binary beside the PATH "
                    "launcher and the standard desktop-app install paths"
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

    Bare ``cursor`` on Windows prefers the desktop application binary. ExecWeave
    first derives ``Cursor.exe`` from a VS Code-style PATH shim such as
    ``<install>/resources/app/bin/cursor.cmd`` and then checks standard desktop
    install paths. This keeps the GUI process and provider hooks in the ExecWeave
    launch environment instead of treating a short-lived CLI shim as the observed
    application lifetime. Explicit launcher paths are never rewritten.

    ``antigravity`` is accepted as a friendly alias for Google's current
    Antigravity CLI executable, ``agy``.

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
