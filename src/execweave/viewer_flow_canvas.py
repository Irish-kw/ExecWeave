"""Solve the canvas layout over the graph the canvas actually draws.

``viewer_flow_layout`` lays out the projected graph, server side. The canvas draws a
different graph: it withholds whole node types for its own reasons, and it synthesises
nodes of its own -- a model context, an orchestration step -- that the projection never
saw. Columns solved on one graph and edges drawn on the other is what put a node behind
something that leads to it, so the edge folded back into its right-hand side.

So the projection's layers and rows arrive here as the preferred answer, not the final
one, and the column each node takes is solved again over exactly the set being drawn.
Every edge of that set that is not part of a cycle then runs strictly left to right, and
the rows the projection solved are kept wherever they do not collide.

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
let execweaveFlowSpec=null,execweaveFlowColumnX=null,execweaveFlowSolved=null;
function execweaveFlowPayload(){return execweaveFlowSpec}
function execweaveFlowInvalidate(){execweaveFlowColumnX=null;execweaveFlowSolved=null}
function execweaveRememberFlow(data){
  const flow=data&&typeof data==='object'?data.viewer_flow:null;
  if(flow&&Array.isArray(flow.nodes)){execweaveFlowSpec=flow;execweaveFlowInvalidate()}
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
// What the projection would like this node's column and row to be. Membership in its own
// node list, not the presence of the attributes: a node the browser synthesises from
// another one inherits that node's layer and row, and reading those back places it
// exactly on top of the node it was copied from.
function execweaveFlowPreference(id){
  const owned=execweaveFlowNodeIds();
  if(owned&&!owned.has(String(id)))return null;
  const node=nodeById.get(id);if(!node)return null;
  const a=node.attributes||{};
  if(!Number.isInteger(a.viewer_layer))return null;
  // viewer_row is a solved coordinate and may be fractional; viewer_order is the ordinal
  // it was derived from, and stands in for older payloads that carry no row.
  const row=Number.isFinite(a.viewer_row)?a.viewer_row:a.viewer_order;
  return{layer:a.viewer_layer,row:Number.isFinite(row)?row:null};
}
// The edges between the nodes on the canvas, as one entry per ordered pair. Two nodes
// joined by several relations are one constraint on the layout, not several.
function execweaveFlowEdgePairs(){
  const pairs=new Map();
  if(typeof edgeById==='undefined')return pairs;
  for(const edge of edgeById.values()){
    const source=String(edge.source),target=String(edge.target);
    if(source===target||!nodeById.has(source)||!nodeById.has(target))continue;
    const key=source+'|'+target;
    if(!pairs.has(key))pairs.set(key,{source,target});
  }
  return pairs;
}
// Solve every drawn node's column and row together, over the drawn graph.
//
// A cycle has no left-to-right order, so one edge of each has to fold back whatever we
// do. Ranking the nodes first, and calling an edge that runs against that rank the
// feedback edge, picks which one: the projection's own layering is the rank wherever it
// has an opinion, so its decisions about direction survive, and a node it never saw takes
// a rank from the company it keeps. Longest path over what is left then puts every other
// edge on a strictly increasing column, which is the property that was missing.
function execweaveFlowSolve(){
  const solved=new Map();
  execweaveFlowSolved=solved;
  if(typeof nodeById==='undefined'||!nodeById.size)return solved;
  const ids=[...nodeById.keys()].map(String);
  const pairs=[...execweaveFlowEdgePairs().values()];
  const before=new Map(ids.map(id=>[id,[]])),after=new Map(ids.map(id=>[id,[]]));
  for(const pair of pairs){after.get(pair.source).push(pair.target);before.get(pair.target).push(pair.source)}

  const preference=new Map(ids.map(id=>[id,execweaveFlowPreference(id)]));
  const rank=new Map(ids.map(id=>[id,preference.get(id)?preference.get(id).layer:null]));
  // A node with no preference of its own settles just after whatever leads to it, or
  // just before whatever it leads to. Repeat so a chain of them settles end to end.
  for(let pass=0;pass<ids.length&&ids.some(id=>rank.get(id)===null);pass++){
    let moved=false;
    for(const id of ids){
      if(rank.get(id)!==null)continue;
      const back=before.get(id).map(peer=>rank.get(peer)).filter(value=>value!==null);
      const fore=after.get(id).map(peer=>rank.get(peer)).filter(value=>value!==null);
      if(!back.length&&!fore.length)continue;
      rank.set(id,back.length?Math.max(...back)+1:Math.min(...fore)-1);moved=true;
    }
    if(!moved)break;
  }
  for(const id of ids)if(rank.get(id)===null)rank.set(id,0);

  const order=new Map();
  [...ids].sort((a,b)=>rank.get(a)-rank.get(b)||a.localeCompare(b)).forEach((id,index)=>order.set(id,index));

  // Which edges fold back is decided by finding the cycles, not by comparing ranks: two
  // nodes of equal rank would otherwise have their edge pointed by whichever id sorts
  // first, and an orchestration step landed in the same column as the agents it targets
  // because of it. An edge is feedback only when its target is already open on the search
  // stack, which is to say only when it closes a cycle. Every other edge is kept, so a
  // node always takes a column after the nodes that lead to it.
  const feedback=new Set(),state=new Map(ids.map(id=>[id,0]));
  const roots=[...ids].sort((a,b)=>order.get(a)-order.get(b));
  for(const root of roots){
    if(state.get(root))continue;
    const stack=[{id:root,next:0}];
    state.set(root,1);
    while(stack.length){
      const frame=stack[stack.length-1];
      const peers=after.get(frame.id);
      if(frame.next>=peers.length){state.set(frame.id,2);stack.pop();continue}
      const peer=peers[frame.next++];
      const seen=state.get(peer);
      if(seen===1)feedback.add(frame.id+'|'+peer);
      else if(seen===0){state.set(peer,1);stack.push({id:peer,next:0})}
    }
  }
  const parents=new Map(ids.map(id=>[id,[]])),pending=new Map(ids.map(id=>[id,0]));
  for(const pair of pairs){
    if(feedback.has(pair.source+'|'+pair.target))continue;
    parents.get(pair.target).push(pair.source);
    pending.set(pair.target,pending.get(pair.target)+1);
  }
  // The projection's own layer is a floor, not a starting point to be recomputed away: it
  // counts depth through nodes the canvas hides, and rebuilding depth from the drawn edges
  // alone collapses a run into three columns. Longest path only ever pushes a node further
  // right, so every kept edge gains a column and the structure the projection found holds.
  const layer=new Map(ids.map(id=>{
    const want=preference.get(id);
    return[id,want?want.layer:0];
  }));
  const ready=ids.filter(id=>!pending.get(id)).sort((a,b)=>order.get(a)-order.get(b));
  for(let head=0;head<ready.length;head++){
    const id=ready[head];
    const depths=parents.get(id).map(peer=>layer.get(peer)+1);
    if(depths.length)layer.set(id,Math.max(layer.get(id),...depths));
    for(const peer of after.get(id)){
      if(feedback.has(id+'|'+peer))continue;
      pending.set(peer,pending.get(peer)-1);
      if(!pending.get(peer))ready.push(peer);
    }
  }

  // Rows: keep the row the projection solved, and give a node it never saw the average of
  // the neighbours that do have one, so it lands beside its own edges.
  const desired=new Map(ids.map(id=>{
    const want=preference.get(id);
    return[id,want&&want.row!==null?want.row:null];
  }));
  for(let pass=0;pass<ids.length&&ids.some(id=>desired.get(id)===null);pass++){
    let moved=false;
    for(const id of ids){
      if(desired.get(id)!==null)continue;
      const rows=[...before.get(id),...after.get(id)].map(peer=>desired.get(peer)).filter(value=>value!==null);
      if(!rows.length)continue;
      desired.set(id,rows.reduce((a,b)=>a+b,0)/rows.length);moved=true;
    }
    if(!moved)break;
  }
  ids.forEach((id,index)=>{if(desired.get(id)===null)desired.set(id,index)});

  // Separate within a column, in the order the desired rows already imply, so a node only
  // ever moves far enough to clear the one above it.
  const columns=new Map();
  for(const id of ids){
    const value=layer.get(id);
    if(!columns.has(value))columns.set(value,[]);
    columns.get(value).push(id);
  }
  for(const [value,members] of columns){
    members.sort((a,b)=>desired.get(a)-desired.get(b)||a.localeCompare(b));
    let floor=-Infinity;
    for(const id of members){
      const row=Math.max(desired.get(id),floor+1);
      solved.set(id,{layer:value,row});floor=row;
    }
  }
  return solved;
}
function execweaveFlowCoords(id){
  if(!execweaveFlowSolved)execweaveFlowSolve();
  return execweaveFlowSolved.get(String(id))||null;
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
  for(const value of [...widest.keys()].sort((a,b)=>a-b)){
    x[value]=cursor;cursor+=widest.get(value)+EXECWEAVE_FLOW_COL_GAP;
  }
  execweaveFlowColumnX=x;return x;
}
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
// A router picks which side of a box an edge leaves and enters by comparing the two
// nodes' ranks in the topology, not by comparing where they were actually drawn. Left as
// it was, an edge whose column the flow layout changed keeps the old answer and arrives
// at the right-hand side of a node that sits to the right of its source. The rank is the
// column, so say so.
function execweaveFlowSyncSpec(topo){
  if(!topo||!topo.spec||!topo.spec.get)return;
  for(const id of nodeById.keys()){
    const at=execweaveFlowCoords(id),spec=topo.spec.get(id);
    if(!at||!spec)continue;
    spec.rank=at.layer;spec.order=at.row;
    const p=positions.get(id);
    if(p){spec.x=p.x;spec.y=p.y}
  }
}
// The dagre engine, layout v2 and the lane table all write `positions`, and whichever
// runs last wins. Rather than compete with them, take the positions they produced and
// overwrite the ones the flow layout has an opinion about. A node it says nothing about
// keeps whatever the previous authority chose for it.
function execweaveApplyFlowPositions(){
  if(typeof positions==='undefined'||!positions||!positions.set)return 0;
  // The drawn set changes as nodes arrive, so the solve belongs to the paint, not to the
  // payload that happened to introduce them.
  execweaveFlowInvalidate();
  const x=execweaveFlowColumns();let applied=0;
  for(const id of nodeById.keys()){
    const at=execweaveFlowCoords(id);if(!at)continue;
    if(!Number.isFinite(x[at.layer]))continue;
    positions.set(id,{x:x[at.layer],y:EXECWEAVE_FLOW_TOP+at.row*EXECWEAVE_FLOW_ROW_GAP});
    applied++;
  }
  if(!applied)return 0;
  try{execweaveFlowSyncSpec(execweaveTopology)}catch(_){}
  try{execweaveFlowScrubGeometry(execweaveTopology)}catch(_){}
  try{if(typeof execweaveRecomputePorts==='function')execweaveRecomputePorts(execweaveTopology)}catch(_){}
  try{for(const id of nodeById.keys()){const node=nodeById.get(id);if(node)updateNodeElement(node)}}catch(_){}
  try{for(const edge of edgeById.values())updateEdgeElement(edge)}catch(_){}
  return applied;
}
try{window.__execweaveFlow={payload:execweaveFlowPayload,columns:execweaveFlowColumns,solve:execweaveFlowSolve,apply:execweaveApplyFlowPositions}}catch(_){}
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
    "return{x:x[at.layer],y:EXECWEAVE_FLOW_TOP+at.row*EXECWEAVE_FLOW_ROW_GAP}}\n"
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
