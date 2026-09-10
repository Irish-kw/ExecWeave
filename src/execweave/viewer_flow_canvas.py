"""Draw the canvas the projection described, instead of a table keyed on node type.

``viewer_flow_layout`` decides, server side, which nodes a canvas draws and which column
and row each one takes. This installs the browser half: the display graph is narrowed to
that set, and a node's position is read from its own ``viewer_layer`` / ``viewer_order``
rather than looked up in the fixed lane table.

Both seams fall back to the previous behaviour when a payload carries no ``viewer_flow``,
so an older run artifact, a compact payload, or a graph the layout declined to describe
still renders exactly as it did before.
"""

from __future__ import annotations

FLOW_CANVAS_SCRIPT = r"""
// Column pitch is measured, not assumed: a column is as wide as its widest label plus a
// gap, so a long path pushes only the columns after it instead of overlapping its
// neighbour. Mirrors what the lane table did, keyed on layer instead of type.
const EXECWEAVE_FLOW_COL_GAP=120,EXECWEAVE_FLOW_ROW_GAP=104,EXECWEAVE_FLOW_TOP=100;
let execweaveFlowSpec=null,execweaveFlowColumnX=null;
function execweaveFlowPayload(){return execweaveFlowSpec}
function execweaveRememberFlow(data){
  const flow=data&&typeof data==='object'?data.viewer_flow:null;
  if(flow&&Array.isArray(flow.nodes)){
    execweaveFlowSpec=flow;execweaveFlowColumnX=null;
  }
  return execweaveFlowSpec;
}
function execweaveFlowNodeIds(){
  const flow=execweaveFlowSpec;
  if(!flow||!Array.isArray(flow.nodes))return null;
  const ids=new Set();
  for(const entry of flow.nodes)if(entry&&entry.id)ids.add(String(entry.id));
  return ids.size?ids:null;
}
// Narrow whatever the existing display filter produced to the set the projection says is
// drawn. Anything it withholds stays in `graph`, so panels and lookups still find it.
function execweaveFlowDisplay(data,display){
  execweaveRememberFlow(data);
  const ids=execweaveFlowNodeIds();
  if(!ids)return display;
  const nodes=(display.nodes||[]).filter(node=>node&&ids.has(String(node.id)));
  if(!nodes.length)return display;
  const kept=new Set(nodes.map(node=>String(node.id)));
  const edges=(display.edges||[]).filter(edge=>edge&&kept.has(String(edge.source))&&kept.has(String(edge.target)));
  return{...display,nodes,edges,node_count:nodes.length,edge_count:edges.length};
}
function execweaveFlowCoords(id){
  const node=nodeById.get(id);if(!node)return null;
  const a=node.attributes||{};
  const layer=a.viewer_layer,order=a.viewer_order;
  if(!Number.isInteger(layer)||!Number.isInteger(order))return null;
  return{layer,order};
}
// A column must clear its widest box. The renderer's own measurement is the authority
// where it is available; where it is not, estimate from the label rather than assuming
// the minimum, because assuming the minimum is what lets a long label overlap the
// column beside it.
function execweaveFlowWidth(id){
  try{const measured=execweaveWidthOf(id);if(Number.isFinite(measured)&&measured>0)return measured}catch(_){}
  const node=nodeById.get(id),label=String(node&&(node.name||node.id)||'');
  const estimated=label.length*7.1+EXECWEAVE_LABEL_PAD*2;
  return Math.min(EXECWEAVE_NODE_W_MAX,Math.max(EXECWEAVE_NODE_W,estimated));
}
function execweaveFlowColumns(){
  if(execweaveFlowColumnX)return execweaveFlowColumnX;
  const widest=new Map();
  for(const id of nodeById.keys()){
    const at=execweaveFlowCoords(id);if(!at)continue;
    const width=execweaveFlowWidth(id);
    if(!widest.has(at.layer)||widest.get(at.layer)<width)widest.set(at.layer,width);
  }
  const x={};let cursor=0;
  for(const layer of [...widest.keys()].sort((a,b)=>a-b)){
    x[layer]=cursor;cursor+=widest.get(layer)+EXECWEAVE_FLOW_COL_GAP;
  }
  execweaveFlowColumnX=x;return x;
}
// The dagre engine, layout v2 and the lane table all write `positions`, and whichever
// runs last wins. Rather than compete with them, take the positions they produced and
// overwrite the ones the projection has an opinion about. A node the projection said
// nothing about keeps whatever the previous authority chose for it.
function execweaveApplyFlowPositions(){
  if(typeof positions==='undefined'||!positions||!positions.set)return 0;
  const x=execweaveFlowColumns();let applied=0;
  for(const id of nodeById.keys()){
    const at=execweaveFlowCoords(id);if(!at)continue;
    if(!Number.isFinite(x[at.layer]))continue;
    positions.set(id,{x:x[at.layer],y:EXECWEAVE_FLOW_TOP+at.order*EXECWEAVE_FLOW_ROW_GAP});
    applied++;
  }
  if(!applied)return 0;
  // Route points were solved against the positions we just replaced, so drop them and
  // let edges fall back to the plain curve between their new endpoints.
  try{if(execweaveTopology&&execweaveTopology.routePoints)execweaveTopology.routePoints=new Map()}catch(_){}
  try{if(typeof execweaveRecomputePorts==='function')execweaveRecomputePorts(execweaveTopology)}catch(_){}
  try{for(const id of nodeById.keys()){const node=nodeById.get(id);if(node)updateNodeElement(node)}}catch(_){}
  try{for(const edge of edgeById.values())updateEdgeElement(edge)}catch(_){}
  return applied;
}
try{window.__execweaveFlow={payload:execweaveFlowPayload,columns:execweaveFlowColumns,apply:execweaveApplyFlowPositions}}catch(_){}
""".strip()

