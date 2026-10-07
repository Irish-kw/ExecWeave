"""Real HTTP/file navigation and native browser cryptography; no substitutes."""

from __future__ import annotations

import os
import threading
import time
from http.server import ThreadingHTTPServer

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from execweave.finalization import record_finalization
from test_delivery_status import archive

pytestmark = pytest.mark.viewer_e2e


def _wait_for_axis_state(page, selector: str, expected: str, *, timeout_ms: int = 30_000) -> None:
    locator = page.locator(selector)
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if locator.get_attribute("data-state") == expected:
            return
        page.wait_for_timeout(50)
    actual = locator.get_attribute("data-state")
    raise AssertionError(f"{selector} did not reach data-state={expected!r}; got {actual!r}")


@pytest.fixture
def native_page():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        executable = os.environ.get("EXECWEAVE_E2E_CHROMIUM")
        browser = playwright.chromium.launch(**({"executable_path": executable} if executable else {}))
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        yield page
        assert not errors
        browser.close()


@pytest.mark.parametrize("mode", ["http", "offline"])
def test_native_browser_verifies_selected_archive_and_rejects_later_tampering(native_page, tmp_path, mode):
    page = native_page
    from execweave.live import _LiveState, _handler_factory

    graph, ref, _ = archive(tmp_path)
    html = render_static_dashboard_html(graph, conversation_entries=[])
    (tmp_path / "viewer.html").write_text(html, encoding="utf-8")
    report = record_finalization(tmp_path, state="complete")
    server = None
    worker = None
    if mode == "http":
        state = _LiveState(graph["session_id"], tmp_path / "events.jsonl")
        state.publish_finalization(report)
        state.finish(graph, final_html=html)
        server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_factory(state, "native-test-token"))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        page.set_extra_http_headers({"X-ExecWeave-Token": "native-test-token"})
        url = f"http://127.0.0.1:{server.server_port}/"
    else:
        url = (tmp_path / "viewer.html").as_uri()
    try:
        page.goto(url)
        if mode == "http":
            _wait_for_axis_state(page, "[data-axis=synchronization]", "synced")
            assert page.locator("[data-axis=archive]").get_attribute("data-state") == "complete"
        else:
            assert (
                page.locator("[data-axis=synchronization]").get_attribute("data-state")
                == "embedded"
            )
        page.locator("#execweave-delivery-summary").click()
        assert page.evaluate("!!globalThis.crypto.subtle")
        with page.expect_file_chooser() as chooser:
            page.get_by_role("button", name="Verify exported run folder", exact=True).click()
        chooser.value.set_files(str(tmp_path))
        _wait_for_axis_state(page, "[data-axis=archive]", "verified_now")
        assert (
            "3 primary files and 1 unique content files"
            in page.locator("[data-axis=archive]").inner_text()
        )
        assert page.locator("[data-axis=task]").get_attribute("data-state") == "unverified"
        (tmp_path / ref["path"]).write_bytes(b"evil")
        with page.expect_file_chooser() as chooser:
            page.get_by_role("button", name="Verify exported run folder", exact=True).click()
        chooser.value.set_files(str(tmp_path))
        _wait_for_axis_state(page, "[data-axis=archive]", "not_verified")
        assert (
            "does not match its recorded SHA-256"
            in page.locator("[data-axis=archive]").inner_text()
        )
    finally:
        if server:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)
