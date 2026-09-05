"""Native Windows-only terminal contract; never fake os.name."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ollama_interactive_acceptance as interactive  # noqa: E402


def test_windows_terminal_explicitly_overrides_backend_environment(tmp_path, monkeypatch) -> None:
    if os.name != "nt":
        pytest.skip("Windows ConPTY environment contract; POSIX uses its separate native PTY gate")
    from winpty import PtyProcess

    original_spawn = PtyProcess.spawn
    selected = []

    def spawn(*args, **kwargs):
        selected.append(kwargs.get("backend"))
        return original_spawn(*args, **kwargs)

    monkeypatch.setenv("PYWINPTY_BACKEND", "1")
    monkeypatch.setattr(PtyProcess, "spawn", spawn)
    artifact = tmp_path / "explicit-conpty.txt"
    terminal = interactive._spawn_terminal(
        [sys.executable, "-c", "import os,sys; print('TTY='+str(os.isatty(0)),flush=True); print('ECHO='+input(),flush=True)"],
        cwd=tmp_path, env=dict(os.environ), artifact=artifact,
    )
    try:
        terminal.write("HELLO\r")
        assert terminal.wait(10)
    finally:
        terminal.close()
    assert selected == ["0"]
    assert "TTY=True" in artifact.read_text(encoding="utf-8")
    assert "ECHO=HELLO" in artifact.read_text(encoding="utf-8")
