"""SDK-backed synthetic message routes in the shipped Dashboard.

This is component coverage, not the private AutoGen replay or native offline
body verification. The actual content reader's folder-required boundary is used.
"""

from __future__ import annotations

from copy import deepcopy
import json

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from execweave.framework_adapters import (
    AdapterContext,
    AutoGenAdapter,
    CAMELAdapter,
    ContentCapturePolicy,
    MessageRecord,
    MetaGPTAdapter,
)
from execweave.graph import GraphAccumulator
from execweave.investigation_index import build_investigation_index
from test_investigation_workspace import browser_page

__all__ = ["browser_page"]
pytestmark = pytest.mark.viewer_e2e
PANEL = "#execweave-message-handoffs"


def capture(root, framework="autogen", count=2, mode="prompt_and_response"):
    ctx = AdapterContext(
        framework=framework,
        run_id="one",
        session_id="one",
        sidecar=root / "semantic.jsonl",
        content_root=root,
        capture_policy=ContentCapturePolicy(mode),
    )
    adapter = {"autogen": AutoGenAdapter, "camel": CAMELAdapter, "metagpt": MetaGPTAdapter}[
        framework
    ](ctx)
    a, b, c = [adapter.agent(x, name="Same name") for x in "abc"]
    for i in range(count):
        entity = adapter.entity("message", f"m{i}")
        ctx.record_message(MessageRecord(entity, a, b, content="SAME_BODY", direction="sent"))
        if i == 0:
            ctx.record_message(
                MessageRecord(entity, a, b, content="SAME_BODY", direction="received")
            )
    ctx.record_message(
        MessageRecord(adapter.entity("message", "other"), a, c, content="PRIVATE_SIBLING")
    )
    ctx.record_message(
        MessageRecord(adapter.entity("message", "reverse"), b, a, content="REVERSE_BODY")
    )
    acc = GraphAccumulator(session_id="one", source_path=root / "events.jsonl")
    for i, line in enumerate((root / "semantic.jsonl").read_text().splitlines()):
        acc.apply({**json.loads(line), "session_id": "one", "sequence": i})
    g = acc.to_dict()
    return g, build_investigation_index(g, root), a.id, b.id, c.id


def select(page, source, target):
    group = page.evaluate(
        """([s,t])=>window.__execweaveCore.getDisplayGraph().nodes.find(n=>
        n.attributes?.viewer_framework_messages&&n.attributes.sender_agent_id===s&&n.attributes.recipient_agent_id===t)?.id""",
        [source, target],
    )
    assert group is not None
    page.evaluate("id=>window.__execweaveCore.selectNode(id)", group)
    page.locator(PANEL).wait_for()
    return group


def show(page, g, index, a, b):
    page.set_default_timeout(2000)
    page.set_content(render_static_dashboard_html(g, investigation_index=index))
    return select(page, a, b)


@pytest.mark.parametrize("framework", ["autogen", "camel", "metagpt"])
def test_message_group_opens_exact_body_reference(tmp_path, browser_page, framework):
    g, index, a, b, _ = capture(tmp_path, framework)
    page = browser_page
    show(page, g, index, a, b)
    rows = page.locator(PANEL + " .investigation-row")
    assert rows.count() == 2
    keys = rows.evaluate_all("xs=>xs.map(n=>n.dataset.recordId)")
    assert set(keys) == {
        r["key"] for r in index["messages"] if r["owner_id"] == a and r["target_id"] == b
    }
    rows.first.locator("summary").click()
    page.get_by_text("Consumption: not observed", exact=False).wait_for()
    # The unchanged shared reader receives the exact source record, not a name.
    page.locator(PANEL + " .execweave-content-actions button").first.click()
    dialog = page.locator("#execweave-content-dialog")
    assert dialog.is_visible() and dialog.get_attribute("data-state") == "folder_required"
    ref = next(r for r in index["messages"] if r["owner_id"] == a and r["target_id"] == b)[
        "references"
    ][0]["reference"]
    assert ref["sha256"] in dialog.inner_text()
    assert page.evaluate("window.__execweaveCore.getGraph()") == g


