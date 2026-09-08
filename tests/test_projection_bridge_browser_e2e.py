"""Real Chromium renderer/filter contracts, independent of HTTP-origin acceptance."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from execweave.dashboard_shell import render_static_dashboard_html
from test_projection_bridge_evidence import HIDDEN, edge, node
from test_viewer_agent_isolation_e2e import _browser, _launch

pytestmark = pytest.mark.viewer_e2e


@pytest.mark.parametrize('owned', [False, True])
def test_real_dashboard_retains_native_files_and_respects_filters(tmp_path, owned):
    nodes = [node('ctx', 'provider_session' if owned else 'session'), node('write', 'file'),
             node('read', 'file'), node('raw-orphan', 'file')]
    edges = [edge('write-edge', 'ctx', 'write', 'OBSERVED_FILE_CHANGE', event_types=['filesystem.modified']),
             edge('read-edge', 'ctx', 'read', 'OBSERVED_FILE', event_types=['filesystem.opened'])]
    if owned:
        nodes.append(node('root', 'agent', agent_role='root'))
        edges.append(edge('owner', 'root', 'ctx', 'OBSERVED_PROVIDER_SESSION'))
    raw = {'session_id': 'projection-browser', 'nodes': nodes, 'edges': edges}
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        try:
            page.set_content(render_static_dashboard_html(raw))
            page.wait_for_selector('.node')
            original = page.evaluate('JSON.stringify(window.__execweaveCore.getGraph())')
            results = []
            for mode, files in [('changed', {'write', 'raw-orphan'}), ('all', {'write', 'read', 'raw-orphan'}), ('hide', set()), ('all', {'write', 'read', 'raw-orphan'})]:
                page.locator('#file-graph-filter').select_option(mode)
                graph = page.evaluate('window.__execweaveCore.getDisplayGraph()')
                assert {n['id'] for n in graph['nodes'] if n['type'] == 'file'} == files
                assert page.locator('.node').count() == len(graph['nodes'])
                for identity in files - {'raw-orphan'}:
                    assert any(e['target'] == identity for e in graph['edges'])
                assert page.evaluate('JSON.stringify(window.__execweaveCore.getGraph())') == original
                results.append({'mode': mode, 'graph': graph})
            assert not errors
            evidence = Path(os.environ.get('EXECWEAVE_VISUAL_ARTIFACT_DIR', tmp_path)) / f'projection-owned-{owned}'
            evidence.mkdir(parents=True, exist_ok=True)
            page.locator('#svg').screenshot(path=str(evidence / 'final.png'))
            (evidence / 'display.json').write_text(json.dumps(results, indent=2))
        finally:
            browser.close()


def test_real_dashboard_hidden_type_chains_and_ambiguous_model(tmp_path):
    raw = {'session_id': 'projection-chain', 'nodes': [node('a', 'agent'), node('b', 'agent'), node('m', 'model')], 'edges': []}
    previous = 'a'
    for index, hidden in enumerate(HIDDEN):
        identity = f'hidden:{index}'
        raw['nodes'].append(node(identity, hidden))
        raw['edges'].append(edge(f'chain:{index}', previous, identity))
        previous = identity
    raw['edges'].append(edge('leaf', previous, 'm', 'INVOKES_MODEL', evidence_ids=['observed-model']))
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            for ambiguous in (False, True):
                fixture = json.loads(json.dumps(raw))
                if ambiguous:
                    fixture['edges'].append(edge('second-agent', 'b', previous))
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.set_content(render_static_dashboard_html(fixture))
                page.wait_for_selector('.node')
                display = page.evaluate('window.__execweaveCore.getDisplayGraph()')
                bridges = [e for e in display['edges'] if e.get('viewer_hidden_bridge')]
                if ambiguous:
                    assert not bridges
                    assert any(e['source'] == previous and e['target'] == 'm' for e in display['edges'])
                else:
                    assert len(bridges) == 1 and bridges[0]['source'] == 'a'
                    assert len(bridges[0]['viewer_supporting_edges']) == len(HIDDEN) + 1
                assert not errors
                page.close()
        finally:
            browser.close()


@pytest.mark.parametrize('conflict', ['conversation', 'session'])
def test_conflicting_identity_aliases_remain_inspectable_without_guessed_owner(tmp_path, conflict):
    aliases = ({'conversation_id': 'one', 'antigravity_conversation_id': 'two'}
               if conflict == 'conversation' else {'provider_session_id': 'one', 'session_id': 'two'})
    raw = {'session_id': 'conflict-browser',
           'nodes': [node('a', 'agent'), node('s', 'provider_session', **aliases), node('m', 'model')],
           'edges': [edge('as', 'a', 's'), edge('sm', 's', 'm', 'INVOKES_MODEL', causal=False)]}
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.set_content(render_static_dashboard_html(raw))
            page.wait_for_selector('.node')
            display = page.evaluate('window.__execweaveCore.getDisplayGraph()')
            assert not any(e.get('viewer_hidden_bridge') for e in display['edges'])
            assert page.locator('.node[data-id="s"]').count() == 1
            assert page.locator('.edge[data-source="s"][data-target="m"]').count() == 1
            assert page.locator('.edge[data-source="a"][data-target="m"]').count() == 0
            page.locator('.node[data-id="s"]').click()
            assert page.locator('.node[data-id="s"]').evaluate("e=>e.classList.contains('selected')")
            assert not errors
        finally:
            browser.close()
