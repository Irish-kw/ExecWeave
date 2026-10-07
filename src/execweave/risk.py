"""Conservative risk classification for observations, never enforcement claims."""
from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath
from typing import Mapping, Sequence

_PRIVILEGE_LAUNCHERS = frozenset({"sudo", "doas", "pkexec", "su", "runas"})
_POSIX_SYSTEM_PREFIXES = (
    ("/etc", "system_configuration"),
    ("/usr", "system_software"),
    ("/bin", "system_software"),
    ("/sbin", "system_software"),
    ("/lib", "system_software"),
    ("/lib64", "system_software"),
    ("/boot", "boot_configuration"),
    ("/System", "macos_system"),
    ("/Library", "macos_system_library"),
)


def _command_basename(value: str) -> str:
    name = Path(value).name.lower()
    for suffix in (".exe", ".cmd", ".bat", ".ps1"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name


def privilege_process_trigger(
    *,
    name: str,
    cmdline: Sequence[str],
    exe: str | None = None,
) -> str | None:
    candidates = [name, exe or "", cmdline[0] if cmdline else ""]
    for value in candidates:
        if value and _command_basename(value) in _PRIVILEGE_LAUNCHERS:
            return _command_basename(value)
    lowered = [part.lower() for part in cmdline]
    executable = _command_basename(candidates[-1] or name)
    if executable in {"powershell", "pwsh"}:
        for index, part in enumerate(lowered[:-1]):
            if part in {"-verb", "/verb"} and lowered[index + 1] == "runas":
                return "powershell_runas"
    return None


def system_path_category(
    path: str | Path,
    *,
    os_name: str | None = None,
    environment: Mapping[str, str] | None = None,
) -> str | None:
    platform = os.name if os_name is None else os_name
    if platform == "nt":
        env = os.environ if environment is None else environment
        candidate = str(PureWindowsPath(str(path))).casefold().rstrip("\\/")
        roots = []
        for key, category in (
            ("SystemRoot", "windows_system"),
            ("ProgramFiles", "installed_programs"),
            ("ProgramFiles(x86)", "installed_programs"),
            ("ProgramData", "system_program_data"),
        ):
            raw = env.get(key)
            if raw:
                roots.append((str(PureWindowsPath(raw)).casefold().rstrip("\\/"), category))
        # Standard roots remain covered even in deliberately sparse environments.
        roots.extend(((r"c:\\windows", "windows_system"),
                      (r"c:\\program files", "installed_programs"),
                      (r"c:\\program files (x86)", "installed_programs"),
                      (r"c:\\programdata", "system_program_data")))
        for root, category in roots:
            if candidate == root or candidate.startswith(root + "\\"):
                return category
        return None

    candidate = str(path)
    for prefix, category in _POSIX_SYSTEM_PREFIXES:
        if candidate == prefix or candidate.startswith(prefix + "/"):
            return category
    return None


def risk_attributes(kind: str, trigger: str, **details: object) -> dict[str, object]:
    return {
        "risk_kind": kind,
        "trigger": trigger,
        "severity": "high",
        "default_decision": "deny",
        "enforced": False,
        "control_state": "observation_only",
        **details,
    }
