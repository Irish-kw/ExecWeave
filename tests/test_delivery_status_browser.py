"""Real DOM interactions; mocked sync responses are not native HTTP acceptance."""

from __future__ import annotations

import os

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from execweave.delivery_status import summarize_finalization
from test_delivery_status import archive

pytestmark = pytest.mark.viewer_e2e


@pytest.fixture
def page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        executable = os.environ.get("EXECWEAVE_E2E_CHROMIUM")
        browser = pw.chromium.launch(**({"executable_path": executable} if executable else {}))
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        yield page
        assert errors == []
        browser.close()


def load(page, *, expand_delivery=True):
    graph = {
        "graph_schema_version": "0.2",
        "session_id": "delivery-run",
        "source_path": "/recorded/run/events.jsonl",
        "nodes": [{"id": "a", "type": "agent", "name": "A"}],
        "edges": [],
    }
    entries = [
        {
            "source_id": "a",
            "source_type": "agent",
            "provider": "ollama",
            "conversation_preview": {
                "provider": "ollama",
                "is_root": True,
                "agent_path": "/root",
                "messages": [
                    {
                        "kind": "user_message",
                        "sender": "user",
                        "recipient": "/root",
                        "text": "old question",
                    },
                    {
                        "kind": "assistant_message",
                        "sender": "/root",
                        "recipient": "user",
                        "text": "old answer",
                        "phase": "final_answer",
                    },
                ],
            },
        }
    ]
    page.set_content(render_static_dashboard_html(graph, conversation_entries=entries))
    if expand_delivery:
        page.locator("#execweave-delivery-summary").click()
    return graph


def receipt(page, tmp_path, state="complete"):
    graph, _, report = archive(tmp_path)
    report["state"] = state
    record = {
        **summarize_finalization(report),
        "session_id": graph["session_id"],
        "source_path": graph["source_path"],
    }
    page.evaluate("r=>window.__execweaveRunAssessment.refresh({finalization_assessment:r})", record)
    return record


def prepare_sync(page, response):
    page.evaluate(
        """r=>{
      window.__execweaveStaticMode=false;window.fetchCount=0;
      window.fetch=async()=>{window.fetchCount++;return {ok:true,json:async()=>r}};
    }""",
        response,
    )


def test_static_embedded_is_not_live_synchronized_or_archive_verified(page):
    load(page)
    assert page.locator('[data-axis="synchronization"]').get_attribute("data-state") == "embedded"
    assert page.locator('[data-axis="archive"]').get_attribute("data-state") == "unavailable"
    assert page.locator("#execweave-delivery-status").is_visible()
    assert not page.locator("#current-title").is_visible()


@pytest.mark.parametrize("state", ["complete", "incomplete", "failed", "recording", "exporting"])
def test_receipt_is_visible_but_not_a_fresh_verification(page, tmp_path, state):
    load(page)
    receipt(page, tmp_path, state)
    assert page.locator('[data-axis="archive"]').get_attribute("data-state") == state
    assert page.locator('[data-axis="task"]').get_attribute("data-state") == "unverified"
    if state == "complete":
        assert "have not been rechecked" in page.locator('[data-axis="archive"]').inner_text()
        assert "verified_now" not in page.locator('[data-axis="archive"]').get_attribute(
            "data-state"
        )


def test_status_packet_does_not_start_any_fetch(page, tmp_path):
    load(page)
    page.evaluate(
        '()=>{window.fetchCount=0;window.fetch=()=>{window.fetchCount++;throw Error("unexpected fetch")}}'
    )
    receipt(page, tmp_path)
    assert page.evaluate("window.fetchCount") == 0


def test_stale_receipt_after_run_change_is_not_reused(page, tmp_path):
    load(page)
    record = receipt(page, tmp_path)
    page.evaluate(
        """r=>{
      const graph=window.__execweaveCore.getGraph();graph.session_id='another-run';
      window.__execweaveRunAssessment.refresh({finalization_assessment:r});
    }""",
        record,
    )
    assert page.locator('[data-axis="archive"]').get_attribute("data-state") == "unavailable"


def test_status_refresh_preserves_open_scope_and_unchanged_controls(page, tmp_path):
    load(page)
    record = receipt(page, tmp_path)
    page.locator("#execweave-run-assessment > details > summary").click()
    page.evaluate("window.savedControl=document.querySelector('[data-axis=archive] button')")
    for _ in range(3):
        page.evaluate(
            "r=>window.__execweaveRunAssessment.refresh({finalization_assessment:r})", record
        )
    assert page.locator("#execweave-run-assessment > details").evaluate("e=>e.open")
    assert page.evaluate(
        'window.savedControl===document.querySelector("[data-axis=archive] button")'
    )


