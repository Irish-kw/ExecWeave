"""Prove real Dashboard runtime context cannot become unsupported root ownership."""
from __future__ import annotations

import json

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from execweave.viewer_projection import project_viewer_graph
from test_viewer_agent_isolation_e2e import _browser, _launch

pytestmark = pytest.mark.viewer_e2e


def fixture(case):
    nodes = [{'id': 'agent:Ollama', 'type': 'agent', 'name': 'Ollama', 'attributes': {'provider': 'ollama'}},
             {'id': 'runtime:foreign', 'type': 'model_runtime', 'name': 'ollama', 'attributes': {'provider': 'ollama', 'endpoint': 'http://127.0.0.1:11434'}},
             {'id': 'model:foreign', 'type': 'model', 'name': 'foreign-model', 'attributes': {'provider': 'ollama'}}]
    edges = [{'id': 'catalog', 'source': 'runtime:foreign', 'target': 'model:foreign', 'relation': 'LOADED_MODEL', 'causal': False}]
    if case != 'unattributed':
        edges.append({'id': 'context', 'source': 'agent:Ollama', 'target': 'runtime:foreign',
                      'relation': 'OBSERVED_MODEL_RUNTIME', 'causal': False})
    if case == 'ambiguous':
        nodes.append({'id': 'other-agent', 'type': 'agent', 'name': 'other agent', 'attributes': {}})
        edges.append({'id': 'second-owner', 'source': 'other-agent', 'target': 'runtime:foreign', 'relation': 'OBSERVED_MODEL_RUNTIME'})
    if case == 'conflicting-run':
        nodes[0]['attributes']['run_id'] = 'A'
        nodes[1]['attributes']['run_id'] = 'B'
    if case == 'wrong-relation':
        edges[-1]['relation'] = 'UNRELATED_HINT'
    if case == 'foreign-provider':
        nodes[0]['attributes']['provider'] = 'claude'
    if case == 'two-contexts':
        nodes.append({'id': 'runtime:second', 'type': 'model_runtime', 'name': 'ollama', 'attributes': {'provider': 'ollama', 'endpoint': 'http://127.0.0.1:22434'}})
        edges.extend([{'id': 'context2', 'source': 'agent:Ollama', 'target': 'runtime:second', 'relation': 'OBSERVED_MODEL_RUNTIME'},
                      {'id': 'catalog2', 'source': 'runtime:second', 'target': 'model:foreign', 'relation': 'LOADED_MODEL', 'causal': False}])
    return {'session_id': 'runtime-context-regression', 'nodes': nodes, 'edges': edges,
            'node_count': len(nodes), 'edge_count': len(edges)}


@pytest.mark.parametrize('case', ['unattributed', 'ambiguous', 'conflicting-run', 'wrong-relation', 'foreign-provider', 'explicit-context', 'two-contexts'])
@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_runtime_context_requires_actual_support_and_preserves_evidence(tmp_path, case, theme):
    graph = fixture(case)
    frozen = json.dumps(graph, sort_keys=True)
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={'width': 1600, 'height': 1100})
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.set_content(render_static_dashboard_html(project_viewer_graph(graph)))
            page.wait_for_selector('.node')
            if page.locator('html').get_attribute('data-theme') != theme:
                page.locator('#theme-toggle').click()
            raw_before = page.evaluate('JSON.stringify(window.__execweaveCore.getGraph())')
            page.locator('#arrange').click()
            display = page.evaluate('window.__execweaveCore.getDisplayGraph()')
            ids = {n['id'] for n in display['nodes']}
            catalog = [e for e in display['edges'] if e.get('relation') == 'LOADED_MODEL']
            assert catalog and page.locator('.node').count() >= 2  # Non-vacuous.
            if case in {'explicit-context', 'two-contexts'}:
                assert 'runtime:foreign' not in ids
                assert len(catalog) == (2 if case == 'two-contexts' else 1)
                for e in catalog:
                    assert e['source'] == 'agent:Ollama'
                    assert e['viewer_only'] is True and e['inferred'] is True and e['causal'] is False
                    assert len(e['viewer_supporting_edges']) == 2
                    assert e['viewer_original_source'].startswith('runtime:')
                if case == 'two-contexts':
                    assert {e['viewer_original_source'] for e in catalog} == {'runtime:foreign', 'runtime:second'}
                    assert {s['id'] for e in catalog for s in e['viewer_supporting_edges']} == {'context', 'context2', 'catalog', 'catalog2'}
            else:
                assert 'runtime:foreign' in ids
                assert all(e['source'] == 'runtime:foreign' for e in catalog)
                assert not any(e.get('viewer_runtime_context') for e in catalog)
            assert page.evaluate('JSON.stringify(window.__execweaveCore.getGraph())') == raw_before
            assert json.dumps(graph, sort_keys=True) == frozen
            page.locator('#svg').screenshot(path=str(tmp_path/f'{case}-{theme}.png'))
            (tmp_path/'display.json').write_text(json.dumps(display, indent=2), encoding='utf-8')
            assert not errors, errors
        finally:
            browser.close()
