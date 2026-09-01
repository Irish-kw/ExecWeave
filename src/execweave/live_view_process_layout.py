from __future__ import annotations

# Injected after LIVE_READABILITY_SCRIPT. The lane layout parks types in columns and
# routes same-column edges as cubic S-curves. Process trees go left-to-right by spawn
# depth; related agent/tool/file/External nodes are then pulled toward their neighbors.
# Arrange recomputes every visible node and edge and does not call fit().

LIVE_PROCESS_LAYOUT_SCRIPT = r"""
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
const execweaveBuildTopologyBase=execweaveBuildTopology;
execweaveBuildTopology=function(){return execweaveLayoutRelated(execweaveLayoutProcessTree(execweaveBuildTopologyBase()))};
const execweaveRouteBase=execweaveRoute;
execweaveRoute=function(edge){
  const sourceSpec=execweaveTopology.spec.get(edge.source)||{};
  const targetSpec=execweaveTopology.spec.get(edge.target)||{};
  const bundle=execweaveTopology.bundleByEdge.get(edgeId(edge));
  if(bundle&&bundle.size>1)return execweaveRouteBase(edge);
  if(execweaveIsStopped(edge))return execweaveRouteBase(edge);
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
})();
""".strip()
