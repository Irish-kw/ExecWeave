"""Shipped-shell interactions with synthetic evidence, not provider acceptance."""
from __future__ import annotations

import copy
import json

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from test_investigation_workspace import browser_page, scenario
from execweave.investigation_index import build_investigation_index
from test_runtime_evidence_browser import graph

__all__ = ["browser_page"]
pytestmark = pytest.mark.viewer_e2e


def show(page, data=None, index=None):
    data = graph() if data is None else data
    page.set_content(render_static_dashboard_html(data, investigation_index=index))
    return data


def visible(page):
    return page.evaluate("window.__execweaveCore.getDisplayGraph().nodes.map(n=>n.id)")


def health(page, value):
    return page.evaluate("x=>window.__execweaveContentHealth.summarize(x)", value)


def projection(page, value):
    return page.evaluate("g=>window.__execweaveStructureShare.project(g)", value)


def test_workflow_default_and_all_evidence_keep_raw_unchanged(browser_page):
    data = show(browser_page)
    assert browser_page.evaluate("window.__execweaveWorkflow.status().mode") == "all"
    assert {"a", "b", "pa", "pb"} <= set(visible(browser_page))
    browser_page.get_by_role("combobox", name="Graph view", exact=True).select_option("workflow")
    assert browser_page.evaluate("window.__execweaveWorkflow.status().mode") == "workflow"
    assert {"a", "b"} <= set(visible(browser_page))
    assert "pa" not in visible(browser_page)
    assert "hidden, not deleted" in browser_page.locator("#execweave-workflow-summary").inner_text()
    browser_page.get_by_role("combobox", name="Graph view", exact=True).select_option("all")
    assert {"a", "b", "pa", "pb"} <= set(visible(browser_page))
    assert browser_page.evaluate("window.__execweaveCore.getGraph()") == data


def test_selected_runtime_identity_is_revealed_without_names(browser_page):
    show(browser_page)
    browser_page.get_by_role("combobox", name="Graph view", exact=True).select_option("workflow")
    browser_page.evaluate("window.__execweaveCore.selectNode('pa')")
    assert "pa" in visible(browser_page)
    assert browser_page.evaluate("window.__execweaveWorkflow.status().mode") == "all"
    assert browser_page.locator('#nodes .node.selected').get_attribute('data-id') == 'pa'
    browser_page.get_by_role("combobox", name="Graph view", exact=True).select_option("workflow")
    assert "pa" in visible(browser_page)  # The current selection never disappears.
    assert "pb" not in visible(browser_page)


def test_missing_identity_cannot_reveal_a_similarly_named_node(browser_page):
    show(browser_page)
    browser_page.get_by_role("combobox", name="Graph view", exact=True).select_option("workflow")
    assert browser_page.evaluate("window.__execweaveWorkflow.reveal('Same name')") is False
    assert browser_page.evaluate("window.__execweaveWorkflow.status().mode") == "workflow"


def test_runtime_only_and_single_agent_keep_full_view(browser_page):
    data = graph()
    data['nodes'] = [n for n in data['nodes'] if n['id'] != 'b']
    data['edges'] = [e for e in data['edges'] if e['source'] != 'b']
    show(browser_page, data)
    assert browser_page.evaluate("window.__execweaveWorkflow.status().mode") == "all"
    assert 'pa' in visible(browser_page)


def test_failures_and_recorded_snapshot_nodes_are_not_hidden(browser_page):
    data = graph()
    data['nodes'][5]['attributes']['status'] = 'failed'
    data['edges'].append({'id': 'snapshot', 'source': 'f', 'target': 'content', 'relation': 'OBSERVED_FILE_CONTENT_BEFORE_READ'})
    show(browser_page, data)
    browser_page.get_by_role('combobox', name='Graph view', exact=True).select_option('workflow')
    assert 'pa' in visible(browser_page)
    # Inspect the filter directly so the previous file-display policy is separate.
    result = browser_page.evaluate("g=>window.__execweaveWorkflow.project(g,g,'workflow',null,null)", data)
    assert {'a', 'b', 'pa', 'f'} <= {n['id'] for n in result['display']['nodes']}


