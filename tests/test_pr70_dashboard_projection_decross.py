from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from execweave.dashboard_shell import DASHBOARD_HTML
from execweave.viewer_dashboard_pr70 import PR70_DASHBOARD_SCRIPT


def _node() -> str:
    executable = shutil.which("node")
    if executable is None:
        pytest.skip("node is required for dashboard JavaScript regression coverage")
    return executable


def test_hidden_provider_session_reanchors_model_and_drops_projection_orphan() -> None:
    script = r"""
global.window={};
global.execweaveDashboardGraph=data=>{
  const hidden=new Set(['provider_session']);
  const nodes=(data.nodes||[]).filter(node=>!hidden.has(node.type));
  const ids=new Set(nodes.map(node=>node.id));
  const edges=(data.edges||[]).filter(edge=>ids.has(edge.source)&&ids.has(edge.target));
  return{...data,nodes,edges,node_count:nodes.length,edge_count:edges.length};
};
global.execweaveBuildTopology=()=>({
  spec:new Map(),routePoints:new Map(),bundleByEdge:new Map(),sourcePort:new Map(),
  targetPort:new Map(),dagrePipeline:{stages:{POST_DAGRE:new Map()}},
});
global.execweaveRoute=()=>({d:'M 0 0',kind:'base'});
global.positions=new Map();
global.execweaveTopology={
  spec:new Map(),routePoints:new Map(),bundleByEdge:new Map(),sourcePort:new Map(),
  targetPort:new Map(),
};
global.edgeById=new Map();
global.edgeId=edge=>edge.id;
global.execweaveWidthOf=()=>160;
global.execweaveHeightOf=()=>50;
global.execweavePortY=(position)=>position.y+25;
global.execweaveIsStopped=()=>false;
""" + PR70_DASHBOARD_SCRIPT + r"""
const raw={
  nodes:[
    {id:'agent:root',type:'agent',name:'/root'},
    {id:'provider-session:agy:1',type:'provider_session',name:'session'},
    {id:'model:agy:gemini',type:'model',name:'gemini-3.8-flash-low'},
    {id:'directory:semantic-lock',type:'directory',name:'semantic.jsonl.lock'},
  ],
  edges:[
    {id:'session-edge',source:'agent:root',target:'provider-session:agy:1',relation:'OBSERVED_PROVIDER_SESSION'},
    {id:'model-edge',source:'provider-session:agy:1',target:'model:agy:gemini',relation:'INVOKES_MODEL',causal:false},
    {id:'lock-edge',source:'provider-session:agy:1',target:'directory:semantic-lock',relation:'OBSERVED_DIRECTORY',causal:false},
  ],
};
const display=execweaveDashboardGraph(raw);
process.stdout.write(JSON.stringify(display));
"""
    completed = subprocess.run(
        [_node(), "-e", script], check=True, capture_output=True, text=True
    )
    display = json.loads(completed.stdout)
    node_ids = {node["id"] for node in display["nodes"]}
    assert node_ids == {"agent:root", "model:agy:gemini"}
    bridges = [edge for edge in display["edges"] if edge.get("viewer_hidden_bridge")]
    assert len(bridges) == 1
    assert bridges[0]["source"] == "agent:root"
    assert bridges[0]["target"] == "model:agy:gemini"
    assert bridges[0]["relation"] == "INVOKES_MODEL"
    assert bridges[0]["inferred"] is True
    projection = display["dashboard_projection"]
    assert projection["hidden_bridge_edge_count"] == 1
    assert projection["removed_projection_orphan_ids"] == ["directory:semantic-lock"]


def test_dagre_route_points_survive_semantic_position_restore() -> None:
    script = r"""
global.window={};
global.execweaveDashboardGraph=data=>data;
const topo={
  spec:new Map([
    ['a',{x:10,y:20,lane:'agent'}],
    ['b',{x:300,y:100,lane:'model'}],
  ]),
  routePoints:new Map([['a\u0000b',[{x:100,y:20},{x:100,y:40},{x:200,y:20}]]]),
  bundleByEdge:new Map(),
  sourcePort:new Map([['e',{index:0,total:1}]]),
  targetPort:new Map([['e',{index:0,total:1}]]),
  dagrePipeline:{stages:{POST_DAGRE:new Map([
    ['a',{x:0,y:0}],
    ['b',{x:200,y:0}],
  ])}},
};
global.execweaveBuildTopology=()=>topo;
global.execweaveRoute=()=>({d:'M 0 0 C 1 1, 2 2, 3 3',kind:'base'});
global.positions=new Map([
  ['a',{x:10,y:20}],
  ['b',{x:300,y:100}],
]);
global.execweaveTopology=topo;
const edge={id:'e',source:'a',target:'b',relation:'USES_MODEL'};
global.edgeById=new Map([['e',edge]]);
global.edgeId=value=>value.id;
global.execweaveWidthOf=()=>100;
global.execweaveHeightOf=()=>50;
global.execweavePortY=position=>position.y+25;
global.execweaveIsStopped=()=>false;
""" + PR70_DASHBOARD_SCRIPT + r"""
execweaveTopology=execweaveBuildTopology();
const route=execweaveRoute(edge);
const points=execweaveTopology.routePoints.get('a\u0000b');
process.stdout.write(JSON.stringify({route,points}));
"""
    completed = subprocess.run(
        [_node(), "-e", script], check=True, capture_output=True, text=True
    )
    payload = json.loads(completed.stdout)
    route = payload["route"]
    assert route["kind"] == "dagre-polyline"
    assert route["usesDagrePoints"] is True
    assert " C " not in route["d"]
    # The old midpoint (100, 40) is shifted by the interpolated source/target
    # displacement: ((10, 20) + (100, 100)) / 2 = (55, 60).
    assert payload["points"][1] == {"x": 155, "y": 100}
    assert "L 155 100" in route["d"]


def test_shared_dashboard_installs_crossing_aware_live_reflow_gate() -> None:
    assert "window.__execweavePr70" in DASHBOARD_HTML
    assert "kind:'dagre-polyline'" in DASHBOARD_HTML
    assert "pr70StraightCrossings" in DASHBOARD_HTML
    assert (
        "execweaveRestorePriorYUnlessWorse(priorY,execweaveTopology)" in DASHBOARD_HTML
    )
    # The former unconditional restoration remains only as the explicit fallback.
    assert "priorCrossings<=newCrossings" in DASHBOARD_HTML
