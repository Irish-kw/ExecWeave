"""Synthetic browser navigation contracts for graph-backed source references."""
from __future__ import annotations

import hashlib
import json
import os
import shutil

import pytest

from execweave.viewer_content_browser import inject_content_browser
from execweave.viewer_recorded_sources import inject_recorded_sources


def fixture_graph():
    digest = hashlib.sha256(b'hello').hexdigest()
    return {'session_id': 'run-one', 'nodes': [
        {'id': 'a', 'type': 'agent', 'name': 'same name'},
        {'id': 'b', 'type': 'agent', 'name': 'same name'},
        {'id': 'm', 'type': 'model', 'name': 'shared model'},
        {'id': 'call-a', 'type': 'tool_call', 'name': 'tool'},
        {'id': 'call-b', 'type': 'tool_call', 'name': 'tool'},
        {'id': 'ca', 'type': 'observed_content', 'attributes': {
            'path': f'content/sha256/{digest}.txt', 'sha256': digest,
            'size_bytes': 5, 'content_kind': 'test.tool_output'}},
        {'id': 'cb', 'type': 'observed_content', 'attributes': {
            'path': 'content/sha256/' + 'f' * 64 + '.txt', 'sha256': 'f' * 64,
            'content_kind': 'private-b-response'}},
    ], 'edges': [
        {'id': 'owned-a', 'source': 'a', 'target': 'call-a', 'relation': 'REQUESTED_TOOL_CALL'},
        {'id': 'output-a', 'source': 'call-a', 'target': 'ca', 'relation': 'HAS_TOOL_OUTPUT'},
        {'id': 'owned-b', 'source': 'b', 'target': 'call-b', 'relation': 'REQUESTED_TOOL_CALL'},
        {'id': 'output-b', 'source': 'call-b', 'target': 'cb', 'relation': 'HAS_TOOL_OUTPUT'},
        {'id': 'model-a', 'source': 'a', 'target': 'm', 'relation': 'USED_MODEL'},
        {'id': 'model-b', 'source': 'b', 'target': 'm', 'relation': 'USED_MODEL'},
    ]}


@pytest.fixture
def page():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        if os.environ.get('EXECWEAVE_E2E_REQUIRED'):
            pytest.fail('Playwright required')
        pytest.skip('Playwright not installed')
    with sync_playwright() as p:
        path = os.environ.get('EXECWEAVE_E2E_CHROMIUM') or shutil.which('chromium') or shutil.which('chromium-browser')
        try:
            browser = p.chromium.launch(**({'executable_path': path} if path else {}))
        except Exception as error:
            if os.environ.get('EXECWEAVE_E2E_REQUIRED'):
                pytest.fail(f'Chromium required: {error}')
            pytest.skip(f'Chromium unavailable: {error}')
        page = browser.new_page()
        problems = []
        page.on('pageerror', lambda error: problems.append(str(error)))
        yield page
        assert not problems
        browser.close()


def load(page, graph=None):
    graph = fixture_graph() if graph is None else graph
    payload = json.dumps(graph).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    html = '<html><body><div id="nodes"><button class="node selected" data-id="a">A</button><button class="node" data-id="b">B</button></div><div id="details"><p>Existing inspector</p></div>'
    html += '<script>window.__execweaveStaticMode=true;window.testGraph=' + payload + ';'
    html += 'window.__execweaveCore={getGraph:()=>window.testGraph,getDisplayGraph:()=>window.displayGraph||window.testGraph};'
    html += "document.getElementById('nodes').onclick=e=>{const n=e.target.closest('.node');if(n){document.querySelectorAll('.node').forEach(x=>x.classList.remove('selected'));n.classList.add('selected')}};"
    html += '</script></body></html>'
    page.set_content(inject_content_browser(html))


def test_injectors_are_idempotent_and_order_reader_before_sources():
    html = inject_content_browser('<html><body><div id="details"></div></body></html>')
    assert inject_content_browser(html) == html
    assert inject_recorded_sources(html) == html
    assert html.count('id="execweave-content-browser"') == 1
    assert html.count('id="execweave-recorded-sources-script"') == 1
    assert html.index('id="execweave-content-browser"') < html.index('id="execweave-recorded-sources-script"')


@pytest.mark.viewer_e2e
def test_exact_agent_call_opens_shared_reader_without_borrowing_other_content(page):
    graph = fixture_graph()
    load(page, graph)
    panel = page.locator('#execweave-recorded-sources')
    assert panel.locator('.execweave-source-card').count() == 1
    assert 'private-b-response' not in panel.inner_text()
    assert page.evaluate('window.testGraph') == graph
    panel.get_by_role('button', name='Read output', exact=True).click()
    assert page.locator('#execweave-content-dialog').get_attribute('data-state') == 'folder_required'
    assert 'call-a' in page.locator('#execweave-content-meta').inner_text()
    page.get_by_role('button', name='Close', exact=True).click()
    page.locator('.node[data-id="b"]').click()
    page.wait_for_function("document.getElementById('execweave-recorded-sources')?.dataset.sourceId==='b'")
    assert 'private-b-response' in panel.inner_text()
    assert 'call-a' not in panel.inner_text()


@pytest.mark.viewer_e2e
def test_no_name_or_shared_model_fallback(page):
    graph = fixture_graph()
    graph['edges'] = [e for e in graph['edges'] if e['id'] not in {'owned-a', 'output-a'}]
    load(page, graph)
    assert page.locator('#execweave-recorded-sources').count() == 0


