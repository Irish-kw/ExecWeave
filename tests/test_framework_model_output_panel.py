"""SDK-backed synthetic model records in the shipped agent inspector.

These are not a replay of the private buyer capture or fresh model calls.
"""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from execweave.conversation_records import conversation_index_payload
from execweave.dashboard_shell import render_static_dashboard_html
from execweave.framework_adapters import (
    AdapterContext, AutoGenAdapter, CAMELAdapter, ContentCapturePolicy,
    MetaGPTAdapter, ModelCallRecord, MessageRecord,
)
from execweave.graph import GraphAccumulator
from test_investigation_workspace import browser_page

__all__ = ['browser_page']
pytestmark = pytest.mark.viewer_e2e


def capture(root, framework='metagpt', responses=2):
    ctx = AdapterContext(framework=framework, run_id='run', session_id='run',
                         sidecar=root/'semantic.jsonl', content_root=root,
                         capture_policy=ContentCapturePolicy('prompt_and_response'))
    cls = {'metagpt': MetaGPTAdapter, 'autogen': AutoGenAdapter, 'camel': CAMELAdapter}[framework]
    adapter = cls(ctx)
    engineer = adapter.agent('engineer', name='Same display name')
    sibling = adapter.agent('reviewer', name='Same display name')
    model = adapter.model('shared-model')
    for owner, text in [(engineer, 'ACTUAL_ENGINEER_BODY'), (sibling, 'PRIVATE_REVIEWER_BODY')]:
        for i in range(responses):
            call = adapter.entity('model_call', owner.id+str(i))
            ctx.record_model_call(ModelCallRecord(call, owner, model,
                request=[{'role':'assistant', 'content':'REQUEST_CONTEXT_NOT_NEW_OUTPUT'},
                         {'role':'user', 'content':'Implement the feature'}], status='request'))
            ctx.record_model_call(ModelCallRecord(call, owner, model,
                response=f'{text}_{i}', status='response'))
    # A later framework report is not the model's generated code/deliverable.
    ctx.record_message(MessageRecord(adapter.entity('message', 'final-report'), engineer, sibling,
        content='No actions taken yet', content_payload={
            'text':'No actions taken yet', 'sender':f'/{framework}/engineer',
            'recipient':f'/{framework}/reviewer', 'kind':'agent_result', 'phase':'final_answer'}))
    accumulator = GraphAccumulator(session_id='run', source_path=root/'events.jsonl')
    for i, line in enumerate((root/'semantic.jsonl').read_text().splitlines()):
        accumulator.apply({**json.loads(line), 'session_id':'run', 'sequence':i})
    graph = accumulator.to_dict()
    payload = conversation_index_payload(graph, root)
    return graph, payload, engineer.id, sibling.id


def show(page, graph, payload, source):
    page.set_default_timeout(3000)
    page.set_content(render_static_dashboard_html(graph, conversation_entries=payload['entries']))
    page.evaluate('id=>window.__execweaveCore.selectNode(id)', source)


@pytest.mark.parametrize('framework', ['metagpt', 'autogen', 'camel'])
def test_model_output_is_readable_beside_not_as_final_claim(tmp_path, browser_page, framework):
    graph, payload, engineer, _ = capture(tmp_path, framework)
    original = deepcopy(payload)
    show(browser_page, graph, payload, engineer)
    section = browser_page.locator('.execweave-framework-model-output')
    assert section.count() == 1
    assert 'ACTUAL_ENGINEER_BODY_1' in section.inner_text()
    assert 'PRIVATE_REVIEWER' not in section.inner_text()
    assert 'REQUEST_CONTEXT_NOT_NEW_OUTPUT' not in section.inner_text()
    assert 'not a verified task result' in section.inner_text()
    reported = browser_page.locator('.execweave-agent-latest').first
    if not reported.evaluate('n=>n.open'):
        reported.locator('summary').click()
    assert 'No actions taken yet' in reported.inner_text()
    assert browser_page.evaluate('window.__execweaveStaticConversations') == original['entries']
    assert browser_page.evaluate('window.__execweaveCore.getGraph()') == graph


