"""Read JSON hook transport as UTF-8, independently of the terminal code page."""
from __future__ import annotations

from typing import Any


def read_hook_text(source: Any) -> str:
    binary = getattr(source, "buffer", None)
    raw = binary.read() if binary is not None else source.read()
    if isinstance(raw, bytes):
        # Strict decoding avoids silently replacing evidence. Invalid input is
        # reported by the existing fail-open hook boundary, not mis-recorded.
        return raw.decode("utf-8-sig")
    if not isinstance(raw, str):
        raise ValueError("hook stdin must supply UTF-8 bytes or text")
    return raw.lstrip("\ufeff")
