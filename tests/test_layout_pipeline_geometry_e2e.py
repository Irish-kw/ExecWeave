"""Quantitative regression of the actual shared Chromium renderer (not a mock)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from execweave.viewer_projection import project_viewer_graph
from execweave.viewer_dashboard_clean import FOLD_BUDGET_ENV
from layout_acceptance_fixtures import CASES, fixture
from layout_geometry_probe import READ_SVG, measure
from test_viewer_agent_isolation_e2e import _browser, _launch
from test_dashboard_camera_scheduler_e2e import _CORE_SEAM, _CORE_TEST_SEAM

pytestmark = pytest.mark.viewer_e2e


def _open(browser, graph, theme='dark'):
    page = browser.new_page(viewport={'width': 1800, 'height': 1100})
    # These tests measure geometry, not transport/authentication. The unchanged
    # original browser suite separately tests real HTTP/file navigation in CI.
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda msg: errors.append(msg.text) if msg.type == 'error' else None)
    page._execweave_errors = errors
    html = render_static_dashboard_html(project_viewer_graph(graph))
    assert _CORE_SEAM in html
    # Expose, but never replace, the actual delta handler (same seam as the
    # historical camera tests). Geometry tests must execute the shipped callsite.
    page.set_content(html.replace(_CORE_SEAM, _CORE_TEST_SEAM, 1))
    page.wait_for_selector('.node')
    if page.locator('html').get_attribute('data-theme') != theme:
        page.locator('#theme-toggle').click()
    return page


def _shape(snapshot):
    return {'nodes': sorted(snapshot['nodes'], key=lambda n: n['id']),
            'edges': sorted([{k: e[k] for k in ('id', 'd', 'kind')} for e in snapshot['edges']], key=lambda e: e['id'])}


@pytest.mark.parametrize('case', CASES)
@pytest.mark.parametrize('theme', ['dark', 'light'])
def test_final_svg_geometry_matrix(tmp_path, monkeypatch, case, theme):
    if case == 'folded':
        monkeypatch.setenv(FOLD_BUDGET_ENV, '2')
    graph = fixture(case)
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = _open(browser, graph, theme)
            first = page.evaluate(READ_SVG)
            metrics = measure(first)
            quality = page.evaluate('window.__execweavePr70.topology().layoutQuality')
            actual = page.evaluate('window.__execweavePr70.metrics()')
            assert metrics['VISIBLE_NODE_COUNT'] >= (8 if case in ('8-agent', 'shared-model') else 1)
            assert metrics['NODE_OVERLAPS'] == 0, metrics['overlap_pairs']
            assert metrics['EDGE_NODE_INTERSECTIONS'] == 0, metrics['intersection_pairs']
            assert metrics['EDGE_CROSSINGS'] == actual['EDGE_CROSSINGS']
            assert actual['FINAL_ORDER_AUTHORITY_MISMATCHES'] == 0, actual
            assert actual['CROSSINGS_PER_EDGE'] >= 0
            assert 0 <= actual['CROSSING_SPAN_RATE'] <= 1
            assert actual['NODE_DENSITY'] > 0
            assert actual['ASPECT_ERROR'] >= 0
            if actual['VISIBLE_EDGE_COUNT']:
                assert actual['P95_EDGE_STRETCH'] >= 1
            if case in ('shared-model', 'shared-tool'):
                assert actual['HUB_PORT_INVERSION_RATE'] == 0, actual
            assert metrics['EDGE_CROSSINGS'] <= quality['pre']['EDGE_CROSSINGS']
            if case in ('shared-tool', 'mixed'):
                assert metrics['EDGE_CROSSINGS'] < quality['pre']['EDGE_CROSSINGS']
            assert all(e['kind'] != 'dagre-polyline' for e in first['edges'])

            # Arrange is allowed to perform a stronger deterministic geometry search.
            # It must never worsen the hard geometry gates or take over the camera.
            page.locator('#arrange').click()
            arranged = page.evaluate(READ_SVG)
            arranged_metrics = measure(arranged)
            arranged_actual = page.evaluate('window.__execweavePr70.metrics()')
            assert arranged_metrics['NODE_OVERLAPS'] == 0, arranged_metrics['overlap_pairs']
            assert arranged_metrics['EDGE_NODE_INTERSECTIONS'] == 0, arranged_metrics['intersection_pairs']
            assert arranged_actual['EDGE_CROSSINGS'] <= actual['EDGE_CROSSINGS']
            assert arranged_actual['FINAL_ORDER_AUTHORITY_MISMATCHES'] == 0, arranged_actual
            assert first['fit_scale'] == arranged['fit_scale'], 'Arrange took over camera'
            page.locator('#arrange').click()
            assert _shape(arranged) == _shape(page.evaluate(READ_SVG)), 'nondeterministic Arrange geometry'

            again = _open(browser, graph, theme)
            assert _shape(first) == _shape(again.evaluate(READ_SVG)), 'nondeterministic initial geometry'
            evidence = Path(os.environ.get('EXECWEAVE_VISUAL_ARTIFACT_DIR', str(tmp_path))) / f'geometry-{theme}-{case}'
            evidence.mkdir(parents=True, exist_ok=True)
            page.locator('#svg').screenshot(path=str(evidence/'final.png'))
            (evidence/'metrics.json').write_text(json.dumps({'metrics': metrics, 'pipeline': quality, 'svg': first}, indent=2), encoding='utf-8')
            for checked in browser.contexts:
                for observed in checked.pages:
                    assert not observed._execweave_errors, observed._execweave_errors
        finally:
            browser.close()


def test_live_gate_executes_at_real_delta_callsite_and_preserves_manual_camera(tmp_path):
    graph = fixture('mixed')
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = _open(browser, graph)
            page.locator('#zoom-in').click()
            page.wait_for_timeout(250)
            page.evaluate("window.__execweaveCore.selectNode('agent:/root/a0')")
            camera = page.locator('#viewport').get_attribute('transform')
            # Create a reproducible old ordering with more crossings. Mutating the
            # placement exercises the same state as node dragging, not a substitute
            # route or a fake metric. The update itself uses the shipped delta API.
            page.evaluate("""() => {
                const p=window.__execweaveCore.getPositions();
                const a=p.get('file:f0'),b=p.get('file:f4'),y=a.y;a.y=b.y;b.y=y;
                window.__execweavePr70.paint();
            }""")
            before = measure(page.evaluate(READ_SVG))
            changed = next(n for n in graph['nodes'] if n['id'] == 'file:f0')
            page.evaluate("delta=>window.__execweaveCore.applyDelta(delta)", {
                'nodes_added': [], 'nodes_updated': [{**changed, 'event_count': 2}],
                'edges_added': [], 'edges_updated': [], 'event_count': 50,
            })
            after = measure(page.evaluate(READ_SVG))
            decision = page.evaluate('window.__execweavePr70.diagnostics().live')
            assert decision and decision['restored'] is False, decision
            assert decision['newCrossings'] < decision['priorCrossings']
            assert after['EDGE_CROSSINGS'] < before['EDGE_CROSSINGS']
            assert after['NODE_OVERLAPS'] == 0
            assert page.evaluate('window.__execweavePr70.metrics().FINAL_ORDER_AUTHORITY_MISMATCHES') == 0
            assert page.locator('#viewport').get_attribute('transform') == camera
            assert page.locator('.node.selected').get_attribute('data-id') == 'agent:/root/a0'
            assert page.locator('.node.context-dim').count() > 0
            for checked in browser.contexts:
                for observed in checked.pages:
                    assert not observed._execweave_errors, observed._execweave_errors
        finally:
            browser.close()


def test_live_gate_retains_equal_quality_y_and_retargets_ports(tmp_path):
    graph = fixture('3-agent')
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = _open(browser, graph)
            page.evaluate("""()=>{for(const p of window.__execweaveCore.getPositions().values())p.y+=123;window.__execweavePr70.paint()}""")
            before = page.evaluate(READ_SVG)
            page.evaluate("delta=>window.__execweaveCore.applyDelta(delta)", {
                'nodes_added': [], 'nodes_updated': [{**graph['nodes'][0], 'event_count': 2}],
                'edges_added': [], 'edges_updated': [], 'event_count': 50,
            })
            after = page.evaluate(READ_SVG)
            decision = page.evaluate('window.__execweavePr70.diagnostics().live')
            assert decision['restored'] is True
            assert _shape(before) == _shape(after)
            assert page.evaluate('window.__execweavePr70.metrics().FINAL_ORDER_AUTHORITY_MISMATCHES') == 0
            boxes = {n['id']: n for n in after['nodes']}
            from layout_geometry_probe import polyline
            for edge in after['edges']:
                points = polyline(edge)
                for node_id, point in [(edge['source'], points[0]), (edge['target'], points[-1])]:
                    box = boxes[node_id]
                    assert min(abs(point[0]-box['x']), abs(point[0]-box['x']-box['w'])) < 1e-4
                    assert box['y'] <= point[1] <= box['y']+box['h']
            for checked in browser.contexts:
                for observed in checked.pages:
                    assert not observed._execweave_errors, observed._execweave_errors
        finally:
            browser.close()


def test_new_wide_runtime_dimensions_used_before_dagre_and_arrange(tmp_path):
    graph = fixture('3-agent')
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = _open(browser, graph)
            wide = {'id': 'new-runtime', 'type': 'process', 'name': 'wide_runtime_command_'*15, 'attributes': {}}
            edge = {'id': 'new-owner', 'source': 'new-runtime', 'target': 'root', 'relation': 'STARTED_AGENT', 'attributes': {}}
            page.evaluate("delta=>window.__execweaveCore.applyDelta(delta)", {
                'nodes_added': [wide], 'nodes_updated': [], 'edges_added': [edge], 'edges_updated': [],
                'event_count': 50,
            })
            snapshot = page.evaluate(READ_SVG)
            by_id = {n['id']: n for n in snapshot['nodes']}
            assert by_id['new-runtime']['w'] == 320
            assert by_id['new-runtime']['h'] > 50
            assert by_id['new-runtime']['x']+by_id['new-runtime']['w'] <= by_id['root']['x']
            assert measure(snapshot)['NODE_OVERLAPS'] == 0
            page.locator('#arrange').click()
            graph['nodes'].append(wide)
            graph['edges'].append(edge)
            again = _open(browser, graph)
            assert page.evaluate('window.__execweavePr70.metrics().FINAL_ORDER_AUTHORITY_MISMATCHES') == 0
            assert measure(page.evaluate(READ_SVG))['NODE_OVERLAPS'] == 0
            assert measure(again.evaluate(READ_SVG))['NODE_OVERLAPS'] == 0
            for checked in browser.contexts:
                for observed in checked.pages:
                    assert not observed._execweave_errors, observed._execweave_errors
        finally:
            browser.close()