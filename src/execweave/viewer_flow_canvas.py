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
const EXECWEAVE_FLOW_COL_GAP=72,EXECWEAVE_FLOW_ROW_GAP=104,EXECWEAVE_FLOW_TOP=100;
// the clear space kept between two boxes stacked in the same column
const EXECWEAVE_FLOW_ROW_PAD=28;
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
// Every node the layout says it folded into another, so a node that is in neither list
// can be told apart from one that was deliberately hidden.
function execweaveFlowCollapsed(){
  const flow=execweaveFlowSpec,ids=new Set();
  const map=flow&&flow.collapsed;
  if(map)for(const key of Object.keys(map))ids.add(String(key));
  return ids;
}
// Narrow whatever the existing display filter produced to the set the projection says
// is drawn. Deliberately an intersection and not a replacement: the browser withholds
// types for its own reasons, and overriding that puts back nodes it meant to hide.
// Anything withheld stays in `graph`, so panels and lookups still find it.
function execweaveFlowDisplay(data,display){
  execweaveRememberFlow(data);
  const ids=execweaveFlowNodeIds();
  if(!ids)return display;
  const all=display.nodes||[];
  // The display step ahead of this one owns the fold budget. It keeps the most recent
  // members of a crowded type and adds one `viewer:folded:` node listing the rest, which
  // the reader opens to reach them; the number it keeps is a setting the run chooses.
  // The flow layout folds as well, and where the two disagree this one stands, because
  // it is the one the reader asked for and the only one with a way back to what it hid.
  const foldedTypes=new Set();
  for(const node of all){
    const members=node&&node.attributes&&node.attributes.viewer_folded_members;
    if(!Array.isArray(members))continue;
    foldedTypes.add(String(node.type||''));
    for(const member of members)if(member&&member.type)foldedTypes.add(String(member.type));
  }
  const budgeted=node=>{
    if(!node)return false;
    if(node.attributes&&node.attributes.viewer_folded)return true;
    return foldedTypes.has(String(node.type||''));
  };
  // A node the projection never saw -- one that arrived after the layout was worked out,
  // or that the browser built for itself -- is not something this layout chose to hide.
  // It has no entry saying it was folded into anything either, so dropping it would lose
  // it outright. Keep it; the solver settles a column for it from what it connects to.
  const folded=execweaveFlowCollapsed();
  const known=node=>ids.has(String(node.id))||folded.has(String(node.id));
  const nodes=all.filter(node=>node&&(ids.has(String(node.id))||budgeted(node)||!known(node)));
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
  const projected=nodeById.get(id)?.attributes||{};
  // The browser's session projection runs after the Python flow projection. Its
  // explicit ranks supersede copied resource layers, including synthetic nodes.
  if(Number.isInteger(projected.viewer_flow_rank)&&[...nodeById.values()].some(n=>n.attributes?.viewer_session_flow))return{layer:projected.viewer_flow_rank,row:0};
  const owned=execweaveFlowNodeIds();
  // A folded member is still drawn when the browser's file/type budget keeps it. Its
  // annotation carries the survivor's solved layer and row, so keep that preference;
  // treating it as a brand-new node makes the member drift away from the group the flow
  // layout deliberately folded it into and raises crossings in a fully unfolded view.
  if(owned&&!owned.has(String(id))&&!execweaveFlowCollapsed().has(String(id)))return null;
  const node=nodeById.get(id);if(!node)return null;
  const a=node.attributes||{};
  if(!Number.isInteger(a.viewer_layer))return null;
  // viewer_row is a solved coordinate and may be fractional; viewer_order is the ordinal
  // it was derived from, and stands in for older payloads that carry no row.
  const row=Number.isFinite(a.viewer_row)?a.viewer_row:a.viewer_order;
  return{layer:a.viewer_layer,row:Number.isFinite(row)?row:null};
}
// The edges between the nodes on the canvas, as one entry per ordered pair. Two nodes
// joined by several relations are one constraint on the layout, not several. A pair is
// a return only when the session projection marked every one of its edges as one.
function execweaveFlowEdgePairs(){
  const pairs=new Map();
  if(typeof edgeById==='undefined')return pairs;
  for(const edge of edgeById.values()){
    const source=String(edge.source),target=String(edge.target);
    if(source===target||!nodeById.has(source)||!nodeById.has(target))continue;
    const key=source+'|'+target,returns=edge.viewer_flow_feedback===true;
    if(!pairs.has(key))pairs.set(key,{source,target,returns});
    else if(!returns)pairs.get(key).returns=false;
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
  const hasPreference=[...preference.values()].some(value=>value!==null);
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
  // A recorded reply remains a return even if the dispatch was outside this
  // recording; do not move the main agent behind its received message history.
  // The session projection names its own returns (a child reporting back, an actor
  // replying into its session); folding those keeps root, model and session leftmost.
  for(const pair of pairs){
    const source=nodeById.get(pair.source),target=nodeById.get(pair.target);
    if(pair.returns||target?.attributes?.viewer_session_flow&&(source?.attributes?.viewer_framework_messages||source?.attributes?.viewer_return_message))feedback.add(pair.source+'|'+pair.target);
  }
  // With a viewer_flow payload, prefer the projection's layer order when choosing the
  // DFS roots. Without one (the dashboard shell also accepts a raw static graph), keep
  // the graph's insertion order: sorting IDs would visit `agent:child:*` before
  // `agent:root` and incorrectly reverse SPAWNED_AGENT instead of SUBAGENT_STOPPED.
  const roots=[...ids].sort((a,b)=>{
    const pa=preference.get(a),pb=preference.get(b);
    return pa&&pb&&pa.layer!==pb.layer?pa.layer-pb.layer:0;
  });
  for(const root of roots){
    if(state.get(root))continue;
    const stack=[{id:root,next:0}];
    state.set(root,1);
    while(stack.length){
      const frame=stack[stack.length-1];
      const peers=after.get(frame.id);
      if(frame.next>=peers.length){state.set(frame.id,2);stack.pop();continue}
      const peer=peers[frame.next++];
      if(feedback.has(frame.id+'|'+peer))continue;
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
  // the neighbours that do have one, so it lands beside its own edges. A raw static graph
  // has no projection rows at all; seed those by the stable order within each solved
  // column, rather than by the global node index (which leaves the first real column with
  // a misleading gap and makes static/live dashboards disagree about child order).
  const desired=new Map(ids.map(id=>{
    const want=preference.get(id);
    return[id,want&&want.row!==null?want.row:null];
  }));
  if(!hasPreference){
    const byLayer=new Map();
    for(const id of ids){
      const value=layer.get(id);
      if(!byLayer.has(value))byLayer.set(value,[]);
      byLayer.get(value).push(id);
    }
    for(const members of byLayer.values()){
      members.sort((a,b)=>order.get(a)-order.get(b));
      members.forEach((id,index)=>desired.set(id,index));
    }
  }else{
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
  }

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
  // Order each column so the drawn links cross as few times as the columns allow: sweep by
  // the mean row of each node's neighbours, keep the order that crosses the fewest links,
  // then swap neighbours wherever that alone removes a crossing. A tie keeps the order it
  // was given. Sessions keep their own order among themselves, because their names count
  // up in it. A link back into an earlier column is drawn between the same two columns as
  // one forward, so it is counted as one: leaving it out ordered a reply as if it were not
  // there, and it crossed everything its sender sent below it.
  const untangle=(layerOf,members)=>{
    const values=[...members.keys()].sort((a,b)=>a-b);
    const links=[];
    for(const pair of pairs){
      const l0=layerOf.get(pair.source),l1=layerOf.get(pair.target);
      if(l0===undefined||l1===undefined||l0===l1)continue;
      links.push(l0<l1?{source:pair.source,target:pair.target}:{source:pair.target,target:pair.source});
    }
    const peers=new Map([...layerOf.keys()].map(id=>[id,{back:[],fore:[]}]));
    for(const pair of links){peers.get(pair.target).back.push(pair.source);peers.get(pair.source).fore.push(pair.target)}
    const at=new Map(),place=()=>{for(const list of members.values())list.forEach((id,row)=>at.set(id,row))};
    // A link that skips columns passes the columns between as well, at the height a straight
    // line between its ends has there, which is where the router draws it unless a box
    // stands in the way. Two links cross between two adjacent columns when their order
    // there flips; counting only links between the same pair of columns would order a
    // column as if the long links through it were not there. A box in the way is counted
    // as well: the router has to bend the link around it, over or under the links that box
    // sends on, and an order that leaves the line clear is the one that reads.
    const index=new Map(values.map((value,i)=>[value,i]));
    const crossings=()=>{
      const gaps=new Map();let total=0;
      for(const pair of links){
        const l0=layerOf.get(pair.source),l1=layerOf.get(pair.target),r0=at.get(pair.source),r1=at.get(pair.target);
        const height=i=>r0+(r1-r0)*(values[i]-l0)/(l1-l0);
        for(let i=index.get(l0);i<index.get(l1);i++){
          if(!gaps.has(i))gaps.set(i,[]);
          gaps.get(i).push([height(i),height(i+1)]);
          const y=height(i+1);
          if(i+1<index.get(l1)&&y>-.4&&y<members.get(values[i+1]).length-.6&&Math.abs(y-Math.round(y))<.4)total++;
        }
      }
      for(const list of gaps.values())for(let i=0;i<list.length;i++)for(let j=i+1;j<list.length;j++){
        if((list[i][0]-list[j][0])*(list[i][1]-list[j][1])<0)total++;
      }
      return total;
    };
    const isSession=id=>nodeById.get(id)?.type==='session';
    const arrange=(list,side)=>{
      const mean=new Map(list.map((id,row)=>{
        const near=peers.get(id)[side];
        return[id,near.length?near.reduce((sum,peer)=>sum+at.get(peer),0)/near.length:row];
      }));
      const next=[...list].sort((a,b)=>mean.get(a)-mean.get(b));
      const sessions=list.filter(isSession);let k=0;
      return next.map(id=>isSession(id)?sessions[k++]:id);
    };
    place();
    let best=new Map([...members].map(([value,list])=>[value,[...list]]));
    let fewest=links.length<=1500?crossings():0;
    for(let round=0;round<4&&fewest>0;round++){
      for(const [sweep,side] of [[values.slice(1),'back'],[values.slice(0,-1).reverse(),'fore']]){
        for(const value of sweep){members.set(value,arrange(members.get(value),side));place()}
        const now=crossings();
        if(now<fewest){fewest=now;best=new Map([...members].map(([value,list])=>[value,[...list]]))}
      }
    }
    // Means tie whenever two nodes hang off the same neighbour, and the sweep cannot tell
    // them apart then. Swap two neighbours in a column wherever that alone removes a
    // crossing, until no swap does.
    for(const [value,list] of best)members.set(value,[...list]);
    place();
    if(links.length<=250){
      for(let pass=0,improved=true;improved&&fewest>0&&pass<8;pass++){
        improved=false;
        for(const list of members.values())for(let i=0;i+1<list.length&&fewest>0;i++){
          if(isSession(list[i])&&isSession(list[i+1]))continue;
          [list[i],list[i+1]]=[list[i+1],list[i]];place();
          const now=crossings();
          if(now<fewest){fewest=now;improved=true}else{[list[i],list[i+1]]=[list[i+1],list[i]];place()}
        }
      }
    }
    return members;
  };
  // The session projection ranks its nodes into columns and leaves their order within a
  // column to the canvas, where every node had row 0 and ties fell to the id: a model the
  // run switched to sorted above the one it started with, and their edges into the
  // session crossed for no reason. Start each column in the order its nodes first took
  // part in the run and untangle from there; a tie keeps the earlier order, so time
  // decides wherever the structure does not.
  if(ids.some(id=>nodeById.get(id)?.attributes?.viewer_session_flow)&&ids.length<=400){
    const pointOf=item=>({seq:item?.first_sequence,stamp:item?.first_seen});
    const cmp=(p,q)=>Number.isInteger(p.seq)&&Number.isInteger(q.seq)?p.seq-q.seq
      :!p.stamp-!q.stamp||String(p.stamp||'').localeCompare(String(q.stamp||''));
    const first=new Map(ids.map(id=>[id,pointOf(nodeById.get(id))]));
    for(const edge of edgeById.values()){
      const point=pointOf(edge);
      for(const id of [String(edge.source),String(edge.target)])if(first.has(id)&&cmp(point,first.get(id))<0)first.set(id,point);
    }
    const values=[...new Set(ids.map(id=>layer.get(id)))].sort((a,b)=>a-b);
    const members=new Map(values.map(value=>[value,ids.filter(id=>layer.get(id)===value)
      .sort((a,b)=>cmp(first.get(a),first.get(b))||a.localeCompare(b))]));
    untangle(layer,members);
    for(const [value,list] of members)list.forEach((id,row)=>solved.set(id,{layer:value,row}));
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
// Every edge on the canvas is drawn as a smooth curve. Two other shapes reach this
// point: a bundle draws its trunk as a horizontal-vertical-horizontal rail, and an
// ordinary edge arrives from dagre as a run of straight segments. Both put visible
// corners on the canvas, and both are there for a reason -- the run of segments is what
// steers an edge around the boxes between its ends. So the corners are rounded off
// rather than removed: the same points, in the same order, joined by a spline that
// passes through every one of them. The route still goes where it went, and the
// grouping a bundle carries is untouched -- the DOM keeps `data-bundle-size` and the
// panels that count members still read it.
let execweaveFlowRouteWrapped=false;
// Where this layout last put each node. Another authority -- Arrange, a drag -- may
// move a node afterwards, and once it has, the columns are no longer what is on screen
// and the geometry that belongs to them is no longer the geometry to draw.
const execweaveFlowPlaced=new Map();
// Read a path back as the points it visits. Only the commands the routers emit are
// understood; anything else means the path is not ours to redraw.
function execweaveFlowPathPoints(d){
  const tokens=String(d).match(/[A-Za-z]|-?[0-9.]+/g);
  if(!tokens)return null;
  const points=[];let x=0,y=0,index=0;
  while(index<tokens.length){
    const command=tokens[index++];
    if(!/[A-Za-z]/.test(command))return null;
    const number=()=>{const value=Number(tokens[index++]);return Number.isFinite(value)?value:NaN};
    if(command==='M'||command==='L'){x=number();y=number()}
    else if(command==='H'){x=number()}
    else if(command==='V'){y=number()}
    else return null;
    if(!Number.isFinite(x)||!Number.isFinite(y))return null;
    points.push({x,y});
  }
  return points.length>=2?points:null;
}
// Catmull-Rom through the points, written out as the cubics an SVG path takes. The
// curve touches every original point, so an edge routed around a box still clears it.
function execweaveFlowSpline(points){
  const parts=[`M ${points[0].x} ${points[0].y}`];
  for(let i=0;i<points.length-1;i++){
    const p0=points[i>0?i-1:0],p1=points[i],p2=points[i+1],p3=points[i+2<points.length?i+2:points.length-1];
    // Half the usual control arm. A full Catmull-Rom arm overshoots the corner it is
    // rounding, and the segments it rounds here are what steer an edge past a box, so
    // an overshoot puts the curve back through the box the corner existed to avoid.
    const c1x=Math.max(Math.min(p1.x+(p2.x-p0.x)/12,Math.max(p1.x,p2.x)),Math.min(p1.x,p2.x));
    const c1y=Math.max(Math.min(p1.y+(p2.y-p0.y)/12,Math.max(p1.y,p2.y)),Math.min(p1.y,p2.y));
    const c2x=Math.max(Math.min(p2.x-(p3.x-p1.x)/12,Math.max(p1.x,p2.x)),Math.min(p1.x,p2.x));
    const c2y=Math.max(Math.min(p2.y-(p3.y-p1.y)/12,Math.max(p1.y,p2.y)),Math.min(p1.y,p2.y));
    parts.push(`C ${c1x} ${c1y}, ${c2x} ${c2y}, ${p2.x} ${p2.y}`);
  }
  return parts.join(' ');
}
// An edge runs straight from one port to the other, and whatever sits between them is
// run straight through. The pipeline this layout replaces avoided that with dagre's
// route points, which were computed for the positions it replaced, so the avoidance has
// to be done again here. A blocker is any drawn box the run passes through, in any
// column -- the ones that reach the canvas are usually in the target's own column,
// stacked above and below it -- and each contributes one waypoint clear of whichever
// of its horizontal edges the run is nearer.
const EXECWEAVE_FLOW_CLEARANCE=8;
// The height of a drawn box, from whichever of the two authorities is in scope here.
function execweaveFlowBoxHeight(id){
  if(typeof execweaveHeightOf==='function')return execweaveHeightOf(id);
  const measured=execweaveTopology&&execweaveTopology.height&&execweaveTopology.height.get(id);
  return Number.isFinite(measured)?measured:50;
}
function execweaveFlowHolds(id){
  const placed=execweaveFlowPlaced.get(id),now=positions.get(id);
  return !!placed&&!!now&&Math.abs(placed.x-now.x)<.5&&Math.abs(placed.y-now.y)<.5;
}
function execweaveFlowAvoid(edge,base){
  if(!execweaveFlowHolds(edge.source)||!execweaveFlowHolds(edge.target))return null
  if(!execweaveFlowCoords(edge.source)||!execweaveFlowCoords(edge.target))return null
  const sp=positions.get(edge.source),tp=positions.get(edge.target);
  if(!sp||!tp)return null;
  // Two nodes in one column have no room between them for a line: drawn from the right
  // edge of one to the left edge of the other it runs down the column and through every
  // box on the way, and even a near-vertical curve leans far enough to clip its
  // neighbour. Take it out into the empty space beside the column and back.
  const fromAt=execweaveFlowCoords(edge.source),toAt=execweaveFlowCoords(edge.target);
  if(fromAt&&toAt&&fromAt.layer===toAt.layer){
    const edgeOf=id=>positions.get(id).x+execweaveWidthOf(id);
    const sourceEdge=edgeOf(edge.source),targetEdge=edgeOf(edge.target);
    const side=Math.max(sourceEdge,targetEdge);
    const centre=id=>positions.get(id).y+execweaveFlowBoxHeight(id)/2;
    const a=execweaveFlowPortAt(edge,'s',centre(edge.source)),z=execweaveFlowPortAt(edge,'t',centre(edge.target));
    const rail=side+EXECWEAVE_FLOW_COL_GAP*.45;
    return Object.assign({},base,{d:`M ${sourceEdge} ${a} C ${rail} ${a}, ${rail} ${z}, ${targetEdge} ${z}`,
      labelX:side+EXECWEAVE_FLOW_COL_GAP*.45,labelY:(a+z)/2-8});
  }
  const run=execweaveFlowRunOf(edge);
  if(!run)return null;
  execweaveFlowLaneApply(edge,run);
  const points=run.back?run.points.slice().reverse():run.points;
  return Object.assign({},base,{d:execweaveFlowSpline(points),labelX:run.labelX,labelY:run.labelY});
}
// The run an edge between two columns takes, solved left to right; `back` is set on one
// drawn the other way. Null when the edge is not this layout's to draw.
function execweaveFlowRunOf(edge){
  if(!execweaveFlowHolds(edge.source)||!execweaveFlowHolds(edge.target))return null;
  const fromAt=execweaveFlowCoords(edge.source),toAt=execweaveFlowCoords(edge.target);
  if(!fromAt||!toAt||fromAt.layer===toAt.layer)return null;
  const sp=positions.get(edge.source),tp=positions.get(edge.target);
  if(!sp||!tp)return null;
  const id=edgeId(edge),topo=execweaveTopology;
  const sx=sp.x+execweaveWidthOf(edge.source),tx=tp.x;
  const sy=execweaveFlowPortAt(edge,'s',execweavePortY(sp,topo.sourcePort.get(id),edge.source));
  const ty=execweaveFlowPortAt(edge,'t',execweavePortY(tp,topo.targetPort.get(id),edge.target));
  if(tx-sx>1)return execweaveFlowRun(edge,sx,sy,tx,ty,tp.x);
  // An edge into a column further left -- a reply routed back to the agent it answers --
  // leaves the left side of its source and enters the right side of its target. Solved
  // left to right as the run between those two sides and drawn the other way, it clears
  // the same boxes a forward edge would, and its arrow still faces its target.
  const back=tp.x+execweaveWidthOf(edge.target),front=sp.x;
  if(!(front-back>1))return null;
  return Object.assign(execweaveFlowRun(edge,back,ty,front,sy,sp.x,true),{back:true});
}
// Where on its box each line leaves and arrives. A box's left side takes the lines that
// come into it and the ones that go back out of it to a column further left; its right
// side takes the lines that leave it, the ones that come back into it, and the ones drawn
// beside its own column. Counted apart, an arrow coming in and a line going out of the
// same side are both put at its middle, and one line arriving where another leaves reads
// as a single line with its arrow at the wrong end.
// A side is shared out top to bottom in the order its lines head off in. That is not the
// order of the boxes at their other ends: a line to a box level with this one that has to
// go over the boxes between heads up, and given the lower port it cuts across the line
// that runs straight. So the runs are laid out once with the sides shared out by the
// boxes at the other ends, and the sides shared out again by the height each run turns
// to first. Lines of one kind, drawn alike, that come together at the same turn before
// reaching this box already run as one line from there, so they are given one port and
// end in one arrow instead of a row of arrows splitting off the last few pixels.
let execweaveFlowPorts=null;
function execweaveFlowPortPlan(){
  if(typeof edgeById==='undefined')return null;
  const key=execweaveFlowLaneKey();
  if(execweaveFlowPorts&&execweaveFlowPorts.key===key&&execweaveFlowPorts.edges===edgeById)return execweaveFlowPorts;
  const plan={key,edges:edgeById,at:new Map()};
  execweaveFlowPorts=plan;
  if(edgeById.size>400)return plan;
  const sides=new Map();
  const add=(node,side,end,other,edge)=>{
    if(!sides.has(node))sides.set(node,{left:[],right:[]});
    sides.get(node)[side].push({end,other,kind:`${String(edge.relation||'')}\0${edge.causal===true?'c':edge.causal===false?'n':''}${edge.inferred===true?'i':''}`});
  };
  const drawn=[];
  for(const edge of edgeById.values()){
    if(!execweaveFlowHolds(edge.source)||!execweaveFlowHolds(edge.target))continue;
    const fromAt=execweaveFlowCoords(edge.source),toAt=execweaveFlowCoords(edge.target);
    if(!fromAt||!toAt)continue;
    const sp=positions.get(edge.source),tp=positions.get(edge.target);
    if(!sp||!tp)continue;
    const id=edgeId(edge);
    let from,to;
    if(fromAt.layer===toAt.layer){from='right';to='right'}
    else if(tp.x-(sp.x+execweaveWidthOf(edge.source))>1){from='right';to='left'}
    else if(sp.x-(tp.x+execweaveWidthOf(edge.target))>1){from='left';to='right'}
    else continue;
    add(edge.source,from,id+'>s',edge.target,edge);
    add(edge.target,to,id+'>t',edge.source,edge);
    if(fromAt.layer!==toAt.layer)drawn.push(edge);
  }
  const centre=id=>positions.get(id).y+execweaveFlowBoxHeight(id)/2;
  const share=(at,towards,turn)=>{
    for(const [node,both] of sides){
      const box=positions.get(node),height=execweaveFlowBoxHeight(node);
      for(const list of [both.left,both.right]){
        list.sort((a,b)=>towards(a)-towards(b)||centre(a.other)-centre(b.other)||positions.get(a.other).x-positions.get(b.other).x||(a.end<b.end?-1:a.end>b.end?1:0));
        const slots=new Map(),slotOf=list.map(entry=>{
          const at=turn&&turn.get(entry.end),key=at==null?entry.end:`${entry.kind}\0${at}`;
          if(!slots.has(key))slots.set(key,slots.size);
          return slots.get(key);
        });
        list.forEach((entry,index)=>at.set(entry.end,slots.size<2?box.y+height/2:box.y+10+(height-20)*slotOf[index]/(slots.size-1)));
      }
    }
  };
  share(plan.at,entry=>centre(entry.other));
  // The height a run first turns to, away from the port at one end of it: the first
  // stop at another height after the start, or the last one before the end. Where that
  // stop is a bend on the way rather than the far end, it is also the turn the line
  // comes from.
  const heads=new Map(),turns=new Map();
  for(const edge of drawn){
    let run=null;
    try{run=execweaveFlowRunOf(edge)}catch(_){run=null}
    if(!run||run.points.length<2)continue;
    const points=run.points,last=points.length-1,id=edgeId(edge);
    let firstAt=last,finalAt=0;
    for(let i=1;i<=last;i++)if(Math.abs(points[i].y-points[0].y)>.5){firstAt=i;break}
    for(let i=last-1;i>=0;i--)if(Math.abs(points[i].y-points[last].y)>.5){finalAt=i;break}
    heads.set(id+(run.back?'>t':'>s'),Math.round(points[firstAt].y));
    heads.set(id+(run.back?'>s':'>t'),Math.round(points[finalAt].y));
    if(firstAt<last)turns.set(id+(run.back?'>t':'>s'),`${Math.round(points[firstAt].x)},${Math.round(points[firstAt].y)}`);
    if(finalAt>0)turns.set(id+(run.back?'>s':'>t'),`${Math.round(points[finalAt].x)},${Math.round(points[finalAt].y)}`);
  }
  const at=new Map();
  share(at,entry=>heads.has(entry.end)?heads.get(entry.end):Math.round(centre(entry.other)),turns);
  plan.at=at;
  return plan;
}
// The height this edge leaves its source ('s') or enters its target ('t') at; `fallback`
// where the plan has none: a canvas too large to plan, or a line this layout does not draw.
function execweaveFlowPortAt(edge,end,fallback){
  let plan=null;
  try{plan=execweaveFlowPortPlan()}catch(_){plan=null}
  const at=plan&&plan.at.get(edgeId(edge)+'>'+end);
  return Number.isFinite(at)?at:fallback;
}
// Runs that clear the same boxes the same way are sent to the same height, and where
// their level stretches meet they are drawn as one line: nothing on the canvas says which
// end belongs to which. Two runs that share an end and are drawn alike may merge, since
// they meet at that box anyway; a solid line laid over a dashed one would read as neither,
// so those, and any other two that would run along one height, are put on lanes a few pixels
// apart. The shorter stretch keeps the height it was given, nearest the boxes, and the
// longer is moved out past it, so a stretch lying inside another is not crossed by it.
// A lane depends on every other run at that height, so all runs are laid out together
// and the lanes kept until something moves or the graph changes.
const EXECWEAVE_FLOW_LANE=8;
let execweaveFlowLanes=null;
function execweaveFlowLaneKey(){
  let key=Math.imul(edgeById.size+1,0x9e3779b1)^nodeById.size;
  for(const p of positions.values()){
    key=Math.imul(key^Math.round(p.x*2),0x85ebca6b);
    key=Math.imul(key^Math.round(p.y*2),0xc2b2ae35);
  }
  return key;
}
function execweaveFlowLevels(points){
  const levels=[];
  for(let i=1;i+2<points.length;i++){
    const a=points[i],b=points[i+1];
    if(Math.abs(a.y-b.y)>.5||Math.abs(a.x-b.x)<4)continue;
    const last=levels[levels.length-1];
    if(last&&last.to===i&&Math.abs(last.y-a.y)<=.5){last.to=i+1;last.hi=Math.max(last.hi,b.x);continue}
    levels.push({from:i,to:i+1,y:a.y,lo:Math.min(a.x,b.x),hi:Math.max(a.x,b.x)});
  }
  return levels;
}
function execweaveFlowLanePlan(){
  if(typeof edgeById==='undefined')return null;
  const key=execweaveFlowLaneKey();
  if(execweaveFlowLanes&&execweaveFlowLanes.key===key&&execweaveFlowLanes.edges===edgeById)return execweaveFlowLanes;
  const plan={key,edges:edgeById,shift:new Map()};
  execweaveFlowLanes=plan;
  if(edgeById.size>400)return plan;
  const levels=[];
  for(const edge of edgeById.values()){
    let run=null;
    try{run=execweaveFlowRunOf(edge)}catch(_){run=null}
    if(!run)continue;
    for(const level of execweaveFlowLevels(run.points))levels.push(Object.assign(level,{edge,id:edgeId(edge),points:run.points}));
  }
  const look=edge=>`${edge.causal===true?'c':edge.causal===false?'n':''}${edge.inferred===true?'i':''}`;
  const near=24,meets=(a,b)=>(a.edge.source===b.edge.source||a.edge.target===b.edge.target)&&look(a.edge)===look(b.edge);
  const groups=new Map();
  for(const level of levels){const at=Math.round(level.y);if(!groups.has(at))groups.set(at,[]);groups.get(at).push(level)}
  for(const group of groups.values()){
    if(group.length<2)continue;
    group.sort((a,b)=>(a.hi-a.lo)-(b.hi-b.lo)||(a.id<b.id?-1:a.id>b.id?1:a.from-b.from));
    const lane=new Map();
    for(const level of group){
      const used=new Set();
      for(const [other,value] of lane){
        if(meets(level,other))continue;
        if(level.lo<other.hi+near&&other.lo<level.hi+near)used.add(value);
      }
      let value=0;while(used.has(value))value++;
      lane.set(level,value);
    }
    for(const [level,value] of lane){
      if(!value)continue;
      // Out towards whichever side has the more room above or below this stretch.
      const pad=EXECWEAVE_FLOW_CLEARANCE;let up=Infinity,down=Infinity;
      for(const other of nodeById.keys()){
        const box=positions.get(other);if(!box)continue;
        if(box.x+execweaveWidthOf(other)+pad<=level.lo||box.x-pad>=level.hi)continue;
        const top=box.y-pad,bottom=box.y+execweaveFlowBoxHeight(other)+pad;
        if(bottom<=level.y)up=Math.min(up,level.y-bottom);
        else if(top>=level.y)down=Math.min(down,top-level.y);
      }
      const room=Math.max(up,down),offset=value*EXECWEAVE_FLOW_LANE;
      if(offset>room-2)continue;
      const moved=level.points.map((p,i)=>i>=level.from&&i<=level.to?{x:p.x,y:p.y+(up>=down?-offset:offset)}:p);
      if(execweaveFlowBoxHits(level.edge,moved)>execweaveFlowBoxHits(level.edge,level.points))continue;
      if(!plan.shift.has(level.id))plan.shift.set(level.id,[]);
      plan.shift.get(level.id).push({from:level.from,to:level.to,y:level.y,by:up>=down?-offset:offset});
    }
  }
  return plan;
}
// Move this run's level stretches onto the lanes the plan gave them, but only where the
// run is still the one the plan was made from.
function execweaveFlowLaneApply(edge,run){
  let plan=null;
  try{plan=execweaveFlowLanePlan()}catch(_){plan=null}
  const moves=plan&&plan.shift.get(edgeId(edge));
  if(!moves)return run;
  for(const move of moves){
    const span=run.points.slice(move.from,move.to+1);
    if(span.length!==move.to-move.from+1||span.some(p=>Math.abs(p.y-move.y)>.5))continue;
    const lo=Math.min(...span.map(p=>p.x)),hi=Math.max(...span.map(p=>p.x));
    for(let i=move.from;i<=move.to;i++)run.points[i]={x:run.points[i].x,y:run.points[i].y+move.by};
    if(Math.abs(run.labelY+8-move.y)<=.5&&run.labelX>=lo&&run.labelX<=hi)run.labelY+=move.by;
  }
  return run;
}
// What a run would cost to draw: first every box its straight pieces pass through, since
// clearing one column can aim the rest of the run into a box further on; then how many
// of the other links it would cross, each link taken as the straight line from the side
// of its source it leaves to the side of its target it enters. A link within one column,
// or one that shares an end with this one, is left out: the first is drawn beside its
// column, and the second meets this run at a box, not across it.
function execweaveFlowBoxHits(edge,points){
  const pad=EXECWEAVE_FLOW_CLEARANCE;
  let total=0;
  for(const other of nodeById.keys()){
    if(other===edge.source||other===edge.target)continue;
    const box=positions.get(other);if(!box)continue;
    const left=box.x-pad,right=box.x+execweaveWidthOf(other)+pad;
    const top=box.y-pad,bottom=box.y+execweaveFlowBoxHeight(other)+pad;
    for(let i=0;i+1<points.length;i++){
      const a=points[i],b=points[i+1];
      const lo=Math.max(Math.min(a.x,b.x),left),hi=Math.min(Math.max(a.x,b.x),right);
      if(!(hi>lo))continue;
      const at=x=>b.x===a.x?a.y:a.y+(b.y-a.y)*(x-a.x)/(b.x-a.x);
      const ya=at(lo),yb=at(hi);
      if(Math.max(ya,yb)>top&&Math.min(ya,yb)<bottom){total++;break}
    }
  }
  return total;
}
function execweaveFlowCrossings(edge,points){
  let total=execweaveFlowBoxHits(edge,points)*1000;
  if(typeof edgeById==='undefined'||edgeById.size>400)return total;
  const cut=(a,b,c,d)=>{
    const side=(p,q,r)=>(q.x-p.x)*(r.y-p.y)-(q.y-p.y)*(r.x-p.x);
    return side(a,b,c)*side(a,b,d)<0&&side(c,d,a)*side(c,d,b)<0;
  };
  for(const other of edgeById.values()){
    if(other===edge)continue;
    if(other.source===edge.source||other.source===edge.target||other.target===edge.source||other.target===edge.target)continue;
    const sp=positions.get(other.source),tp=positions.get(other.target);
    if(!sp||!tp)continue;
    const from=execweaveFlowCoords(other.source),to=execweaveFlowCoords(other.target);
    if(from&&to&&from.layer===to.layer)continue;
    const sw=execweaveWidthOf(other.source),tw=execweaveWidthOf(other.target);
    const sm=sp.y+execweaveFlowBoxHeight(other.source)/2,tm=tp.y+execweaveFlowBoxHeight(other.target)/2;
    const chord=sp.x+sw<=tp.x?[{x:sp.x+sw,y:sm},{x:tp.x,y:tm}]:[{x:tp.x+tw,y:tm},{x:sp.x,y:sm}];
    for(let i=0;i+1<points.length;i++)if(cut(points[i],points[i+1],chord[0],chord[1])){total++;break}
  }
  return total;
}
// The run from (sx,sy) to (tx,ty), left to right, stepped around every box between. The
// box whose column the run ends in starts at endX. A returning run starts at the box it
// returns to.
function execweaveFlowRun(edge,sx,sy,tx,ty,endX,returning){
  const runY=x=>sy+(ty-sy)*(x-sx)/(tx-sx);
  const waypoints=[],blocked=[];let approach=false;
  for(const other of nodeById.keys()){
    if(other===edge.source||other===edge.target)continue;
    // Any box on the canvas is in the way, whether or not this layout placed it.
    const box=positions.get(other);if(!box)continue;
    const pad=EXECWEAVE_FLOW_CLEARANCE;
    const left=box.x-pad,right=box.x+execweaveWidthOf(other)+pad;
    const top=box.y-pad,bottom=box.y+execweaveFlowBoxHeight(other)+pad;
    // the part of the run that lies within the box's columns, if any
    const lo=Math.max(sx,Math.min(tx,left)),hi=Math.max(sx,Math.min(tx,right));
    if(!(hi-lo>1))continue;
    const ya=runY(lo),yb=runY(hi);
    if(Math.max(ya,yb)<top||Math.min(ya,yb)>bottom)continue;
    // A blocker standing in the target's own column cannot be stepped over inside that
    // column: the run has nowhere left to go before the port. What clears it is to reach
    // the port's height while there is still room, and come in level.
    if(box.x>=endX-1){approach=true;continue}
    blocked.push({lo,hi});
  }
  // Clear a column for its whole width, not only at its middle: one waypoint in the
  // centre lets the curve back in on the way to it. Two, one at each side, carry the run
  // level past it. Every box in the column is cleared at once, through whichever opening
  // lies nearest the line -- above the column, below it, or the gap between two boxes --
  // since clearing them one at a time sends the run over one box and under the next, and
  // two such stops in one column can only be resolved by leaving the column altogether.
  blocked.sort((a,b)=>a.lo-b.lo);
  const columns=[];
  for(const span of blocked){
    const last=columns[columns.length-1];
    if(last&&span.lo<last.hi)last.hi=Math.max(last.hi,span.hi);else columns.push({...span});
  }
  for(const {lo,hi} of columns){
    const pad=EXECWEAVE_FLOW_CLEARANCE,here=runY((lo+hi)/2),taken=[];
    for(const other of nodeById.keys()){
      if(other===edge.source||other===edge.target)continue;
      const box=positions.get(other);if(!box)continue;
      if(box.x+execweaveWidthOf(other)+pad<=lo||box.x-pad>=hi)continue;
      taken.push([box.y-pad-10,box.y+execweaveFlowBoxHeight(other)+pad+10]);
    }
    taken.sort((a,b)=>a[0]-b[0]);
    // The nearest opening above the line and the nearest below it are both short ways
    // round; of the two, take the one that runs into fewer boxes and crosses fewer of the
    // other links, and the nearer only when they cost the same.
    let above=null,below=null,floor=-Infinity;
    const open=(from,to)=>{
      if(!(to>=from))return;
      const y=Math.min(to,Math.max(from,here));
      if(y<=here&&(above===null||y>above))above=y;
      if(y>=here&&(below===null||y<below))below=y;
    };
    for(const [top,bottom] of taken){open(floor,top);floor=Math.max(floor,bottom)}
    open(floor,Infinity);
    const options=[above,below].filter(y=>y!==null);
    const cost=y=>execweaveFlowCrossings(edge,[{x:sx,y:sy},{x:lo,y},{x:hi,y},{x:tx,y:ty}]);
    let clear=options[0];
    if(options.length>1&&above!==below){
      const up=cost(above),down=cost(below);
      clear=up<down?above:down<up?below:Math.abs(above-here)<=Math.abs(below-here)?above:below;
    }
    waypoints.push({x:lo,y:clear},{x:hi,y:clear});
  }
  if(approach)waypoints.push({x:tx-Math.min(44,(tx-sx)*.45),y:ty});
  // A run that falls much further than it travels cannot be stepped past box by box:
  // clipped to any one box's width it is a sliver, and every box in that column stands
  // in it, so the stops pile up in a few pixels and read as a scribble. The space between
  // two columns is empty by construction, so the descent belongs there instead. Enter a
  // clear horizontal band before the first middle box, cross the full middle span, then
  // come back to the port level after the last one; stopping at the midpoint would leave
  // the final horizontal run cutting through that last box.
  // A run back across columns with anything in its way takes the band as well, and the
  // side is chosen by the box it returns to alone: every return into one box then shares
  // a single trunk, rather than some passing over the graph and the rest under it.
  const middle=[];
  for(const other of nodeById.keys()){
    if(other===edge.source||other===edge.target)continue;
    const box=positions.get(other);if(!box)continue;
    if(box.x>sx+1&&box.x+execweaveFlowWidth(other)<tx-1){
      middle.push({box,width:execweaveFlowWidth(other),height:execweaveFlowBoxHeight(other)});
    }
  }
  if(waypoints.length>3||returning&&waypoints.length&&middle.length){
    const firstLeft=Math.min(...middle.map(item=>item.box.x))-EXECWEAVE_FLOW_CLEARANCE;
    const middleRight=Math.max(...middle.map(item=>item.box.x+item.width));
    const middleTop=Math.min(...middle.map(item=>item.box.y-EXECWEAVE_FLOW_CLEARANCE));
    const middleBottom=Math.max(...middle.map(item=>item.box.y+item.height+EXECWEAVE_FLOW_CLEARANCE));
    const above=middleTop-10,below=middleBottom+10;
    const safeY=returning?(Math.abs(sy-above)<=Math.abs(sy-below)?above:below)
      :Math.abs(sy-above)+Math.abs(ty-above)<=Math.abs(sy-below)+Math.abs(ty-below)?above:below;
    const entry=Math.max(sx+EXECWEAVE_FLOW_CLEARANCE+2,Math.min(firstLeft-10,(sx+firstLeft)/2));
    const exit=Math.min(tx-EXECWEAVE_FLOW_CLEARANCE-2,Math.max(middleRight+10,(tx+middleRight)/2));
    if(exit>entry+2){
      return{points:[{x:sx,y:sy},{x:entry,y:sy},{x:entry,y:safeY},
        {x:exit,y:safeY},{x:exit,y:ty},{x:tx,y:ty}],
        labelX:(entry+exit)/2,labelY:safeY-8};
    }
    const corridor=(sx+tx)/2;
    return{points:[{x:sx,y:sy},{x:corridor,y:sy},{x:corridor,y:ty},{x:tx,y:ty}],
      labelX:corridor,labelY:(sy+ty)/2-8};
  }
  // A waypoint that clears one box can land inside the next one along. Walk each of them
  // out of whatever it is standing in, in the direction it was already heading.
  for(const stop of waypoints){
    for(let attempt=0;attempt<12;attempt++){
      let moved=false;
      for(const other of nodeById.keys()){
        if(other===edge.source||other===edge.target)continue;
        const box=positions.get(other);if(!box)continue;
        const pad=EXECWEAVE_FLOW_CLEARANCE;
        if(stop.x<box.x-pad||stop.x>box.x+execweaveFlowWidth(other)+pad)continue;
        const top=box.y-pad,bottom=box.y+execweaveFlowBoxHeight(other)+pad;
        if(stop.y<top||stop.y>bottom)continue;
        stop.y=stop.y<=(top+bottom)/2?top-10:bottom+10;moved=true;
      }
      if(!moved)break;
    }
  }
  // No waypoints means the run is already clear, and it is still the path to draw: the
  // route the base router offers was computed for the positions this layout replaced,
  // so following it now walks through boxes that have since moved into its way.
  waypoints.sort((a,b)=>a.x-b.x);
  // Two blockers in the same column give one waypoint, not two on top of each other.
  const stops=[];
  for(const stop of waypoints){
    const last=stops[stops.length-1];
    if(last&&Math.abs(last.x-stop.x)<2){if(Math.abs(stop.y-runY(stop.x))>Math.abs(last.y-runY(last.x)))last.y=stop.y;continue}
    stops.push(stop);
  }
  return{points:[{x:sx,y:sy},...stops,{x:tx,y:ty}],labelX:(sx+tx)/2,labelY:(sy+ty)/2-8};
}
// The router is reassigned several times as the page builds, so wrap whatever is current
// at the first paint rather than at load, and wrap it only once.
function execweaveFlowInstallRoute(){
  if(execweaveFlowRouteWrapped)return;
  if(typeof execweaveRoute!=='function')return;
  execweaveFlowRouteWrapped=true;
  const execweaveFlowRouteBase=execweaveRoute;
  execweaveRoute=function(edge){
    const value=execweaveFlowRouteBase(edge);
    if(!value||typeof value.d!=='string')return value;
    // A path already drawn as cubics is what this wants; anything carrying a line, a
    // horizontal or a vertical segment has a corner in it and gets rounded off.
    try{
      const clear=execweaveFlowAvoid(edge,value);
      if(clear)return clear;
      if(!/[LHVlhv]/.test(value.d))return value;
      const points=execweaveFlowPathPoints(value.d);
      if(!points)return value;
      return Object.assign({},value,{d:execweaveFlowSpline(points)});
    }catch(_){return value}
  };
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
  execweaveFlowInstallRoute();
  const x=execweaveFlowColumns();let applied=0;
  // A row is not always a whole number -- it carries the alignment the layout wants
  // against the columns either side -- so two rows can land closer together than the
  // boxes they hold are tall. Take the row as the height the node wants to sit at, then
  // walk each column from the top and push any box that would land on the one above it.
  const byColumn=new Map();
  for(const id of nodeById.keys()){
    const at=execweaveFlowCoords(id);if(!at)continue;
    if(!Number.isFinite(x[at.layer]))continue;
    if(!byColumn.has(at.layer))byColumn.set(at.layer,[]);
    byColumn.get(at.layer).push({id,y:EXECWEAVE_FLOW_TOP+at.row*EXECWEAVE_FLOW_ROW_GAP});
  }
  for(const [layer,column] of byColumn){
    column.sort((a,b)=>a.y-b.y||String(a.id).localeCompare(String(b.id)));
    let floor=-Infinity;
    for(const seat of column){
      const y=Math.max(seat.y,floor);
      positions.set(seat.id,{x:x[layer],y});
      execweaveFlowPlaced.set(seat.id,{x:x[layer],y});
      const group=nodeElements.get(seat.id);
      if(group)group.setAttribute('transform',`translate(${x[layer]} ${y})`);
      floor=y+execweaveFlowBoxHeight(seat.id)+EXECWEAVE_FLOW_ROW_PAD;
      applied++;
    }
  }
  if(!applied)return 0;
  try{execweaveFlowSyncSpec(execweaveTopology)}catch(_){}
  try{execweaveFlowScrubGeometry(execweaveTopology)}catch(_){}
  try{if(typeof execweaveRecomputePorts==='function')execweaveRecomputePorts(execweaveTopology)}catch(_){}
  try{for(const id of nodeById.keys()){const node=nodeById.get(id);if(node)updateNodeElement(node)}}catch(_){}
  try{for(const edge of edgeById.values())updateEdgeElement(edge)}catch(_){}
  try{execweaveFlowSpreadLabels()}catch(_){}
  return applied;
}
// Edges that share a gap between two columns put their labels at the same midpoint, and
// two relation names written over each other read as neither. A label that lands on one
// already placed moves to the nearest seat that is clear of every placed label and covers
// no more of the boxes than where the router put it: a point further along its own edge,
// or a few pixels above or below. With no such seat it stays where it was.
//
// Returns into one box share one trunk, so the router puts all of their labels on the same
// point. Those labels name one relation into one target; the first stands for all of them
// with their total count, and the rest are folded behind it.
//
// Each pass first undoes what the previous one did, so running it again over labels the
// edges have not redrawn since leaves them where one pass would.
function execweaveFlowSpreadLabels(){
  if(typeof edgeElements==='undefined'||edgeElements.size>600)return;
  for(const els of edgeElements.values()){
    const label=els.label;if(!label)continue;
    if(label.dataset.execweaveFolded==='1'){label.style.display='';delete label.dataset.execweaveFolded}
    const text=label.dataset.execweaveFoldedText;
    if(text!==undefined){
      const [from,to]=JSON.parse(text);if(label.textContent===to)label.textContent=from;
      delete label.dataset.execweaveFoldedText;
    }
    const moved=label.dataset.execweaveSpread;
    if(moved!==undefined){
      const [x0,y0,x,y]=moved.split(',').map(Number);
      if(Number(label.getAttribute('x'))===x&&Number(label.getAttribute('y'))===y){label.setAttribute('x',x0);label.setAttribute('y',y0)}
      delete label.dataset.execweaveSpread;
    }
  }
  const stacks=new Map();
  for(const [id,els] of edgeElements){
    const label=els.label,edge=edgeById.get(id);
    if(!label||!edge||label.getAttribute('aria-hidden')==='true'||label.style.display==='none')continue;
    const x=Number(label.getAttribute('x')),y=Number(label.getAttribute('y'));
    if(!Number.isFinite(x)||!Number.isFinite(y))continue;
    const key=[edge.target,edge.relation,Math.round(x),Math.round(y)].join('\u0000');
    if(!stacks.has(key))stacks.set(key,[]);stacks.get(key).push({label,edge});
  }
  for(const stack of stacks.values()){
    if(stack.length<2)continue;
    const keep=stack[0].label,from=keep.textContent;
    const total=stack.reduce((sum,{edge})=>sum+Math.max(1,Number(edge.count)||1),0);
    const to=`${stack[0].edge.relation} ×${total}`;
    keep.textContent=to;keep.dataset.execweaveFoldedText=JSON.stringify([from,to]);
    for(const {label} of stack.slice(1)){label.style.display='none';label.dataset.execweaveFolded='1'}
  }
  const boxes=[];
  for(const [id,p] of positions)if(nodeById.has(id))boxes.push({x:p.x,y:p.y,w:execweaveWidthOf(id),h:execweaveFlowBoxHeight(id)});
  const clashes=(box,list)=>list.some(other=>box.x<other.x+other.w+1&&box.x+box.w+1>other.x&&box.y<other.y+other.h+1&&box.y+box.h+1>other.y);
  const covered=box=>boxes.reduce((sum,other)=>sum
    +Math.max(0,Math.min(box.x+box.w,other.x+other.w)-Math.max(box.x,other.x))
    *Math.max(0,Math.min(box.y+box.h,other.y+other.h)-Math.max(box.y,other.y)),0);
  const placed=[];
  for(const els of edgeElements.values()){
    const label=els.label,path=els.visible;
    if(!label||!path||label.getAttribute('aria-hidden')==='true'||label.style.display==='none')continue;
    let box;try{box=label.getBBox()}catch(_){continue}
    if(!(box.width>0&&box.height>0))continue;
    const x0=Number(label.getAttribute('x')),y0=Number(label.getAttribute('y'));
    if(!Number.isFinite(x0)||!Number.isFinite(y0))continue;
    const at=(x,y)=>({x:box.x-x0+x,y:box.y-y0+y,w:box.width,h:box.height});
    let x=x0,y=y0;
    if(clashes(at(x0,y0),placed)){
      const limit=covered(at(x0,y0)),seats=[];
      for(let dy=1;dy<=3*box.height;dy++)seats.push([x0,y0-dy],[x0,y0+dy]);
      let length=0;try{length=path.getTotalLength()}catch(_){}
      if(length>0)for(let share=.1;share<.95;share+=.05){
        const point=path.getPointAtLength(length*share);
        seats.push([point.x,point.y-4],[point.x,point.y+box.height+2]);
      }
      seats.sort((a,b)=>Math.hypot(a[0]-x0,a[1]-y0)-Math.hypot(b[0]-x0,b[1]-y0));
      for(const [sx,sy] of seats){
        const seat=at(sx,sy);
        if(!clashes(seat,placed)&&covered(seat)<=limit){x=sx;y=sy;break}
      }
      if(x!==x0||y!==y0){label.setAttribute('x',x);label.setAttribute('y',y);label.dataset.execweaveSpread=[x0,y0,x,y].join(',')}
    }
    placed.push(at(x,y));
  }
}
if(typeof refreshEdgeLabels==='function'){
  // The snapshot draws every edge, then refreshes their labels; only after that pass does
  // every label have a place to be spread from.
  const refreshBase=refreshEdgeLabels;
  refreshEdgeLabels=function(){refreshBase();try{execweaveFlowSpreadLabels()}catch(_){}};
}
try{window.__execweaveFlow={payload:execweaveFlowPayload,columns:execweaveFlowColumns,solve:execweaveFlowSolve,apply:execweaveApplyFlowPositions,spreadLabels:execweaveFlowSpreadLabels}}catch(_){}
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


_ARRANGE_SEAM = "if(arrangeButton)arrangeButton.onclick=()=>execweaveArrangePositions();"
_ARRANGE_REPLACEMENT = (
    # This handler is emitted after the flow script in the final page, so it is the
    # binding that remains active. Apply the flow contract here; only an empty flow falls
    # back to the older arrangement implementation.
    "if(arrangeButton)arrangeButton.onclick=()=>{"
    "try{if(execweaveApplyFlowPositions())return}catch(_){}"
    "execweaveArrangePositions();};"
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
    html = html.replace(_FINAL_LAYOUT_SEAM, _FINAL_LAYOUT_REPLACEMENT, 1)
    if html.count(_ARRANGE_SEAM) != 1:
        raise RuntimeError("flow canvas arrange seam changed")
    return html.replace(_ARRANGE_SEAM, _ARRANGE_REPLACEMENT, 1)
