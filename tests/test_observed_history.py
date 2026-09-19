"""Real Chromium contracts for published exact-source history, not provider calls."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from copy import deepcopy

import pytest

from execweave.dashboard_shell import DASHBOARD_HTML, render_static_dashboard_html
from execweave.viewer_history_browser import HISTORY_BROWSER_CSS, HISTORY_BROWSER_JS

pytestmark = pytest.mark.viewer_e2e
PROVIDERS = ['claude', 'codex', 'antigravity', 'cursor', 'opencode', 'ollama',
             'llamacpp', 'vllm', 'lmstudio', 'anthropic', 'openrouter', 'litellm',
             'openai-compatible', 'camel', 'autogen', 'metagpt']


def message(index, **extra):
    return {'ordinal': index, 'kind': 'assistant_message', 'sender': '/root',
            'recipient': None, 'content_state': 'plaintext', 'text': f'record {index}',
            'phase': 'response', **extra}


def entry(source, messages, **preview):
    return {'source_id': source, 'provider': 'codex', 'conversation_preview': {
        'thread_id': source, 'is_root': True, 'agent_path': '/root',
        'message_count': len(messages), 'messages_truncated': False,
        'conversation_completeness': 'provider_transcript', 'messages': messages, **preview}}


def graph():
    return {'graph_schema_version': '0.2', 'session_id': 'run-one', 'nodes': [
        {'id': 'agent:a', 'type': 'agent', 'name': 'same name', 'attributes': {'agent_path': '/root'}},
        {'id': 'agent:b', 'type': 'agent', 'name': 'same name', 'attributes': {'agent_path': '/root'}},
    ], 'edges': [], 'node_count': 2, 'edge_count': 0, 'event_count': 0}


@pytest.fixture(scope='module')
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        path = os.environ.get('EXECWEAVE_E2E_CHROMIUM') or shutil.which('chromium') or shutil.which('chromium-browser')
        b = p.chromium.launch(**({'executable_path': path} if path else {}))
        yield b
        b.close()


@pytest.fixture
def page(browser):
    page = browser.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    yield page
    page.close()
    assert errors == []


def load(page, records=None, *, full=False, g=None):
    g = graph() if g is None else g
    records = [entry('agent:a', [message(i) for i in range(210)]),
               entry('agent:b', [message(1, text='private sibling answer')])] if records is None else records
    if full:
        page.set_content(render_static_dashboard_html(g, conversation_entries=records))
        page.evaluate('window.__execweaveAgentPanel.render(window.__execweaveStaticGraph.nodes[0])')
        page.get_by_role('button', name='Browse observed history', exact=True).click()
    else:
        data = json.dumps({'graph': g, 'entries': records}).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
        html = '<html><body><style>' + HISTORY_BROWSER_CSS + '</style><script>window.fixture=' + data + ';let entries=window.fixture.entries;'
        html += 'window.__execweaveStaticGraph=window.fixture.graph;' + HISTORY_BROWSER_JS
        html += '</script></body></html>'
        page.set_content(html)
        page.evaluate('window.__execweaveHistoryBrowser.open(window.fixture.graph.nodes[0])')
    return records


def find(page, text):
    page.locator('#execweave-history-search').fill(text)
    page.locator('#execweave-history-search').press('Enter')


@pytest.mark.parametrize('provider', PROVIDERS)
def test_each_provider_reads_exact_records_without_sibling_fallback(page, provider):
    records = [entry('agent:a', [message(1, text=f'{provider} own answer')]),
               entry('agent:b', [message(1, text='private sibling answer')])]
    for e in records:
        e['provider'] = provider
    before = deepcopy(records)
    load(page, records, full=True)
    assert f'{provider} own answer' in page.locator('#execweave-history-list').inner_text()
    assert 'private sibling' not in page.locator('#execweave-history-dialog').inner_text()
    assert page.evaluate('window.__execweaveStaticConversations') == before


def test_middle_and_last_records_remain_searchable_with_bounded_dom(page):
    load(page, full=True)
    assert page.locator('.execweave-history-message').count() == 25
    find(page, 'record 83')
    assert page.locator('.execweave-history-message').count() == 1
    page.locator('#execweave-history-list summary').click()
    assert page.locator('.history-message-text').inner_text() == 'record 83'
    find(page, 'record 209')
    assert 'record 209' in page.locator('#execweave-history-list').inner_text()
    find(page, 'not-present')
    assert page.locator('.execweave-history-message').count() == 0
    assert '0 matching / 210' in page.locator('#execweave-history-status').inner_text()


def test_pagination_retains_open_record_per_agent(page):
    load(page)
    page.get_by_role('button', name='Next records', exact=True).click()
    page.locator('#execweave-history-list summary').first.click()
    page.get_by_role('button', name='Close history', exact=True).click()
    page.evaluate('window.__execweaveHistoryBrowser.open(window.fixture.graph.nodes[1])')
    assert 'private sibling' in page.locator('#execweave-history-list').inner_text()
    page.get_by_role('button', name='Close history', exact=True).click()
    page.evaluate('window.__execweaveHistoryBrowser.open(window.fixture.graph.nodes[0])')
    assert 'Page 2/9' in page.locator('#execweave-history-status').inner_text()
    assert page.locator('.execweave-history-message').first.get_attribute('open') is not None
    assert page.locator('.history-message-text').first.inner_text() == 'record 25'


def test_refresh_notification_pins_snapshot_page_expansion_and_scroll(page):
    records = load(page, full=True)
    page.get_by_role('button', name='Next records', exact=True).click()
    page.locator('#execweave-history-list summary').first.click()
    page.locator('#execweave-history-list').evaluate('(n)=>n.scrollTop=77')
    scroll = page.locator('#execweave-history-list').evaluate('(n)=>n.scrollTop')
    records[0]['conversation_preview']['messages'].append(message(210, text='fresh arrival'))
    page.evaluate('(e)=>window.__execweaveAgentPanel.setEntries(e)', records)
    assert 'Updated history is available' in page.locator('#execweave-history-updates').inner_text()
    assert '210 loaded' in page.locator('#execweave-history-status').inner_text()
    assert 'Page 2/9' in page.locator('#execweave-history-status').inner_text()
    assert page.locator('#execweave-history-list').evaluate('(n)=>n.scrollTop') == scroll
    assert page.locator('.execweave-history-message').first.get_attribute('open') is not None
    page.get_by_role('button', name='Refresh history', exact=True).click()
    assert '211 loaded' in page.locator('#execweave-history-status').inner_text()
    assert 'Page 2/9' in page.locator('#execweave-history-status').inner_text()
    assert page.locator('.execweave-history-message').first.get_attribute('open') is not None


def test_middle_record_correction_is_not_silently_swapped_under_reader(page):
    records = load(page, full=True)
    find(page, 'record 83')
    records[0]['conversation_preview']['messages'][83]['text'] = 'corrected eighty three'
    page.evaluate('(e)=>window.__execweaveAgentPanel.setEntries(e)', records)
    assert 'record 83' in page.locator('#execweave-history-list').inner_text()
    assert 'Updated history' in page.locator('#execweave-history-updates').inner_text()
    page.get_by_role('button', name='Refresh history', exact=True).click()
    assert '0 matching' in page.locator('#execweave-history-status').inner_text()
    find(page, 'corrected eighty three')
    assert page.locator('.execweave-history-message').count() == 1


def test_same_text_at_distinct_ordinals_is_not_deduplicated(page):
    load(page, [entry('agent:a', [message(i, text='same reply', occurrence_id=f'call-{i}') for i in range(83)])])
    find(page, 'same reply')
    assert '83 matching / 83 loaded' in page.locator('#execweave-history-status').inner_text()
    page.get_by_role('button', name='Next records', exact=True).click()
    assert '#26' in page.locator('#execweave-history-list summary').first.inner_text()


@pytest.mark.parametrize('token', ['TERMINATE', '<CAMEL_TASK_DONE>'])
def test_termination_hint_preserves_raw_text_without_promoting_previous_output(page, token):
    load(page, [entry('agent:a', [message(1, text='unfinished output'), message(2, text=token)])], full=True)
    page.locator('#execweave-history-filter').select_option('marker')
    assert page.locator('.execweave-history-message').count() == 1
    page.locator('#execweave-history-list summary').click()
    assert page.locator('.history-message-text').inner_text() == token
    assert 'not verified task completion' in page.locator('.history-body-controls').inner_text()
    assert 'unfinished output' not in page.locator('#execweave-history-list').inner_text()


@pytest.mark.parametrize('extra', [
    {'sender': 'user'}, {'kind': 'user_message'}, {'text_truncated': True},
    {'kind': 'tool_result'}, {'content_role': 'shared_injected_context'},
    {'text': 'Please print TERMINATE'}, {'text': '```\nTERMINATE\n```'},
])
def test_user_tool_context_partial_and_quoted_markers_are_not_classified(page, extra):
    load(page, [entry('agent:a', [message(1, text='TERMINATE') | extra])])
    page.locator('#execweave-history-filter').select_option('marker')
    assert page.locator('.execweave-history-message').count() == 0


def test_encrypted_record_does_not_render_or_search_supplied_ciphertext(page):
    load(page, [entry('agent:a', [message(1, content_state='provider_encrypted', text='ciphertext-secret')])])
    assert 'ciphertext-secret' not in page.locator('#execweave-history-dialog').inner_text()
    page.locator('#execweave-history-list summary').click()
    assert 'plaintext was not exposed' in page.locator('.history-message-text').inner_text()
    find(page, 'ciphertext-secret')
    assert '0 matching' in page.locator('#execweave-history-status').inner_text()


def test_partial_and_routing_only_transcripts_are_not_called_complete(page):
    load(page, [entry('agent:a', [message(1)], messages_truncated=True, conversation_completeness='routing_only')])
    text = page.locator('#execweave-history-boundary').inner_text()
    assert 'not a complete transcript' in text
    assert "does not establish the recipient's own transcript" in text


def test_unknown_source_has_no_path_name_thread_or_root_fallback(page):
    load(page, [entry('agent:b', [message(1, text='private sibling answer')])], full=True)
    assert 'No exact-source conversation record' in page.locator('#execweave-history-status').inner_text()
    assert 'private sibling' not in page.locator('#execweave-history-dialog').inner_text()


def test_explicit_projection_member_ids_are_the_only_aliases(page):
    g = graph()
    g['nodes'][0]['attributes']['viewer_agent_member_ids'] = ['agent:old-a']
    load(page, [entry('agent:old-a', [message(1, text='explicit member')]),
                entry('agent:b', [message(1, text='private sibling answer')])], g=g)
    assert 'explicit member' in page.locator('#execweave-history-list').inner_text()
    assert 'private sibling' not in page.locator('#execweave-history-dialog').inner_text()


def test_cross_run_change_closes_dialog_and_discards_reading_state(page):
    records = load(page, full=True)
    find(page, 'record 83')
    page.evaluate("window.__execweaveCore.getGraph().session_id='run-two'")
    page.evaluate('(e)=>window.__execweaveAgentPanel.setEntries(e)', records)
    assert page.locator('#execweave-history-dialog').get_attribute('open') is None
    assert page.locator('#execweave-history-list').inner_text() == ''
    page.get_by_role('button', name='Browse observed history', exact=True).click()
    assert page.locator('#execweave-history-search').input_value() == ''
    assert 'Page 1/9' in page.locator('#execweave-history-status').inner_text()


def test_selecting_another_node_closes_pinned_history(page):
    load(page, full=True)
    page.evaluate('window.__execweaveAgentPanel.render(window.__execweaveStaticGraph.nodes[1])')
    assert page.locator('#execweave-history-dialog').get_attribute('open') is None
    page.get_by_role('button', name='Browse observed history', exact=True).click()
    assert 'private sibling answer' in page.locator('#execweave-history-list').inner_text()
    assert 'record 83' not in page.locator('#execweave-history-dialog').inner_text()


def test_literal_html_is_never_executed_or_fetched(page):
    requests = []
    page.on('request', lambda r: requests.append(r.url))
    malicious = '<img src="https://invalid.example/x" onerror="window.bad=true"><script>window.bad=true</script>'
    load(page, [entry('agent:a', [message(1, text=malicious)])], full=True)
    page.locator('#execweave-history-list summary').click()
    assert page.locator('.history-message-text').inner_text() == malicious
    assert page.locator('#execweave-history-list img').count() == 0
    assert page.evaluate('window.bad||false') is False
    assert not any('invalid.example' in r for r in requests)


def test_long_text_is_lazy_paged_without_losing_unicode_boundary(page):
    text = 'x' * 16383 + '\U0001f680' + 'y' * 17000 + 'TAIL'
    load(page, [entry('agent:a', [message(1, text=text)])])
    assert page.locator('.history-message-text').inner_text() == ''
    page.locator('#execweave-history-list summary').click()
    chunks = [page.locator('.history-message-text').inner_text()]
    while page.get_by_role('button', name='Next text', exact=True).is_enabled():
        page.get_by_role('button', name='Next text', exact=True).click()
        chunks.append(page.locator('.history-message-text').inner_text())
    assert ''.join(chunks) == text
    find(page, 'TAIL')
    assert '1 matching' in page.locator('#execweave-history-status').inner_text()


def test_empty_null_and_missing_text_are_distinct_from_encrypted_records(page):
    load(page, [entry('agent:a', [message(1, text=''), message(2, text=None), message(3, content_state='provider_encrypted')])])
    for summary in page.locator('#execweave-history-list summary').all():
        summary.click()
    text = page.locator('#execweave-history-list').inner_text()
    assert 'empty string' in text and 'No text supplied' in text and 'plaintext was not exposed' in text


def test_live_static_and_projected_shells_have_one_reader_and_valid_js(tmp_path):
    from execweave.viewer_projection import render_graph_html
    for index, html in enumerate([DASHBOARD_HTML, render_static_dashboard_html(graph()), render_graph_html(graph())]):
        assert html.count('function execweaveCreateHistoryBrowser') == 1
        assert html.count('window.__execweaveHistoryBrowser=historyBrowser') == 1
        path = tmp_path / f'shell-{index}.js'
        path.write_text('\n'.join(re.findall(r'<script[^>]*>(.*?)</script>', html, re.S)), encoding='utf-8')
        subprocess.run(['node', '--check', str(path)], check=True, capture_output=True)


def test_real_parser_publication_and_shipped_shell_keep_middle_record(page, tmp_path):
    from test_codex_preserved_history import rollout
    from execweave.conversation_preview_codex import conversation_preview
    from execweave.conversation_records import _merge_conversation_previews
    source = graph()['nodes'][0]
    preview = conversation_preview(rollout(tmp_path), content_kind='codex.conversation_transcript',
                                   provider='codex', source=source)
    records = [{'source_id': source['id'], 'provider': 'codex',
                'content_kind': 'codex.conversation_transcript', 'conversation_preview': preview}]
    _merge_conversation_previews(records)
    load(page, records, full=True)
    assert '210 loaded records' in page.locator('#execweave-history-status').inner_text()
    find(page, 'answer 83')
    page.locator('#execweave-history-list summary').click()
    assert page.locator('.history-message-text').inner_text() == 'answer 83'


def test_conflicting_native_execution_scopes_on_one_source_are_withheld(page):
    records = [entry('agent:a', [message(1, text='first execution secret')],
                     thread_id_source='provider_native', provider_native_id='execution-a'),
               entry('agent:a', [message(1, text='second execution secret')],
                     thread_id_source='provider_native', provider_native_id='execution-b')]
    load(page, records, full=True)
    assert page.locator('.execweave-history-message').count() == 0
    assert 'Conflicting native execution identities' in page.locator('#execweave-history-boundary').inner_text()
    assert 'execution secret' not in page.locator('#execweave-history-dialog').inner_text()


def test_repeated_source_records_in_same_native_scope_remain_available(page):
    records = [entry('agent:a', [message(i, text=f'observation {i}')],
                     thread_id_source='provider_native', provider_native_id='execution-a') for i in range(2)]
    load(page, records, full=True)
    assert page.locator('.execweave-history-message').count() == 2
    assert 'Conflicting native' not in page.locator('#execweave-history-boundary').inner_text()
