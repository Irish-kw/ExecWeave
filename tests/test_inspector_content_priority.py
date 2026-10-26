"""Role discovery stays usable without pushing selected evidence out of view."""
from __future__ import annotations

import pytest

from test_delivery_status_browser import load, page, receipt
from test_run_guide import show

__all__ = ['page']
pytestmark = pytest.mark.viewer_e2e


@pytest.mark.parametrize('width,height', [(1500, 1000), (1800, 1100), (1024, 900)])
def test_selected_evidence_precedes_open_guide_without_losing_search(page, tmp_path, width, height):
    page.set_viewport_size({'width': width, 'height': height})
    graph = load(page, expand_delivery=False)
    receipt(page, tmp_path, 'failed')
    page.get_by_label('Find role in run guide').fill('A')
    page.evaluate("window.savedRoleButton=document.querySelector('#execweave-run-guide-roles button')")
    page.evaluate("window.__execweaveAgentPanel.render(window.__execweaveCore.getDisplayGraph().nodes.find(n=>n.id==='a'))")
    guide = page.locator('#execweave-run-guide')
    body = page.locator('#details')
    assert guide.evaluate('n=>n.open')  # Never auto-collapse a reader's disclosure.
    assert page.get_by_label('Find role in run guide').input_value() == 'A'
    assert page.evaluate("window.savedRoleButton===document.querySelector('#execweave-run-guide-roles button')")
    assert body.bounding_box()['y'] < height - 150
    assert body.evaluate("n=>!!(n.compareDocumentPosition(document.getElementById('execweave-run-guide'))&Node.DOCUMENT_POSITION_FOLLOWING)")
    assert 'old answer' in body.inner_text()
    answer = page.locator('#details .execweave-agent-body').last.bounding_box()
    viewport = page.locator('#inspector').bounding_box()
    assert viewport['y'] <= answer['y']
    assert answer['y'] + answer['height'] <= viewport['y'] + viewport['height']
    assert page.locator('#execweave-delivery-summary').bounding_box()['y'] < body.bounding_box()['y']
    assert 'export failed' in page.locator('#execweave-delivery-summary').inner_text().lower()
    assert not page.locator('#details #execweave-run-guide').count()
    assert page.evaluate('window.__execweaveCore.getGraph()') == graph


def test_guide_first_before_selection_preserves_reading_after_clear(page):
    show(page)
    assert page.locator('#execweave-run-guide').evaluate('n=>n.open')
    assert page.locator('#execweave-run-guide').evaluate("n=>!!(n.compareDocumentPosition(document.getElementById('details'))&Node.DOCUMENT_POSITION_FOLLOWING)")
    page.locator('#execweave-run-guide-roles button[data-agent-id="a"]').click()
    assert page.locator('#details').evaluate("n=>n.nextElementSibling.id==='execweave-run-guide'")
    page.keyboard.press('Escape')
    page.wait_for_function("!document.querySelector('#nodes .node.selected')")
    assert page.locator('#execweave-run-guide').evaluate('n=>n.open')
    # The existing core retains readable details when graph highlighting clears.
    assert page.locator('#details').evaluate("n=>n.nextElementSibling.id==='execweave-run-guide'")


def test_live_refresh_does_not_replace_guide_or_move_manual_camera(page):
    graph = show(page)
    page.locator('#zoom-in').click()
    page.wait_for_timeout(300)
    camera = page.locator('#viewport').get_attribute('transform')
    page.get_by_label('Find role in run guide').fill('Same')
    page.locator('#execweave-run-guide-roles button[data-agent-id="b"]').click()
    page.evaluate("window.roleGuide=document.getElementById('execweave-run-guide')")
    page.evaluate("()=>{window.__execweaveDashboard.onPayload({});window.__execweaveCore.selectNode('b')}")
    assert page.evaluate("window.roleGuide===document.getElementById('execweave-run-guide')")
    assert page.get_by_label('Find role in run guide').input_value() == 'Same'
    assert page.locator('#execweave-run-guide').evaluate('n=>n.open')
    assert page.locator('#viewport').get_attribute('transform') == camera
    assert page.evaluate('window.__execweaveCore.getGraph()') == graph
