from __future__ import annotations

import sys
from pathlib import Path

import pytest

from test_viewer_agent_isolation_e2e import _browser, _launch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import dashboard_acceptance as dashboard_runner  # noqa: E402
from acceptance.browser_diagnostics import BrowserDiagnostics  # noqa: E402
from acceptance.reporting import Status  # noqa: E402

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
            failure_root = tmp_path / "missing" / "diagnostics"
            assert not diagnostics.finish(page, failure_root)
            transcript = (failure_root / "browser-console.log").read_text(encoding="utf-8")
            assert "private-value" not in transcript
            assert "[REDACTED]" in transcript
            assert "EW-REJECTED" in transcript
            assert (failure_root / "FAILURE.png").stat().st_size > 0
        finally:
            browser.close()


def test_formal_offline_runner_propagates_console_error_to_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class InjectingDiagnostics(BrowserDiagnostics):
        def __init__(self, page) -> None:
            super().__init__(page)
            page.evaluate("console.error('api_key=runner-private EW-RUNNER-CONSOLE')")

    monkeypatch.setattr(dashboard_runner, "BrowserDiagnostics", InjectingDiagnostics)
    result = dashboard_runner._run_offline(tmp_path / "runner", headed=False)
    assert result.checks["JS console"].status == Status.FAIL
    assert result.checks["Cleanup"].status == Status.PASS

    root = Path(result.artifacts)
    transcript = (root / "browser-console.log").read_text(encoding="utf-8")
    assert "runner-private" not in transcript
    assert "[REDACTED]" in transcript
    assert "EW-RUNNER-CONSOLE" in transcript
    assert (root / "FAILURE.png").stat().st_size > 0
