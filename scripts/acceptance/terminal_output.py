"""Streaming, redacted terminal transcript shared by PTY and ConPTY.

Credential labels/values and UTF-8 code points may straddle independent reads, so
redaction is stateful across chunks. Visible output is a transcript, not terminal
emulation. ANSI controls are deliberately not replayed into the user's terminal.
"""

from __future__ import annotations

import codecs
import sys
import threading
from collections.abc import Callable
from typing import TextIO

_PRINT_LOCK = threading.Lock()
_REDACTED = "[REDACTED]"
_FIXED_PREFIXES = {
    "?t=": "query",
    "&t=": "query",
    "?token=": "query",
    "&token=": "query",
    "?api_key=": "query",
    "&api_key=": "query",
    "bearer": "bearer",
    "apikey": "header",
    "api-key": "header",
    "api_key": "header",
    "authorization": "authorization",
}
_PREFIX_STARTS = {value[0] for value in _FIXED_PREFIXES}
_HEADER_VALUE_DELIMITERS = frozenset({" ", "\t", ",", '"', "'"})
_BEARER_VALUE_DELIMITERS = frozenset({" ", "\t", '"', "'"})
_QUERY_VALUE_DELIMITERS = frozenset({" ", "\t", "&", "#"})


class _StreamingRedactor:
    """Redact the supported credential forms with bounded look-behind.

    Only a possible fixed credential label is buffered. Once a label is known, the
    parser emits the non-secret prefix immediately and suppresses the value until
    its delimiter, so an arbitrarily long terminal line never requires whole-line
    buffering and a secret can never be split into an unlabelled later chunk.
    """

    def __init__(self, emit: Callable[[str], None]) -> None:
        self._emit = emit
        self._candidate = ""
        self._state = "normal"

    def feed(self, char: str) -> None:
        state = self._state
        if state == "normal":
            self._feed_normal(char)
        elif state == "header_after_label":
            if char.isspace():
                self._emit(char)
            elif char in {":", "="}:
                self._emit(char)
                self._state = "header_value_pending"
            else:
                self._state = "normal"
                self._feed_normal(char)
        elif state == "authorization_after_label":
            if char.isspace():
                self._emit(char)
            elif char in {":", "="}:
                self._emit(char)
                self._emit(_REDACTED)
                self._state = "authorization_secret"
            else:
                self._state = "normal"
                self._feed_normal(char)
        elif state == "header_value_pending":
            if char.isspace():
                self._emit(char)
            elif char in _HEADER_VALUE_DELIMITERS:
                self._emit(char)
                self._state = "normal"
            else:
                self._emit(_REDACTED)
                self._state = "header_secret"
        elif state == "header_secret":
            if char in _HEADER_VALUE_DELIMITERS:
                self._emit(char)
                self._state = "normal"
        elif state == "authorization_secret":
            return
        elif state == "bearer_after_label":
            if char.isspace():
                self._emit(char)
                self._state = "bearer_gap"
            else:
                self._state = "normal"
                self._feed_normal(char)
        elif state == "bearer_gap":
            if char.isspace():
                self._emit(char)
            elif char in _BEARER_VALUE_DELIMITERS:
                self._emit(char)
                self._state = "normal"
            else:
                self._emit(_REDACTED)
                self._state = "bearer_secret"
        elif state == "bearer_secret":
            if char in _BEARER_VALUE_DELIMITERS:
                self._emit(char)
                self._state = "normal"
        elif state == "query_value_pending":
            if char in _QUERY_VALUE_DELIMITERS:
                self._emit(char)
                self._state = "normal"
            else:
                self._emit(_REDACTED)
                self._state = "query_secret"
        elif state == "query_secret":
            if char in _QUERY_VALUE_DELIMITERS:
                self._emit(char)
                self._state = "normal"
        else:  # pragma: no cover - internal invariant
            raise AssertionError(f"unknown terminal redaction state: {state}")

    def _feed_normal(self, char: str) -> None:
        if not self._candidate:
            if char.lower() in _PREFIX_STARTS:
                self._candidate = char
            else:
                self._emit(char)
            return

        self._candidate += char
        lowered = self._candidate.lower()
        matching = [prefix for prefix in _FIXED_PREFIXES if prefix.startswith(lowered)]
        if matching:
            kind = _FIXED_PREFIXES.get(lowered)
            if kind is None:
                return
            candidate = self._candidate
            self._candidate = ""
            self._emit(candidate)
            if kind == "query":
                self._state = "query_value_pending"
            elif kind == "bearer":
                self._state = "bearer_after_label"
            elif kind == "authorization":
                self._state = "authorization_after_label"
            else:
                self._state = "header_after_label"
            return

        buffered = self._candidate
        self._candidate = ""
        self._emit(buffered[0])
        for pending in buffered[1:]:
            self._feed_normal(pending)

    def finish_line(self) -> None:
        if self._candidate:
            self._emit(self._candidate)
        self._candidate = ""
        self._state = "normal"


class TerminalTranscript:
    def __init__(self, artifact: TextIO, *, label: str = "OLLAMA") -> None:
        self._artifact = artifact
        self._label = label
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._redactor = _StreamingRedactor(self._write_piece)
        self._stdout_started = False
        self._line_seen = False
        self._ansi_state = "normal"

    def feed(self, chunk: bytes | str) -> None:
        text = self._decoder.decode(chunk) if isinstance(chunk, bytes) else chunk
        for char in text:
            self._feed_char(char)

    def _feed_char(self, char: str) -> None:
        if char == "\n":
            self._ansi_state = "normal"
            self._finish_line()
            return

        self._line_seen = True
        state = self._ansi_state
        if state == "esc":
            if char == "[":
                self._ansi_state = "csi"
            elif char == "]":
                self._ansi_state = "osc"
            else:
                self._ansi_state = "normal"
            return
        if state == "csi":
            if "@" <= char <= "~":
                self._ansi_state = "normal"
            return
        if state == "osc":
            if char == "\x07":
                self._ansi_state = "normal"
            elif char == "\x1b":
                self._ansi_state = "osc_esc"
            return
        if state == "osc_esc":
            self._ansi_state = "normal" if char == "\\" else "osc"
            return
        if char == "\x1b":
            self._ansi_state = "esc"
            return
        if char == "\t" or char.isprintable():
            self._redactor.feed(char)

    def _write_piece(self, text: str) -> None:
        if not text:
            return
        self._artifact.write(text)
        self._artifact.flush()
        with _PRINT_LOCK:
            if not self._stdout_started:
                sys.stdout.write("[" + self._label + "] ")
                self._stdout_started = True
            sys.stdout.write(text)
            sys.stdout.flush()

    def _finish_line(self) -> None:
        self._redactor.finish_line()
        self._artifact.write("\n")
        self._artifact.flush()
        with _PRINT_LOCK:
            if not self._stdout_started:
                sys.stdout.write("[" + self._label + "] ")
            sys.stdout.write("\n")
            sys.stdout.flush()
        self._stdout_started = False
        self._line_seen = False

    def close(self) -> None:
        self.feed(self._decoder.decode(b"", final=True))
        self._ansi_state = "normal"
        if self._line_seen:
            self._finish_line()
