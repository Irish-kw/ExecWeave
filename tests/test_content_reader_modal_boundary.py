"""Real modal keyboard events over synthetic SDK records in the shared shell.

These are component interaction checks, not original-run replay or proof of
native Offline body verification. No key handler, fetch, File API or timer is
replaced. The body reader is exercised at its real folder-required boundary.
"""
from __future__ import annotations

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from test_investigation_workspace import browser_page
from test_message_handoff_navigation import PANEL, capture, select

__all__ = ['browser_page']
pytestmark = pytest.mark.viewer_e2e
DIALOG = '#execweave-content-dialog'
EXPLORER = '#execweave-investigation-dialog'


def open_body(page, root, origin):
    data, index, sender, recipient, _ = capture(root)
    page.set_default_timeout(2000)
    page.set_content(render_static_dashboard_html(data, investigation_index=index))
    if origin == 'message':
        selected = select(page, sender, recipient)
        parent = PANEL
    else:
        selected = sender
        page.evaluate('id=>window.__execweaveCore.selectNode(id)', selected)
        page.get_by_role('button', name='Explore run', exact=True).click()
        page.get_by_role('button', name='Handoffs', exact=True).click()
        parent = EXPLORER
    row = page.locator(parent + ' .investigation-row').first
    row.locator('summary').click()
    opener = row.locator('.execweave-content-actions button').first
    opener.wait_for(state='visible')
    opener.evaluate("n=>n.setAttribute('data-modal-opener','body')")
    opener.click()
    page.wait_for_function("document.querySelector('#execweave-content-dialog')?.dataset.state==='folder_required'")
    return selected, row, opener, data


@pytest.mark.parametrize('origin', ['message', 'investigation'])
@pytest.mark.parametrize('action', ['escape', 'close'])
def test_closing_body_keeps_selection_parent_record_and_return_focus(
    tmp_path, browser_page, origin, action,
):
    page = browser_page
    selected, row, opener, data = open_body(page, tmp_path, origin)
    if action == 'escape':
        page.keyboard.press('Escape')
    else:
        page.locator(DIALOG).get_by_role('button', name='Close', exact=True).click()
    assert not page.locator(DIALOG).is_visible()
    assert page.locator('#nodes .node.selected').get_attribute('data-id') == selected
    assert row.evaluate('n=>n.open')
    assert opener.evaluate('n=>n===document.activeElement')
    assert page.evaluate('window.__execweaveCore.getGraph()') == data
    if origin == 'investigation':
        assert page.locator(EXPLORER).is_visible()
    opener.press('Enter')
    assert page.locator(DIALOG).is_visible()
    assert page.locator(DIALOG).get_attribute('data-state') == 'folder_required'


@pytest.mark.parametrize('origin', ['message', 'investigation'])
def test_escape_unwinds_modals_before_the_canvas_selection(tmp_path, browser_page, origin):
    page = browser_page
    selected, row, _, _ = open_body(page, tmp_path, origin)
    page.keyboard.press('Escape')
    assert not page.locator(DIALOG).is_visible()
    assert page.locator('#nodes .node.selected').get_attribute('data-id') == selected
    assert row.evaluate('n=>n.open')
    if origin == 'investigation':
        assert page.locator(EXPLORER).is_visible()
        page.keyboard.press('Escape')
        assert not page.locator(EXPLORER).is_visible()
        assert page.locator('#nodes .node.selected').get_attribute('data-id') == selected
    page.keyboard.press('Escape')
    assert page.locator('#nodes .node.selected').count() == 0


def test_retry_then_escape_preserves_message_record(tmp_path, browser_page):
    page = browser_page
    selected, row, opener, _ = open_body(page, tmp_path, 'message')
    page.get_by_role('button', name='Load / retry', exact=True).click()
    assert page.locator(DIALOG).get_attribute('data-state') == 'folder_required'
    page.keyboard.press('Escape')
    assert page.locator('#nodes .node.selected').get_attribute('data-id') == selected
    assert row.evaluate('n=>n.open')
    assert opener.evaluate('n=>n===document.activeElement')
