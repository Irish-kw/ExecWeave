from __future__ import annotations

import json
import threading
from pathlib import Path

from .schema import RuntimeEvent


class JsonlSink:
    """Thread-safe local JSONL sink used by Phase 1 collectors."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def emit(self, event: RuntimeEvent) -> None:
        line = json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
