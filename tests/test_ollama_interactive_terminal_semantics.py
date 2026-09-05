from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ollama_interactive_acceptance as interactive  # noqa: E402


class _FakeTerminal:
    pid = 4242
    backend = "fake-pty"

    def __init__(self, *, exit_on_ctrl_c: bool = False) -> None:
        self.alive = True
        self.exit_on_ctrl_c = exit_on_ctrl_c
        self.writes: list[str] = []
        self.closed = False

    def write(self, text: str) -> None:
        self.writes.append(text)
        if text == "\x03" and self.exit_on_ctrl_c:
            self.alive = False
        if text == "/bye\r":
            self.alive = False

    def is_alive(self) -> bool:
        return self.alive

    def close(self) -> None:
        self.closed = True
        self.alive = False


def test_ollama_exit_sequence_uses_terminal_ctrl_c_then_bye() -> None:
    inner = _FakeTerminal()
    terminal = interactive._OllamaExitAwareTerminal(inner, interrupt_pause=0)

    terminal.interrupt()

    assert inner.writes == ["\x03", "/bye\r"]
    assert terminal.is_alive() is False


def test_ctrl_c_must_not_be_misinterpreted_as_ollama_exit() -> None:
    inner = _FakeTerminal(exit_on_ctrl_c=True)
    terminal = interactive._OllamaExitAwareTerminal(inner, interrupt_pause=0)

    with pytest.raises(AssertionError, match="exited on Ctrl\+C"):
        terminal.interrupt()

    assert inner.writes == ["\x03"]


def test_exit_aware_terminal_preserves_identity_backend_and_cleanup() -> None:
    inner = _FakeTerminal()
    terminal = interactive._OllamaExitAwareTerminal(inner, interrupt_pause=0)

    assert terminal.pid == inner.pid
    assert terminal.backend == inner.backend
    terminal.close()
    assert inner.closed is True