def test_workflow_never_contracts_paths_or_invents_edges(browser_page):
    data = show(browser_page)
    result = browser_page.evaluate("g=>window.__execweaveWorkflow.project(g,g,'workflow',null,null)", data)
    assert result['display']['edges'] == []
    assert result['display']['nodes'] == data['nodes'][:2] + [data['nodes'][4]]


def test_ambiguous_workflow_nodes_do_not_silently_disappear(browser_page):
    show(browser_page)
    data = graph()
    data['nodes'].append({**data['nodes'][0], 'name': 'conflict'})
    result = browser_page.evaluate("g=>window.__execweaveWorkflow.project(g,g,'workflow',null,null)", data)
    assert result['ambiguous'] and result['display'] == data


def test_protected_snapshot_cannot_be_redrawn_by_switching_views(browser_page):
    data = {'session_id': 'compact', 'live_payload_compact': True,
            'node_count': 100000, 'edge_count': 200000, 'nodes': [], 'edges': []}
    show(browser_page, data)
    assert browser_page.locator('#protective').is_visible()
    assert browser_page.get_by_role('combobox', name='Graph view', exact=True).is_disabled()
    assert browser_page.evaluate("window.__execweaveWorkflow.setMode('all')") is False
    assert browser_page.locator('#protective').is_visible()
    assert browser_page.locator('#nodes .node').count() == 0
    browser_page.get_by_role('button', name='Share structure', exact=True).click()
    browser_page.get_by_role('button', name='Prepare structural preview', exact=True).click()
    assert 'protection is active' in browser_page.locator('#execweave-share-status').inner_text()


def test_legacy_graph_and_repeated_switches_do_not_duplicate_nodes(browser_page):
    data = show(browser_page)
    for mode in ['all', 'workflow', 'all', 'workflow']:
        browser_page.get_by_role('combobox', name='Graph view', exact=True).select_option(mode)
        ids = visible(browser_page)
        assert len(ids) == len(set(ids))
    assert browser_page.evaluate('window.__execweaveCore.getGraph()') == data
    assert browser_page.locator('#execweave-workflow-controls').count() == 1


def test_content_health_denominators_are_record_phases_not_recall(tmp_path, browser_page):
    data, *_ = scenario(tmp_path)
    index = build_investigation_index(data, tmp_path)
    show(browser_page, data, index)
    report = health(browser_page, index)
    groups = {g['id']: g for g in report['groups']}
    assert report['denominator_version'] == 'indexed-record-phase-v1'
    assert groups['tool-request']['total'] == groups['tool-response']['total'] == 1
    assert groups['tool-request']['counts']['registered'] == 1
    assert groups['message-sent']['total'] == groups['message-received']['total'] == 2
    assert groups['message-received']['counts']['phase_unobserved'] == 1
    browser_page.get_by_role('button', name='Content health', exact=True).click()
    assert 'not total provider activity' in browser_page.locator('#execweave-health-dialog').inner_text()
    assert 'bytes not' not in browser_page.locator('#execweave-health-summary').inner_text()  # Table is metadata-only.
    assert browser_page.locator('#execweave-health-table').is_visible()


def test_explicit_omission_is_not_unknown_capture_failure(tmp_path, browser_page):
    data, *_ = scenario(tmp_path, mode='metadata_only')
    index = build_investigation_index(data, tmp_path)
    show(browser_page, data, index)
    report = health(browser_page, index)
    group = next(g for g in report['groups'] if g['id'] == 'tool-response')
    assert group['counts']['configured_omission'] == 1
    assert group['counts']['not_recorded'] == 0


@pytest.mark.parametrize('state,expected', [('invalid_reference', 'invalid'), ('not_in_graph_inventory', 'outside_inventory'), ('not_recorded', 'not_recorded')])
def test_content_reference_gaps_remain_distinct(tmp_path, browser_page, state, expected):
    data, *_ = scenario(tmp_path)
    index = build_investigation_index(data, tmp_path)
    for row in index['calls']:
        for ref in row['references']:
            if ref['phase'] == 'response':
                ref['state'] = state
                ref['reference'] = None
    show(browser_page, data, index)
    assert next(g for g in health(browser_page, index)['groups'] if g['id'] == 'tool-response')['counts'][expected] == 1


