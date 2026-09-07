from __future__ import annotations

from pathlib import Path

# Injected after LIVE_READABILITY_SCRIPT. Process trees stay left-to-right by spawn
# depth; Arrange and the first computed frame then run a layered LR DAG so visible
# nodes do not overlap. Dagre is vendored; Fit remains the camera button.

_DAGRE_JS = (Path(__file__).resolve().parent / "vendor" / "dagre.min.js").read_text(
    encoding="utf-8"
)

_LIVE_PROCESS_LAYOUT_BODY = r"""
(()=>{
const PROCESS_COL_GAP=48;
const PROCESS_ROW_GAP=72;
function isProcess(node){
  const type=String(node?.type||'').toLowerCase();
  return type==='process'||type==='session'||type==='runtime';
}
function processParentEdges(){
  const parents=new Map();
  for(const edge of edgeById.values()){
    const relation=String(edge?.relation||'').toUpperCase();
    if(relation!=='SPAWNED'&&relation!=='LAUNCHED')continue;
    const source=nodeById.get(edge.source),target=nodeById.get(edge.target);
    if(!isProcess(source)||!isProcess(target))continue;
    const current=parents.get(target.id);
    const moment=Number.isInteger(edge.first_sequence)?edge.first_sequence:Number.MAX_SAFE_INTEGER;
    if(!current||moment<current.moment)parents.set(target.id,{parent:source.id,moment});
  }
  return parents;
}
function execweaveLayoutProcessTree(topo){
  if(!topo||!topo.spec)return topo;
  const processes=[...nodeById.values()].filter(node=>isProcess(node)&&topo.spec.has(node.id));
  if(processes.length<2)return topo;
  const parentOf=processParentEdges();
  const children=new Map();
  for(const node of processes){
    const parent=parentOf.get(node.id)?.parent;
    if(!parent||!topo.spec.has(parent))continue;
    if(!children.has(parent))children.set(parent,[]);
    children.get(parent).push(node.id);
  }
  for(const list of children.values()){
    list.sort((a,b)=>{
      const am=parentOf.get(a)?.moment??Number.MAX_SAFE_INTEGER;
      const bm=parentOf.get(b)?.moment??Number.MAX_SAFE_INTEGER;
      return am-bm||String(nodeById.get(a)?.name||a).localeCompare(String(nodeById.get(b)?.name||b));
    });
  }
  const roots=processes.filter(node=>!parentOf.has(node.id)||!topo.spec.has(parentOf.get(node.id).parent)).map(node=>node.id);
  roots.sort((a,b)=>String(nodeById.get(a)?.name||a).localeCompare(String(nodeById.get(b)?.name||b)));
  const depth=new Map();
  const order=[];
  const walk=(id,level)=>{
    if(depth.has(id))return;
    depth.set(id,level);
    order.push(id);
    for(const child of(children.get(id)||[]))walk(child,level+1);
  };
  for(const id of roots)walk(id,0);
  for(const node of processes)if(!depth.has(node.id))walk(node.id,0);
  const colWidth=new Map();
  for(const id of order){
    const level=depth.get(id)||0;
    colWidth.set(level,Math.max(colWidth.get(level)||EXECWEAVE_NODE_W,execweaveWidthOf(id)));
  }
  const colX=new Map();
  let x=typeof execweaveLaneXOf==='function'?execweaveLaneXOf('runtime'):0;
  const maxDepth=Math.max(0,...depth.values());
  for(let level=0;level<=maxDepth;level++){
    colX.set(level,x);
    x+=(colWidth.get(level)||EXECWEAVE_NODE_W)+PROCESS_COL_GAP;
  }
  const subtree=new Map();
  const measure=id=>{
    const kids=children.get(id)||[];
    if(!kids.length){subtree.set(id,1);return 1}
    let size=0;for(const child of kids)size+=measure(child);
    subtree.set(id,Math.max(1,size));return subtree.get(id);
  };
  for(const id of roots)measure(id);
  const placed=new Set();
  let row=0;
  const place=(id,rowStart)=>{
    if(placed.has(id))return;
    placed.add(id);
    const kids=children.get(id)||[];
    const spec=topo.spec.get(id);if(!spec)return;
    const span=subtree.get(id)||1;
    spec.x=colX.get(depth.get(id)||0)||spec.x;
    spec.y=100+rowStart*PROCESS_ROW_GAP+Math.max(0,span-1)*PROCESS_ROW_GAP/2;
    spec.processDepth=depth.get(id)||0;
    let childRow=rowStart;
    for(const child of kids){
      place(child,childRow);
      childRow+=subtree.get(child)||1;
    }
  };
  for(const id of roots){
    place(id,row);
    row+=subtree.get(id)||1;
  }
  return topo;
}
function execweaveNodeType(node){return String(node?.type||'').toLowerCase()}
function execweaveIsEndpointNode(node){
  const type=execweaveNodeType(node);
  return type.includes('network')||type.includes('endpoint')||type.includes('socket')||type.includes('host')||node?.name==='External';
}
function execweaveNeighborIds(id,topo){
  const out=[];
  for(const edge of edgeById.values()){
    if(!topo.spec.has(edge.source)||!topo.spec.has(edge.target))continue;
    if(edge.source===id)out.push(edge.target);
    else if(edge.target===id)out.push(edge.source);
  }
  return out;
}
function execweaveAlignRelatedY(id,topo,prefer){
  const spec=topo.spec.get(id);if(!spec)return;
  const ys=[];
  for(const other of execweaveNeighborIds(id,topo)){
    const node=nodeById.get(other),os=topo.spec.get(other);
    if(!node||!os)continue;
    const type=execweaveNodeType(node);
    if(prefer&&![...prefer].some(token=>type.includes(token)||(token==='agent'&&type==='agent')))continue;
    ys.push(os.y);
  }
  if(!ys.length)return;
  spec.y=ys.reduce((sum,value)=>sum+value,0)/ys.length;
}
function execweavePullBesideNeighbors(id,topo,prefer){
  const spec=topo.spec.get(id);if(!spec)return;
  let right=-Infinity,hits=0;
  for(const other of execweaveNeighborIds(id,topo)){
    const node=nodeById.get(other),os=topo.spec.get(other);
    if(!node||!os)continue;
    const type=execweaveNodeType(node);
    if(prefer&&![...prefer].some(token=>type.includes(token)||(token==='agent'&&type==='agent')))continue;
    right=Math.max(right,os.x+(typeof execweaveWidthOf==='function'?execweaveWidthOf(other):EXECWEAVE_NODE_W));
    hits++;
  }
  if(!hits||!Number.isFinite(right))return;
  const desired=right+PROCESS_COL_GAP;
  if(spec.x>desired)spec.x=desired;
}
function execweaveSeparateLane(topo){
  const byLane=new Map();
  for(const [id,spec] of topo.spec){
    if(!byLane.has(spec.lane))byLane.set(spec.lane,[]);
    byLane.get(spec.lane).push(id);
  }
  for(const ids of byLane.values()){
    ids.sort((a,b)=>(topo.spec.get(a).y-topo.spec.get(b).y)||String(a).localeCompare(String(b)));
    for(let index=1;index<ids.length;index++){
      const prev=topo.spec.get(ids[index-1]),cur=topo.spec.get(ids[index]);
      const prevH=typeof execweaveHeightOf==='function'?execweaveHeightOf(ids[index-1]):EXECWEAVE_NODE_H;
      const floor=prev.y+prevH+24;
      if(cur.y<floor)cur.y=floor;
    }
  }
}
function execweaveLayoutRelated(topo){
  if(!topo||!topo.spec)return topo;
  for(const node of nodeById.values()){
    if(!topo.spec.has(node.id))continue;
    const type=execweaveNodeType(node);
    if(type==='agent'&&!execweaveIsRoot(node))execweaveAlignRelatedY(node.id,topo,['agent']);
    else if(type.includes('tool'))execweaveAlignRelatedY(node.id,topo,['agent']);
    else if(type.includes('file')||type.includes('path'))execweaveAlignRelatedY(node.id,topo,['agent','process']);
    else if(execweaveIsEndpointNode(node))execweaveAlignRelatedY(node.id,topo,['process','session','runtime','agent']);
  }
  for(const node of nodeById.values()){
    if(!topo.spec.has(node.id))continue;
    const type=execweaveNodeType(node);
    if(type.includes('tool')||type.includes('model'))execweavePullBesideNeighbors(node.id,topo,['agent']);
    else if(execweaveIsEndpointNode(node))execweavePullBesideNeighbors(node.id,topo,['process','session','runtime']);
  }
  execweaveSeparateLane(topo);
  return topo;
}
const EXECWEAVE_DAG_GAP=24;
function execweaveEdgeKey(source,target){return`${source}\0${target}`}
function execweaveRecomputePorts(topo){
  if(!topo||!topo.spec)return topo;
  const sourceEdges=new Map(),targetEdges=new Map();
  for(const edge of edgeById.values()){
    if(!topo.spec.has(edge.source)||!topo.spec.has(edge.target))continue;
    if(!sourceEdges.has(edge.source))sourceEdges.set(edge.source,[]);
    sourceEdges.get(edge.source).push(edge);
    if(!targetEdges.has(edge.target))targetEdges.set(edge.target,[]);
    targetEdges.get(edge.target).push(edge);
  }
  const sourcePort=new Map(),targetPort=new Map();
  for(const list of sourceEdges.values()){
    list.sort((a,b)=>{
      const at=topo.spec.get(a.target),bt=topo.spec.get(b.target);
      return(at?.y??0)-(bt?.y??0)||(at?.x??0)-(bt?.x??0)||edgeId(a).localeCompare(edgeId(b));
    });
    list.forEach((edge,index)=>sourcePort.set(edgeId(edge),{index,total:list.length}));
  }
  for(const list of targetEdges.values()){
    list.sort((a,b)=>{
      const as=topo.spec.get(a.source),bs=topo.spec.get(b.source);
      return(as?.y??0)-(bs?.y??0)||(as?.x??0)-(bs?.x??0)||edgeId(a).localeCompare(edgeId(b));
    });
    list.forEach((edge,index)=>targetPort.set(edgeId(edge),{index,total:list.length}));
  }
  topo.sourcePort=sourcePort;
  topo.targetPort=targetPort;
  return topo;
}
function execweaveSeparateOverlappingNodes(topo){
  if(!topo||!topo.spec)return false;
  let shifted=false;
  for(let pass=0;pass<32;pass++){
    const boxes=[...topo.spec.keys()].filter(id=>nodeById.has(id)).map(id=>({
      id,
      spec:topo.spec.get(id),
      x:topo.spec.get(id).x,
      y:topo.spec.get(id).y,
      w:execweaveWidthOf(id),
      h:execweaveHeightOf(id),
    }));
    boxes.sort((a,b)=>a.y-b.y||a.x-b.x||String(a.id).localeCompare(String(b.id)));
    let moved=false;
    for(let i=0;i<boxes.length;i++){
      for(let j=0;j<i;j++){
        const A=boxes[j],B=boxes[i];
        const ix=Math.max(0,Math.min(A.x+A.w,B.x+B.w)-Math.max(A.x,B.x));
        const iy=Math.max(0,Math.min(A.y+A.h,B.y+B.h)-Math.max(A.y,B.y));
        if(ix*iy<=0)continue;
        B.spec.y=A.y+A.h+EXECWEAVE_DAG_GAP;
        B.y=B.spec.y;
        moved=true;
        shifted=true;
      }
    }
    if(!moved)break;
  }
  return shifted;
}
function execweaveLayoutDirectedGraph(topo){
  if(!topo||!topo.spec)return topo;
  topo.routePoints=new Map();
  const engine=(typeof dagre!=='undefined'&&dagre&&dagre.graphlib&&typeof dagre.layout==='function')?dagre:null;
  if(!engine){
    console.warn('execweaveLayoutDirectedGraph: dagre unavailable, using process-tree layout');
    execweaveSeparateLane(topo);
    return topo;
  }
  try{
    const graph=new engine.graphlib.Graph();
    graph.setGraph({rankdir:'LR',nodesep:EXECWEAVE_DAG_GAP,ranksep:48,marginx:16,marginy:16,edgesep:16});
    graph.setDefaultEdgeLabel(()=>({}));
    const ids=[];
    for(const id of topo.spec.keys()){
      if(!nodeById.has(id))continue;
      graph.setNode(id,{width:execweaveWidthOf(id),height:execweaveHeightOf(id)});
      ids.push(id);
    }
    const seen=new Set();
    for(const edge of edgeById.values()){
      if(!topo.spec.has(edge.source)||!topo.spec.has(edge.target)||edge.source===edge.target)continue;
      const key=execweaveEdgeKey(edge.source,edge.target);
      if(seen.has(key))continue;
      seen.add(key);
      graph.setEdge(edge.source,edge.target);
    }
    // dagre.layout runs Sugiyama: rank → order (crossing minimization) → position → edge points.
    engine.layout(graph);
    for(const id of ids){
      const placed=graph.node(id),spec=topo.spec.get(id);
      if(!placed||!spec)continue;
      spec.x=placed.x-placed.width/2;
      spec.y=placed.y-placed.height/2;
    }
    // Keep Sugiyama step 4 (routing points). First/last are node-box hits; midpoints bend around ranks.
    for(const edge of graph.edges()){
      const label=graph.edge(edge);
      const points=label&&Array.isArray(label.points)?label.points:[];
      if(points.length<2)continue;
      topo.routePoints.set(execweaveEdgeKey(edge.v,edge.w),points.map(point=>({x:point.x,y:point.y})));
    }
  }catch(error){
    console.warn('execweaveLayoutDirectedGraph: dagre failed, using process-tree layout',error);
    execweaveSeparateLane(topo);
  }
  return topo;
}
function execweaveRetargetRoutePoints(topo,dagrePlacement){
  if(!topo||!topo.routePoints||!dagrePlacement)return;
}
function execweaveRestoreSemanticLayoutConstraints(topo,preferred,dagrePlacement){
  if(!topo||!topo.spec||!preferred||!dagrePlacement)return topo;
  if(typeof nodeById==='undefined'||typeof edgeById==='undefined'||typeof execweaveComponents!=='function')return topo;
  topo.secondaryPackedIds=new Set();
  const nodes=[...nodeById.values()],edges=[...edgeById.values()];
  const componentOf=execweaveComponents(nodes,edges);

  // X constraint: Semantic lanes define bounding constraints.
  // Dynamically propagate corridor lower bounds across semantic ranks so Dagre
  // horizontal positions are retained within their architectural corridors.
  const laneRank = {
    runtime: 0,
    root: 1,
    agent: 2,
    model: 3,
    tool: 4,
    file: 5,
    endpoint: 6,
    other: 6
  };

  // Group non-process nodes by semantic rank
  const nodesByRank = new Map();
  for (const [id, before] of preferred) {
    const node = nodeById.get(id);
    if (!node) continue;
    const type = String(node.type || '').toLowerCase();
    if (type === 'process' || type === 'session' || type === 'runtime') continue;
    const lane = topo.spec.get(id)?.lane || before.lane || 'other';
    const rank = laneRank[lane] ?? 3;
    if (!nodesByRank.has(rank)) nodesByRank.set(rank, []);
    nodesByRank.get(rank).push(id);
  }

  // Handle process-like nodes first (pinned to process-tree coordinates)
  let maxProcessRight = 0;
  for (const [id, before] of preferred) {
    const after = topo.spec.get(id), node = nodeById.get(id);
    if (!after || !node) continue;
    const type = String(node.type || '').toLowerCase();
    if (type === 'process' || type === 'session' || type === 'runtime') {
      if (Number.isFinite(before.x)) after.x = before.x;
      const pw = topo.width?.get(id) || (typeof execweaveWidthOf === 'function' ? execweaveWidthOf(id) : 160);
      const px = Number.isFinite(after.x) ? after.x : 0;
      maxProcessRight = Math.max(maxProcessRight, px + pw);
    }
  }

  // Propagate corridor lower bounds across ranks:
  // rank 1 (root) < rank 2 (agent) < rank 3 (model) < rank 4 (tool) < rank 5 (file) < rank 6 (endpoint)
  let minAllowedX = maxProcessRight;
  for (let r = 1; r <= 6; r++) {
    const ids = nodesByRank.get(r) || [];
    if (!ids.length) continue;
    let rankMaxX = minAllowedX;
    for (const id of ids) {
      const after = topo.spec.get(id);
      const before = preferred.get(id);
      const dagreX = dagrePlacement.get(id)?.x;
      const laneX = topo.laneX && Number.isFinite(topo.laneX[after?.lane]) ? topo.laneX[after.lane] : before?.x;
      if (!after) continue;

      const isBundledTarget = edges.some(e => e.target === id && topo.bundleByEdge?.get(edgeId(e))?.size > 1);
      const candidateX = isBundledTarget && Number.isFinite(laneX) ? laneX : dagreX;

      if (Number.isFinite(candidateX) && candidateX >= minAllowedX) {
        after.x = candidateX;
      } else if (Number.isFinite(before?.x) && before.x >= minAllowedX) {
        after.x = before.x;
      } else {
        after.x = minAllowedX;
      }
      rankMaxX = Math.max(rankMaxX, after.x);
    }
    minAllowedX = rankMaxX + 1;
  }

  // Y constraint: Dagre coordinates optimize positions within semantic lane/component bounds
  const reorderable=new Set(['agent','model','tool','file','endpoint','other']);
  const groups=new Map();
  for(const [id,before] of preferred){
    const spec=topo.spec.get(id);
    if(!spec)continue;
    const lane=spec.lane||before.lane;
    if(!reorderable.has(lane)){
      spec.y=before.y;
      continue;
    }
    const component=componentOf.has(id)?componentOf.get(id):-1;
    const key=`${lane}\0${component}`;
    if(!groups.has(key))groups.set(key,[]);
    groups.get(key).push(id);
  }

  for(const ids of groups.values()){
    const slots=ids.map(id=>preferred.get(id)?.y).filter(Number.isFinite).sort((a,b)=>a-b);
    if(!slots.length)continue;
    const ordered=[...ids].sort((a,b)=>{
      const ay=dagrePlacement.get(a)?.y??0,by=dagrePlacement.get(b)?.y??0;
      return ay-by||String(a).localeCompare(String(b));
    });
    const minY=slots[0],maxY=slots[slots.length-1];
    const nodeH=typeof execweaveHeightOf==='function'?execweaveHeightOf(ids[0]):(typeof EXECWEAVE_NODE_H!=='undefined'?EXECWEAVE_NODE_H:50);
    const minStep=nodeH+16;
    let prevY=-Infinity;

    ordered.forEach((id,index)=>{
      const spec=topo.spec.get(id);
      if(!spec)return;
      const targetY=dagrePlacement.get(id)?.y;
      const slotY=slots[index];
      if(Number.isFinite(targetY)&&targetY>=minY-20&&targetY<=maxY+30&&targetY>=prevY+minStep){
        spec.y=targetY;
      }else if(Number.isFinite(targetY)){
        const bounded=Math.max(prevY+minStep,Math.min(maxY+30,Math.max(minY,targetY)));
        spec.y=bounded;
      }else if(Number.isFinite(slotY)){
        spec.y=slotY;
      }
      prevY=spec.y;
    });
  }

  // Secondary components 2D grid packing (wrapping with spineWidth)
  if(!componentOf.size)return topo;
  const sizes=new Map();
  for(const value of componentOf.values())sizes.set(value,(sizes.get(value)||0)+1);
  const roots=nodes.filter(typeof execweaveIsRoot==='function'?execweaveIsRoot:()=>false).sort(typeof execweaveStableNodeSort==='function'?execweaveStableNodeSort:(a,b)=>String(a.id).localeCompare(String(b.id)));
  let primary=roots.length?componentOf.get(roots[0].id):undefined;
  if(primary===undefined){
    let best=-1;
    for(const [value,size] of [...sizes.entries()].sort((a,b)=>a[0]-b[0]))if(size>best){best=size;primary=value}
  }
  const agentIds=new Set(nodes.filter(node=>node?.type==='agent').map(node=>node.id));
  const spineComponents=new Set([...componentOf.entries()].filter(([id])=>agentIds.has(id)).map(([,value])=>value));
  if(primary!==undefined)spineComponents.add(primary);

  let spineLeft=Infinity,spineRight=-Infinity,spineFloor=-Infinity;
  for(const [id,value] of componentOf){
    if(!spineComponents.has(value))continue;
    const spec=topo.spec.get(id);
    if(!spec)continue;
    const w=typeof execweaveWidthOf==='function'?execweaveWidthOf(id):(typeof EXECWEAVE_NODE_W!=='undefined'?EXECWEAVE_NODE_W:160);
    const h=typeof execweaveHeightOf==='function'?execweaveHeightOf(id):(typeof EXECWEAVE_NODE_H!=='undefined'?EXECWEAVE_NODE_H:50);
    spineLeft=Math.min(spineLeft,spec.x);
    spineRight=Math.max(spineRight,spec.x+w);
    spineFloor=Math.max(spineFloor,spec.y+h);
  }
  if(!Number.isFinite(spineLeft)){spineLeft=0;spineRight=600;spineFloor=100}
  const spineWidth=Math.max(600,spineRight-spineLeft);
  const bandGap=typeof EXECWEAVE_BAND_GAP!=='undefined'?EXECWEAVE_BAND_GAP:170;

  const secondary=[...sizes.keys()].filter(value=>!spineComponents.has(value)).sort((a,b)=>a-b);
  const compBoxes=secondary.map(value=>{
    const members=[...componentOf.entries()].filter(entry=>entry[1]===value).map(entry=>entry[0]);
    let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;
    for(const id of members){
      const s=topo.spec.get(id);
      if(s){
        const w=typeof execweaveWidthOf==='function'?execweaveWidthOf(id):(typeof EXECWEAVE_NODE_W!=='undefined'?EXECWEAVE_NODE_W:160);
        const h=typeof execweaveHeightOf==='function'?execweaveHeightOf(id):(typeof EXECWEAVE_NODE_H!=='undefined'?EXECWEAVE_NODE_H:50);
        minX=Math.min(minX,s.x);maxX=Math.max(maxX,s.x+w);
        minY=Math.min(minY,s.y);maxY=Math.max(maxY,s.y+h);
      }
    }
    return{value,members,minX,maxX,minY,maxY,w:maxX-minX,h:maxY-minY};
  }).filter(box=>Number.isFinite(box.minX));

  let cursorX=spineLeft,cursorY=spineFloor+bandGap,rowHeight=0;
  for(const box of compBoxes){
    if(cursorX>spineLeft&&cursorX+box.w>spineLeft+spineWidth){
      cursorX=spineLeft;cursorY+=rowHeight+bandGap;rowHeight=0;
    }
    const shiftX=cursorX-box.minX,shiftY=cursorY-box.minY;
    for(const id of box.members){
      const s=topo.spec.get(id);if(s){s.x+=shiftX;s.y+=shiftY;topo.secondaryPackedIds.add(id)}
    }
    cursorX+=box.w+bandGap;
    rowHeight=Math.max(rowHeight,box.h);
  }
  return topo;
}
function execweaveApplyDirectedGraph(topo){
  if(!topo||!topo.spec)return topo;

  // Stage 1: PRE_DAGRE validation snapshot
  const preDagre=new Map();
  for(const [id,spec] of topo.spec.entries()){
    preDagre.set(id,{x:spec.x,y:spec.y,lane:spec.lane,rank:spec.rank,order:spec.order});
  }

  // Stage 2: POST_DAGRE layout
  execweaveLayoutDirectedGraph(topo);
  const postDagre=new Map();
  for(const [id,spec] of topo.spec.entries()){
    postDagre.set(id,{x:spec.x,y:spec.y,lane:spec.lane});
  }

  // Stage 3: POST_FINAL_CONSTRAINT integration
  execweaveRestoreSemanticLayoutConstraints(topo,preDagre,postDagre);
  execweaveSeparateOverlappingNodes(topo);
  execweaveRetargetRoutePoints(topo,postDagre);
  execweaveRecomputePorts(topo);

  const postFinalConstraint=new Map();
  for(const [id,spec] of topo.spec.entries()){
    postFinalConstraint.set(id,{x:spec.x,y:spec.y,lane:spec.lane});
  }

  // Measure Dagre 2D retention rates
  let xRetained=0,yRetained=0,total=postDagre.size;
  for(const [id,dagrePos] of postDagre.entries()){
    const finalPos=postFinalConstraint.get(id);
    if(!finalPos)continue;
    if(Math.abs(finalPos.x-dagrePos.x)<=2.0)xRetained++;
    if(Math.abs(finalPos.y-dagrePos.y)<=2.0)yRetained++;
  }
  const xRetentionRate=total>0?(xRetained/total)*100:0;
  const yRetentionRate=total>0?(yRetained/total)*100:0;

  const stagesComplete = preDagre.size === total && postDagre.size === total && postFinalConstraint.size === total;
  const retentionHealthy = total > 0 ? (xRetained > 0 && yRetained > 0) : true;
  const pipelineStatus = (stagesComplete && retentionHealthy) ? 'PASS' : 'FAIL';

  topo.dagrePipeline={
    stages:{
      PRE_DAGRE:preDagre,
      POST_DAGRE:postDagre,
      POST_FINAL_CONSTRAINT:postFinalConstraint,
    },
    metrics:{
      totalNodes:total,
      xRetained,
      yRetained,
      DAGRE_X_RETENTION_RATE:xRetentionRate,
      DAGRE_Y_RETENTION_RATE:yRetentionRate,
      DAGRE_SEMANTIC_CONSTRAINT_PIPELINE:pipelineStatus,
    },
  };
  if(typeof window!=='undefined'){
    window.__execweaveDagrePipeline=topo.dagrePipeline;
  }
  return topo;
}
function execweaveRouteFromPoints(edge,points){
  const sp=(typeof positions!=='undefined'&&positions.get(edge.source))||(execweaveTopology?.spec&&execweaveTopology.spec.get(edge.source))||{x:0,y:0};
  const tp=(typeof positions!=='undefined'&&positions.get(edge.target))||(execweaveTopology?.spec&&execweaveTopology.spec.get(edge.target))||{x:0,y:0};
  const sourcePort=execweaveTopology.sourcePort.get(edgeId(edge)),targetPort=execweaveTopology.targetPort.get(edgeId(edge));
  const sourceSpec=execweaveTopology.spec.get(edge.source)||{},targetSpec=execweaveTopology.spec.get(edge.target)||{};
  const forward=(targetSpec.rank??0)>=(sourceSpec.rank??0);
  const sx=forward?sp.x+execweaveWidthOf(edge.source):sp.x;
  const tx=forward?tp.x:tp.x+execweaveWidthOf(edge.target);
  const sy=execweavePortY(sp,sourcePort,edge.source),ty=execweavePortY(tp,targetPort,edge.target);
  const distance=Math.abs(tx-sx),bend=Math.max(44,distance*.42),sign=forward?1:-1;
  const p0={x:sx,y:sy},p1={x:sx+sign*bend,y:sy},p2={x:tx-sign*bend,y:ty},p3={x:tx,y:ty};
  const cubic=t=>{
    const u=1-t;
    return{
      x:u*u*u*p0.x+3*u*u*t*p1.x+3*u*t*t*p2.x+t*t*t*p3.x,
      y:u*u*u*p0.y+3*u*u*t*p1.y+3*u*t*t*p2.y+t*t*t*p3.y,
    };
  };
  let d=`M ${sx} ${sy}`;
  for(let index=1;index<8;index++){
    const point=cubic(index/8);d+=` L ${point.x} ${point.y}`;
  }
  d+=` L ${tx} ${ty}`;
  const labelPoint=cubic(.5);
  return{d,labelX:labelPoint.x,labelY:labelPoint.y-8,kind:execweaveIsSpawn(edge)?'spawn':(forward?'forward':'reverse'),bundle:null};
}
const execweaveBuildTopologyBase=execweaveBuildTopology;
execweaveBuildTopology=function(){return execweaveApplyDirectedGraph(execweaveLayoutRelated(execweaveLayoutProcessTree(execweaveBuildTopologyBase())))};
if(typeof window!=='undefined'){
  window.execweaveLayoutDirectedGraph=execweaveLayoutDirectedGraph;
  window.execweaveSeparateOverlappingNodes=execweaveSeparateOverlappingNodes;
  window.execweaveRecomputePorts=execweaveRecomputePorts;
  window.execweaveApplyDirectedGraph=execweaveApplyDirectedGraph;
  window.execweaveRestoreSemanticLayoutConstraints=execweaveRestoreSemanticLayoutConstraints;
}
const execweaveRouteBase=execweaveRoute;
execweaveRoute=function(edge){
  const bundle=execweaveTopology.bundleByEdge.get(edgeId(edge));
  if(bundle&&bundle.size>1)return execweaveRouteBase(edge);
  if(execweaveIsStopped(edge))return execweaveRouteBase(edge);
  const points=execweaveTopology.routePoints&&execweaveTopology.routePoints.get(execweaveEdgeKey(edge.source,edge.target));
  if(points&&points.length>=2)return execweaveRouteFromPoints(edge,points);
  const sp=positions.get(edge.source)||{x:0,y:0},tp=positions.get(edge.target)||{x:0,y:0};
  const sameColumn=Math.abs(sp.x-tp.x)<8;
  if(!sameColumn)return execweaveRouteBase(edge);
  const sourcePort=execweaveTopology.sourcePort.get(edgeId(edge)),targetPort=execweaveTopology.targetPort.get(edgeId(edge));
  const sx=sp.x+execweaveWidthOf(edge.source),sy=execweavePortY(sp,sourcePort,edge.source);
  const tx=tp.x+execweaveWidthOf(edge.target),ty=execweavePortY(tp,targetPort,edge.target);
  const offset=36+((sourcePort?.index||0)%8)*12;
  const rail=Math.max(sx,tx)+offset;
  return{d:`M ${sx} ${sy} H ${rail} V ${ty} H ${tx}`,labelX:rail+8,labelY:(sy+ty)/2,kind:'column',bundle:null};
};
function execweaveIsNodeVisible(id){
  if(typeof nodeById==='undefined'||!nodeById.has(id))return false;
  if(typeof nodeElements==='undefined'||!nodeElements.has(id))return true;
  const el=nodeElements.get(id);
  if(!el)return false;
  if(el.classList?.contains('dim'))return false;
  if(el.style?.display==='none'||el.hasAttribute?.('hidden'))return false;
  return true;
}
function execweaveIsEdgeVisible(edge){
  if(!execweaveIsNodeVisible(edge.source)||!execweaveIsNodeVisible(edge.target))return false;
  if(typeof edgeElements==='undefined')return true;
  const id=typeof edgeId==='function'?edgeId(edge):edge.id;
  const els=edgeElements.get(id);
  if(!els)return true;
  if(els.visible?.classList?.contains('dim')||els.visible?.style?.display==='none'||els.visible?.hasAttribute?.('hidden'))return false;
  return true;
}
function execweaveArrangePositions(){
  execweaveTopology=execweaveBuildTopology();
  const next=new Map();
  const visibleIds=typeof nodeById!=='undefined'?[...nodeById.keys()].filter(execweaveIsNodeVisible):[];
  const ordered=visibleIds.sort((a,b)=>{
    const av=execweaveTopology.spec.get(a)||{},bv=execweaveTopology.spec.get(b)||{};
    return Number(av.rank||0)-Number(bv.rank||0)||Number(av.processDepth||0)-Number(bv.processDepth||0)||Number(av.order||0)-Number(bv.order||0)||String(a).localeCompare(String(b));
  });
  for(const id of ordered){
    const spec=execweaveTopology.spec.get(id);
    next.set(id,spec?{x:spec.x,y:spec.y}:execweavePlaceStable(id,execweaveDesiredPosition(id),next,id));
  }
  if(typeof positions!=='undefined'){
    for(const [id,p] of positions){
      if(!next.has(id))next.set(id,p);
    }
  }
  positions=next;layerRows=new Map();
  for(const [id,p] of positions){
    const spec=execweaveTopology.spec.get(id);
    if(spec)layerRows.set(spec.rank,Math.max(layerRows.get(spec.rank)||0,spec.order+1));
    const group=typeof nodeElements!=='undefined'?nodeElements.get(id):null;
    if(group)group.setAttribute('transform',`translate(${p.x} ${p.y})`);
    const node=typeof nodeById!=='undefined'?nodeById.get(id):null;
    if(node&&typeof updateNodeElement==='function')updateNodeElement(node);
  }
  const visibleEdges=typeof edgeById!=='undefined'?[...edgeById.values()].filter(execweaveIsEdgeVisible):[];
  for(const edge of visibleEdges)if(typeof updateEdgeElement==='function')updateEdgeElement(edge);
  if(typeof svg!=='undefined'&&svg.classList)svg.classList.toggle('execweave-crowded',execweaveTopology.crowded);
  if(typeof applySearch==='function')applySearch();
  if(typeof updateJumpLatest==='function')updateJumpLatest();
  return new Map(positions);
}
execweaveArrangeGraph=execweaveArrangePositions;
if(typeof window!=='undefined'){
  window.__execweaveArrangeGraph=execweaveArrangePositions;
  window.execweaveArrangePositions=execweaveArrangePositions;
  window.execweaveArrangeGraph=execweaveArrangePositions;
}
const arrangeButton=typeof document!=='undefined'?document.getElementById('arrange'):null;
if(arrangeButton)arrangeButton.onclick=()=>execweaveArrangePositions();
function execweaveWriteDirectedPositions(topo){
  const next=new Map();
  for(const id of nodeById.keys()){
    const spec=topo.spec.get(id);
    const packed=topo.secondaryPackedIds?.has(id);
    const laneX=(topo.laneX&&spec?.lane&&Number.isFinite(topo.laneX[spec.lane]))?topo.laneX[spec.lane]:spec?.x;
    // Connected semantic lanes retain their established X contract. Only
    // disconnected components use the final 2D packing X; forcing those back
    // to the lane origin would stack every orphan node on the same rectangle.
    const initialX=packed?spec?.x:laneX;
    next.set(id,spec?{x:initialX,y:spec.y}:execweaveDesiredPosition(id));
  }
  positions=next;layerRows=new Map();
  for(const [id,p] of positions){
    const spec=topo.spec.get(id);
    if(spec)layerRows.set(spec.rank,Math.max(layerRows.get(spec.rank)||0,spec.order+1));
    const group=nodeElements.get(id);
    if(group)group.setAttribute('transform',`translate(${p.x} ${p.y})`);
    const node=nodeById.get(id);
    if(node)updateNodeElement(node);
  }
  for(const edge of edgeById.values())updateEdgeElement(edge);
  svg.classList.toggle('execweave-crowded',!!topo.crowded);
}
const execweaveFullLayoutBase=fullLayout;
fullLayout=function(){
  const prior=positions;
  const incoming=[...nodeById.keys()].some(id=>!prior.has(id));
  if(prior.size&&!incoming){execweaveFullLayoutBase();return}
  execweaveTopology=execweaveBuildTopology();
  execweaveWriteDirectedPositions(execweaveTopology);
};
const execweavePlaceAddedBase=placeAddedNodes;
placeAddedNodes=function(ids){
  const incoming=(ids||[]).filter(id=>nodeById.has(id)&&!positions.has(id));
  if(!incoming.length){execweavePlaceAddedBase(ids);return}
  execweaveTopology=execweaveBuildTopology();
  execweaveWriteDirectedPositions(execweaveTopology);
};
})();
""".strip()

LIVE_PROCESS_LAYOUT_SCRIPT = f"{_DAGRE_JS}\n{_LIVE_PROCESS_LAYOUT_BODY}"
