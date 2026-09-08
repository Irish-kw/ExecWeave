"""Execute the actual projection policy; assertions concern evidence, not source text."""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from execweave.viewer_dashboard_pr70 import PR70_DASHBOARD_SCRIPT

HIDDEN = [
    'provider_session', 'tool_call', 'tool_call_observation', 'agent_turn',
    'conversation_item', 'observed_content', 'agent_execution', 'terminal_operation',
    'permission_request', 'context_compaction', 'agent_turn_stop', 'compaction',
    'compaction_request', 'session', 'command', 'agent_trace_capability', 'inference_call',
    'code_cell', 'agent_message',
]


def node(identity, kind, **attributes):
    return {'id': identity, 'type': kind, 'name': identity, 'attributes': attributes}


def edge(identity, source, target, relation='OBSERVED', **extra):
    return {'id': identity, 'source': source, 'target': target, 'relation': relation, **extra}


def project(raw, display=None):
    executable = shutil.which('node')
    if executable is None:
        raise RuntimeError('Node.js is a required dependency for projection regression tests')
    if display is None:
        visible = [n for n in raw['nodes'] if n['type'] not in HIDDEN]
        ids = {n['id'] for n in visible}
        display = {**raw, 'nodes': visible, 'edges': [e for e in raw['edges'] if e['source'] in ids and e['target'] in ids]}
    stub = r"""
global.window={};global.execweaveDashboardGraph=data=>data;
global.execweaveBuildTopology=()=>({});global.execweaveRoute=()=>({d:'M 0 0',kind:'base'});
global.positions=new Map();global.edgeById=new Map();
global.execweaveTopology={spec:new Map(),routePoints:new Map(),bundleByEdge:new Map(),sourcePort:new Map(),targetPort:new Map()};
global.edgeId=e=>e.id;global.execweaveWidthOf=()=>160;global.execweaveHeightOf=()=>50;
global.execweavePortY=p=>p.y+25;global.execweaveIsStopped=()=>false;
"""
    script = stub + PR70_DASHBOARD_SCRIPT + '\n' + f"""
const raw={json.dumps(raw)},display={json.dumps(display)};
const before=JSON.stringify(raw),displayBefore=JSON.stringify(display);
const out=window.__execweavePr70.projectionRepair(raw,display);
if(before!==JSON.stringify(raw)||displayBefore!==JSON.stringify(display))throw new Error('evidence mutated');
process.stdout.write(JSON.stringify(out));
"""
    # Feed the full shared renderer via stdin; its size grows with unrelated
    # layout features and exceeds Windows' command-line limit. Preserve every
    # fixture byte and assertion instead of truncating or skipping any case.
    result = subprocess.run([executable, '-'], input=script, check=True,
                            capture_output=True, text=True, encoding='utf-8', timeout=30)
    return json.loads(result.stdout)


@pytest.mark.parametrize('hidden', HIDDEN)
@pytest.mark.parametrize('kind', ['model', 'file', 'directory', 'process', 'network_endpoint'])
def test_every_hidden_detail_preserves_visible_evidence(hidden, kind):
    raw = {'nodes': [node('a', 'agent'), node('s', hidden), node('v', kind)],
           'edges': [edge('owner', 'a', 's'), edge('observed', 's', 'v', evidence_ids=['ev'])]}
    out = project(raw)
    assert {n['id'] for n in out['nodes']} == {'a', 'v'}
    bridges = [e for e in out['edges'] if e.get('viewer_hidden_bridge')]
    assert len(bridges) == 1
    bridge = bridges[0]
    assert (bridge['source'], bridge['target']) == ('a', 'v')
    assert bridge['viewer_only'] is True and bridge['inferred'] is True and bridge['causal'] is False
    assert bridge['viewer_hidden_bridge_sources'] == ['s']
    assert {e['id'] for e in bridge['viewer_supporting_edges']} == {'owner', 'observed'}
    assert bridge['evidence_ids'] == ['ev']


