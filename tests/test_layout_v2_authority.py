from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from execweave.dashboard_shell import DASHBOARD_HTML
from execweave.viewer_layout_v2 import LAYOUT_V2_SCRIPT


def _node() -> str:
    executable = shutil.which("node")
    if executable is None:
        pytest.skip("Node.js is required for Layout V2 JavaScript regression coverage")
    return executable


def test_layout_v2_is_installed_after_pr70() -> None:
    assert "window.__execweaveLayoutV2={" in DASHBOARD_HTML
    assert "const EXECWEAVE_BAND_GAP=64;" in DASHBOARD_HTML
    assert "const EXECWEAVE_BAND_GAP=170;" not in DASHBOARD_HTML
    assert "FINAL_ORDER_AUTHORITY_MISMATCHES" in DASHBOARD_HTML
    assert "HUB_PORT_INVERSION_RATE" in DASHBOARD_HTML
    assert "geometryKind:'shared-resource-bus'" in DASHBOARD_HTML
    assert "mode:layoutMode" in DASHBOARD_HTML
    assert "layoutMode==='arrange'?4:2" in DASHBOARD_HTML


def test_final_order_is_single_authority_and_bus_uses_one_channel() -> None:
    script = (
        r"""
global.window=global;
global.document={getElementById:()=>null};
global.svg={getBoundingClientRect:()=>({width:1600,height:900})};
global.positions=new Map([
  ['a',{x:0,y:300}],['b',{x:0,y:100}],['c',{x:0,y:200}],['tool',{x:500,y:180}],
]);
global.nodeById=new Map([
  ['a',{id:'a',type:'agent'}],['b',{id:'b',type:'agent'}],
  ['c',{id:'c',type:'agent'}],['tool',{id:'tool',type:'tool'}],
]);
const edges=[
  {id:'ea',source:'a',target:'tool',relation:'USES_TOOL'},
  {id:'eb',source:'b',target:'tool',relation:'USES_TOOL'},
  {id:'ec',source:'c',target:'tool',relation:'USES_TOOL'},
];
global.edgeById=new Map(edges.map(e=>[e.id,e]));
global.edgeId=e=>e.id;
global.execweaveWidthOf=()=>160;
global.execweaveHeightOf=()=>50;
global.execweavePortY=(p,port)=>p.y+10+(30*(port?.index||0))/Math.max(1,(port?.total||1)-1);
global.execweaveIsStopped=()=>false;
global.execweaveTopology={
  spec:new Map([
    ['a',{lane:'agent',order:0}],['b',{lane:'agent',order:1}],
    ['c',{lane:'agent',order:2}],['tool',{lane:'tool',order:0}],
  ]),
  sourcePort:new Map(),targetPort:new Map(),
  bundleByEdge:new Map(edges.map((e,i)=>[e.id,{key:'tool\u0000USES_TOOL',size:3,index:i,representative:i===0,groupIndex:0}])),
  width:new Map(),height:new Map(),
};
global.execweaveGeometry={
  measure:(nodes,actualEdges)=>({EDGE_CROSSINGS:0,NODE_OVERLAPS:0,EDGE_NODE_INTERSECTIONS:0,
    MAX_EDGE_LENGTH:0,P95_EDGE_LENGTH:0,VISIBLE_NODE_COUNT:nodes.length,VISIBLE_EDGE_COUNT:actualEdges.length}),
  sample:d=>{
    const nums=[...String(d).matchAll(/[-+]?(?:\d*\.\d+|\d+\.?\d*)/g)].map(m=>Number(m[0]));
    return [{x:nums[0]||0,y:nums[1]||0},{x:nums.at(-2)||0,y:nums.at(-1)||0}];
  },
  throughBox:()=>false,
};
"""
        + LAYOUT_V2_SCRIPT
        + r"""
window.__execweaveLayoutV2.syncFinalOrder(execweaveTopology,positions);
const byY=[...positions.keys()].filter(id=>id!=='tool').sort((x,y)=>positions.get(x).y-positions.get(y).y);
const orders=byY.map(id=>execweaveTopology.spec.get(id).order);
for(const edge of edges){
  const sourceIndex=byY.indexOf(edge.source);
  execweaveTopology.sourcePort.set(edge.id,{index:0,total:1});
  execweaveTopology.targetPort.set(edge.id,{index:sourceIndex,total:3});
}
const routes=edges.map(edge=>window.__execweaveLayoutV2.busRoute(edge));
const trunks=routes.map(route=>Number(route.d.match(/ H ([^ ]+) V /)[1]));
process.stdout.write(JSON.stringify({
  byY,orders,trunks,
  mismatch:window.__execweaveLayoutV2.orderMismatches(),
  hub:window.__execweaveLayoutV2.hubInversionRate(),
  packing:window.__execweaveLayoutV2.packingWidth([{w:200,h:80},{w:120,h:80},{w:120,h:80}],400,64),
}));
"""
    )
    proc = subprocess.run(
        [_node(), "-"],
        input=script,
        text=True,
        capture_output=True,
        check=True,
        encoding="utf-8",
        timeout=30,
    )
    payload = json.loads(proc.stdout)
    assert payload["byY"] == ["b", "c", "a"]
    assert payload["orders"] == [0, 1, 2]
    assert payload["mismatch"] == 0
    assert payload["hub"] == 0
    assert len(set(payload["trunks"])) == 1
    assert payload["packing"] >= 400
