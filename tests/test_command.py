from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from execweave.collector import infer_agent_name
from execweave.command import resolve_launch_command


def _prepend_path(monkeypatch, directory: Path) -> None:
    current = os.environ.get("PATH", "")
    value = str(directory) if not current else f"{directory}{os.pathsep}{current}"
    monkeypatch.setenv("PATH", value)


def test_infer_agent_name_normalizes_windows_launcher_suffixes() -> None:
    assert infer_agent_name(["codex.cmd"]) == "OpenAI Codex"
    assert infer_agent_name(["claude.exe"]) == "Claude Code"
    assert infer_agent_name(["gemini.bat"]) == "Gemini CLI"
    assert infer_agent_name(["cursor.ps1"]) == "Cursor"
    assert infer_agent_name(["opencode.cmd"]) == "OpenCode"


def test_missing_command_has_actionable_error(monkeypatch) -> None:
    monkeypatch.setenv("PATH", "")
    with pytest.raises(FileNotFoundError, match="was not found on PATH"):
        resolve_launch_command(["execweave-command-that-does-not-exist-83a219"])


@pytest.mark.skipif(os.name == "nt", reason="POSIX launcher test")
def test_posix_path_script_is_resolved_and_launchable(tmp_path: Path, monkeypatch) -> None:
    shim = tmp_path / "codex"
    shim.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    shim.chmod(0o755)
    _prepend_path(monkeypatch, tmp_path)

    resolved = resolve_launch_command(["codex"])

    assert Path(resolved[0]).resolve() == shim.resolve()
    assert subprocess.run(resolved, cwd=tmp_path, check=False).returncode == 0


@pytest.mark.skipif(os.name != "nt", reason="Windows launcher test")
@pytest.mark.parametrize("agent", ["codex", "cursor", "claude", "gemini", "opencode"])
def test_windows_cmd_shim_is_resolved_and_launchable(
    agent: str, tmp_path: Path, monkeypatch
) -> None:
    shim = tmp_path / f"{agent}.cmd"
    shim.write_text("@echo off\r\nexit /b 0\r\n", encoding="utf-8")
    _prepend_path(monkeypatch, tmp_path)

    resolved = resolve_launch_command([agent])

    assert Path(resolved[0]).resolve() == shim.resolve()
    assert subprocess.run(resolved, cwd=tmp_path, check=False).returncode == 0


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell launcher test")
def test_explicit_powershell_script_uses_powershell(tmp_path: Path) -> None:
    powershell = shutil.which("pwsh.exe") or shutil.which("powershell.exe")
    if powershell is None:
        pytest.skip("PowerShell is not installed")

    script = tmp_path / "probe.ps1"
    script.write_text("exit 0\n", encoding="utf-8")
    resolved = resolve_launch_command([str(script)])

    assert Path(resolved[0]).resolve() == Path(powershell).resolve()
    assert "-File" in resolved
    assert subprocess.run(resolved, cwd=tmp_path, check=False).returncode == 0