def test_two_paths_preserve_all_support_and_are_input_order_independent():
    raw = {'nodes': [node('a', 'agent'), node('s1', 'provider_session'), node('s2', 'provider_session'), node('m', 'model')],
           'edges': [edge('p1', 'a', 's1'), edge('p2', 'a', 's2'),
                     edge('e1', 's1', 'm', 'INVOKES_MODEL', evidence_ids=['ev1'], first_sequence=4),
                     edge('e2', 's2', 'm', 'INVOKES_MODEL', evidence_ids=['ev2'], first_sequence=7)]}
    result = project(raw)
    reversed_result = project({'nodes': list(reversed(raw['nodes'])), 'edges': list(reversed(raw['edges']))})
    bridge = result['edges'][0]
    assert result['edges'] == reversed_result['edges']
    assert bridge['evidence_ids'] == ['ev1', 'ev2']
    assert bridge['viewer_hidden_bridge_sources'] == ['s1', 's2']
    assert {e['id'] for e in bridge['viewer_supporting_edges']} == {'p1', 'p2', 'e1', 'e2'}
    assert bridge['first_sequence'] == 4
    assert len(bridge['viewer_supporting_paths']) == 2


@pytest.mark.parametrize('kind', ['file', 'directory', 'model', 'process', 'network_endpoint'])
def test_unattributed_native_evidence_keeps_original_context_and_edge(kind):
    raw = {'nodes': [node('s', 'session'), node('v', kind), node('true-orphan', kind)],
           'edges': [edge('native', 's', 'v', 'OBSERVED_FILE_CHANGE', causal=False)]}
    out = project(raw)
    assert {n['id'] for n in out['nodes']} == {'s', 'v', 'true-orphan'}
    assert not any(e.get('viewer_hidden_bridge') for e in out['edges'])
    kept = next(e for e in out['edges'] if e['id'] == 'native')
    assert kept['source'] == 's' and kept['target'] == 'v' and kept['causal'] is False
    assert next(n for n in out['nodes'] if n['id'] == 's')['attributes']['viewer_retained_context'] is True


def test_ambiguous_agents_never_gain_direct_model_edges():
    raw = {'nodes': [node('a', 'agent'), node('b', 'agent'), node('s', 'provider_session'), node('m', 'model')],
           'edges': [edge('a-s', 'a', 's'), edge('b-s', 'b', 's'), edge('s-m', 's', 'm')]}
    out = project(raw)
    assert not any(e.get('viewer_hidden_bridge') for e in out['edges'])
    assert any(e['source'] == 's' and e['target'] == 'm' for e in out['edges'])
    assert not any(e['source'] in {'a', 'b'} and e['target'] == 'm' for e in out['edges'])


@pytest.mark.parametrize('field', ['conversation_id', 'provider_session_id', 'run_id', 'provider'])
def test_conflicting_identity_is_not_promoted_to_certain_owner(field):
    raw = {'nodes': [node('a', 'agent', **{field: 'one'}), node('s', 'provider_session', **{field: 'two'}), node('m', 'model')],
           'edges': [edge('as', 'a', 's'), edge('sm', 's', 'm')]}
    out = project(raw)
    assert not any(e.get('viewer_hidden_bridge') for e in out['edges'])
    assert out['dashboard_projection']['unresolved_hidden_paths'][0]['reason'] == 'identity_conflict'


def test_alias_target_is_repaired_without_resurrecting_filtered_files():
    raw = {'nodes': [node('a', 'agent'), node('s', 'provider_session'), node('m1', 'model'), node('m2', 'model'), node('f', 'file')],
           'edges': [edge('as', 'a', 's'), edge('sm1', 's', 'm1'), edge('sm2', 's', 'm2'), edge('sf', 's', 'f')]}
    display = {'nodes': [raw['nodes'][0], node('m1', 'model', viewer_occurrence_ids=['m1', 'm2'])], 'edges': []}
    out = project(raw, display)
    assert {n['id'] for n in out['nodes']} == {'a', 'm1'}
    assert {e['target'] for e in out['edges']} == {'m1'}
    assert out['edges'][0]['viewer_original_targets'] == ['m1', 'm2']


def test_already_presented_tool_declaration_is_not_duplicated():
    raw = {'nodes': [node('a', 'agent'), node('s', 'tool_call'), node('tool', 'tool'), node('f', 'file')],
           'edges': [edge('as', 'a', 's'), edge('sf', 's', 'f', 'DECLARED_TARGET')]}
    display = {'nodes': [raw['nodes'][0], raw['nodes'][2], raw['nodes'][3]],
               'edges': [edge('sf', 'tool', 'f', 'DECLARED_TARGET')]}
    assert project(raw, display)['edges'] == display['edges']
