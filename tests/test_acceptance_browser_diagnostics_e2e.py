from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from test_viewer_agent_isolation_e2e import _browser, _launch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
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
            page.route(
                "https://execweave.invalid/diagnostic-401",
                lambda route: route.fulfill(status=401, body="Unauthorized"),
            )
            page.set_content("<p>offline diagnostic fixture</p>")
            assert diagnostics.errors == []
            with page.expect_event("pageerror"):
                page.evaluate("""() => {
                    console.error('api_key=private-value');
                    setTimeout(() => { Promise.reject(new Error('EW-REJECTED')); }, 0);
                }""")
            response = page.evaluate(
                "async()=>{const r=await fetch('https://execweave.invalid/diagnostic-401');return r.status}"
            )
            assert response == 401
            assert any("console.error:" in text for text in diagnostics.errors)
            assert any("pageerror:" in text and "EW-REJECTED" in text for text in diagnostics.errors)
            assert any(
                text == "http.401: https://execweave.invalid/diagnostic-401"
                for text in diagnostics.messages
            )
            failure_root = tmp_path / "missing" / "diagnostics"
            assert not diagnostics.finish(page, failure_root)
            transcript = (failure_root / "browser-console.log").read_text(encoding="utf-8")
            assert "private-value" not in transcript
            assert "[REDACTED]" in transcript
            assert "EW-REJECTED" in transcript
            assert "http.401: https://execweave.invalid/diagnostic-401" in transcript
            assert (failure_root / "FAILURE.png").stat().st_size > 0
        finally:
            browser.close()


def test_formal_offline_runner_propagates_console_error_to_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        if os.environ.get("EXECWEAVE_E2E_REQUIRED"):
            pytest.fail("Playwright is required for the formal browser diagnostics journey")
        pytest.skip("Playwright is not installed")

    import dashboard_acceptance as dashboard_runner

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


def test_formal_g6_runner_propagates_console_error_to_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        if os.environ.get("EXECWEAVE_E2E_REQUIRED"):
            pytest.fail("Playwright is required for the formal G6 browser diagnostics journey")
        pytest.skip("Playwright is not installed")

    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        if os.environ.get("EXECWEAVE_E2E_REQUIRED"):
            pytest.fail("formal headed G6 regression must run under Xvfb on Linux")
        pytest.skip("headed G6 regression requires DISPLAY/Xvfb on Linux")

    import python_native_acceptance as python_runner

    execweave_bin = shutil.which("execweave")
    if not execweave_bin:
        if os.environ.get("EXECWEAVE_E2E_REQUIRED"):
            pytest.fail("execweave is required for the formal G6 browser diagnostics journey")
        pytest.skip("execweave executable is not installed")

    class InjectingDiagnostics(BrowserDiagnostics):
        def __init__(self, page) -> None:
            super().__init__(page)
            page.evaluate("console.error('api_key=g6-private EW-G6-CONSOLE')")

    monkeypatch.setattr(python_runner, "BrowserDiagnostics", InjectingDiagnostics)
    result = python_runner._run_native(
        output_root=tmp_path / "g6-runner",
        execweave_bin=execweave_bin,
        timeout=45.0,
    )
    assert result.checks["JS console"].status == Status.FAIL
    assert result.checks["Cleanup"].status == Status.PASS

    root = Path(result.artifacts)
    transcript = (root / "browser-console.log").read_text(encoding="utf-8")
    assert "g6-private" not in transcript
    assert "[REDACTED]" in transcript
    assert "EW-G6-CONSOLE" in transcript
    assert (root / "FAILURE.png").stat().st_size > 0
