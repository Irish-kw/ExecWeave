"""Adversarial identity regressions from the independent Stage 2 review."""
from __future__ import annotations

import pytest

from test_projection_bridge_evidence import edge, node, project

ALIASES = [
    ('conversation_id', 'antigravity_conversation_id'),
    ('provider_session_id', 'session_id'),
    ('execweave_session_id', 'run_id'),
]


def graph():
    return {'nodes': [node('a', 'agent'), node('s', 'provider_session'), node('m', 'model')],
            'edges': [edge('as', 'a', 's'), edge('sm', 's', 'm')]}


@pytest.mark.parametrize('aliases', ALIASES)
@pytest.mark.parametrize('where', ['agent', 'hidden', 'owner-edge', 'leaf-edge'])
def test_intra_object_conflicting_aliases_abstain(aliases, where):
    raw = graph()
    target = {'agent': raw['nodes'][0], 'hidden': raw['nodes'][1],
              'owner-edge': raw['edges'][0], 'leaf-edge': raw['edges'][1]}[where]
    target['attributes'] = {aliases[0]: 'one', aliases[1]: 'two'}
    out = project(raw)
    assert not any(e.get('viewer_hidden_bridge') for e in out['edges'])
    assert any(e['source'] == 's' and e['target'] == 'm' for e in out['edges'])
    assert out['dashboard_projection']['unresolved_hidden_paths'][0]['reason'] == 'identity_conflict'


@pytest.mark.parametrize('field', ['provider', 'conversation_id', 'provider_session_id', 'run_id'])
def test_top_level_and_attribute_conflicts_abstain(field):
    raw = graph()
    raw['nodes'][1][field] = 'two'
    raw['nodes'][1]['attributes'][field] = 'one'
    out = project(raw)
    assert not any(e.get('viewer_hidden_bridge') for e in out['edges'])


@pytest.mark.parametrize('aliases', ALIASES)
def test_matching_aliases_do_not_hide_a_valid_bridge(aliases):
    raw = graph()
    raw['nodes'][1]['attributes'] = {name: 'same' for name in aliases}
    out = project(raw)
    assert len([e for e in out['edges'] if e.get('viewer_hidden_bridge')]) == 1


def test_missing_source_is_unknown_not_a_proved_unique_agent():
    raw = graph()
    raw['edges'].append(edge('ghost-edge', 'ghost', 's'))
    out = project(raw)
    assert not any(e.get('viewer_hidden_bridge') for e in out['edges'])
    retained = next(e for e in out['edges'] if e['id'] == 'sm')
    assert retained['source'] == 's' and retained['target'] == 'm'
    assert retained['viewer_missing_source_ids'] == ['ghost']
    assert {e['id'] for e in retained['viewer_supporting_edges']} == {'as', 'sm', 'ghost-edge'}
    # The missing source can later prove to be another agent. A former direct
    # a->m bridge would have asserted a unique owner without enough evidence.
    raw['nodes'].append(node('ghost', 'agent'))
    resolved = project(raw)
    assert not any(e.get('viewer_hidden_bridge') for e in resolved['edges'])
    assert resolved['dashboard_projection']['unresolved_hidden_paths'][0]['ancestor_ids'] == ['a', 'ghost']


def test_distinct_conversations_on_one_agent_keep_separate_justifications():
    raw = {'nodes': [node('a', 'agent'), node('m', 'model'),
                     node('s1', 'provider_session', conversation_id='one'),
                     node('s2', 'provider_session', conversation_id='two')],
           'edges': [edge('a1', 'a', 's1'), edge('a2', 'a', 's2'),
                     edge('e1', 's1', 'm', evidence_ids=['ev1'], attributes={'conversation_id': 'one'}),
                     edge('e2', 's2', 'm', evidence_ids=['ev2'], attributes={'conversation_id': 'two'})]}
    out = project(raw)
    bridges = [e for e in out['edges'] if e.get('viewer_hidden_bridge')]
    assert len(bridges) == 2
    assert {e['viewer_identity_scope']['conversation'] for e in bridges} == {'one', 'two'}
    assert {tuple(e['evidence_ids']) for e in bridges} == {('ev1',), ('ev2',)}
    assert {tuple(e['viewer_hidden_bridge_sources']) for e in bridges} == {('s1',), ('s2',)}
    assert out['edges'] == project({'nodes': raw['nodes'][::-1], 'edges': raw['edges'][::-1]})['edges']


def test_recording_session_is_not_confused_with_provider_session():
    raw = graph()
    raw['edges'][1].update(session_id='recording-run')
    raw['edges'][1]['attributes'] = {'session_id': 'provider-conversation'}
    out = project(raw)
    assert len([e for e in out['edges'] if e.get('viewer_hidden_bridge')]) == 1
