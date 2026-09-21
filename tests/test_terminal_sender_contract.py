"""Behavioral protection for the terminal annotation's strict sender gate.

The legacy compact-inspector test scans its assembled source. These cases check
actual DOM output instead, so satisfying that textual contract cannot admit a
missing/coercible sender or turn a child's own output into an assignment.
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from test_framework_model_terminal_interpretation import model_terminal_capture
from test_framework_terminal_response import body, capture, messages, show
from test_investigation_workspace import browser_page

__all__ = ['browser_page']
pytestmark = pytest.mark.viewer_e2e


@pytest.mark.parametrize('record', ['terminal', 'earlier'])
@pytest.mark.parametrize('sender', [None, '', False, 7, ['/autogen/worker'],
    {'name': '/autogen/worker'}, '/autogen/reviewer', 'Same name'],
    ids=['missing', 'empty', 'boolean', 'number', 'list', 'object', 'sibling', 'display-name'])
def test_annotation_requires_an_explicit_exact_string_sender(tmp_path, browser_page, record, sender):
    if record == 'terminal':
        graph, payload, owner, _, _ = model_terminal_capture(tmp_path, 'autogen')
        target = next(m for m in messages(payload, owner)
                      if m['kind'] == 'assistant_message' and m['text'] == 'TERMINATE')
    else:
        graph, payload, owner, _ = capture(tmp_path)
        target = next(m for m in messages(payload, owner)
                      if m['text'] == 'UNFINISHED_WORKER_MESSAGE')
    target['sender'] = sender
    before = deepcopy(payload)
    show(browser_page, graph, payload, owner)
    if record == 'terminal':
        assert body(browser_page, 'Response interpretation').count() == 0
    else:
        assert 'No earlier eligible outgoing message' in body(
            browser_page, 'Response interpretation').inner_text()
    assert body(browser_page, 'Earlier observed message').count() == 0
    assert browser_page.evaluate('window.__execweaveStaticConversations') == before['entries']
    assert browser_page.evaluate('window.__execweaveCore.getGraph()') == graph


@pytest.mark.parametrize('sender,accepted', [('/autogen', True), ('user', True),
    ('/autogen/worker', False), ('/autogen/reviewer', False)],
    ids=['parent', 'user', 'self', 'sibling'])
def test_terminal_annotation_does_not_change_assignment_authority(tmp_path, browser_page, sender, accepted):
    graph, payload, owner, _ = capture(tmp_path)
    messages(payload, owner).insert(0, {'kind': 'subagent_task', 'phase': 'assignment',
        'sender': sender, 'recipient': '/autogen/worker', 'text': 'ASSIGNMENT_SENTINEL',
        'ordinal': -1, 'timestamp': '2026-01-01T00:00:00Z'})
    before = deepcopy(payload)
    show(browser_page, graph, payload, owner)
    assert ('ASSIGNMENT_SENTINEL' in body(browser_page, 'Task').inner_text()) is accepted
    assert body(browser_page, 'Response').last.inner_text() == 'TERMINATE'
    assert 'not a verified task result' in body(browser_page, 'Response interpretation').inner_text()
    assert browser_page.evaluate('window.__execweaveStaticConversations') == before['entries']
    assert browser_page.evaluate('window.__execweaveCore.getGraph()') == graph