def test_failed_final_sync_has_retry_and_keeps_old_history(page):
    load(page)
    prepare_sync(page, {"error": "not an index"})
    assert page.evaluate("window.__execweaveAgentPanel.finishConversationPolling()") is False
    assert page.locator('[data-axis="synchronization"]').get_attribute("data-state") == "failed"
    page.evaluate(
        "window.__execweaveAgentPanel.render(window.__execweaveCore.getDisplayGraph().nodes.find(n=>n.id==='a'))"
    )
    assert "old answer" in page.locator("#details").inner_text()
    page.evaluate(
        "()=>{window.fetch=async()=>{window.fetchCount++;return {ok:true,json:async()=>({session_id:'delivery-run',entries:[]})}}}"
    )
    page.get_by_role("button", name="Retry final synchronization", exact=True).click()
    page.wait_for_function(
        "document.querySelector('[data-axis=synchronization]').dataset.state==='synced'"
    )
    assert "matched this run" in page.locator('[data-axis="synchronization"]').inner_text()
    assert page.locator("#conversation-sync-status").count() == 0
    calls = page.evaluate("window.fetchCount")
    assert page.evaluate("window.__execweaveAgentPanel.refresh()") is False
    page.wait_for_timeout(950)
    assert page.evaluate("window.fetchCount") == calls


def test_wrong_session_response_is_rejected(page):
    load(page)
    prepare_sync(page, {"session_id": "other", "entries": []})
    assert page.evaluate("window.__execweaveAgentPanel.finishConversationPolling()") is False
    assert page.locator('[data-axis="synchronization"]').get_attribute("data-state") == "failed"


def test_legacy_response_does_not_claim_session_was_checked(page):
    load(page)
    prepare_sync(page, {"entries": []})
    assert page.evaluate("window.__execweaveAgentPanel.finishConversationPolling()") is True
    assert (
        "omitted its session identity" in page.locator('[data-axis="synchronization"]').inner_text()
    )


def test_inflight_previous_run_response_never_marks_new_run_synchronized(page):
    load(page)
    page.evaluate("""()=>{
      window.__execweaveStaticMode=false;
      window.fetch=()=>new Promise(resolve=>window.resolveOld=resolve);
      window.oldFinish=window.__execweaveAgentPanel.finishConversationPolling();
    }""")
    page.wait_for_function("!!window.resolveOld")
    assert page.locator('[data-axis="synchronization"]').get_attribute("data-state") == "syncing"
    page.evaluate("""()=>{
      const graph=window.__execweaveCore.getGraph();graph.session_id='next-run';
      window.__execweaveDashboard.onPayload({});
      window.resolveOld({ok:true,json:async()=>({session_id:'delivery-run',entries:[]})});
    }""")
    assert page.evaluate("window.oldFinish") is False
    page.wait_for_timeout(30)
    status = page.evaluate("window.__execweaveAgentPanel.getSynchronizationStatus()")
    assert status["session_id"] == "next-run" and status["state"] == "live"
    assert page.locator('[data-axis="synchronization"]').get_attribute("data-state") == "live"


def test_receipt_diagnostics_are_literal_text(page, tmp_path):
    load(page)
    record = receipt(page, tmp_path, "failed")
    record["diagnostics"] = ['<img src=x onerror="window.bad=true">']
    page.evaluate("r=>window.__execweaveRunAssessment.refresh({finalization_assessment:r})", record)
    assert page.locator("#execweave-delivery-status img").count() == 0
    assert page.evaluate("window.bad||false") is False


def test_real_directory_selection_is_not_verified_without_native_crypto(page, tmp_path):
    load(page)
    archive(tmp_path)
    # about:blank has no secure-context WebCrypto here. Assert fail-closed only;
    # native SHA-256 positive cases run in Node and in the separate HTTP browser test.
    page.evaluate("Object.defineProperty(window,'crypto',{value:{},configurable:true})")
    with page.expect_file_chooser() as chooser:
        page.get_by_role("button", name="Verify exported run folder", exact=True).click()
    chooser.value.set_files(str(tmp_path))
    page.wait_for_function(
        "document.querySelector('[data-axis=archive]').dataset.state==='not_verified'"
    )
    assert "Native SHA-256 is unavailable" in page.locator('[data-axis="archive"]').inner_text()


