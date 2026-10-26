"""Native folder verification for relocated redacted derivatives."""

from __future__ import annotations

import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from execweave.redacted_archive import create_redacted_archive
from test_redacted_archive import policy, source_archive

pytestmark = pytest.mark.viewer_e2e


@pytest.fixture
def native_page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        executable = os.environ.get("EXECWEAVE_E2E_CHROMIUM")
        browser = playwright.chromium.launch(
            **({"executable_path": executable} if executable else {})
        )
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        yield page
        assert errors == []
        browser.close()


def _derived(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    source_archive(source)
    policy_path = tmp_path / "policy.json"
    policy(policy_path)
    derived = tmp_path / "derived"
    create_redacted_archive(source, derived, policy_path)
    return derived


@pytest.mark.parametrize("mode", ["http", "offline"])
def test_native_selected_redacted_folder_verifies_lineage(native_page, tmp_path, mode):
    derived = _derived(tmp_path)
    page = native_page
    server = None
    thread = None
    if mode == "offline":
        url = (derived / "viewer.html").as_uri()
    else:
        body = (derived / "viewer.html").read_bytes()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}/viewer.html"
    try:
        page.goto(url)
        page.locator("#execweave-delivery-summary").click()
        assert page.evaluate("!!globalThis.crypto?.subtle")
        with page.expect_file_chooser() as chooser:
            page.get_by_role("button", name="Verify exported run folder", exact=True).click()
        chooser.value.set_files(str(derived))
        page.wait_for_function(
            "document.querySelector('[data-axis=archive]')?.dataset.state==='verified_now'",
            timeout=20000,
        )
        text = page.locator("[data-axis=archive]").inner_text()
        assert "Redacted derivative lineage verified for 3 source→derived mapping(s)" in text
        assert "source archive itself was declared by fingerprint and was not rechecked" in text
        assert page.locator("[data-axis=task]").get_attribute("data-state") == "unverified"
    finally:
        if server:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            assert not thread.is_alive()
