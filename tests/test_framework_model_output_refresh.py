"""Refresh only the captured-output view without replacing a reader's snapshot.

Real Chromium and SDK-shaped synthetic records, not a fresh provider recording.
The shared setEntries path is used without replacing fetch or its outcome API.
"""
from copy import deepcopy

import pytest

from test_framework_model_output_panel import capture, show
from test_investigation_workspace import browser_page

__all__ = ['browser_page']
pytestmark = pytest.mark.viewer_e2e
SECTION = '.execweave-framework-model-output'
RECORD = '.execweave-framework-model-record'


def update(page, payload):
    page.evaluate('rows=>window.__execweaveAgentPanel.setEntries(rows)', payload['entries'])


def changed_preview(payload, owner, text='UPDATED_MODEL_BODY'):
    changed = deepcopy(payload)
    row = [e for e in changed['entries'] if e['source_id'] == owner and 'model_response_preview' in e][-1]
    row['model_response_preview']['messages'][0]['text'] = text
    return changed


def refresh(page):
    page.get_by_role('button', name='Refresh captured model output', exact=True).click()


@pytest.mark.parametrize('framework', ['metagpt', 'autogen', 'camel'])
def test_preview_only_update_is_visible_but_does_not_replace_open_content(tmp_path, browser_page, framework):
    graph, payload, owner, _ = capture(tmp_path, framework)
    show(browser_page, graph, payload, owner)
    changed = changed_preview(payload, owner)
    update(browser_page, changed)
    browser_page.get_by_role('button', name='Refresh captured model output', exact=True).wait_for()
    assert 'ACTUAL_ENGINEER_BODY_1' in browser_page.locator(SECTION).inner_text()
    assert 'UPDATED_MODEL_BODY' not in browser_page.locator(SECTION).inner_text()
    refresh(browser_page)
    assert 'UPDATED_MODEL_BODY' in browser_page.locator(SECTION).inner_text()
    assert 'No actions taken yet' in browser_page.locator('.execweave-agent-latest').inner_text()
    assert browser_page.evaluate('window.__execweaveCore.getGraph()') == graph
    assert browser_page.evaluate('window.__execweaveStaticConversations') == payload['entries']


def test_equal_index_and_sibling_changes_do_not_offer_false_refresh(tmp_path, browser_page):
    graph, payload, owner, sibling = capture(tmp_path)
    show(browser_page, graph, payload, owner)
    browser_page.evaluate("window.savedModelSection=document.querySelector('.execweave-framework-model-output')")
    update(browser_page, deepcopy(payload))
    update(browser_page, changed_preview(payload, sibling, 'SIBLING_ONLY'))
    assert browser_page.evaluate("window.savedModelSection===document.querySelector('.execweave-framework-model-output')")
    assert not browser_page.get_by_role('button', name='Refresh captured model output', exact=True).is_visible()
    assert 'SIBLING_ONLY' not in browser_page.locator(SECTION).inner_text()


def test_later_conversation_refresh_keeps_model_snapshot_until_explicit_action(tmp_path, browser_page):
    graph, payload, owner, _ = capture(tmp_path)
    show(browser_page, graph, payload, owner)
    changed = changed_preview(payload, owner)
    merged = next(e for e in changed['entries'] if e['source_id'] == owner and 'conversation_preview' in e)
    merged['conversation_preview']['messages'].append({
        'sender': '/metagpt/engineer', 'recipient': '/metagpt/reviewer',
        'kind': 'agent_message', 'text': 'A later report', 'ordinal': 999,
    })
    update(browser_page, changed)
    browser_page.get_by_role('button', name='Refresh captured model output', exact=True).wait_for()
    assert 'ACTUAL_ENGINEER_BODY_1' in browser_page.locator(SECTION).inner_text()
    assert 'UPDATED_MODEL_BODY' not in browser_page.locator(SECTION).inner_text()
    refresh(browser_page)
    assert 'UPDATED_MODEL_BODY' in browser_page.locator(SECTION).inner_text()


