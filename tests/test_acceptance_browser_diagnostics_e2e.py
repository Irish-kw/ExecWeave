from __future__ import annotations

import sys
from pathlib import Path

import pytest

from test_viewer_agent_isolation_e2e import _browser, _launch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from acceptance.browser_diagnostics import BrowserDiagnostics  # noqa: E402

pytestmark = pytest.mark.viewer_e2e


def test_browser_diagnostics_captures_console_and_rejected_promise(tmp_path: Path) -> None:
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page()
            diagnostics = BrowserDiagnostics(page)
            page.set_content("<p>offline diagnostic fixture</p>")
            assert diagnostics.errors == []
            with page.expect_event("pageerror"):
                page.evaluate("""() => {
                    console.error('api_key=private-value');
                    setTimeout(() => { Promise.reject(new Error('EW-REJECTED')); }, 0);
                }""")
            assert any("console.error:" in text for text in diagnostics.errors)
            assert any("pageerror:" in text and "EW-REJECTED" in text for text in diagnostics.errors)
            diagnostics.failure(page, tmp_path)
            transcript = (tmp_path / "browser-console.log").read_text(encoding="utf-8")
            assert "private-value" not in transcript
            assert "[REDACTED]" in transcript
            assert "EW-REJECTED" in transcript
            assert (tmp_path / "FAILURE.png").stat().st_size > 0
        finally:
            browser.close()
