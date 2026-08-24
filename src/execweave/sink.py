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
        self._sequence = 0

    def emit(self, event: RuntimeEvent) -> None:
        payload = event.to_dict()
        with self._lock:
            self._sequence += 1
            payload["sequence"] = self._sequence
            line = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