def test_new_record_is_discoverable_without_reselecting_agent(tmp_path, browser_page):
    graph, payload, owner, _ = capture(tmp_path)
    initially_empty = deepcopy(payload)
    for e in initially_empty['entries']:
        if e['source_id'] == owner:
            e.pop('model_response_preview', None)
    show(browser_page, graph, initially_empty, owner)
    assert browser_page.locator(SECTION).count() == 0
    update(browser_page, payload)
    browser_page.get_by_role('button', name='Refresh captured model output', exact=True).wait_for()
    refresh(browser_page)
    assert 'ACTUAL_ENGINEER_BODY_1' in browser_page.locator(SECTION).inner_text()


def test_refresh_preserves_expanded_older_records_and_loaded_pages(tmp_path, browser_page):
    graph, payload, owner, _ = capture(tmp_path, responses=26)
    show(browser_page, graph, payload, owner)
    browser_page.get_by_role('button', name='Show more model output records', exact=True).click()
    browser_page.locator(RECORD).last.locator('summary').click()
    changed = changed_preview(payload, owner)
    update(browser_page, changed)
    browser_page.get_by_role('button', name='Refresh captured model output', exact=True).wait_for()
    refresh(browser_page)
    assert browser_page.locator(RECORD).count() == 26
    assert browser_page.locator(RECORD).last.evaluate('n=>n.open')
    assert 'ACTUAL_ENGINEER_BODY_0' in browser_page.locator(RECORD).last.inner_text()


def test_withdrawn_output_is_removed_only_on_explicit_refresh(tmp_path, browser_page):
    graph, payload, owner, _ = capture(tmp_path)
    show(browser_page, graph, payload, owner)
    withdrawn = deepcopy(payload)
    for e in withdrawn['entries']:
        if e['source_id'] == owner:
            e.pop('model_response_preview', None)
    update(browser_page, withdrawn)
    browser_page.get_by_role('button', name='Refresh captured model output', exact=True).wait_for()
    assert 'ACTUAL_ENGINEER_BODY_1' in browser_page.locator(SECTION).inner_text()
    refresh(browser_page)
    assert browser_page.locator(SECTION).count() == 0


def test_reselected_agent_never_receives_another_agents_pinned_body(tmp_path, browser_page):
    graph, payload, owner, sibling = capture(tmp_path)
    show(browser_page, graph, payload, owner)
    update(browser_page, changed_preview(payload, owner))
    browser_page.evaluate('id=>window.__execweaveCore.selectNode(id)', sibling)
    assert 'PRIVATE_REVIEWER_BODY_1' in browser_page.locator(SECTION).inner_text()
    assert 'ACTUAL_ENGINEER' not in browser_page.locator(SECTION).inner_text()
    browser_page.evaluate('id=>window.__execweaveCore.selectNode(id)', owner)
    assert 'UPDATED_MODEL_BODY' in browser_page.locator(SECTION).inner_text()
    assert 'PRIVATE_REVIEWER' not in browser_page.locator(SECTION).inner_text()


def test_new_latest_record_does_not_close_the_previously_read_record(tmp_path, browser_page):
    graph, payload, owner, _ = capture(tmp_path)
    earlier = deepcopy(payload)
    latest = [e for e in earlier['entries'] if e['source_id'] == owner and 'model_response_preview' in e][-1]
    latest.pop('model_response_preview')
    show(browser_page, graph, earlier, owner)
    assert 'ACTUAL_ENGINEER_BODY_0' in browser_page.locator(SECTION).inner_text()
    update(browser_page, payload)
    refresh(browser_page)
    assert browser_page.locator(RECORD + '[open]').count() == 2
    assert 'ACTUAL_ENGINEER_BODY_0' in browser_page.locator(SECTION).inner_text()
    assert 'ACTUAL_ENGINEER_BODY_1' in browser_page.locator(SECTION).inner_text()


def test_changed_run_cannot_keep_another_runs_pinned_output(tmp_path, browser_page):
    graph, payload, owner, _ = capture(tmp_path)
    show(browser_page, graph, payload, owner)
    unrelated = deepcopy(payload)
    for e in unrelated['entries']:
        e.pop('model_response_preview', None)
    browser_page.evaluate("window.__execweaveCore.getGraph().session_id='different-run'")
    update(browser_page, unrelated)
    assert browser_page.locator(SECTION).count() == 0
