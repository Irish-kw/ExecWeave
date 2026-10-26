#!/usr/bin/env python3
"""Formal G5 interactive acceptance with provider-correct terminal exit semantics.

The stable terminal primitives and compatibility surface live in
``_ollama_interactive_acceptance_impl``. The formal journey is supplied by
``acceptance.g5_runner`` so browser diagnostics, owned network evidence, crash
persistence, and bounded cleanup share the hardened acceptance contracts.
"""

from __future__ import annotations

import time
from typing import Any

import _ollama_interactive_acceptance_impl as _impl

# Preserve the historical module surface because tests and handoff commands import
# private harness helpers directly. Provider-aware overrides below replace only the
# terminal spawn path and formal journey.
for _name in dir(_impl):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_impl, _name)

_ORIGINAL_SPAWN_TERMINAL = _impl._spawn_terminal


class _OllamaExitAwareTerminal(_impl._TerminalBase):
    """Delegate a real PTY/ConPTY while enforcing Ollama's Ctrl+C/exit contract."""

    def __init__(
        self,
        terminal: _impl._TerminalBase,
        *,
        interrupt_pause: float = 0.25,
    ) -> None:
        self._terminal = terminal
        self.pid = terminal.pid
        self.backend = terminal.backend
        self._interrupt_pause = max(0.0, float(interrupt_pause))

    def write(self, text: str) -> None:
        self._terminal.write(text)

    def interrupt(self) -> None:
        if not self.is_alive():
            return
        # Ollama documents Ctrl+C as "stop the model from responding". Send the
        # control byte through the pseudo-terminal on every OS; an external POSIX
        # SIGINT is not equivalent to a terminal Ctrl+C interaction.
        self.write("\x03")
        if self._interrupt_pause:
            time.sleep(self._interrupt_pause)
        if not self.is_alive():
            raise AssertionError(
                "interactive Ollama exited on Ctrl+C; expected Ctrl+C to interrupt "
                "while /bye or Ctrl+D performs exit"
            )
        self.write("/bye\r")

    def is_alive(self) -> bool:
        return self._terminal.is_alive()

    def close(self) -> None:
        self._terminal.close()


def _spawn_terminal(*args: Any, **kwargs: Any) -> _impl._TerminalBase:
    terminal = _ORIGINAL_SPAWN_TERMINAL(*args, **kwargs)
    return _OllamaExitAwareTerminal(terminal)


# _run_interactive is defined in the implementation module and resolves this global
# there, so patch the provider-aware terminal seam before importing the hardened
# journey that uses it.
_impl._spawn_terminal = _spawn_terminal

from acceptance.g5_runner import run_interactive as _hardened_run_interactive  # noqa: E402

_impl._run_interactive = _hardened_run_interactive
_run_interactive = _hardened_run_interactive


def main() -> int:
    return _impl.main()


if __name__ == "__main__":
    raise SystemExit(main())
