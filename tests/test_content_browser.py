"""Synthetic inspector contracts; these are not fresh provider recordings."""
from __future__ import annotations

import hashlib
import html
import json
import os
import shutil
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from execweave.viewer_content_browser import inject_content_browser


def reference(data: bytes, **extra) -> dict:
    digest = hashlib.sha256(data).hexdigest()
    return {"path": f"content/sha256/{digest}.txt", "sha256": digest,
            "relation": "HAS_TOOL_OUTPUT", "size_bytes": len(data), **extra}


def fixture_html(refs: list, *, static: bool = False, model: bool = False) -> str:
    if model:
        metadata = ('<section class="execweave-agent-card">'
                    '<div class="execweave-agent-label">Content references</div>'
                    f'<pre>{html.escape(json.dumps(refs))}</pre></section>')
        kind = "execweave-inference-occurrence"
    else:
        metadata = f'<pre>{html.escape(json.dumps({"content_references": refs}))}</pre>'
        kind = "execweave-tool-occurrence"
    source = ('<!doctype html><html><head><title>Content fixture</title></head><body>'
              f'<div id="details"><details class="{kind}" open>'
              f'<summary>agent-A / call-17</summary>{metadata}</details></div>'
              '<script>window.__execweaveToken="fixture-token";'
              f'window.__execweaveStaticMode={json.dumps(static)};'
              'window.__execweaveStaticGraph={session_id:"run-A",nodes:[]};'
              '</script></body></html>')
    return inject_content_browser(source)


def test_injection_is_additive_and_idempotent():
    source = '<html><body><script>const sentinel="unchanged";</script></body></html>'
    result = inject_content_browser(source)
    assert 'const sentinel="unchanged";' in result
    assert result.count('id="execweave-content-browser"') == 1
    assert inject_content_browser(result) == result
    with pytest.raises(RuntimeError):
        inject_content_browser("no body")


def test_shared_shell_integration():
    # This check needs the full repository, unlike the isolated browser fixtures.
    from execweave.dashboard_shell import DASHBOARD_HTML, render_static_dashboard_html

    assert DASHBOARD_HTML.count('id="execweave-content-browser"') == 1
    offline = render_static_dashboard_html({"nodes": [], "edges": []})
    assert offline.count('id="execweave-content-browser"') == 1
    assert "window.__execweaveStaticMode=true" in offline


@pytest.fixture(scope="module")
def browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        if os.environ.get("EXECWEAVE_E2E_REQUIRED"):
            pytest.fail("playwright is required")
        pytest.skip("playwright is not installed")
    manager = sync_playwright().start()
    executable = os.environ.get("EXECWEAVE_E2E_CHROMIUM") or shutil.which("chromium") or shutil.which("chromium-browser")
    try:
        instance = manager.chromium.launch(**({"executable_path": executable} if executable else {}))
    except Exception as error:
        manager.stop()
        if os.environ.get("EXECWEAVE_E2E_REQUIRED"):
            pytest.fail(f"Chromium failed to launch: {error}")
        pytest.skip(f"Chromium unavailable: {error}")
    yield instance
    instance.close()
    manager.stop()


@pytest.fixture
def harness(browser):
    class State:
        document = ""
        bodies: dict = {}
        hits: list = []

    state = State()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            if self.path == "/":
                payload = state.document.encode()
                code, headers, delay = 200, {"Content-Type": "text/html; charset=utf-8"}, 0
            else:
                state.hits.append((self.path, self.headers.get("X-ExecWeave-Token")))
                payload, code, headers, delay = state.bodies.get(self.path, (b"missing", 404, {}, 0))
                if self.headers.get("X-ExecWeave-Token") != "fixture-token":
                    payload, code = b"unauthorized", 401
            if delay:
                time.sleep(delay)
            self.send_response(code)
            if "no-length" not in headers:
                self.send_header("Content-Length", str(len(payload)))
            for key, value in headers.items():
                if key != "no-length":
                    self.send_header(key, value)
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    state.page = page
    state.url = f"http://127.0.0.1:{server.server_port}/"
    yield state
    page.close()
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
    assert not errors


def open_fixture(h, refs, *, static=False, model=False):
    h.document = fixture_html(refs, static=static, model=model)
    h.page.goto(h.url)
    h.page.locator(".execweave-content-actions button").first.wait_for()
    h.page.locator(".execweave-content-actions button").first.click()


