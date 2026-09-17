"""Shipped dashboard regressions; synthetic conversations only."""
from __future__ import annotations

import os
import shutil

import pytest

from execweave.dashboard_shell import render_static_dashboard_html

pytestmark = pytest.mark.viewer_e2e


@pytest.fixture
def browser():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as manager:
        executable = os.environ.get("EXECWEAVE_TEST_CHROMIUM") or shutil.which("chromium")
        try:
            instance = manager.chromium.launch(executable_path=executable, headless=True, args=["--no-sandbox"])
        except playwright.Error:
            if os.environ.get("EXECWEAVE_E2E_REQUIRED") == "1":
                raise
            pytest.skip("Chromium is not available")
        yield instance
        instance.close()


def entries(rounds=200):
    messages = []
    for i in range(rounds):
        for sender, kind, phase, text in [
            ("user", "user_message", None, f"private prompt {i}"),
            ("/root", "assistant_message", "final_answer", f"reply {i}"),
        ]:
            messages.append({"sender": sender, "recipient": "/root" if sender == "user" else "user",
                             "kind": kind, "phase": phase, "text": text, "ordinal": 0,
                             "occurrence_id": f"request:{i}", "timestamp": f"2026-09-17T00:{i//60:02}:{i%60:02}Z"})
    return [{"source_id": "agent:Ollama", "source_type": "agent", "provider": "ollama",
             "conversation_preview": {"is_root": True, "provider": "ollama", "agent_path": "/root",
                                      "messages": messages, "message_count": len(messages)}}]


def html(rounds=200, session="test-run", counts=True):
    graph = {"graph_schema_version": "0.2", "session_id": session, "source_path": "", "event_count": 400,
             "nodes": [{"id": "agent:Ollama", "name": "/root", "type": "agent", "attributes": {"agent_role": "root"}},
                       {"id": "model:test", "name": "test-model", "type": "model", "attributes": {
                           "viewer_inference_occurrences": [{"request_ids": [f"request:{i}"],
                           "messages": [{"sender": "user", "text": f"model prompt {i}"}], "first_sequence": i} for i in range(12)]}}],
             "edges": [{"id": "uses", "source": "agent:Ollama", "target": "model:test", "relation": "INFERRED", "count": 200}],
             "session_outcome": {"state": "failed", "return_code": 1, "recorder_finished": True}}
    if counts:
        graph["evidence_counts"] = {"os_runtime": 30, "specialized": 370}
    return render_static_dashboard_html(graph, conversation_entries=entries(rounds))


def render_root(page):
    page.evaluate("""()=>window.__execweaveAgentPanel.render(window.__execweaveCore.getDisplayGraph().nodes.find(n=>n.id==='agent:Ollama'))""")


def folds(page):
    return page.locator("#details details[data-fold-key]").evaluate_all("nodes=>nodes.map(n=>({key:n.dataset.foldKey,open:n.open}))")


def test_200_rounds_fold_preservation_and_repeated_local_ordinal(browser):
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.set_content(html())
    render_root(page)
    assert page.locator("#details .execweave-agent-older").count() == 199
    assert page.locator("#details .execweave-agent-latest[open]").count() == 1
    assert "private prompt 37" in page.locator("#details").text_content()
    chosen = page.locator("#details .execweave-agent-older").nth(80)
    key = chosen.get_attribute("data-fold-key")
    chosen.locator("summary").click()
    page.wait_for_timeout(20)
    page.evaluate("next=>window.__execweaveAgentPanel.setEntries(next)", entries(201))
    assert next(f for f in folds(page) if f["key"] == key)["open"]
    # The formerly-latest round becomes collapsed unless explicitly opened by
    # the user; merely having been the automatic latest is not user intent.
    assert sum(f["open"] for f in folds(page)) == 2
    page.evaluate("""()=>window.__execweaveAgentPanel.render(window.__execweaveCore.getDisplayGraph().nodes.find(n=>n.type==='model'))""")
    render_root(page)
    assert next(f for f in folds(page) if f["key"] == key)["open"]
    assert not errors
    page.close()


