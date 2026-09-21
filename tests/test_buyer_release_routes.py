"""Buyer-only release routes: protective roles, handoff states and historical artifacts."""
from __future__ import annotations

import hashlib

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from execweave.investigation_index import build_investigation_index
from test_investigation_workspace import browser_page, scenario
from test_dashboard_camera_scheduler_e2e import _CORE_SEAM, _CORE_TEST_SEAM
from test_runtime_evidence_browser import graph as base_graph

__all__ = ["browser_page"]
pytestmark = pytest.mark.viewer_e2e


def show(page, graph, index=None):
    page.set_content(render_static_dashboard_html(graph, investigation_index=index))


def test_full_large_protective_snapshot_keeps_role_inventory_usable(browser_page):
    agents = [
        {"id": f"role-{i}", "type": "agent", "name": f"Worker {i}", "attributes": {"agent_role": "worker"}}
        for i in range(1600)
    ]
    graph = {
        "session_id": "large-role-release",
        "source_path": "/run/events.jsonl",
        "nodes": agents,
        "edges": [],
        "event_count": 10_000,
    }
    html = render_static_dashboard_html(base_graph())
    assert _CORE_SEAM in html
    browser_page.set_content(html.replace(_CORE_SEAM, _CORE_TEST_SEAM, 1))
    browser_page.evaluate(
        "g=>{window.__execweaveCore.setSnapshot(g);window.__execweaveDashboard.onPayload({graph:g})}",
        graph,
    )
    assert browser_page.locator("#protective").is_visible()
    search = browser_page.get_by_label("Find role in run guide")
    assert search.is_enabled()
    assert browser_page.locator("#execweave-run-guide-roles button").count() == 6
    search.fill("Worker 1599")
    assert browser_page.locator("#execweave-run-guide-roles button").count() == 1
    browser_page.locator("#execweave-run-guide-roles button").click()
    assert browser_page.locator(".run-guide-selected").is_visible()
    assert "current full snapshot" in browser_page.locator("#execweave-run-guide-status").inner_text()
    assert "Worker 1599" in browser_page.locator(".run-guide-selected").inner_text()
    assert browser_page.evaluate("window.__execweaveCore.getGraph().nodes.length") == 1600


def test_selected_role_opens_exact_handoffs_with_send_receipt_consumption_boundaries(tmp_path, browser_page):
    graph, _, a, b, _ = scenario(tmp_path)
    index = build_investigation_index(graph, tmp_path)
    show(browser_page, graph, index)
    role = browser_page.locator(f'#execweave-run-guide-roles [data-agent-id="{a.id}"]')
    assert "2 handoff" in role.inner_text() and "1 call" in role.inner_text()
    role.click()
    selected = browser_page.locator(".run-guide-selected")
    assert selected.is_visible()
    selected.get_by_role("button", name="Handoffs for selected role", exact=True).click()
    dialog = browser_page.locator("#execweave-investigation-dialog")
    assert dialog.is_visible()
    assert dialog.locator('[data-tab="messages"]').get_attribute("aria-pressed") == "true"
    assert dialog.locator(".investigation-row").count() == 2
    delivered = dialog.locator(".investigation-row").filter(has_text="Receipt observed")
    assert delivered.count() == 1
    assert "Send observed" in delivered.locator("summary").inner_text()
    assert "Consumption not observed" in delivered.locator("summary").inner_text()
    delivered.locator("summary").click()
    delivered.get_by_text("Evidence states", exact=False).wait_for()
    detail = delivered.inner_text().lower()
    assert "send: observed" in detail
    assert "receipt: observed" in detail
    assert "consumption evidence: not observed" in detail
    assert b.name in detail


def test_selected_role_artifact_route_shows_execution_snapshot_hash_and_size(tmp_path, browser_page):
    graph, _, a, _, _ = scenario(tmp_path)
    payload = b"historical artifact bytes"
    digest = hashlib.sha256(payload).hexdigest()
    ref = {
        "path": f"content/sha256/{digest}.txt",
        "sha256": digest,
        "size_bytes": len(payload),
        "content_kind": "test.file_snapshot",
        "media_type": "text/plain; charset=utf-8",
        "representation": "source_file_snapshot",
        "complete_from_source": True,
    }
    graph["nodes"] += [
        {"id": "artifact-report", "type": "file", "name": "report.txt"},
        {"id": "artifact-body", "type": "observed_content", "name": "snapshot", "attributes": ref},
    ]
    graph["edges"] += [
        {"id": "artifact-owner", "source": a.id, "target": "artifact-report", "relation": "WROTE", "causal": True},
        {"id": "artifact-snapshot", "source": "artifact-report", "target": "artifact-body", "relation": "OBSERVED_FILE_CONTENT_BEFORE_READ", "first_seen": "2026-09-21T01:02:03Z", "causal": False},
    ]
    index = build_investigation_index(graph, tmp_path)
    show(browser_page, graph, index)
    role = browser_page.locator(f'#execweave-run-guide-roles [data-agent-id="{a.id}"]')
    assert "1 artifact" in role.inner_text()
    role.click()
    browser_page.get_by_role("button", name="Artifacts for selected role", exact=True).click()
    dialog = browser_page.locator("#execweave-investigation-dialog")
    assert dialog.locator('[data-tab="artifacts"]').get_attribute("aria-pressed") == "true"
    row = dialog.locator(".investigation-row")
    assert row.count() == 1
    assert "Snapshot reference recorded" in row.locator("summary").inner_text()
    row.locator("summary").click()
    row.get_by_text("Historical snapshot reference(s) recorded", exact=False).wait_for()
    text = row.inner_text()
    assert "Historical snapshot reference(s) recorded at execution time" in text
    assert f"Historical snapshot SHA-256: {digest}" in text
    assert f"{len(payload)} bytes" in text
    assert "observed 2026-09-21T01:02:03Z" in text
    assert "Current workspace bytes are not substituted" in text
    assert row.locator(".execweave-content-actions button").count() == 1


def test_selected_role_content_health_is_one_visible_action(tmp_path, browser_page):
    graph, _, a, _, _ = scenario(tmp_path)
    index = build_investigation_index(graph, tmp_path)
    show(browser_page, graph, index)
    browser_page.locator(f'#execweave-run-guide-roles [data-agent-id="{a.id}"]').click()
    browser_page.locator(".run-guide-selected").get_by_role("button", name="Content health", exact=True).click()
    assert browser_page.locator("#execweave-health-dialog").is_visible()
    assert "Denominator:" in browser_page.locator("#execweave-health-summary").inner_text()