def wait_state(h, state):
    h.page.wait_for_function(
        "s=>document.querySelector('#execweave-content-dialog')?.dataset.state===s", arg=state)


@pytest.mark.viewer_e2e
@pytest.mark.parametrize("model", [False, True])
def test_load_verified_text_from_tool_and_model_metadata(harness, model):
    h = harness
    data = '完整回傳 <script>window.pwned=1</script><img src="https://invalid.test/track">'.encode()
    ref = reference(data)
    h.bodies["/" + ref["path"]] = (data, 200, {}, 0)
    open_fixture(h, [ref], model=model)
    wait_state(h, "verified")
    assert h.page.locator("#execweave-content-text").text_content() == data.decode()
    assert h.page.evaluate("window.pwned") is None
    assert h.page.locator("#execweave-content-text img").count() == 0
    assert "call-17" in h.page.locator("#execweave-content-meta").text_content()
    assert h.hits == [("/" + ref["path"], "fixture-token")]
    h.page.get_by_role("button", name="Close", exact=True).click()
    h.page.evaluate("window.__execweaveContentBrowser.refresh()")
    assert h.page.locator(".execweave-content-actions button").count() == 1


@pytest.mark.viewer_e2e
@pytest.mark.parametrize("path", ["../secrets", "/content/sha256/x.txt", "file:///etc/passwd", "https://example.test/x", "content/sha256/" + "0" * 64 + ".txt?x=1", "content/sha256/" + "0" * 64 + ".txt\n", "content\\sha256\\x.txt", "content/sha256/%2e%2e/x.txt"])
def test_rejects_unsafe_references_without_fetch(harness, path):
    h = harness
    open_fixture(h, [{"path": path, "sha256": "0" * 64}])
    wait_state(h, "invalid_reference")
    assert not h.hits


@pytest.mark.viewer_e2e
@pytest.mark.parametrize("data", [b"", b"null", b"false", b"0"])
def test_preserves_empty_and_json_scalar_content(harness, data):
    h = harness
    ref = reference(data)
    h.bodies["/" + ref["path"]] = (data, 200, {}, 0)
    open_fixture(h, [ref])
    wait_state(h, "verified")
    assert h.page.locator("#execweave-content-text").text_content() == data.decode()
    if not data:
        assert "empty" in h.page.locator("#execweave-content-status").text_content()


@pytest.mark.viewer_e2e
@pytest.mark.parametrize("code,state", [(404, "missing_blob"), (401, "unauthorized"), (403, "unauthorized"), (500, "request_failed"), (206, "incomplete_response")])
def test_read_failures_are_visible_and_not_provider_gaps(harness, code, state):
    h = harness
    ref = reference(b"okay")
    h.bodies["/" + ref["path"]] = (b"failure", code, {}, 0)
    open_fixture(h, [ref])
    wait_state(h, state)
    assert h.page.locator("#execweave-content-text").text_content() == ""


@pytest.mark.viewer_e2e
@pytest.mark.parametrize("body,state", [(b"evil", "hash_mismatch"), (b"different length", "size_mismatch")])
def test_rejects_tampered_bytes(harness, body, state):
    h = harness
    ref = reference(b"okay")
    h.bodies["/" + ref["path"]] = (body, 200, {}, 0)
    open_fixture(h, [ref])
    wait_state(h, state)
    assert not h.page.locator("#execweave-content-text").text_content()


@pytest.mark.viewer_e2e
@pytest.mark.parametrize("data", [b"\xff\xfe", b"a\x00b"])
def test_binary_is_not_presented_as_text(harness, data):
    h = harness
    ref = reference(data)
    h.bodies["/" + ref["path"]] = (data, 200, {}, 0)
    open_fixture(h, [ref])
    wait_state(h, "binary_content")


@pytest.mark.viewer_e2e
def test_large_content_is_bounded_even_without_content_length(harness):
    h = harness
    ref = reference(b"okay")
    ref.pop("size_bytes")
    h.bodies["/" + ref["path"]] = (b"x" * (8 * 1024 * 1024 + 1), 200, {"no-length": "1"}, 0)
    open_fixture(h, [ref])
    wait_state(h, "too_large")
    assert h.page.locator("#execweave-content-text").text_content() == ""


