"""Line-buffered, redacted terminal transcript shared by PTY and ConPTY.

Never redact independent read chunks: credential labels/values and UTF-8 code
points can straddle them. Visible output is a transcript, not terminal emulation.
ANSI controls are deliberately not replayed into the user's terminal.
"""

from __future__ import annotations

import codecs
import re
import sys
import threading
from typing import TextIO

from acceptance.reporting import redact

_PRINT_LOCK = threading.Lock()
_ANSI = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]")
_LIMIT = 64 * 1024


class TerminalTranscript:
    def __init__(self, artifact: TextIO, *, label: str = "OLLAMA") -> None:
        self._artifact = artifact
        self._label = label
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._pending = ""
        self._discard = False

    def feed(self, chunk: bytes | str) -> None:
        text = self._decoder.decode(chunk) if isinstance(chunk, bytes) else chunk
        for char in text:
            if char == "\n":
                self._emit()
            elif not self._discard:
                self._pending += char
                if len(self._pending) > _LIMIT:
                    # Do not publish a possibly incomplete secret at a size boundary.
                    self._pending = ""
                    self._discard = True

    def _emit(self) -> None:
        if self._discard:
            text = "[terminal line omitted: exceeded safe redaction buffer]"
        else:
            text = _ANSI.sub("", self._pending)
            # Drop unterminated escape sequences rather than replaying OSC/CSI.
            text = text.split("\x1b", 1)[0]
            text = "".join(c for c in text if c == "\t" or (c.isprintable()))
            text = redact(text)
            # Keep Bearer values hidden when a header redactor consumes the label.
            text = re.sub(r"(?i)(authorization\s*[:=]\s*).*", r"\1[REDACTED]", text)
        self._artifact.write(text + "\n")
        self._artifact.flush()
        with _PRINT_LOCK:
            sys.stdout.write("[" + self._label + "] " + text + "\n")
            sys.stdout.flush()
        self._pending = ""
        self._discard = False

    def close(self) -> None:
        self.feed(self._decoder.decode(b"", final=True))
        if self._pending or self._discard:
            self._emit()
