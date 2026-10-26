"""Existing tool-call presentation and generic hidden bridges must not double count."""
from __future__ import annotations

import json
import pytest

from test_projection_bridge_evidence import edge, node, project
from dashboard_readability_fixture import CHILD_IDS, SHARED_TOOL_IDS, build_dashboard_readability_graph
from execweave.dashboard_shell import render_static_dashboard_html
from test_viewer_agent_isolation_e2e import _browser, _launch


def fixture(ambiguous=False):
    raw = {'nodes': [node('a', 'agent'), node('s', 'tool_call'), node('t', 'tool')],
           'edges': [edge('as', 'a', 's', 'ISSUED_TOOL_CALL'), edge('st', 's', 't', 'RESOLVED_TOOL', evidence_ids=['tool-ev'])]}
    if ambiguous:
        raw['nodes'].append(node('b', 'agent'))
        raw['edges'].append(edge('bs', 'b', 's', 'ISSUED_TOOL_CALL'))
    shown = {'nodes': [n for n in raw['nodes'] if n['id'] != 's'], 'edges': [{
        'id': 'viewer:called', 'source': 'a', 'target': 't', 'relation': 'CALLED_TOOL', 'viewer_only': True,
        'count': 1, 'evidence_call_count': 1,
        'viewer_tool_call_occurrences': [{'invocation_id': 'call', 'call_ids': ['s'], 'owner_id': 'a', 'tool_id': 't'}]}]}
    return raw, shown


def test_existing_called_tool_represents_resolved_tool_path_once():
    raw, shown = fixture()
    result = project(raw, shown)
    assert len(result['edges']) == 1
    called = result['edges'][0]
    assert called['id'] == 'viewer:called' and called['count'] == 1
    assert called['relation'] == 'CALLED_TOOL'
    assert {e['id'] for e in called['viewer_supporting_edges']} == {'as', 'st'}
    assert called['viewer_supporting_edges'][-1]['evidence_ids'] == ['tool-ev']


def test_ambiguous_tool_aggregation_does_not_override_unique_ancestor_rule():
    raw, shown = fixture(ambiguous=True)
    result = project(raw, shown)
    assert not any(e['source'] == 'a' and e['target'] == 't' for e in result['edges'])
    assert any(e['source'] == 's' and e['target'] == 't' for e in result['edges'])
    assert result['dashboard_projection']['rejected_tool_occurrence_count'] == 1


def test_tool_summary_matching_by_name_without_raw_target_still_requires_proven_owner():
    raw, shown = fixture()
    raw['edges'] = raw['edges'][:1]
    raw['nodes'][1]['attributes']['tool_name'] = 't'
    result = project(raw, shown)
    assert len(result['edges']) == 1 and result['edges'][0]['relation'] == 'CALLED_TOOL'
    assert {e['id'] for e in result['edges'][0]['viewer_supporting_edges']} == {'as'}


@pytest.mark.viewer_e2e
def test_shared_tool_fixture_keeps_24_bundle_members_not_48(tmp_path):
    raw = build_dashboard_readability_graph()
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page(viewport={'width': 1600, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.set_content(render_static_dashboard_html(raw))
            page.wait_for_selector('.node')
            display = page.evaluate('window.__execweaveCore.getDisplayGraph()')
            count = len(CHILD_IDS) * len(SHARED_TOOL_IDS)
            assert count == 24
            assert page.locator('.edge[data-bundle-size="6"]').count() == count
            pairs = {(e['source'], e['target']) for e in display['edges'] if e['relation'] == 'CALLED_TOOL'}
            assert len(pairs) == 27
            assert not any(e.get('viewer_hidden_bridge') and e['target'] in SHARED_TOOL_IDS for e in display['edges'])
            assert all(e.get('viewer_supporting_edges') for e in display['edges'] if e['relation'] == 'CALLED_TOOL')
            assert len(page.evaluate('window.__execweaveCore.getGraph().edges')) == len(raw['edges'])
            assert not errors
            (tmp_path / 'tool-display.json').write_text(json.dumps(display, indent=2))
        finally:
            browser.close()


@pytest.mark.viewer_e2e
@pytest.mark.parametrize('conflicting', [False, True])
def test_actual_tool_projection_does_not_guess_an_ambiguous_owner(tmp_path, conflicting):
    raw, _ = fixture(ambiguous=not conflicting)
    if conflicting:
        raw['nodes'][1]['attributes'] = {'conversation_id': 'one', 'antigravity_conversation_id': 'two'}
    manager, executable = _browser()
    with manager as playwright:
        browser = _launch(playwright, executable)
        try:
            page = browser.new_page()
            page.set_content(render_static_dashboard_html(raw))
            page.wait_for_selector('.node')
            display = page.evaluate('window.__execweaveCore.getDisplayGraph()')
            assert not any(e['relation'] == 'CALLED_TOOL' for e in display['edges'])
            assert page.locator('.edge[data-source="s"][data-target="t"]').count() == 1
            assert page.locator('.edge[data-source="a"][data-target="t"]').count() == 0
        finally:
            browser.close()
