"""Unfolded hundred-node browser coverage and genuine pointer-driven routing."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from execweave.viewer_dashboard_clean import FOLD_BUDGET_ENV
from layout_geometry_probe import READ_SVG, measure
from test_layout_pipeline_geometry_e2e import _open, _shape
from test_viewer_agent_isolation_e2e import _browser, _launch

pytestmark = pytest.mark.viewer_e2e


def large_unfolded_fixture() -> dict:
    nodes = [{'id': 'root', 'type': 'agent', 'name': '/root', 'attributes': {'agent_role': 'root'}}]
    edges = []
    for i in range(8):
        owner = f'a{i}'
        nodes.append({'id': owner, 'type': 'agent', 'name': f'/root/worker-{i}',
                      'attributes': {'agent_path': f'/root/worker-{i}'}})
        edges.append({'id': f'spawn{i}', 'source': 'root', 'target': owner, 'relation': 'SPAWNED_AGENT'})
        for j in range(12):
            target = f'f{i}-{j}'
            nodes.append({'id': target, 'type': 'file', 'name': f'report-{i}-{j}.txt', 'attributes': {}})
            edges.append({'id': f'w{i}-{j}', 'source': owner, 'target': target,
                          'relation': 'WROTE', 'first_sequence': len(edges)})
    for k in range(4):
        nodes.append({'id': f'm{k}', 'type': 'model', 'name': f'model-{k}', 'attributes': {}})
        for i in range(8):
            edges.append({'id': f'u{i}-{k}', 'source': f'a{i}', 'target': f'm{k}', 'relation': 'USES_MODEL'})
    return {'session_id': 'large-unfolded', 'nodes': nodes, 'edges': edges,
            'node_count': len(nodes), 'edge_count': len(edges)}


def test_large_unfolded_display_and_real_node_drag_ports(tmp_path, monkeypatch):
    """A raw large graph collapsed to 12 DOM nodes is not dense coverage."""
    import time
    from layout_geometry_probe import polyline

    monkeypatch.setenv(FOLD_BUDGET_ENV, '120')
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            started = time.monotonic()
            page = _open(browser, large_unfolded_fixture())
            elapsed = time.monotonic() - started
            initial = page.evaluate(READ_SVG)
            metrics = measure(initial)
            assert metrics['VISIBLE_NODE_COUNT'] == 109
            assert metrics['VISIBLE_EDGE_COUNT'] == 136
            assert metrics['NODE_OVERLAPS'] == metrics['EDGE_NODE_INTERSECTIONS'] == 0
            assert metrics['EDGE_CROSSINGS'] <= page.evaluate('window.__execweavePr70.topology().layoutQuality.pre.EDGE_CROSSINGS')
            page.locator('#fit').click()
            page.wait_for_timeout(350)
            before = page.evaluate(READ_SVG)
            camera = page.locator('#viewport').get_attribute('transform')
            node = page.locator('.node[data-id="m0"]')
            box = node.bounding_box()
            assert box and box['width'] > 0 and box['height'] > 0
            x, y = box['x'] + box['width']/2, box['y'] + box['height']/2
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(x + 12, y + 10, steps=8)
            page.mouse.up()
            after = page.evaluate(READ_SVG)
            old = {n['id']: n for n in before['nodes']}
            boxes = {n['id']: n for n in after['nodes']}
            assert boxes['m0']['x'] != old['m0']['x'] or boxes['m0']['y'] != old['m0']['y']
            assert page.locator('#viewport').get_attribute('transform') == camera
            # Verify all sibling/incident ports, not only the path dragged under
            # the mouse. An explicit user placement may overlap a box; Arrange
            # must restore the validated nonoverlapping deterministic layout.
            for edge in after['edges']:
                points = polyline(edge)
                for identity, point in ((edge['source'], points[0]), (edge['target'], points[-1])):
                    n = boxes[identity]
                    assert min(abs(point[0]-n['x']), abs(point[0]-n['x']-n['w'])) < 1e-4
                    assert n['y']-1e-4 <= point[1] <= n['y']+n['h']+1e-4
            page.locator('#arrange').click()
            restored = page.evaluate(READ_SVG)
            assert _shape(initial) == _shape(restored)
            assert measure(restored)['NODE_OVERLAPS'] == 0
            out = Path(os.environ.get('EXECWEAVE_VISUAL_ARTIFACT_DIR', str(tmp_path))) / 'large-unfolded-drag'
            out.mkdir(parents=True, exist_ok=True)
            (out / 'metrics.json').write_text(json.dumps({'initial': metrics, 'render_seconds': elapsed,
                'dom': initial, 'after_drag': after, 'restored': restored}, indent=2), encoding='utf-8')
            page.locator('#svg').screenshot(path=str(out / 'arranged.png'))
            assert not page._execweave_errors, page._execweave_errors
        finally:
            browser.close()
