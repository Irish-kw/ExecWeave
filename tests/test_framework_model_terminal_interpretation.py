"""Reproduce the SDK message shapes reported by buyer replay #87.

Generated fixtures, not the original R1/R2 captures. The earlier-message gate
must stay stricter than a text-only annotation of the selected Response card.
"""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from execweave.conversation_records import conversation_index_payload
from execweave.framework_adapters import (
    AdapterContext, AutoGenAdapter, CAMELAdapter, ContentCapturePolicy,
    MessageRecord, ModelCallRecord,
)
from execweave.graph import GraphAccumulator
from test_framework_terminal_response import body, capture, messages, show
from test_investigation_workspace import browser_page

__all__ = ['browser_page']
pytestmark = pytest.mark.viewer_e2e


def model_terminal_capture(root, framework):
    """Use default SDK serialization, including display-name message senders."""
    ctx = AdapterContext(framework=framework, run_id='model-terminal',
        session_id='model-terminal', sidecar=root/'semantic.jsonl', content_root=root,
        capture_policy=ContentCapturePolicy('prompt_and_response'))
    adapter = {'camel': CAMELAdapter, 'autogen': AutoGenAdapter}[framework](ctx)
    token = '<CAMEL_TASK_DONE>' if framework == 'camel' else 'TERMINATE'
    name = 'Security Analyst (AI User)' if framework == 'camel' else 'autogen_assistant'
    owner = adapter.agent('worker', name=name)
    peer = adapter.agent('peer', name='Python Programmer (AI Assistant)')
    model = adapter.model('shared')
    call = adapter.entity('model_call', 'terminal')
    ctx.record_model_call(ModelCallRecord(call, owner, model, request=[
        {'role': 'assistant', 'content': 'REPEATED_REQUEST_CONTEXT'},
        {'role': 'user', 'content': 'Return the next message'}], status='request'))
    ctx.record_model_call(ModelCallRecord(call, owner, model, response=token, status='response'))
    ctx.record_message(MessageRecord(adapter.entity('message', 'terminal'), owner,
        peer if framework == 'camel' else None, content=token))
    ctx.record_model_call(ModelCallRecord(adapter.entity('model_call', 'peer'),
        peer, model, response='PRIVATE_PEER_OUTPUT', status='response'))
    acc = GraphAccumulator(session_id='model-terminal', source_path=root/'events.jsonl')
    for i, line in enumerate((root/'semantic.jsonl').read_text().splitlines()):
        acc.apply({**json.loads(line), 'session_id': 'model-terminal', 'sequence': i})
    graph = acc.to_dict()
    return graph, conversation_index_payload(graph, root), owner.id, token, name


@pytest.mark.parametrize('framework', ['camel', 'autogen'])
def test_sdk_model_terminal_gets_text_note_without_earlier_context(tmp_path, browser_page, framework):
    graph, payload, owner, token, name = model_terminal_capture(tmp_path, framework)
    history = messages(payload, owner)
    # Verify the real serializer produced both shapes described in #87. Do not
    # modify the positive fixture to satisfy the presentation gate.
    assert any(m['kind'] == 'assistant_message' and m['phase'] == 'response'
               and m['sender'] == f'/{framework}/worker' and m.get('recipient') is None
               and m['text'] == token for m in history)
    assert any(m['kind'] == 'agent_message' and m['phase'] == 'sent'
               and m['sender'] == name and m['text'] == token for m in history)
    before = deepcopy(payload)
    show(browser_page, graph, payload, owner)
    note = body(browser_page, 'Response interpretation').inner_text()
    assert 'text match' in note and 'not a verified task result' in note
    assert 'No earlier eligible outgoing message' in note
    assert body(browser_page, 'Earlier observed message').count() == 0
    cards = browser_page.locator('.execweave-agent-latest .execweave-agent-card')
    assert cards.filter(has=browser_page.get_by_text('Response', exact=True)).locator(
        '.execweave-agent-body').inner_text() == token
    assert 'REPEATED_REQUEST_CONTEXT' not in browser_page.locator('.execweave-agent-latest').inner_text()
    assert 'PRIVATE_PEER_OUTPUT' not in browser_page.locator('.execweave-agent-latest').inner_text()
    assert browser_page.evaluate('window.__execweaveStaticConversations') == before['entries']
    assert browser_page.evaluate('window.__execweaveCore.getGraph()') == graph


def test_model_terminal_can_keep_a_separately_proven_earlier_outgoing_message(tmp_path, browser_page):
    graph, payload, owner, _ = capture(tmp_path)
    terminal = next(m for m in messages(payload, owner) if m['text'] == 'TERMINATE')
    terminal.update(kind='assistant_message', phase='response', recipient=None)
    show(browser_page, graph, payload, owner)
    assert body(browser_page, 'Earlier observed message').inner_text() == 'UNFINISHED_WORKER_MESSAGE'
    assert 'not a replacement final answer' in body(browser_page, 'Response interpretation').inner_text()


@pytest.mark.parametrize('change', [
    {'phase': 'request'}, {'phase': 'received'}, {'phase': 'candidate'},
    {'recipient': '/autogen/worker'}, {'recipient': '/autogen/peer'},
    {'sender': 'autogen_assistant'}, {'sender': '/autogen/peer'},
    {'text_truncated': True}, {'content_role': 'shared_injected_context'},
    {'content_state': 'provider_encrypted'}, {'text': '"TERMINATE"'},
], ids=['request', 'received', 'candidate', 'inbound', 'addressed', 'display-name',
        'peer', 'truncated', 'injected', 'encrypted', 'quoted'])
def test_model_terminal_note_does_not_relax_excluded_shapes(tmp_path, browser_page, change):
    graph, payload, owner, token, _ = model_terminal_capture(tmp_path, 'autogen')
    next(m for m in messages(payload, owner) if m['kind'] == 'assistant_message'
         and m['text'] == token).update(change)
    show(browser_page, graph, payload, owner)
    assert body(browser_page, 'Response interpretation').count() == 0
    assert body(browser_page, 'Earlier observed message').count() == 0


@pytest.mark.parametrize('conflict', ['source', 'path', 'native'])
def test_model_terminal_note_keeps_exact_source_authority(tmp_path, browser_page, conflict):
    graph, payload, owner, _, _ = model_terminal_capture(tmp_path, 'autogen')
    exact = next(e for e in payload['entries'] if e['source_id'] == owner and 'conversation_preview' in e)
    if conflict == 'source':
        for entry in payload['entries']:
            if entry['source_id'] == owner:
                entry['source_id'] = 'unknown-source'
    else:
        other = deepcopy(exact)
        field = 'agent_path' if conflict == 'path' else 'provider_native_id'
        other['conversation_preview'][field] = 'different-identity'
        if conflict == 'native':
            exact['conversation_preview'][field] = 'first-identity'
        payload['entries'].append(other)
    show(browser_page, graph, payload, owner)
    assert body(browser_page, 'Response interpretation').count() == 0