def test_invalid_registered_reference_never_counts_as_registered(tmp_path, browser_page):
    data, *_ = scenario(tmp_path)
    index = build_investigation_index(data, tmp_path)
    index['calls'][0]['references'][0]['reference']['path'] = '../secret'
    show(browser_page, data, index)
    g = next(g for g in health(browser_page, index)['groups'] if g['id'] == 'tool-request')
    assert g['counts']['invalid'] == 1 and g['counts']['registered'] == 0


def test_duplicate_index_id_is_withheld_instead_of_first_writer_wins(tmp_path, browser_page):
    data, *_ = scenario(tmp_path)
    index = build_investigation_index(data, tmp_path)
    index['calls'].append(copy.deepcopy(index['calls'][0]))
    show(browser_page, data, index)
    report = health(browser_page, index)
    assert report['partial'] and report['invalid_rows']
    assert not any(r['tab'] == 'calls' for r in report['rows'])


def test_health_rows_open_exact_record_and_escape_preserves_selection(tmp_path, browser_page):
    data, *_ = scenario(tmp_path)
    index = build_investigation_index(data, tmp_path)
    show(browser_page, data, index)
    selected = next(n['id'] for n in data['nodes'] if n['type'] == 'agent')
    browser_page.evaluate('id=>window.__execweaveCore.selectNode(id)', selected)
    browser_page.get_by_role('button', name='Content health', exact=True).click()
    browser_page.get_by_label('Content health category').select_option('tool-request')
    browser_page.get_by_role('button', name='Inspect indexed record', exact=True).click()
    assert browser_page.locator('.investigation-row').count() == 1
    assert browser_page.locator('.investigation-row').get_attribute('data-record-id') == index['calls'][0]['key']
    browser_page.keyboard.press('Escape')
    assert browser_page.locator('#nodes .node.selected').get_attribute('data-id') == selected


def test_health_snapshot_is_pinned_until_refresh(tmp_path, browser_page):
    data, *_ = scenario(tmp_path)
    index = build_investigation_index(data, tmp_path)
    show(browser_page, data, index)
    browser_page.get_by_role('button', name='Content health', exact=True).click()
    before = browser_page.locator('#execweave-health-table').inner_text()
    changed = {**index, 'calls': []}
    browser_page.evaluate('x=>window.__execweaveInvestigation.setIndex(x)', changed)
    assert browser_page.locator('#execweave-health-table').inner_text() == before
    browser_page.get_by_role('button', name='Refresh content health', exact=True).click()
    assert browser_page.locator('#execweave-health-table').inner_text() != before


def test_structure_export_omits_all_arbitrary_input_strings(browser_page):
    data = graph()
    secret = 'PRIVATE__日本語__<script>SECRET</script>'
    data['session_id'] = secret
    data['source_path'] = secret
    for n in data['nodes']:
        n['name'] = secret
        n['first_seen'] = secret
        n.setdefault('attributes', {})['token'] = secret
    data['edges'][0]['relation'] = secret
    show(browser_page, data)
    result = projection(browser_page, data)
    value = json.dumps(result, ensure_ascii=False)
    assert secret not in value and '/recorded/' not in value and 'example.invalid' not in value
    assert 'shared-tool' not in value and 'a-call' not in value
    assert result['original_ids_included'] is False and result['content_included'] is False
    assert result['edges'][0]['relation'] == 'other recorded relationship'
    assert browser_page.evaluate('window.__execweaveCore.getGraph()') == data


def test_structure_html_is_static_and_escaped(browser_page):
    show(browser_page)
    data = projection(browser_page, graph())
    data['nodes'][0]['type'] = '<img src=x onerror=evil()>'
    result = browser_page.evaluate('x=>window.__execweaveStructureShare.renderDocument(x)', data)
    assert '<script' not in result and '<img' not in result
    assert '&lt;img' in result and 'Content-Security-Policy' in result
    assert 'https://' not in result


def test_structure_does_not_promote_correlation_or_view_only_edges(browser_page):
    data = graph()
    data['edges'][0].update(causal=True, inferred=True)
    data['edges'][1].update(causal=True, viewer_only=True)
    data['edges'][2].update(causal=True, inferred='false')
    show(browser_page, data)
    result = projection(browser_page, data)
    assert [e['evidence'] for e in result['edges'][:3]] == ['inferred correlation', 'presentation only', 'causality not established']


