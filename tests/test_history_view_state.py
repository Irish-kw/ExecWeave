"""Session-view state tests; controller restart is not native page reload.

The component cases inject a bounded storage double in an opaque-origin browser
page. The separately named native HTTP test uses real sessionStorage and reload.
Neither fixture is a fresh provider/model recording.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from test_observed_history import browser, entry, find, graph, load, message, page

__all__ = ["browser", "page"]
pytestmark = pytest.mark.viewer_e2e
STORE = "execweave.history.view.v1"


def storage_double(page):
    page.evaluate("""()=>{
      window.testStore=new Map();
      Object.defineProperty(window,'sessionStorage',{configurable:true,value:{
        getItem:k=>window.testStore.get(k)??null,
        setItem:(k,v)=>window.testStore.set(k,v),
        removeItem:k=>window.testStore.delete(k)
      }});
    }""")


def restart_controller(page, node=0):
    page.evaluate("""i=>{
      window.__execweaveHistoryBrowser.close();
      document.getElementById('execweave-history-dialog')?.remove();
      window.__execweaveHistoryBrowser=execweaveCreateHistoryBrowser(
        ()=>window.fixture.graph,()=>window.fixture.entries);
      window.__execweaveHistoryBrowser.open(window.fixture.graph.nodes[i]);
    }""", node)


def move_and_expand(page):
    page.get_by_role("button", name="Next records", exact=True).click()
    page.locator("#execweave-history-list summary").first.click()


def test_component_restart_restores_page_filter_and_expansion(page):
    storage_double(page)
    load(page)
    page.get_by_label("History message category").select_option("message")
    move_and_expand(page)
    restart_controller(page)
    assert page.get_by_label("History message category").input_value() == "message"
    assert "Page 2/9" in page.locator("#execweave-history-status").inner_text()
    assert page.locator(".execweave-history-message").first.evaluate("n=>n.open")
    assert page.locator(".history-message-text").first.inner_text() == "record 25"


def test_storage_never_contains_body_or_search_term(page):
    storage_double(page)
    load(page)
    move_and_expand(page)
    find(page, "SECRET_SEARCH")
    saved = page.evaluate("key=>window.testStore.get(key)", STORE)
    assert "SECRET_SEARCH" not in saved and "record 25" not in saved
    assert "private sibling answer" not in saved and '"text"' not in saved
    restart_controller(page)
    assert page.get_by_label("Search observed history").input_value() == ""
    assert "Page 1/9" in page.locator("#execweave-history-status").inner_text()


@pytest.mark.parametrize("change", ["run", "native", "agent", "path"])
def test_view_state_does_not_cross_execution_or_agent_identity(page, change):
    storage_double(page)
    load(page)
    move_and_expand(page)
    page.evaluate("window.__execweaveHistoryBrowser.close()")
    if change == "run":
        page.evaluate("window.fixture.graph.session_id='other-run'")
    elif change == "native":
        page.evaluate("window.fixture.entries[0].conversation_preview.provider_native_id='other-native-execution'")
    elif change == "path":
        page.evaluate("window.fixture.graph.source_path='/different/events.jsonl'")
    restart_controller(page, 1 if change == "agent" else 0)
    assert "Page 1/" in page.locator("#execweave-history-status").inner_text()
    assert not page.locator(".execweave-history-message[open]").count()


def test_unknown_execution_does_not_persist_by_filename_or_label(page):
    storage_double(page)
    g = graph()
    g.pop("session_id")
    g["source_path"] = "events.jsonl"
    load(page, g=g)
    move_and_expand(page)
    assert page.evaluate("window.testStore.size") == 0
    restart_controller(page)
    assert "Page 1/9" in page.locator("#execweave-history-status").inner_text()


@pytest.mark.parametrize("saved", ["not-json", "[]", '{"version":2,"views":[]}', "x" * 131073],
                         ids=["invalid-json", "wrong-shape", "unsupported-version", "oversized"])
def test_malformed_or_oversized_storage_does_not_break_reading(page, saved):
    storage_double(page)
    page.evaluate("([k,v])=>window.testStore.set(k,v)", [STORE, saved])
    load(page)
    assert page.locator(".execweave-history-message").count() == 25
    assert "Page 1/9" in page.locator("#execweave-history-status").inner_text()


def test_disabled_storage_and_quota_errors_are_not_reader_failures(page):
    page.evaluate("""()=>Object.defineProperty(window,'sessionStorage',{
      configurable:true,get(){throw new DOMException('disabled','SecurityError')}
    })""")
    load(page)
    move_and_expand(page)
    restart_controller(page)
    assert "Page 1/9" in page.locator("#execweave-history-status").inner_text()
    storage_double(page)
    page.evaluate("()=>{window.sessionStorage.setItem=()=>{throw new DOMException('full','QuotaExceededError')}}")
    move_and_expand(page)
    assert page.locator(".execweave-history-message").first.evaluate("n=>n.open")


def test_store_validation_rejects_invalid_page_filter_and_fold_types(page):
    storage_double(page)
    load(page)
    page.evaluate("window.__execweaveHistoryBrowser.close()")
    saved = json.loads(page.evaluate("k=>window.testStore.get(k)", STORE))
    saved["views"][0][1] = {"page": -1, "filter": "<script>", "open": [42]}
    page.evaluate("([k,v])=>window.testStore.set(k,JSON.stringify(v))", [STORE, saved])
    restart_controller(page)
    assert page.get_by_label("History message category").input_value() == "all"
    assert "Page 1/9" in page.locator("#execweave-history-status").inner_text()


def test_native_http_reload_preserves_view_without_persisting_message_text(page):
    """Native origin/reload acceptance; no route interception or storage mock."""
    g = graph()
    records = [entry("agent:a", [message(i) for i in range(80)])]
    html = render_static_dashboard_html(g, conversation_entries=records).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/viewer.html"
        page.goto(url)
        page.evaluate("window.__execweaveCore.selectNode('agent:a')")
        page.get_by_role("button", name="Browse observed history", exact=True).click()
        move_and_expand(page)
        assert "record 25" not in page.evaluate("k=>sessionStorage.getItem(k)", STORE)
        page.reload()
        page.evaluate("window.__execweaveCore.selectNode('agent:a')")
        page.get_by_role("button", name="Browse observed history", exact=True).click()
        assert "Page 2/4" in page.locator("#execweave-history-status").inner_text()
        assert page.locator(".execweave-history-message").first.evaluate("n=>n.open")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()