def test_direction_and_same_name_siblings_remain_separate(tmp_path, browser_page):
    g, index, a, b, c = capture(tmp_path)
    page = browser_page
    show(page, g, index, a, b)
    select(page, a, c)
    assert page.locator(PANEL + " .investigation-row").count() == 1
    select(page, b, a)
    row = page.locator(PANEL + " .investigation-row")
    assert row.count() == 1 and "reverse" in row.inner_text()
    assert page.locator(PANEL).get_attribute("data-source-id") == b


def test_updates_do_not_replace_open_records_until_explicit_refresh(tmp_path, browser_page):
    g, index, a, b, _ = capture(tmp_path)
    page = browser_page
    show(page, g, index, a, b)
    row = page.locator(PANEL + " .investigation-row").first
    row.locator("summary").click()
    page.get_by_text("Consumption: not observed", exact=False).wait_for()
    before = page.locator(PANEL + " .investigation-row").all_inner_texts()
    changed = deepcopy(index)
    changed["messages"] = [r for r in changed["messages"] if r["owner_id"] != a]
    page.evaluate("x=>window.__execweaveInvestigation.setIndex(x)", changed)
    page.locator(PANEL + " .message-handoff-notice").get_by_text(
        "snapshot remains pinned", exact=False
    ).wait_for()
    assert row.evaluate("n=>n.open")
    assert page.locator(PANEL + " .investigation-row").all_inner_texts() == before
    page.get_by_role("button", name="Load / refresh message records", exact=True).click()
    assert page.locator(PANEL + " .investigation-row").count() == 0


def test_duplicate_index_identity_is_withheld(tmp_path, browser_page):
    g, index, a, b, _ = capture(tmp_path)
    dup = deepcopy(next(r for r in index["messages"] if r["owner_id"] == a and r["target_id"] == b))
    index["messages"].append(dup)
    show(browser_page, g, index, a, b)
    assert browser_page.locator(PANEL + " .investigation-row").count() == 1
    assert "2 ambiguous or unbound" in browser_page.locator(PANEL).inner_text()


def test_inferred_route_never_grants_access_to_indexed_bodies(tmp_path, browser_page):
    g, index, a, b, _ = capture(tmp_path)
    for e in g["edges"]:
        if (
            e["source"] == a
            and e["target"] == b
            and e["relation"] in ("MESSAGE_SENT", "MESSAGE_RECEIVED")
        ):
            e["attributes"] = {**e.get("attributes", {}), "inferred": True}
    show(browser_page, g, index, a, b)
    assert browser_page.locator(PANEL + " .investigation-row").count() == 0
    assert "ambiguous or inferred" in browser_page.locator(PANEL).inner_text()


def test_missing_index_is_not_zero_activity_or_borrowed_body(tmp_path, browser_page):
    g, _, a, b, _ = capture(tmp_path)
    show(browser_page, g, None, a, b)
    assert "index is unavailable" in browser_page.locator(PANEL).inner_text()
    browser_page.get_by_role("button", name="Load / refresh message records", exact=True).click()
    assert "unavailable or refresh failed" in browser_page.locator(PANEL).inner_text()
    assert browser_page.locator(PANEL + " .execweave-content-actions").count() == 0


def test_metadata_only_is_not_empty_payload_or_capture_failure(tmp_path, browser_page):
    g, index, a, b, _ = capture(tmp_path, mode="metadata_only")
    show(browser_page, g, index, a, b)
    browser_page.locator(PANEL + " .investigation-row summary").first.click()
    browser_page.get_by_text("No body recorded in this observation", exact=False).first.wait_for()
    assert browser_page.locator(PANEL + " .execweave-content-actions").count() == 0


def test_pagination_preserves_equal_text_occurrences(tmp_path, browser_page):
    g, index, a, b, _ = capture(tmp_path, count=30)
    show(browser_page, g, index, a, b)
    assert browser_page.locator(PANEL + " .investigation-row").count() == 25
    browser_page.get_by_role("button", name="Show more message records", exact=False).click()
    assert browser_page.locator(PANEL + " .investigation-row").count() == 30
    keys = browser_page.locator(PANEL + " .investigation-row").evaluate_all(
        "xs=>xs.map(n=>n.dataset.recordId)"
    )
    assert len(set(keys)) == 30