def test_structure_conflicting_id_is_not_reassigned(browser_page):
    data = graph()
    data['nodes'].append({**data['nodes'][0], 'name': 'other'})
    show(browser_page)
    result = projection(browser_page, data)
    assert result['inventory_partial'] and result['omitted_nodes'] == 2 and result['ambiguous_node_ids'] == 1
    assert len(result['nodes']) == len(data['nodes']) - 2
    assert all(e['source'] in {n['id'] for n in result['nodes']} for e in result['edges'])


def test_structure_requires_explicit_preparation_and_confirmation(browser_page):
    show(browser_page)
    browser_page.get_by_role('button', name='Share structure', exact=True).click()
    for name in ['Save structural JSON', 'Save structural HTML', 'Save derived checksums']:
        assert browser_page.get_by_role('button', name=name, exact=True).is_disabled()
    assert 'Nothing is exported' in browser_page.locator('#execweave-share-status').inner_text()
    browser_page.get_by_label('I reviewed the derived structure', exact=False).check()
    assert browser_page.get_by_role('button', name='Save structural JSON', exact=True).is_disabled()


def test_structure_without_native_crypto_refuses_export(browser_page):
    show(browser_page)
    browser_page.evaluate("Object.defineProperty(globalThis,'crypto',{configurable:true,value:{}})")
    browser_page.get_by_role('button', name='Share structure', exact=True).click()
    browser_page.get_by_role('button', name='Prepare structural preview', exact=True).click()
    assert 'unavailable' in browser_page.locator('#execweave-share-status').inner_text()
    assert browser_page.get_by_role('button', name='Save structural JSON', exact=True).is_disabled()


def test_structure_cancel_during_digest_can_reopen_and_retry(browser_page):
    show(browser_page)
    # Deliberately deferred digest double: tests UI race only, not SHA correctness.
    browser_page.evaluate("""()=>{window.resolveDigest=null;Object.defineProperty(globalThis,'crypto',{configurable:true,value:{subtle:{digest:()=>new Promise(r=>window.resolveDigest=r)}}})}""")
    browser_page.get_by_role('button', name='Share structure', exact=True).click()
    browser_page.get_by_role('button', name='Prepare structural preview', exact=True).click()
    browser_page.get_by_role('button', name='Close structural sharing', exact=True).click()
    browser_page.get_by_role('button', name='Share structure', exact=True).click()
    assert browser_page.get_by_role('button', name='Prepare structural preview', exact=True).is_enabled()
    assert browser_page.get_by_role('button', name='Save structural JSON', exact=True).is_disabled()


def test_changed_run_clears_health_and_share_dialogs(browser_page):
    show(browser_page)
    browser_page.get_by_role('button', name='Share structure', exact=True).click()
    browser_page.evaluate("()=>{window.__execweaveCore.getGraph().session_id='another';window.__execweaveDashboard.onPayload({})}")
    assert not browser_page.locator('#execweave-share-dialog').is_visible()


def test_structural_export_limit_is_not_silent_truncation(browser_page):
    show(browser_page)
    result = browser_page.evaluate("""()=>{try{window.__execweaveStructureShare.project({nodes:Array.from({length:10001},(_,i)=>({id:'n'+i})),edges:[]});return ''}catch(e){return e.message}}""")
    assert 'safety limit' in result


def test_native_structure_downloads_match_derived_checksums(tmp_path, browser_page):
    """Real localhost origin, native crypto and downloads, without request mocks."""
    import hashlib
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    data = graph()
    data['nodes'][0]['attributes']['secret'] = 'NOT_FOR_EXPORT_9bdde'
    document = render_static_dashboard_html(data).encode('utf-8')

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(document)))
            self.end_headers()
            self.wfile.write(document)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        page = browser_page
        page.goto(f'http://127.0.0.1:{server.server_address[1]}/viewer.html')
        page.get_by_role('button', name='Share structure', exact=True).click()
        page.get_by_role('button', name='Prepare structural preview', exact=True).click()
        page.wait_for_function("document.querySelector('#execweave-share-status').textContent.startsWith('Prepared ')")
        page.get_by_label('I reviewed the derived structure', exact=False).check()
        for action in ['Save structural JSON', 'Save structural HTML', 'Save derived checksums']:
            with page.expect_download() as info:
                page.get_by_role('button', name=action, exact=True).click()
            download = info.value
            download.save_as(tmp_path / download.suggested_filename)
        checksums = (tmp_path / 'execweave-structure.sha256').read_text()
        for line in checksums.splitlines():
            digest, filename = line.split('  ', 1)
            assert filename in {'execweave-structure.json', 'execweave-structure.html'}
            value = (tmp_path / filename).read_bytes()
            assert hashlib.sha256(value).hexdigest() == digest
            assert b'NOT_FOR_EXPORT_9bdde' not in value
        assert page.evaluate('window.__execweaveCore.getGraph()') == data
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


