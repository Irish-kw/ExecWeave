"""Regression for the real AGY observation overrejection reported by Grok #21."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from test_projection_bridge_evidence import edge, node, project
from test_viewer_agent_isolation_e2e import _browser, _launch
from execweave.dashboard_shell import render_static_dashboard_html


def fixture():
    owner = 'agent:antigravity:conversation:conversation-one'
    identity = {'provider': 'antigravity', 'conversation_id': 'conversation-one',
                'step_index': 2, 'tool_name': 'write_to_file'}
    raw = {'session_id': 'mirror-regression', 'nodes': [
        node(owner, 'agent', provider='antigravity', conversation_id='conversation-one'),
        node('call', 'tool_call', **identity), node('observation', 'tool_call_observation', **identity),
        node('tool', 'tool', provider='antigravity', tool_name='write_to_file'),
        node('content', 'observed_content', sha256='test-only-content', content_kind='tool_result')],
        'edges': [edge('owner-call', owner, 'call', 'ISSUED_TOOL_CALL'),
                  edge('call-tool', 'call', 'tool', 'USES_TOOL', evidence_ids=['invocation']),
                  edge('observation-content', 'observation', 'content', 'OBSERVED_CONTENT', evidence_ids=['result'])]}
    row = {'invocation_id': '\0'.join(['antigravity','conversation-step','conversation-one','2','write_to_file']),
           'owner_id': owner, 'tool_id': 'tool', 'call_ids': ['call', 'observation'], 'input': 'write', 'output': 'done'}
    shown = {'nodes': [raw['nodes'][0], raw['nodes'][3]], 'edges': [
        {**edge('called', owner, 'tool', 'CALLED_TOOL'), 'viewer_only': True, 'count': 1,
         'evidence_call_count': 1, 'viewer_tool_call_occurrences': [row]}]}
    return raw, shown


def test_unlinked_exact_step_observation_preserves_one_complete_call():
    raw, shown = fixture()
    out = project(raw, shown)
    assert len(out['edges']) == 1
    called = out['edges'][0]
    assert called['relation'] == 'CALLED_TOOL' and called['count'] == 1
    assert called['viewer_tool_call_occurrences'][0]['call_ids'] == ['call', 'observation']
    assert {e['id'] for e in called['viewer_supporting_edges']} == {'owner-call', 'call-tool', 'observation-content'}
    assert {n['id'] for n in called['viewer_supporting_nodes']} >= {'call', 'observation', 'content'}
    witness = called['viewer_tool_call_occurrences'][0]['viewer_mirror_identity_evidence'][0]
    assert witness['kind'] == 'provider-conversation-step-tool'
    assert witness['inferred'] is True and witness['causal'] is False
    assert out['edges'] == project({'nodes': raw['nodes'][::-1], 'edges': raw['edges'][::-1]}, shown)['edges']


@pytest.mark.parametrize('field,value', [('conversation_id', 'foreign'), ('provider', 'foreign'),
    ('step_index', 3), ('tool_name', 'foreign'), ('antigravity_step_index', 3), ('stepIdx', -1),
    ('provider_call_id', 'contradiction')])
def test_mirror_identity_mismatch_never_bypasses_proved_ownership(field, value):
    raw, shown = fixture()
    if field == 'provider_call_id':
        raw['nodes'][1]['attributes']['tool_call_id'] = 'native-one'
        raw['nodes'][2]['attributes']['tool_call_id'] = 'native-one'
    raw['nodes'][2]['attributes'][field] = value
    out = project(raw, shown)
    assert not any(e['relation'] == 'CALLED_TOOL' for e in out['edges'])


def test_dangling_observation_ancestor_is_not_overridden_by_matching_step():
    raw, shown = fixture()
    raw['edges'].append(edge('unknown-owner', 'ghost', 'observation'))
    assert not any(e['relation'] == 'CALLED_TOOL' for e in project(raw, shown)['edges'])


def test_mirror_without_any_proved_call_does_not_invent_ownership():
    raw, shown = fixture()
    raw['edges'] = [e for e in raw['edges'] if e['id'] != 'owner-call']
    assert not any(e['relation'] == 'CALLED_TOOL' for e in project(raw, shown)['edges'])


@pytest.mark.viewer_e2e
@pytest.mark.parametrize('theme', ['dark', 'light'])
def test_actual_clean_projection_and_browser_keep_mirrored_tool_occurrence(tmp_path: Path, theme):
    raw, _ = fixture()
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.set_content(render_static_dashboard_html(raw))
            page.wait_for_selector('.node')
            if page.evaluate("document.documentElement.dataset.theme") != theme:
                page.locator('#theme-toggle').click()
            assert page.evaluate("document.documentElement.dataset.theme") == theme
            out = page.evaluate('window.__execweaveCore.getDisplayGraph()')
            called = [e for e in out['edges'] if e['relation'] == 'CALLED_TOOL']
            assert len(called) == 1 and called[0]['count'] == 1
            row = called[0]['viewer_tool_call_occurrences'][0]
            assert set(row['call_ids']) == {'call', 'observation'}
            assert row['viewer_mirror_identity_evidence'][0]['observation_id'] == 'observation'
            assert page.locator('.edge[data-source="agent:antigravity:conversation:conversation-one"][data-target="tool"]').count() == 1
            assert not any(e.get('viewer_hidden_bridge') and e['target'] == 'tool' for e in out['edges'])
            assert page.evaluate('window.__execweaveCore.getGraph()') == raw
            assert not errors
            (tmp_path / f'mirror-{theme}.json').write_text(json.dumps(out, indent=2))
        finally:
            browser.close()