@pytest.mark.viewer_e2e
def test_explicit_projection_alias_selects_only_declared_raw_members(page):
    load(page)
    page.evaluate("""()=>{
      window.displayGraph={nodes:[{id:'view-a',type:'agent',attributes:{viewer_agent_member_ids:['a']}}]};
      document.querySelector('.node.selected').dataset.id='view-a';
    }""")
    page.wait_for_function("document.getElementById('execweave-recorded-sources')?.dataset.sourceId==='view-a'")
    assert 'call-a' in page.locator('#execweave-recorded-sources').inner_text()
    assert 'call-b' not in page.locator('#execweave-recorded-sources').inner_text()


@pytest.mark.viewer_e2e
def test_equal_content_hashes_do_not_merge_distinct_calls(page):
    graph = fixture_graph()
    graph['nodes'].append({'id': 'call-a2', 'type': 'tool_call', 'name': 'tool'})
    graph['edges'] += [
        {'id': 'owned-a2', 'source': 'a', 'target': 'call-a2', 'relation': 'REQUESTED_TOOL_CALL'},
        {'id': 'output-a2', 'source': 'call-a2', 'target': 'ca', 'relation': 'HAS_TOOL_OUTPUT'},
    ]
    load(page, graph)
    assert page.locator('.execweave-source-card').count() == 2
    assert sorted(page.locator('.execweave-source-card').evaluate_all('(nodes)=>nodes.map(n=>n.dataset.sourceId)')) == ['call-a', 'call-a2']


@pytest.mark.viewer_e2e
def test_invalid_registered_path_has_visible_reader_error_not_a_file_read(page):
    graph = fixture_graph()
    graph['nodes'][5]['attributes']['path'] = '../outside.txt'
    load(page, graph)
    page.get_by_role('button', name='Read output', exact=True).click()
    assert page.locator('#execweave-content-dialog').get_attribute('data-state') == 'invalid_reference'
    assert page.locator('#execweave-content-text').inner_text() == ''


@pytest.mark.viewer_e2e
def test_source_labels_are_literal_text(page):
    graph = fixture_graph()
    graph['nodes'][5]['attributes']['content_kind'] = '<img src=x onerror="window.bad=true">'
    load(page, graph)
    assert '<img' in page.locator('#execweave-recorded-sources').inner_text()
    assert page.locator('#execweave-recorded-sources img').count() == 0
    assert page.evaluate('window.bad||false') is False


@pytest.mark.viewer_e2e
def test_long_source_list_loads_more_and_keeps_node_local_limit(page):
    graph = fixture_graph()
    for index in range(60):
        graph['edges'].append({'id': f'ref-{index}', 'source': 'a', 'target': 'ca',
                               'relation': 'OBSERVED_MESSAGE', 'first_sequence': index})
    load(page, graph)
    assert page.locator('.execweave-source-card').count() == 25
    page.get_by_role('button', name='Load more sources').click()
    assert page.locator('.execweave-source-card').count() == 50
    page.locator('.node[data-id="b"]').click()
    page.wait_for_function("document.querySelectorAll('.execweave-source-card').length===1")
    page.locator('.node[data-id="a"]').click()
    page.wait_for_function("document.querySelectorAll('.execweave-source-card').length===50")


@pytest.mark.viewer_e2e
def test_inspector_refresh_reinstalls_sources_once_without_replacing_existing_cards(page):
    load(page)
    page.evaluate("document.getElementById('details').innerHTML='<p id=existing>Existing content</p>'")
    page.wait_for_function("document.querySelectorAll('#execweave-recorded-sources').length===1")
    assert page.locator('#existing').inner_text() == 'Existing content'
    page.evaluate("window.__execweaveRecordedSources.refresh();window.__execweaveRecordedSources.refresh()")
    assert page.locator('#execweave-recorded-sources').count() == 1


@pytest.mark.viewer_e2e
def test_new_reference_arrival_updates_selected_agent(page):
    load(page)
    page.evaluate("""()=>{
      window.testGraph.edges.push({id:'new-ref',source:'a',target:'ca',relation:'OBSERVED_MESSAGE'});
      window.__execweaveDashboard.onPayload({});
    }""")
    page.wait_for_function("document.querySelectorAll('.execweave-source-card').length===2")


@pytest.mark.viewer_e2e
def test_duplicate_raw_identity_is_not_last_writer_wins(page):
    graph = fixture_graph()
    graph['nodes'].append(dict(graph['nodes'][5]))
    load(page, graph)
    assert page.locator('#execweave-recorded-sources').count() == 0


@pytest.mark.viewer_e2e
def test_task_reference_is_reachable_only_through_explicit_assignment(page):
    graph = fixture_graph()
    graph['nodes'].append({'id': 'task', 'type': 'task', 'name': 'assigned work'})
    graph['edges'] += [
        {'id': 'assigned', 'source': 'task', 'target': 'a', 'relation': 'ASSIGNED_TO'},
        {'id': 'task-text', 'source': 'task', 'target': 'ca', 'relation': 'HAS_TASK_CONTENT'},
    ]
    load(page, graph)
    assert page.locator('.execweave-source-card').count() == 2
    assert 'ASSIGNED_TO' in page.locator('#execweave-recorded-sources').inner_text()


def test_full_shell_installs_reader_and_sources_in_live_and_static():
    from execweave.dashboard_shell import DASHBOARD_HTML, render_static_dashboard_html

    for html in (DASHBOARD_HTML, render_static_dashboard_html(fixture_graph())):
        assert html.count('id="execweave-content-browser"') == 1
        assert html.count('id="execweave-recorded-sources-script"') == 1
        assert 'close:cancel,attach' in html