@pytest.mark.viewer_e2e
def test_known_large_file_is_rejected_before_fetch(harness):
    h = harness
    ref = reference(b"okay", size_bytes=8 * 1024 * 1024 + 1)
    open_fixture(h, [ref])
    wait_state(h, "too_large")
    assert not h.hits


@pytest.mark.viewer_e2e
def test_search_reaches_tail_without_dumping_full_body_into_dom(harness):
    h = harness
    data = (("x" * 16383) + "\U0001F600" + ("中" * 18000) + "TAIL-MARKER").encode()
    ref = reference(data)
    h.bodies["/" + ref["path"]] = (data, 200, {}, 0)
    open_fixture(h, [ref])
    wait_state(h, "verified")
    assert "TAIL-MARKER" not in h.page.locator("#execweave-content-text").text_content()
    h.page.locator("#execweave-content-search").fill("TAIL-MARKER")
    h.page.get_by_role("button", name="Find", exact=True).click()
    assert "TAIL-MARKER" in h.page.locator("#execweave-content-text").text_content()
    assert len(h.page.locator("#execweave-content-text").text_content()) <= 16385


@pytest.mark.viewer_e2e
def test_offline_explicit_folder_reads_snapshot_without_http(harness, tmp_path):
    h = harness
    data = "離線快照不是現在的工作目錄".encode()
    ref = reference(data)
    exported = tmp_path / "exported-run"
    stored = exported / ref["path"]
    stored.parent.mkdir(parents=True)
    stored.write_bytes(data)
    open_fixture(h, [ref], static=True)
    wait_state(h, "folder_required")
    h.page.locator("#execweave-content-folder").set_input_files(str(exported))
    wait_state(h, "verified")
    assert h.page.locator("#execweave-content-text").text_content() == data.decode()
    assert not h.hits


@pytest.mark.viewer_e2e
def test_closing_cancels_old_read_and_does_not_contaminate_new_call(harness):
    h = harness
    first, second = reference(b"old call"), reference(b"new call")
    h.bodies["/" + first["path"]] = (b"old call", 200, {}, .6)
    h.bodies["/" + second["path"]] = (b"new call", 200, {}, 0)
    open_fixture(h, [first, second])
    wait_state(h, "loading")
    h.page.get_by_role("button", name="Close", exact=True).click()
    h.page.locator(".execweave-content-actions button").nth(1).click()
    wait_state(h, "verified")
    h.page.wait_for_timeout(700)
    assert h.page.locator("#execweave-content-text").text_content() == "new call"


@pytest.mark.viewer_e2e
def test_no_hash_verification_means_no_verified_preview(harness):
    h = harness
    ref = reference(b"okay")
    h.bodies["/" + ref["path"]] = (b"okay", 200, {}, 0)
    h.document = fixture_html([ref])
    h.page.goto(h.url)
    h.page.evaluate("Object.defineProperty(window,'crypto',{value:{}})")
    h.page.locator(".execweave-content-actions button").first.click()
    wait_state(h, "crypto_unavailable")
    assert h.page.locator("#execweave-content-text").text_content() == ""


@pytest.mark.viewer_e2e
def test_run_change_during_read_discards_previous_run_content(harness):
    h = harness
    ref = reference(b"run A only")
    h.bodies["/" + ref["path"]] = (b"run A only", 200, {}, .4)
    open_fixture(h, [ref])
    wait_state(h, "loading")
    h.page.evaluate("window.__execweaveStaticGraph.session_id='run-B'")
    wait_state(h, "run_changed")
    assert h.page.locator("#execweave-content-text").text_content() == ""


@pytest.mark.viewer_e2e
def test_new_run_requires_renewed_offline_folder_selection(harness, tmp_path):
    h = harness
    data = b"snapshot"
    ref = reference(data)
    exported = tmp_path / "exported-run"
    stored = exported / ref["path"]
    stored.parent.mkdir(parents=True)
    stored.write_bytes(data)
    open_fixture(h, [ref], static=True)
    wait_state(h, "folder_required")
    h.page.locator("#execweave-content-folder").set_input_files(str(exported))
    wait_state(h, "verified")
    h.page.get_by_role("button", name="Close", exact=True).click()
    h.page.evaluate("window.__execweaveStaticGraph.session_id='run-B'")
    h.page.locator(".execweave-content-actions button").first.click()
    wait_state(h, "folder_required")
    assert not h.hits
