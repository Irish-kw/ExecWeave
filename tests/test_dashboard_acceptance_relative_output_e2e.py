"""Exercise the runner CLI, not merely Path.resolve, with a relative artifact root."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.viewer_e2e


def test_offline_runner_relative_output_reaches_finished_viewer(tmp_path: Path) -> None:
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        if os.environ.get("EXECWEAVE_E2E_REQUIRED"):
            pytest.fail("Playwright is required for the offline CLI journey")
        pytest.skip("Playwright is not installed")
    script = Path(__file__).resolve().parents[1] / "scripts" / "dashboard_acceptance.py"
    completed = subprocess.run(
        [sys.executable, str(script), "--mode", "offline", "--output-dir", "relative output",
         "--require", "offline-ollama-fixture"],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads(completed.stdout.splitlines()[-1])
    assert report["status"] == "PASS"
    checks = report["results"][0]["checks"]
    assert checks["Finished viewer"]["status"] == "PASS"
    assert checks["Cleanup"]["status"] == "PASS"
    assert checks["Network"]["status"] == "SKIP_UNAVAILABLE"
    assert list((tmp_path / "relative output").glob("*/viewer.html"))
