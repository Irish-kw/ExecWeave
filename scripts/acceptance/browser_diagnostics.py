"""Capture both browser console errors and uncaught JavaScript failures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from acceptance.reporting import redact


class BrowserDiagnostics:
    def __init__(self, page: Any) -> None:
        self.errors: list[str] = []
        self.messages: list[str] = []
        page.on("pageerror", self._page_error)
        page.on("console", self._console)

    def _page_error(self, error: Any) -> None:
        message = redact(f"pageerror: {error}")
        self.errors.append(message)
        self.messages.append(message)

    def _console(self, message: Any) -> None:
        text = redact(f"console.{message.type}: {message.text}")
        self.messages.append(text)
        if message.type == "error":
            self.errors.append(text)

    def write(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        (root / "browser-console.log").write_text("\n".join(self.messages), encoding="utf-8")

    def failure(self, page: Any, root: Path) -> None:
        try:
            page.screenshot(path=str(root / "FAILURE.png"), full_page=True)
        except Exception as exc:
            self.messages.append(redact(f"failure screenshot unavailable: {exc}"))
        self.write(root)
