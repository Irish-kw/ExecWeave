from __future__ import annotations

# Injected after LIVE_READABILITY_SCRIPT. The lane layout parks every process in one
# runtime column and routes same-rank edges as cubic S-curves, which is the braid in
# the process stack. This pass places a process by spawn depth so parent	o child is
# mostly horizontal. Arrange is redefined without fit(): Fit is the camera button.

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
const execweaveBuildTopologyBase=execweaveBuildTopology;
execweaveBuildTopology=function(){return execweaveLayoutProcessTree(execweaveBuildTopologyBase())};
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
