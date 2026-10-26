"""Navigation controls must not become part of an agent's recorded response.

Real Chromium with synthetic captured records; native HTTP journeys remain in
existing tests/test_relay_prompt_live_e2e.py and the formal offline runner.
"""
from __future__ import annotations

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from test_investigation_workspace import browser_page
from test_observed_history import entry, graph, message

__all__ = ["browser_page"]
pytestmark = pytest.mark.viewer_e2e


def show(page):
    data = graph()
    data["nodes"][0]["attributes"].update(provider="ollama", agent_role="root")
    records = [entry("agent:a", [
        message(1, kind="user_message", sender="user", recipient="/root", text="exact prompt"),
        message(2, text="EXACT FINAL RESPONSE", phase="final_answer"),
    ])]
    page.set_content(render_static_dashboard_html(data, conversation_entries=records))
    page.evaluate("window.__execweaveCore.selectNode('agent:a')")
    page.get_by_role("button", name="Runtime evidence for selection", exact=True).wait_for()


def test_runtime_action_does_not_pollute_response_text(browser_page):
    show(browser_page)
    text = browser_page.locator("#details").inner_text()
    assert text.partition("FINAL RESPONSE\n")[2].strip() == "EXACT FINAL RESPONSE"
    assert "Runtime evidence for selection" not in text
    assert browser_page.locator("#details #execweave-runtime-selection").count() == 0
    assert browser_page.locator("#inspector #execweave-runtime-selection").count() == 1


def test_runtime_action_remains_available_after_inspector_refresh(browser_page):
    show(browser_page)
    for _ in range(3):
        browser_page.evaluate("window.__execweaveAgentPanel.render(window.__execweaveCore.getGraph().nodes[0])")
    action = browser_page.get_by_role("button", name="Runtime evidence for selection", exact=True)
    assert action.count() == 1
    action.click()
    assert browser_page.locator("#execweave-runtime-dialog").is_visible()
    browser_page.keyboard.press("Escape")
    assert action.evaluate("n=>n===document.activeElement")
    assert browser_page.locator("#details").inner_text().partition("FINAL RESPONSE\n")[2].strip() == "EXACT FINAL RESPONSE"


def test_runtime_selection_rebinds_without_duplicate_controls(browser_page):
    show(browser_page)
    browser_page.evaluate("window.__execweaveCore.selectNode('agent:b')")
    browser_page.get_by_role("button", name="Runtime evidence for selection", exact=True).click()
    assert "agent:b" in browser_page.locator("#execweave-runtime-status").inner_text()
    assert "agent:a" not in browser_page.locator("#execweave-runtime-status").inner_text()
    assert browser_page.locator("#execweave-runtime-selection").count() == 1
    assert "Runtime evidence for selection" not in browser_page.locator("#details").inner_text()