def test_missing_live_index_uses_explicit_success_and_accepted_payload(tmp_path, browser_page):
    g, index, a, b, _ = capture(tmp_path)
    page = browser_page
    show(page, g, None, a, b)
    page.evaluate("""()=>{window.__execweaveStaticMode=false;
        window.__execweaveDashboard.agentPanel.refresh=async()=>true}""")
    page.get_by_role("button", name="Load / refresh message records", exact=True).click()
    assert "unavailable or refresh failed" in page.locator(PANEL).inner_text()
    page.evaluate(
        """index=>{window.__execweaveDashboard.agentPanel.refresh=async()=>{
        window.__execweaveInvestigation.setIndex(index);return true}}""",
        index,
    )
    page.get_by_role("button", name="Load / refresh message records", exact=True).click()
    assert page.locator(PANEL + " .investigation-row").count() == 2


def test_pending_load_cannot_cross_agent_selection(tmp_path, browser_page):
    g, index, a, b, c = capture(tmp_path)
    page = browser_page
    show(page, g, None, a, b)
    page.evaluate("""()=>{window.__execweaveStaticMode=false;
        window.__execweaveDashboard.agentPanel.refresh=()=>new Promise(r=>window.finishMessage=r)}""")
    page.get_by_role("button", name="Load / refresh message records", exact=True).click()
    select(page, a, c)
    page.evaluate(
        """index=>{window.__execweaveInvestigation.setIndex(index);window.finishMessage(true)}""",
        index,
    )
    assert page.locator(PANEL).get_attribute("data-target-id") == c
    assert page.locator(PANEL + " .investigation-row").count() == 0
    page.get_by_role("button", name="Load / refresh message records", exact=True).click()
    assert page.locator(PANEL + " .investigation-row").count() == 1
    assert "other" in page.locator(PANEL + " .investigation-row").inner_text()


def test_leaving_message_selection_removes_navigation_not_agent_output(tmp_path, browser_page):
    g, index, a, b, _ = capture(tmp_path)
    page = browser_page
    show(page, g, index, a, b)
    assert page.locator("#details " + PANEL).count() == 0
    page.evaluate("id=>window.__execweaveCore.selectNode(id)", a)
    page.wait_for_function("!document.getElementById('execweave-message-handoffs')")
    assert "Recorded message handoffs" not in page.locator("#details").inner_text()


def test_changed_execution_clears_old_message_bodies(tmp_path, browser_page):
    g, index, a, b, _ = capture(tmp_path)
    page = browser_page
    show(page, g, index, a, b)
    assert page.locator(PANEL + " .investigation-row").count() == 2
    page.evaluate(
        "()=>{window.__execweaveCore.getGraph().session_id='different';window.__execweaveDashboard.onPayload({})}"
    )
    page.wait_for_function(
        "document.querySelectorAll('#execweave-message-handoffs .investigation-row').length===0"
    )
    assert "index is unavailable" in page.locator(PANEL).inner_text()


def test_withdrawn_route_evidence_does_not_keep_an_authorized_body_list(tmp_path, browser_page):
    g, index, a, b, _ = capture(tmp_path)
    page = browser_page
    show(page, g, index, a, b)
    page.evaluate(
        """([a,b])=>{
        for(const e of window.__execweaveCore.getGraph().edges)
            if(e.source===a&&e.target===b)e.inferred=true;
        window.__execweaveDashboard.onPayload({});
    }""",
        [a, b],
    )
    page.wait_for_function(
        "document.querySelectorAll('#execweave-message-handoffs .investigation-row').length===0"
    )
    assert "ambiguous or inferred" in page.locator(PANEL).inner_text()


def test_hostile_index_label_does_not_execute_html(tmp_path, browser_page):
    g, index, a, b, _ = capture(tmp_path)
    for row in index["messages"]:
        row["source_name"] = '<img src=x onerror="window.pwned=true">'
    show(browser_page, g, index, a, b)
    assert "<img" in browser_page.locator(PANEL).inner_text()
    assert browser_page.locator(PANEL + " img").count() == 0
    assert browser_page.evaluate("window.pwned===undefined")
