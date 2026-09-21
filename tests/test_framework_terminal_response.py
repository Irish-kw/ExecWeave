"""SDK-backed terminal reports remain distinct from earlier observed messages.

Synthetic captures rendered in Chromium; not the original R1/R2 replay.
"""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from execweave.conversation_records import conversation_index_payload
from execweave.dashboard_shell import render_static_dashboard_html
from execweave.framework_adapters import (
    AdapterContext, AutoGenAdapter, CAMELAdapter, ContentCapturePolicy, MessageRecord,
)
from execweave.graph import GraphAccumulator
from test_investigation_workspace import browser_page

__all__ = ['browser_page']
pytestmark = pytest.mark.viewer_e2e


def capture(root, framework='autogen', token='TERMINATE', previous=True):
    ctx = AdapterContext(framework=framework, run_id='terminal-run', session_id='terminal-run',
                         sidecar=root/'semantic.jsonl', content_root=root,
                         capture_policy=ContentCapturePolicy('prompt_and_response'))
    adapter = {'autogen': AutoGenAdapter, 'camel': CAMELAdapter}[framework](ctx)
    owner = adapter.agent('worker', name='Same name')
    sibling = adapter.agent('reviewer', name='Same name')
    for source, target, native, value, kind in [
        *([(owner, sibling, 'earlier', 'UNFINISHED_WORKER_MESSAGE', 'agent_message')] if previous else []),
        (owner, sibling, 'terminal', token, 'agent_result'),
        (sibling, owner, 'sibling', 'PRIVATE_SIBLING_MESSAGE', 'agent_result'),
    ]:
        ctx.record_message(MessageRecord(adapter.entity('message', native), source, target,
            content=value, content_payload={'text': value,
                'sender': f'/{framework}/'+('worker' if source == owner else 'reviewer'),
                'recipient': f'/{framework}/'+('reviewer' if source == owner else 'worker'),
                'kind': kind, 'phase': 'final_answer' if kind == 'agent_result' else 'sent'}))
    accumulator = GraphAccumulator(session_id='terminal-run', source_path=root/'events.jsonl')
    for i, line in enumerate((root/'semantic.jsonl').read_text().splitlines()):
        accumulator.apply({**json.loads(line), 'session_id': 'terminal-run', 'sequence': i})
    g = accumulator.to_dict()
    return g, conversation_index_payload(g, root), owner.id, sibling.id


def show(page, g, payload, owner):
    page.set_default_timeout(2000)
    page.set_content(render_static_dashboard_html(g, conversation_entries=payload['entries']))
    page.evaluate('id=>window.__execweaveCore.selectNode(id)', owner)


def messages(payload, source):
    return next(e['conversation_preview']['messages'] for e in payload['entries']
                if e['source_id'] == source and 'conversation_preview' in e)


def body(page, label):
    card = page.locator('.execweave-agent-latest .execweave-agent-card').filter(
        has=page.locator('.execweave-agent-label', has_text=label))
    return card.locator('.execweave-agent-body')


@pytest.mark.parametrize('framework,token', [('autogen', 'TERMINATE'), ('camel', '<CAMEL_TASK_DONE>')])
def test_terminal_report_exposes_earlier_message_without_replacing_final(tmp_path, browser_page, framework, token):
    g, payload, owner, _ = capture(tmp_path, framework, token)
    original = deepcopy(payload)
    show(browser_page, g, payload, owner)
    assert body(browser_page, 'Earlier observed message').inner_text() == 'UNFINISHED_WORKER_MESSAGE'
    cards = browser_page.locator('.execweave-agent-latest .execweave-agent-card')
    reported = cards.filter(has=browser_page.get_by_text('Response', exact=True))
    assert reported.locator('.execweave-agent-body').inner_text() == token
    note = body(browser_page, 'Response interpretation').inner_text()
    assert 'text match' in note and 'not a verified task result' in note
    assert 'PRIVATE_SIBLING_MESSAGE' not in browser_page.locator('.execweave-agent-latest').inner_text()
    assert browser_page.evaluate('window.__execweaveCore.getGraph()') == g
    assert browser_page.evaluate('window.__execweaveStaticConversations') == original['entries']
    browser_page.get_by_role('button', name='Browse observed history', exact=True).click()
    assert 'UNFINISHED_WORKER_MESSAGE' in browser_page.locator('#execweave-history-list').inner_text()