_FINAL_LAYOUT_SEAM = "function execweaveInstallFinalLayout(priorY){"
_FINAL_LAYOUT_REPLACEMENT = (
    "function execweaveInstallFinalLayout(priorY){\n"
    "  execweaveInstallFinalLayoutPreFlow(priorY);\n"
    "  try{execweaveApplyFlowPositions()}catch(_){}\n"
    "}\n"
    "function execweaveInstallFinalLayoutPreFlow(priorY){"
)


_DESIRED_SEAM = (
    "function execweaveDesiredPosition(id){const value=execweaveTopology.spec.get(id);"
    "return value?{x:value.x,y:value.y}:{x:0,y:0}}"
)

_DESIRED_REPLACEMENT = (
    "function execweaveDesiredPosition(id){\n"
    "  const at=execweaveFlowCoords(id);\n"
    "  if(at){const x=execweaveFlowColumns();\n"
    "    if(Number.isFinite(x[at.layer]))"
    "return{x:x[at.layer],y:EXECWEAVE_FLOW_TOP+at.order*EXECWEAVE_FLOW_ROW_GAP}}\n"
    "  const value=execweaveTopology.spec.get(id);return value?{x:value.x,y:value.y}:{x:0,y:0}\n"
    "}"
)

# Wrap the display filter by name rather than at its call site. Declarations hoist, so
# the wrapper may be written above the function it renames, and `execweaveDashboardGraph`
# keeps both its name and every existing call to it. The suffix is deliberately not
# `Base`: a later injector already binds `execweaveDashboardGraphBase` to whatever this
# name resolves to, and two declarations of it are a page-wide SyntaxError.
_DISPLAY_SEAM = "function execweaveDashboardGraph(data){"
_DISPLAY_REPLACEMENT = (
    FLOW_CANVAS_SCRIPT
    + "\nfunction execweaveDashboardGraph(data){"
    "return execweaveFlowDisplay(data,execweaveDashboardGraphPreFlow(data))}\n"
    "function execweaveDashboardGraphPreFlow(data){"
)


def inject_flow_canvas(html: str) -> str:
    """Point the canvas at ``viewer_flow``, leaving every other reader on the full graph."""
    if html.count(_DESIRED_SEAM) != 1:
        raise RuntimeError("flow canvas desired-position seam changed")
    html = html.replace(_DESIRED_SEAM, _DESIRED_REPLACEMENT, 1)
    if html.count(_DISPLAY_SEAM) != 1:
        raise RuntimeError("flow canvas display seam changed")
    html = html.replace(_DISPLAY_SEAM, _DISPLAY_REPLACEMENT, 1)
    if html.count(_FINAL_LAYOUT_SEAM) != 1:
        raise RuntimeError("flow canvas final-layout seam changed")
    return html.replace(_FINAL_LAYOUT_SEAM, _FINAL_LAYOUT_REPLACEMENT, 1)