def test_status_cards_render_in_both_themes(page, tmp_path):
    load(page)
    receipt(page, tmp_path, "failed")
    for mode in ["dark", "light"]:
        page.evaluate("v=>document.documentElement.dataset.theme=v", mode)
        assert page.locator('[data-axis="archive"]').is_visible()
        assert page.locator('[data-axis="synchronization"]').is_visible()


def test_sync_getter_does_not_relabel_previous_result_for_new_run(page):
    load(page)
    prepare_sync(page, {"session_id": "delivery-run", "entries": []})
    assert page.evaluate("window.__execweaveAgentPanel.finishConversationPolling()") is True
    page.evaluate("window.__execweaveCore.getGraph().session_id='new-run'")
    result = page.evaluate("window.__execweaveAgentPanel.getSynchronizationStatus()")
    assert result["state"] == "unknown"
    assert page.evaluate("window.__execweaveAgentPanel.isFinishedSynchronized()") is False
    assert result["response_session_checked"] is False


@pytest.mark.parametrize("entries", [[None], [[]], ["not a record"]])
def test_malformed_index_entries_are_not_successful_sync(page, entries):
    load(page)
    prepare_sync(page, {"session_id": "delivery-run", "entries": entries})
    assert page.evaluate("window.__execweaveAgentPanel.finishConversationPolling()") is False


def test_partial_http_response_is_not_final_sync(page):
    load(page)
    page.evaluate("""()=>{window.__execweaveStaticMode=false;
      window.fetch=async()=>({ok:true,status:206,json:async()=>({entries:[]})});
    }""")
    assert page.evaluate("window.__execweaveAgentPanel.finishConversationPolling()") is False


def test_source_path_mismatch_is_not_final_sync(page):
    load(page)
    prepare_sync(page, {"session_id": "delivery-run", "source_path": "/wrong/path", "entries": []})
    assert page.evaluate("window.__execweaveAgentPanel.finishConversationPolling()") is False


def test_browser_rejects_internally_inconsistent_receipt(page, tmp_path):
    load(page)
    record = receipt(page, tmp_path)
    record["verified_file_count"] = 999
    page.evaluate("r=>window.__execweaveRunAssessment.refresh({finalization_assessment:r})", record)
    assert page.locator("[data-axis=archive]").get_attribute("data-state") == "unavailable"


def test_dialog_reading_is_not_replaced_by_delivery_updates(page, tmp_path):
    load(page)
    page.evaluate(
        "window.__execweaveAgentPanel.render(window.__execweaveCore.getDisplayGraph().nodes.find(n=>n.id==='a'))"
    )
    page.get_by_role("button", name="Browse observed history", exact=True).click()
    # Use the history dialog's actual disclosure elements rather than its summary cards.
    dialog = page.locator("dialog").filter(has=page.get_by_text("Observed history · A", exact=True))
    assert dialog.is_visible()
    details = dialog.locator("details").first
    details.locator("summary").click()
    record = receipt(page, tmp_path)
    assert dialog.is_visible() and details.evaluate("n=>n.open")
    page.evaluate("r=>window.__execweaveRunAssessment.refresh({finalization_assessment:r})", record)
    assert details.evaluate("n=>n.open")


def test_delivery_summary_keeps_agent_content_above_the_fold(page, tmp_path):
    load(page, expand_delivery=False)
    receipt(page, tmp_path, "failed")
    page.evaluate("()=>window.__execweaveAgentPanel.render(window.__execweaveCore.getDisplayGraph().nodes.find(n=>n.id==='a'))")
    summary = page.locator("#execweave-delivery-summary")
    assert summary.is_visible()
    assert "Export failed".lower() in summary.inner_text().lower()
    assert not page.locator("#execweave-delivery-status details").evaluate("n=>n.open")
    assert page.locator("#details").bounding_box()["y"] < 750
    summary.click()
    assert page.get_by_role("button", name="Verify exported run folder", exact=True).is_visible()


def test_delivery_disclosure_survives_assessment_updates_but_not_run_changes(page):
    from execweave.run_assessment import build_run_assessment
    graph = load(page)
    graph["event_count"] = 99
    packet = build_run_assessment(graph)
    packet["inspection"]["invalid_records"] = 1
    page.evaluate("r=>window.__execweaveRunAssessment.refresh({run_assessment:r})", packet)
    assert page.locator("#execweave-delivery-status details").evaluate("n=>n.open")
    page.evaluate("()=>{window.__execweaveCore.getGraph().session_id='another-run';window.__execweaveRunAssessment.refresh()}")
    assert not page.locator("#execweave-delivery-status details").evaluate("n=>n.open")
