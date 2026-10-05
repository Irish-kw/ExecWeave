from __future__ import annotations

import json
import os
import stat
import threading
from pathlib import Path

from .schema import RuntimeEvent


class JsonlSink:
    """Thread-safe local JSONL sink used by Phase 1 collectors.

    One event file represents one ExecWeave session. Reusing a non-empty path is
    rejected by default so event sequences and session identities cannot be
    silently mixed by an accidental second run.
    """

    def __init__(self, path: str | Path) -> None:
        original = Path(path).expanduser().absolute()
        if original.is_symlink():
            raise ValueError("event stream must not be a symlink")
        self.path = original
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self.path.stat().st_size > 0:
            raise FileExistsError(f"ExecWeave event stream already exists: {self.path}")
        self._lock = threading.Lock()
        self._sequence = 0

    def emit(self, event: RuntimeEvent) -> None:
        payload = event.to_dict()
        with self._lock:
            self._sequence += 1
            payload["sequence"] = self._sequence
            line = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            flags = (os.O_WRONLY | os.O_APPEND | os.O_CREAT
                     | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
            fd = os.open(self.path, flags, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                info = os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ValueError("event stream must be a private regular file")
                if os.name != "nt" and stat.S_IMODE(info.st_mode) != 0o600:
                    os.fchmod(handle.fileno(), 0o600)
                handle.write(line + "\n")
