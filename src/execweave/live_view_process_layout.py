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
function execweaveApplyDirectedGraph(topo){
  execweaveLayoutDirectedGraph(topo);
  execweaveSeparateOverlappingNodes(topo);
  // Ports were assigned before dagre moved nodes; rebuild against final Y so order matches crossing minimization.
  execweaveRecomputePorts(topo);
  return topo;
}
function execweaveRouteFromPoints(edge,points){
  const sp=positions.get(edge.source)||{x:0,y:0},tp=positions.get(edge.target)||{x:0,y:0};
  const sourcePort=execweaveTopology.sourcePort.get(edgeId(edge)),targetPort=execweaveTopology.targetPort.get(edgeId(edge));
  const sourceSpec=execweaveTopology.spec.get(edge.source)||{},targetSpec=execweaveTopology.spec.get(edge.target)||{};
  const forward=(targetSpec.x??0)>=(sourceSpec.x??0);
  const sx=forward?sp.x+execweaveWidthOf(edge.source):sp.x;
  const tx=forward?tp.x:tp.x+execweaveWidthOf(edge.target);
  const sy=execweavePortY(sp,sourcePort,edge.source),ty=execweavePortY(tp,targetPort,edge.target);
  const mid=points.length>2?points.slice(1,-1):[];
  let d=`M ${sx} ${sy}`;
  for(const point of mid)d+=` L ${point.x} ${point.y}`;
  d+=` L ${tx} ${ty}`;
  const labelPoint=mid.length?mid[Math.floor(mid.length/2)]:{x:(sx+tx)/2,y:(sy+ty)/2};
  return{d,labelX:labelPoint.x,labelY:labelPoint.y-8,kind:execweaveIsSpawn(edge)?'spawn':(forward?'forward':'reverse'),bundle:null};
}
const execweaveBuildTopologyBase=execweaveBuildTopology;
execweaveBuildTopology=function(){return execweaveApplyDirectedGraph(execweaveLayoutRelated(execweaveLayoutProcessTree(execweaveBuildTopologyBase())))};
window.execweaveLayoutDirectedGraph=execweaveLayoutDirectedGraph;
window.execweaveSeparateOverlappingNodes=execweaveSeparateOverlappingNodes;
window.execweaveRecomputePorts=execweaveRecomputePorts;
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
function execweaveArrangePositions(){
  execweaveTopology=execweaveBuildTopology();
  const next=new Map();
  const ordered=[...nodeById.keys()].sort((a,b)=>{
    const av=execweaveTopology.spec.get(a)||{},bv=execweaveTopology.spec.get(b)||{};
    return Number(av.rank||0)-Number(bv.rank||0)||Number(av.processDepth||0)-Number(bv.processDepth||0)||Number(av.order||0)-Number(bv.order||0)||String(a).localeCompare(String(b));
  });
  for(const id of ordered)next.set(id,execweavePlaceStable(id,execweaveDesiredPosition(id),next,id));
  execweaveLayoutDirectedGraph(execweaveTopology);
  execweaveSeparateOverlappingNodes(execweaveTopology);
  execweaveRecomputePorts(execweaveTopology);
  for(const id of ordered){
    const spec=execweaveTopology.spec.get(id);
    if(spec)next.set(id,{x:spec.x,y:spec.y});
  }
  positions=next;layerRows=new Map();
  for(const [id,p] of positions){
    const spec=execweaveTopology.spec.get(id);
    if(spec)layerRows.set(spec.rank,Math.max(layerRows.get(spec.rank)||0,spec.order+1));
    const group=nodeElements.get(id);
    if(group)group.setAttribute('transform',`translate(${p.x} ${p.y})`);
    const node=nodeById.get(id);
    if(node)updateNodeElement(node);
  }
  for(const edge of edgeById.values())updateEdgeElement(edge);
  svg.classList.toggle('execweave-crowded',execweaveTopology.crowded);
  applySearch();
  updateJumpLatest();
  return new Map(positions);
}
execweaveArrangeGraph=execweaveArrangePositions;
window.__execweaveArrangeGraph=execweaveArrangePositions;
const arrangeButton=document.getElementById('arrange');
if(arrangeButton)arrangeButton.onclick=()=>execweaveArrangePositions();
function execweaveWriteDirectedPositions(topo){
  const next=new Map();
  for(const id of nodeById.keys()){
    const spec=topo.spec.get(id);
    next.set(id,spec?{x:spec.x,y:spec.y}:execweaveDesiredPosition(id));
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
