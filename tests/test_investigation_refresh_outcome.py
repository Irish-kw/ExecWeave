"""Refresh outcome contracts in the shipped Dashboard with synthetic records.

Controlled refresh/fetch results exercise UI and parser behavior, not native
HTTP, provider availability, or independent end-to-end acceptance.
"""
from __future__ import annotations

import pytest

from execweave.investigation_index import build_investigation_index
from test_investigation_workspace import browser_page, scenario
from test_workflow_content_health_share import show

__all__ = ["browser_page"]
pytestmark = pytest.mark.viewer_e2e

PANELS = {
    "health": ("Content health", "Refresh content health", "#execweave-health-summary", "#execweave-health-table"),
    "investigation": ("Explore run", "Refresh index", "#execweave-investigation-updates", "#execweave-investigation-rows"),
}


def prepare(tmp_path, page):
    graph, *_ = scenario(tmp_path)
    index = build_investigation_index(graph, tmp_path)
    show(page, graph, index)
    page.evaluate("x=>window.__execweaveInvestigation.setIndex(x)", index)
    return graph, index


@pytest.mark.parametrize("panel", PANELS)
@pytest.mark.parametrize("outcome", ["false", "undefined", "missing", "nonboolean", "throws"])
def test_unsuccessful_refresh_retains_snapshot_and_reports_failure(tmp_path, browser_page, panel, outcome):
    page = browser_page
    graph, _ = prepare(tmp_path, page)
    page.evaluate("""outcome=>{
        window.__execweaveStaticMode=false;
        const api=window.__execweaveDashboard.agentPanel;
        if(outcome==='missing'){delete api.refresh;return}
        api.refresh=async()=>{
            if(outcome==='throws')throw new Error('controlled failure');
            return outcome==='false'?false:outcome==='nonboolean'?'true':undefined;
        };
    }""", outcome)
    launch, refresh, status, content = PANELS[panel]
    page.get_by_role("button", name=launch, exact=True).click()
    before = page.locator(content).inner_text()
    page.get_by_role("button", name=refresh, exact=True).click()
    assert "refresh failed" in page.locator(status).inner_text().lower()
    assert "retained" in page.locator(status).inner_text()
    assert page.locator(content).inner_text() == before
    assert page.get_by_role("button", name=refresh, exact=True).is_enabled()
    assert page.evaluate("window.__execweaveCore.getGraph()") == graph


@pytest.mark.parametrize("panel", PANELS)
def test_explicit_success_updates_the_requested_snapshot(tmp_path, browser_page, panel):
    page = browser_page
    _, index = prepare(tmp_path, page)
    changed = {**index, "agents": [], "calls": []}
    page.evaluate("""changed=>{
        window.__execweaveStaticMode=false;
        window.__execweaveDashboard.agentPanel.refresh=async options=>{
            window.requestedOptions=options;
            window.__execweaveInvestigation.setIndex(changed);return true;
        };
    }""", changed)
    launch, refresh, status, content = PANELS[panel]
    page.get_by_role("button", name=launch, exact=True).click()
    before = page.locator(content).inner_text()
    page.get_by_role("button", name=refresh, exact=True).click()
    assert page.locator(content).inner_text() != before
    assert "refresh failed" not in page.locator(status).inner_text().lower()
    assert page.evaluate("window.requestedOptions") == {"includeInvestigation": True}


@pytest.mark.parametrize("panel", PANELS)
def test_real_refresh_http_error_return_is_not_reported_as_success(tmp_path, browser_page, panel):
    page = browser_page
    _, _ = prepare(tmp_path, page)
    # Keep the shipped refresh function. Substitute only the network response.
    page.evaluate("""()=>{
        window.__execweaveStaticMode=false;
        window.fetch=async()=>new Response('{}',{status:401});
    }""")
    launch, refresh, status, content = PANELS[panel]
    page.get_by_role("button", name=launch, exact=True).click()
    before = page.locator(content).inner_text()
    page.get_by_role("button", name=refresh, exact=True).click()
    assert "refresh failed" in page.locator(status).inner_text().lower()
    assert page.locator(content).inner_text() == before


def test_initial_index_request_reports_false_without_claiming_completion(tmp_path, browser_page):
    page = browser_page
    graph, *_ = scenario(tmp_path)
    show(page, graph)  # No accepted investigation index yet.
    page.evaluate("""()=>{
        window.__execweaveStaticMode=false;
        window.__execweaveDashboard.agentPanel.refresh=async()=>false;
    }""")
    page.get_by_role("button", name="Explore run", exact=True).click()
    text = page.locator("#execweave-investigation-updates").inner_text()
    assert "request failed" in text.lower()
    assert "completed" not in text
