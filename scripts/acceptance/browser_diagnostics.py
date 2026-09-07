"""Capture browser console errors, uncaught JavaScript failures, and HTTP diagnostics."""

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
        page.on("response", self._response)

    @staticmethod
    def _console_location(message: Any) -> str:
        try:
            location = getattr(message, "location", None)
            if callable(location):
                location = location()
        except Exception:  # noqa: BLE001 - diagnostics must not break the acceptance journey
            return ""
        if not isinstance(location, dict):
            return ""
        url = str(location.get("url") or "").strip()
        if not url:
            return ""
        line = location.get("lineNumber")
        column = location.get("columnNumber")
        suffix = url
        if isinstance(line, int):
            suffix += f":{line + 1}"
            if isinstance(column, int):
                suffix += f":{column + 1}"
        return redact(f" @ {suffix}")

    def _page_error(self, error: Any) -> None:
        message = redact(f"pageerror: {error}")
        self.errors.append(message)
        self.messages.append(message)

    def _console(self, message: Any) -> None:
        text = redact(
            f"console.{message.type}: {message.text}{self._console_location(message)}"
        )
        self.messages.append(text)
        if message.type == "error":
            self.errors.append(text)

    def _response(self, response: Any) -> None:
        try:
            status = int(response.status)
            url = str(response.url)
        except Exception:  # noqa: BLE001 - response metadata is supplemental diagnostics
            return
        if status >= 400:
            self.messages.append(redact(f"http.{status}: {url}"))

    def write(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        (root / "browser-console.log").write_text("\n".join(self.messages), encoding="utf-8")

    def failure(self, page: Any, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        try:
            page.screenshot(path=str(root / "FAILURE.png"), full_page=True)
        except Exception as exc:
            self.messages.append(redact(f"failure screenshot unavailable: {exc}"))
        self.write(root)

    def finish(self, page: Any, root: Path) -> bool:
        """Persist diagnostics and capture a failure screenshot when JS errors exist."""
        if self.errors:
            self.failure(page, root)
            return False
        self.write(root)
        return True
