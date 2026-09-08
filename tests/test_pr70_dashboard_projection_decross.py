from __future__ import annotations

import json
import shutil
import subprocess

from execweave.dashboard_shell import DASHBOARD_HTML
from execweave.viewer_dashboard_pr70 import PR70_DASHBOARD_SCRIPT
from test_projection_bridge_evidence import edge, node, project


def _node() -> str:
    executable = shutil.which('node')
    if executable is None:
        raise RuntimeError('Node.js is required for dashboard JavaScript regression coverage')
    return executable


def test_hidden_provider_session_reanchors_model_and_drops_projection_orphan() -> None:
    # Retain the historical test ID, but preserve evidence instead of deleting it.
    raw = {'nodes': [node('agent:root', 'agent'), node('provider-session:agy:1', 'provider_session'),
                     node('model:agy:gemini', 'model'), node('directory:semantic-lock', 'directory')],
           'edges': [edge('session-edge', 'agent:root', 'provider-session:agy:1', 'OBSERVED_PROVIDER_SESSION'),
                     edge('model-edge', 'provider-session:agy:1', 'model:agy:gemini', 'INVOKES_MODEL', causal=False),
                     edge('lock-edge', 'provider-session:agy:1', 'directory:semantic-lock', 'OBSERVED_DIRECTORY', causal=False)]}
    display = project(raw)
    assert {n['id'] for n in display['nodes']} == {'agent:root', 'model:agy:gemini', 'directory:semantic-lock'}
    bridges = [e for e in display['edges'] if e.get('viewer_hidden_bridge')]
    assert len(bridges) == 2
    assert {e['target'] for e in bridges} == {'model:agy:gemini', 'directory:semantic-lock'}
    assert all(e['source'] == 'agent:root' and e['inferred'] is True and e['causal'] is False for e in bridges)
    assert display['dashboard_projection']['removed_projection_orphan_ids'] == []


def test_dagre_route_points_survive_semantic_position_restore() -> None:
    script = r"""
global.window={};global.execweaveDashboardGraph=data=>data;
const topo={
  spec:new Map([['a',{x:10,y:20,lane:'agent'}],['b',{x:300,y:100,lane:'model'}]]),
  routePoints:new Map([['a\u0000b',[{x:100,y:20},{x:100,y:40},{x:200,y:20}]]]),
  bundleByEdge:new Map(),sourcePort:new Map([['e',{index:0,total:1}]]),targetPort:new Map([['e',{index:0,total:1}]]),
  dagrePipeline:{stages:{POST_DAGRE:new Map([['a',{x:0,y:0}],['b',{x:200,y:0}]])}},
};
global.execweaveBuildTopology=()=>topo;global.execweaveRoute=()=>({d:'M 0 0 C 1 1, 2 2, 3 3',kind:'base'});
global.positions=new Map([['a',{x:10,y:20}],['b',{x:300,y:100}]]);global.execweaveTopology=topo;
const edge={id:'e',source:'a',target:'b',relation:'USES_MODEL'};
global.edgeById=new Map([['e',edge]]);global.edgeId=e=>e.id;global.execweaveWidthOf=()=>100;
global.execweaveHeightOf=()=>50;global.execweavePortY=p=>p.y+25;global.execweaveIsStopped=()=>false;
""" + PR70_DASHBOARD_SCRIPT + r"""
execweaveTopology=execweaveBuildTopology();
process.stdout.write(JSON.stringify({route:execweaveRoute(edge),points:execweaveTopology.routePoints.get('a\u0000b')}));
"""
    result = subprocess.run([_node(), '-e', script], check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    assert payload['route']['usesDagrePoints'] is True
    assert ' C ' not in payload['route']['d']
    assert payload['points'][1] == {'x': 155, 'y': 100}
    assert 'L 155 100' in payload['route']['d']


def test_shared_dashboard_installs_crossing_aware_live_reflow_gate() -> None:
    # Wiring checks remain supplemental; real renderer coverage lives in E2E tests.
    assert 'window.__execweavePr70' in DASHBOARD_HTML
    assert 'execweaveRestorePriorYUnlessWorse(priorY,execweaveTopology)' in DASHBOARD_HTML
    assert 'priorCrossings<=newCrossings' in DASHBOARD_HTML