@pytest.mark.parametrize("width,height", [(1600, 1000), (1024, 768), (390, 844)])
def test_workflow_toolbar_does_not_consume_the_canvas(browser_page, width, height):
    browser_page.set_viewport_size({"width": width, "height": height})
    show(browser_page)
    boxes = browser_page.evaluate("""()=>{
        const panel=document.getElementById('graph-panel').getBoundingClientRect();
        const bar=document.getElementById('execweave-workflow-controls').getBoundingClientRect();
        const canvas=document.getElementById('wrap').getBoundingClientRect();
        return {panel:panel.height, toolbar:bar.height, canvas:canvas.height,
            canvasTop:canvas.top, toolbarBottom:bar.bottom};
    }""")
    assert boxes['toolbar'] < 150
    assert boxes['canvas'] >= boxes['panel'] - boxes['toolbar'] - 60
    assert boxes['canvas'] > 200
    assert abs(boxes['canvasTop'] - boxes['toolbarBottom']) <= 2


@pytest.mark.parametrize('flag', ['false', 1, [], {}])
def test_malformed_causal_flag_cannot_become_a_causal_export(browser_page, flag):
    data = graph()
    data['edges'][0]['causal'] = True
    data['edges'][0]['attributes'] = {'causal': flag}
    show(browser_page)
    result = projection(browser_page, data)
    assert result['edges'][0]['evidence'] == 'causality not established'


def test_cancelled_health_refresh_cannot_replace_a_reopened_snapshot(tmp_path, browser_page):
    data, *_ = scenario(tmp_path)
    index = build_investigation_index(data, tmp_path)
    show(browser_page, data, index)
    # Deferred provider-neutral request tests the reader race, not transport.
    browser_page.evaluate("""()=>{
        window.__execweaveStaticMode=false;
        window.__execweaveDashboard.agentPanel.refresh=()=>new Promise(resolve=>window.finishHealth=resolve);
    }""")
    browser_page.get_by_role('button', name='Content health', exact=True).click()
    browser_page.get_by_role('button', name='Refresh content health', exact=True).click()
    browser_page.get_by_role('button', name='Close content health', exact=True).click()
    browser_page.get_by_role('button', name='Content health', exact=True).click()
    before = browser_page.locator('#execweave-health-table').inner_text()
    browser_page.evaluate('x=>window.__execweaveInvestigation.setIndex(x)', {**index, 'calls': []})
    browser_page.evaluate('window.finishHealth()')
    assert browser_page.locator('#execweave-health-table').inner_text() == before
    assert browser_page.get_by_role('button', name='Refresh content health', exact=True).is_enabled()


def test_cancelled_investigation_refresh_does_not_replace_reopened_records(tmp_path, browser_page):
    data, *_ = scenario(tmp_path)
    index = build_investigation_index(data, tmp_path)
    show(browser_page, data, index)
    browser_page.evaluate('x=>window.__execweaveInvestigation.setIndex(x)', index)
    browser_page.evaluate("""()=>{
        window.__execweaveStaticMode=false;
        window.__execweaveDashboard.agentPanel.refresh=()=>new Promise(resolve=>window.finishIndex=resolve);
    }""")
    browser_page.get_by_role('button', name='Explore run', exact=True).click()
    browser_page.get_by_role('button', name='Refresh index', exact=True).click()
    browser_page.get_by_role('button', name='Close exploration', exact=True).click()
    browser_page.get_by_role('button', name='Explore run', exact=True).click()
    before = browser_page.locator('#execweave-investigation-rows').inner_text()
    browser_page.evaluate('x=>window.__execweaveInvestigation.setIndex(x)', {**index, 'agents': []})
    browser_page.evaluate('window.finishIndex()')
    assert browser_page.locator('#execweave-investigation-rows').inner_text() == before
    assert browser_page.get_by_role('button', name='Refresh index', exact=True).is_enabled()


