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
let execweaveFlowSpec=null,execweaveFlowColumnX=null,execweaveFlowExtra=new Map();
function execweaveFlowPayload(){return execweaveFlowSpec}
function execweaveRememberFlow(data){
  const flow=data&&typeof data==='object'?data.viewer_flow:null;
  if(flow&&Array.isArray(flow.nodes)){
    execweaveFlowSpec=flow;execweaveFlowColumnX=null;execweaveFlowExtra=new Map();
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
// Narrow whatever the existing display filter produced to the set the projection says
// is drawn. Deliberately an intersection and not a replacement: the browser withholds
// types for its own reasons, and overriding that puts back nodes it meant to hide.
// Anything withheld stays in `graph`, so panels and lookups still find it.
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
  const extra=execweaveFlowExtra.get(id);if(extra)return extra;
  // Membership in the projection's own list, not the presence of the attributes. A node
  // the browser synthesises from another one inherits that node's layer and row, so an
  // attribute test calls it placed and it lands exactly on top of its original.
  const owned=execweaveFlowNodeIds();
  if(owned&&!owned.has(String(id)))return null;
  const node=nodeById.get(id);if(!node)return null;
  const a=node.attributes||{};
  const layer=a.viewer_layer;
  if(!Number.isInteger(layer))return null;
  // viewer_row is a solved coordinate and may be fractional; viewer_order is the ordinal
  // it was derived from, and stands in for older payloads that carry no row.
  const row=Number.isFinite(a.viewer_row)?a.viewer_row:a.viewer_order;
  if(!Number.isFinite(row))return null;
  return{layer,row};
}
// Some nodes are synthesised in the browser and never reach the projection: a model
// context, an orchestration step, a cluster stand-in. The projection cannot place what
// it never saw, so they keep whatever the previous authority chose -- which is how one
// of them came to sit exactly on top of the model node it describes, and another landed
// alone in the bottom-right corner. Place them from the company they keep instead: one
// column after the latest predecessor that does have a column, at the average row of
// every neighbour already placed, then separated from anything sharing that column.
function execweaveFlowPlaceUnknown(){
  execweaveFlowExtra=new Map();
  if(typeof edgeById==='undefined')return;
  const inbound=new Map(),outbound=new Map();
  for(const edge of edgeById.values()){
    const s=String(edge.source),t=String(edge.target);
    if(!nodeById.has(s)||!nodeById.has(t))continue;
    if(!inbound.has(t))inbound.set(t,[]);inbound.get(t).push(s);
    if(!outbound.has(s))outbound.set(s,[]);outbound.get(s).push(t);
  }
  const unknown=[...nodeById.keys()].filter(id=>!execweaveFlowCoords(id));
  if(!unknown.length)return;
  // Repeat so a chain of unknown nodes settles: each pass places whatever now has a
  // placed neighbour, and the pass after it can build on that.
  for(let pass=0;pass<unknown.length&&unknown.some(id=>!execweaveFlowExtra.has(id));pass++){
    for(const id of unknown){
      if(execweaveFlowExtra.has(id))continue;
      const before=(inbound.get(id)||[]).map(execweaveFlowCoords).filter(Boolean);
      const after=(outbound.get(id)||[]).map(execweaveFlowCoords).filter(Boolean);
      if(!before.length&&!after.length)continue;
      // Prefer the column straight after everything that leads here. Where that column
      // is at or past a successor, the node sits on a cycle and no column satisfies
      // both sides, so take the column before the successors instead: an edge between
      // two nodes of one column is drawn as a right-angled rail, and this leaves one
      // such edge behind rather than one per successor.
      const lower=before.length?Math.max(...before.map(at=>at.layer))+1:0;
      const upper=after.length?Math.min(...after.map(at=>at.layer))-1:lower;
      const layer=Math.max(0,lower<=upper?lower:upper);
      const rows=[...before,...after].map(at=>at.row);
      execweaveFlowExtra.set(id,{layer,row:rows.reduce((a,b)=>a+b,0)/rows.length});
    }
  }
  // Two nodes solved to the same row of the same column overlap exactly, which is the
  // defect this is here to remove. Only a node this pass invented may move: one the
  // projection placed is an anchor, or a stand-in would drag the solved layout around it.
  const anchors=new Map();
  for(const id of nodeById.keys()){
    if(execweaveFlowExtra.has(id))continue;
    const at=execweaveFlowCoords(id);if(!at)continue;
    if(!anchors.has(at.layer))anchors.set(at.layer,[]);
    anchors.get(at.layer).push(at.row);
  }
  for(const id of [...execweaveFlowExtra.keys()].sort()){
    const at=execweaveFlowExtra.get(id);
    const taken=anchors.get(at.layer)||[];
    // Search outward from the row its neighbours imply, not downward from it. Pushing
    // only down walks a node past every occupied row in the column and strands it at the
    // bottom, far from everything it connects to; the nearest free row in either
    // direction keeps it beside its own edges.
    const clear=candidate=>!taken.some(other=>Math.abs(other-candidate)<1);
    let row=at.row;
    for(let step=0;step<=2*(taken.length+4)&&!clear(row);step++){
      const delta=(Math.floor(step/2)+1)*0.5;
      row=step%2?at.row-delta:at.row+delta;
    }
    execweaveFlowExtra.set(id,{layer:at.layer,row});
    // An invented node becomes an anchor for the next one, so two of them in the same
    // column separate from each other as well as from the solved rows.
    if(!anchors.has(at.layer))anchors.set(at.layer,[]);
    anchors.get(at.layer).push(row);
  }
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
// Every corner on a drawn edge comes from a route that was solved against positions the
// flow layout has since replaced. Dagre's polyline is the origin: `routePoints` holds it,
// `rawDagreRoutePoints` holds the pristine copy, and the retarget step re-seeds the first
// from the second on every route call -- so clearing only `routePoints` is undone before
// the next paint. Clearing both leaves the retarget with nothing to restore, and each
// edge falls back to the plain curve between its own two endpoints. An already-present
// empty Map is truthy, so the re-seed guard keeps it empty from then on.
function execweaveFlowScrubGeometry(topo){
  if(!topo)return;
  if(topo.routePoints)topo.routePoints=new Map();
  if(topo.rawDagreRoutePoints)topo.rawDagreRoutePoints=new Map();
  // A bundle draws its own H/V rail, which is a corner the flow columns do not need.
  if(topo.bundleByEdge)topo.bundleByEdge=new Map();
}
function execweaveApplyFlowPositions(){
  if(typeof positions==='undefined'||!positions||!positions.set)return 0;
  try{execweaveFlowPlaceUnknown()}catch(_){execweaveFlowExtra=new Map()}
  execweaveFlowColumnX=null;
  const x=execweaveFlowColumns();let applied=0;
  for(const id of nodeById.keys()){
    const at=execweaveFlowCoords(id);if(!at)continue;
    if(!Number.isFinite(x[at.layer]))continue;
    positions.set(id,{x:x[at.layer],y:EXECWEAVE_FLOW_TOP+at.row*EXECWEAVE_FLOW_ROW_GAP});
    applied++;
  }
  if(!applied)return 0;
  try{execweaveFlowScrubGeometry(execweaveTopology)}catch(_){}
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