def test_original_body_reference_and_preview_survive_conversation_merge(tmp_path, browser_page):
    graph, payload, engineer, _ = capture(tmp_path)
    rows = [e for e in payload['entries'] if e['source_id']==engineer and 'model_response_preview' in e]
    assert len(rows) == 2
    assert [e['model_response_preview']['messages'][0]['text'] for e in rows] == ['ACTUAL_ENGINEER_BODY_0', 'ACTUAL_ENGINEER_BODY_1']
    show(browser_page, graph, payload, engineer)
    browser_page.locator('.execweave-framework-model-output .execweave-content-actions button').first.click()
    assert browser_page.locator('#execweave-content-dialog').is_visible()
    assert browser_page.locator('#execweave-content-dialog').get_attribute('data-state') == 'folder_required'


def test_exact_source_only_even_when_another_agent_has_same_name(tmp_path, browser_page):
    graph, payload, engineer, reviewer = capture(tmp_path)
    payload['entries'] = [e for e in payload['entries'] if e['source_id']!=engineer]
    show(browser_page, graph, payload, engineer)
    assert browser_page.locator('.execweave-framework-model-output').count() == 0
    browser_page.evaluate('id=>window.__execweaveCore.selectNode(id)', reviewer)
    assert 'PRIVATE_REVIEWER_BODY' in browser_page.locator('.execweave-framework-model-output').inner_text()


def test_model_preview_is_escaped_and_expansion_survives_rerender(tmp_path, browser_page):
    graph, payload, engineer, _ = capture(tmp_path)
    rows = [e for e in payload['entries'] if e['source_id']==engineer and 'model_response_preview' in e]
    assert rows
    rows[-1]['model_response_preview']['messages'][0]['text'] = '<img src=x onerror="window.pwned=true">'
    show(browser_page, graph, payload, engineer)
    assert browser_page.locator('.execweave-framework-model-output img').count() == 0
    fold = browser_page.locator('.execweave-framework-model-output details').first
    assert fold.evaluate('n=>n.open')
    fold.locator('summary').click()
    browser_page.evaluate('id=>window.__execweaveCore.selectNode(id)', engineer)
    assert not browser_page.locator('.execweave-framework-model-output details').first.evaluate('n=>n.open')
    assert browser_page.evaluate('window.pwned===undefined')


def test_request_and_failure_are_not_model_response_records(tmp_path, browser_page):
    graph, payload, engineer, _ = capture(tmp_path)
    response_nodes = [n for n in graph['nodes'] if n.get('attributes', {}).get('content_kind') == 'metagpt.model_response']
    for node in response_nodes:
        node['attributes']['content_kind'] = 'metagpt.model_failure'
    payload = conversation_index_payload(graph, tmp_path)
    assert not any('model_response_preview' in e for e in payload['entries'])
    show(browser_page, graph, payload, engineer)
    assert browser_page.locator('.execweave-framework-model-output').count() == 0


def test_ambiguous_graph_source_does_not_publish_model_preview(tmp_path, browser_page):
    graph, _, engineer, _ = capture(tmp_path)
    duplicate = deepcopy(next(n for n in graph['nodes'] if n['id']==engineer))
    duplicate['attributes']['conversation_agent_path'] = '/metagpt/other'
    graph['nodes'].append(duplicate)
    payload = conversation_index_payload(graph, tmp_path)
    assert not any('model_response_preview' in e for e in payload['entries'] if e['source_id']==engineer)


@pytest.mark.parametrize('flags', [{'inferred': True}, {'inferred': 0}, {'viewer_only': 'false'}, {'attributes': {'inferred': True}}])
def test_unproven_model_content_relationship_is_not_published(tmp_path, browser_page, flags):
    graph, _, engineer, _ = capture(tmp_path)
    for edge in graph['edges']:
        if edge['source'] == engineer and edge['relation'] == 'HAS_MODEL_CONTENT':
            edge.update(flags)
    payload = conversation_index_payload(graph, tmp_path)
    assert not any('model_response_preview' in e for e in payload['entries'] if e['source_id'] == engineer)


def test_output_records_are_paged_and_older_record_can_be_opened(tmp_path, browser_page):
    graph, payload, engineer, _ = capture(tmp_path, responses=26)
    show(browser_page, graph, payload, engineer)
    records = browser_page.locator('.execweave-framework-model-record')
    assert records.count() == 25
    browser_page.get_by_role('button', name='Show more model output records', exact=True).click()
    assert records.count() == 26
    records.last.locator('summary').click()
    assert 'ACTUAL_ENGINEER_BODY_0' in records.last.inner_text()
    assert browser_page.get_by_role('button', name='Show more model output records', exact=True).is_hidden()