@pytest.mark.parametrize('case', ['3-agent', '5-agent', '8-agent', 'shared-model'])
def test_workflow_keeps_retained_rails_or_accepts_strict_improvement(browser_page, case):
    from layout_acceptance_fixtures import fixture
    from layout_geometry_probe import READ_SVG, measure
    from test_dashboard_camera_scheduler_e2e import _CORE_SEAM, _CORE_TEST_SEAM
    from test_layout_pipeline_geometry_e2e import _shape
    from execweave.viewer_projection import project_viewer_graph

    data = fixture(case)
    html = render_static_dashboard_html(project_viewer_graph(data))
    assert _CORE_SEAM in html
    # Expose the real delta handler, as the unchanged geometry assertions do.
    browser_page.set_content(html.replace(_CORE_SEAM, _CORE_TEST_SEAM, 1))
    browser_page.get_by_role('combobox', name='Graph view', exact=True).select_option('workflow')
    assert browser_page.evaluate("window.__execweaveWorkflow.status().mode") == 'workflow'
    browser_page.evaluate("()=>{for(const p of window.__execweaveCore.getPositions().values())p.y+=123;window.__execweavePr70.paint()}")
    before = browser_page.evaluate(READ_SVG)
    browser_page.evaluate('delta=>window.__execweaveCore.applyDelta(delta)', {
        'nodes_added': [], 'nodes_updated': [{**data['nodes'][0], 'event_count': 2}],
        'edges_added': [], 'edges_updated': [], 'event_count': 50,
    })
    after = browser_page.evaluate(READ_SVG)
    decision = browser_page.evaluate('window.__execweavePr70.diagnostics().live')
    if decision['restored']:
        assert _shape(before) == _shape(after)
    else:
        # The five-agent fixture is not equal quality: the solver removes a
        # crossing. Keeping a worse layout is not the pinned-geometry contract.
        assert decision['newCrossings'] < decision['priorCrossings']
    if case == '3-agent':
        assert decision['restored'] is True  # Original bundle-rail drift reproducer.
    assert measure(after)['NODE_OVERLAPS'] == 0
    assert measure(after)['EDGE_NODE_INTERSECTIONS'] == 0


def test_unresolved_task_evidence_is_retained_in_workflow(browser_page):
    data = graph()
    data['nodes'].append({'id': 'task-unresolved', 'type': 'subtask', 'name': 'Unresolved handoff'})
    show(browser_page, data)
    browser_page.get_by_role('combobox', name='Graph view', exact=True).select_option('workflow')
    assert 'task-unresolved' in visible(browser_page)


def test_returning_to_default_restores_the_existing_display_inventory(browser_page):
    data = show(browser_page)
    original = browser_page.evaluate("window.__execweaveCore.getDisplayGraph()")
    browser_page.get_by_role("combobox", name="Graph view", exact=True).select_option("workflow")
    assert "pa" not in visible(browser_page)
    browser_page.get_by_role("combobox", name="Graph view", exact=True).select_option("auto")
    assert browser_page.evaluate("window.__execweaveWorkflow.status().mode") == "all"
    assert browser_page.evaluate("window.__execweaveCore.getDisplayGraph()") == original
    assert browser_page.evaluate("window.__execweaveCore.getGraph()") == data


def test_automatic_mode_preserves_every_published_node_and_edge(browser_page):
    show(browser_page)
    data = graph()
    # Automatic presentation must not filter an ambiguous call, an unlinked
    # process, or evidence added after additional agents become visible.
    data["nodes"].append({"id": "third-agent", "type": "agent", "name": "Same name"})
    result = browser_page.evaluate(
        "g=>window.__execweaveWorkflow.project(g,g,'auto',null,null)", data
    )
    assert result["mode"] == "all"
    assert result["hidden"] == 0
    assert result["display"] == data