def test_no_earlier_outgoing_message_does_not_borrow_a_sibling(tmp_path, browser_page):
    g, payload, owner, _ = capture(tmp_path, previous=False)
    show(browser_page, g, payload, owner)
    assert body(browser_page, 'Earlier observed message').count() == 0
    assert 'No earlier eligible outgoing message' in body(browser_page, 'Response interpretation').inner_text()
    assert 'PRIVATE_SIBLING_MESSAGE' not in browser_page.locator('.execweave-agent-latest').inner_text()


@pytest.mark.parametrize('token', ['Please print TERMINATE', '```\nTERMINATE\n```', 'terminate'])
def test_quoted_or_nonexact_marker_is_not_labeled(tmp_path, browser_page, token):
    g, payload, owner, _ = capture(tmp_path, token=token)
    show(browser_page, g, payload, owner)
    assert body(browser_page, 'Response interpretation').count() == 0


@pytest.mark.parametrize('change', [
    {'text_truncated': True}, {'content_state': 'provider_encrypted'},
    {'kind': 'tool_result'}, {'kind': 'user_message', 'sender': 'user'},
    {'content_role': 'shared_injected_context'},
])
def test_unqualified_marker_never_gets_interpretation(tmp_path, browser_page, change):
    g, payload, owner, _ = capture(tmp_path)
    next(m for m in messages(payload, owner) if m.get('text') == 'TERMINATE').update(change)
    show(browser_page, g, payload, owner)
    assert body(browser_page, 'Response interpretation').count() == 0


@pytest.mark.parametrize('change', [
    {'kind': 'assistant_message', 'phase': 'response'},  # Could be repeated request context.
    {'kind': 'tool_result'}, {'phase': 'received'}, {'sender': 'user'},
    {'content_role': 'shared_injected_context'}, {'content_state': 'provider_encrypted'},
])
def test_previous_record_requires_outgoing_message_evidence(tmp_path, browser_page, change):
    g, payload, owner, _ = capture(tmp_path)
    next(m for m in messages(payload, owner) if m.get('text') == 'UNFINISHED_WORKER_MESSAGE').update(change)
    show(browser_page, g, payload, owner)
    assert body(browser_page, 'Earlier observed message').count() == 0


def test_no_framework_authority_does_not_change_generic_policy(tmp_path, browser_page):
    g, payload, owner, _ = capture(tmp_path)
    next(n for n in g['nodes'] if n['id'] == owner)['attributes'].pop('conversation_scope', None)
    show(browser_page, g, payload, owner)
    assert body(browser_page, 'Response interpretation').count() == 0


def test_path_fallback_is_not_annotation_authority(tmp_path, browser_page):
    g, payload, owner, _ = capture(tmp_path)
    for e in payload['entries']:
        if e['source_id'] == owner:
            e['source_id'] = 'not-the-selected-source'
    show(browser_page, g, payload, owner)
    assert body(browser_page, 'Response interpretation').count() == 0


def test_annotation_updates_without_mutating_the_reported_text(tmp_path, browser_page):
    g, payload, owner, _ = capture(tmp_path)
    show(browser_page, g, payload, owner)
    assert body(browser_page, 'Response interpretation').count() == 1
    changed = deepcopy(payload)
    next(m for m in messages(changed, owner) if m.get('text') == 'TERMINATE')['text'] = 'Actually still working'
    browser_page.evaluate('rows=>window.__execweaveAgentPanel.setEntries(rows)', changed['entries'])
    assert body(browser_page, 'Response interpretation').count() == 0
    assert 'Actually still working' in browser_page.locator('.execweave-agent-latest').inner_text()


def test_conflicting_raw_source_is_not_annotation_authority(tmp_path, browser_page):
    g, payload, owner, _ = capture(tmp_path)
    g['nodes'].append(deepcopy(next(n for n in g['nodes'] if n['id'] == owner)))
    show(browser_page, g, payload, owner)
    assert body(browser_page, 'Response interpretation').count() == 0


def test_earlier_message_is_literal_text_and_preserves_history_folds(tmp_path, browser_page):
    g, payload, owner, _ = capture(tmp_path)
    bad = '<img src="https://example.invalid" onerror="window.bad=true">'
    next(m for m in messages(payload, owner) if m.get('text') == 'UNFINISHED_WORKER_MESSAGE')['text'] = bad
    show(browser_page, g, payload, owner)
    assert body(browser_page, 'Earlier observed message').inner_text() == bad
    assert browser_page.locator('.execweave-agent-latest img').count() == 0
    assert browser_page.evaluate('window.bad===undefined')
    browser_page.locator('.execweave-agent-latest > summary').click()
    browser_page.evaluate('id=>window.__execweaveCore.selectNode(id)', owner)
    assert not browser_page.locator('.execweave-agent-latest').evaluate('n=>n.open')