def test_models_have_individual_persistent_inference_folds(browser):
    page = browser.new_page()
    page.set_content(html(2))
    page.evaluate("""()=>window.__execweaveAgentPanel.render(window.__execweaveCore.getDisplayGraph().nodes.find(n=>n.type==='model'))""")
    assert page.locator(".execweave-inference-occurrence").count() == 12
    assert page.locator(".execweave-inference-occurrence[open]").count() == 1
    chosen = page.locator(".execweave-inference-occurrence").nth(4)
    key = chosen.get_attribute("data-fold-key")
    chosen.locator("summary").click()
    page.wait_for_timeout(20)
    render_root(page)
    page.evaluate("""()=>window.__execweaveAgentPanel.render(window.__execweaveCore.getDisplayGraph().nodes.find(n=>n.type==='model'))""")
    assert next(f for f in folds(page) if f["key"] == key)["open"]
    page.close()


def test_final_sync_without_selected_agent_and_no_post_finish_fetch(browser):
    page = browser.new_page()
    page.set_content(html(0))
    page.evaluate("""next=>{window.__execweaveStaticMode=false;window.fetchCount=0;window.fetch=async()=>{window.fetchCount++;return{ok:true,json:async()=>({entries:next})}}}""", entries())
    assert page.evaluate("()=>window.__execweaveAgentPanel.finishConversationPolling()") is True
    assert page.evaluate("()=>window.__execweaveAgentPanel.isFinishedSynchronized()") is True
    assert page.evaluate("()=>window.fetchCount") == 1
    render_root(page)
    assert len(folds(page)) == 200
    assert page.evaluate("()=>window.__execweaveAgentPanel.refresh()") is False
    page.wait_for_timeout(900)
    assert page.evaluate("()=>window.fetchCount") == 1
    page.close()


def test_malformed_final_response_preserves_history_and_explicit_retry(browser):
    page = browser.new_page()
    page.set_content(html(3))
    page.evaluate("""()=>{window.__execweaveStaticMode=false;window.fetch=async()=>({ok:true,json:async()=>({error:'not an index'})})}""")
    assert page.evaluate("()=>window.__execweaveAgentPanel.finishConversationPolling()") is False
    render_root(page)
    assert len(folds(page)) == 3
    assert page.evaluate("()=>window.__execweaveAgentPanel.isFinishedSynchronized()") is False
    page.evaluate("next=>{window.fetch=async()=>({ok:true,json:async()=>({entries:next})})}", entries(4))
    assert page.locator("#conversation-sync-status").is_visible()
    page.locator("#conversation-sync-status button").click()
    page.wait_for_function("()=>window.__execweaveAgentPanel.isFinishedSynchronized()")
    assert page.locator("#conversation-sync-status").count() == 0
    assert len(folds(page)) == 4
    page.close()


def test_static_counts_and_workload_failure_are_not_faked(browser):
    for known in (True, False):
        page = browser.new_page()
        page.set_content(html(2, counts=known))
        assert page.locator("#evidence").inner_text() == ("OS 30 · specialized 370" if known else "OS — · specialized —")
        assert "FAILED" in page.locator("#workload-outcome").inner_text()
        assert "exit 1" in page.locator("#workload-outcome").inner_text()
        page.close()


def test_real_storage_survives_reload_and_is_isolated_by_run(browser):
    # A true origin/reload test, not a mocked localStorage. Restricted sandboxes
    # can still run the in-memory interaction tests above, but cannot claim this
    # one. CI requires Chromium and does not skip an unexpected browser failure.
    playwright = pytest.importorskip("playwright.sync_api")
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    document = [html(4)]
    page.route("http://127.0.0.1:8941/**", lambda route: route.fulfill(content_type="text/html", body=document[0]))
    try:
        page.goto("http://127.0.0.1:8941/")
    except playwright.Error as error:
        page.close()
        if "ERR_BLOCKED_BY_ADMINISTRATOR" in str(error) and os.environ.get("EXECWEAVE_E2E_REQUIRED") != "1":
            pytest.skip("Sandbox blocks navigations; real-origin persistence is not verified here")
        raise
    render_root(page)
    chosen = page.locator("#details .execweave-agent-older").nth(1)
    key = chosen.get_attribute("data-fold-key")
    chosen.locator("summary").click()
    page.wait_for_timeout(30)
    stored = page.evaluate("()=>JSON.stringify({...localStorage})")
    assert "private prompt" not in stored
    assert "execweave:folds:v1:" in stored
    page.reload()
    render_root(page)
    assert next(f for f in folds(page) if f["key"] == key)["open"]
    document[0] = html(4, session="another-run")
    page.reload()
    render_root(page)
    assert next(f for f in folds(page) if f["key"] == key)["open"] is False
    page.close()
