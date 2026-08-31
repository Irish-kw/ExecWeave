from __future__ import annotations

LIVE_READABILITY_STYLE = r"""
#svg.execweave-crowded .label{opacity:0;transition:opacity .12s ease,fill .12s ease}
#svg.execweave-crowded .label.aggregate-label,
#svg.execweave-crowded .label.edge-hover,
#svg.execweave-crowded .label.context-visible,
#svg.execweave-crowded .label.selected{opacity:1}
.edge.context-dim{opacity:.055!important}
.edge.context-related:not(.dim){opacity:1;stroke-width:2.2}
.edge.edge-hover:not(.dim){opacity:1;stroke-width:2.2}
.edge.bundle-member:not(.context-dim){opacity:.52}
.edge.bundle-representative:not(.context-dim){opacity:.94;stroke-width:1.8}
.node.context-dim{opacity:.32}
.label.context-dim{opacity:0!important}
.label.context-visible{fill:var(--text)}
.label.aggregate-label{fill:var(--text);font-size:9px;font-weight:700}
""".strip()


LIVE_READABILITY_SCRIPT = r"""
const EXECWEAVE_NODE_W=160,EXECWEAVE_NODE_H=50,EXECWEAVE_ROW_GAP=104;
const EXECWEAVE_NODE_W_MAX=320,EXECWEAVE_LABEL_PAD=20;
// A second label line adds this much. Every vertical measurement below is written as a
// fraction of the node's own height, so a one-line node reproduces the numbers the fixed
// 50 produced: centre 25, the lifecycle anchor 39, and a port span of 30.
const EXECWEAVE_LINE_H=14;
const EXECWEAVE_LANES={runtime:0,root:1,agent:2,model:3,tool:4,file:5,endpoint:6,other:6};
const EXECWEAVE_LANE_ORDER=['runtime','root','agent','model','tool','file','endpoint'];
// The gap that follows each lane. These are the differences in the fixed table this
// replaced, so a graph whose labels all fit the minimum width lands on exactly the
// x positions it did before: 0, 270, 540, 820, 1100, 1380.
const EXECWEAVE_LANE_GAP={runtime:110,root:110,agent:120,model:120,tool:120,file:120};
// A component with no path to the execution spine is packed below it rather than
// interleaved with it, so its rows never sit between two nodes that talk to each other.
const EXECWEAVE_BAND_GAP=170;
let execweaveTopology={spec:new Map(),bundleByEdge:new Map(),sourcePort:new Map(),targetPort:new Map(),width:new Map(),height:new Map(),laneX:{},crowded:false};
let execweaveRuler=null;
// Measure with a hidden text node carrying the label's own class, so the width comes
// from the font actually in use rather than a guess. Contexts without layout (a
// detached document, an export) report zero or throw; both fall back to an estimate.
function execweaveMeasure(text){
  const value=String(text||'');
  if(!value)return 0;
  try{
    if(!execweaveRuler){
      execweaveRuler=document.createElementNS('http://www.w3.org/2000/svg','text');
      execweaveRuler.classList.add('name-label');
      execweaveRuler.setAttribute('visibility','hidden');
      execweaveRuler.setAttribute('x','-9999');
      execweaveRuler.setAttribute('y','-9999');
      svg.appendChild(execweaveRuler);
    }
    execweaveRuler.textContent=value;
    const measured=execweaveRuler.getComputedTextLength();
    if(Number.isFinite(measured)&&measured>0)return measured;
  }catch(_){}
  return value.length*7.1;
}
function execweaveNodeLabel(node){return String(node?.name||node?.id||node?.type||'node')}
function execweaveNodeWidth(node){
  const wanted=execweaveMeasure(execweaveNodeLabel(node))+EXECWEAVE_LABEL_PAD;
  if(!Number.isFinite(wanted))return EXECWEAVE_NODE_W;
  return Math.max(EXECWEAVE_NODE_W,Math.min(EXECWEAVE_NODE_W_MAX,Math.ceil(wanted)));
}
function execweaveWidthOf(id){const value=execweaveTopology.width.get(id);return Number.isFinite(value)?value:EXECWEAVE_NODE_W}
function execweaveHeightOf(id){const value=execweaveTopology.height.get(id);return Number.isFinite(value)?value:EXECWEAVE_NODE_H}
function execweaveCentreY(position,id){return position.y+execweaveHeightOf(id)/2}
// Break at the last separator that fits, so a path or a namespaced tool name splits
// where a reader would split it. A label with no separator breaks on the character.
function execweaveWrapLabel(text,width){
  const value=String(text||''),room=width-EXECWEAVE_LABEL_PAD;
  if(execweaveMeasure(value)<=room)return[value];
  let cut=0;
  for(let index=1;index<value.length;index++){
    if(execweaveMeasure(value.slice(0,index))>room)break;
    if(/[\/_\-. :]/.test(value[index-1]))cut=index;
  }
  if(!cut){
    let low=0,high=value.length;
    while(low<high){const mid=Math.ceil((low+high)/2);if(execweaveMeasure(value.slice(0,mid))<=room)low=mid;else high=mid-1}
    cut=Math.max(1,low);
  }
  return[value.slice(0,cut),value.slice(cut)];
}
function execweaveLaneXOf(lane){const value=execweaveTopology.laneX[lane];return Number.isFinite(value)?value:0}
// A lane starts far enough right that the widest node in the lane before it cannot
// reach into it. With every label at the minimum width this reproduces the fixed
// table exactly; a wide label pushes every lane after it, and only those.
function execweaveLaneX(widthByLane,occupied){
  const laneX={};let x=0;
  for(const lane of EXECWEAVE_LANE_ORDER){
    laneX[lane]=x;
    // A lane holding nothing reserves nothing. Walking every lane unconditionally
    // spent a column on each empty one, and an agent talking to a file paid for the
    // empty model and tool lanes between them in edge length.
    if(!occupied||occupied.has(lane))x+=Math.max(EXECWEAVE_NODE_W,widthByLane.get(lane)||EXECWEAVE_NODE_W)+EXECWEAVE_LANE_GAP[lane];
  }
  laneX.other=laneX.endpoint;
  return laneX;
}
function execweaveAttrs(node){return node&&typeof node.attributes==='object'&&node.attributes?node.attributes:{}}
function execweaveAgentPath(node){const a=execweaveAttrs(node);return String(a.agent_path||a.child_agent_path||a.root_agent_path||node?.name||node?.id||'')}
function execweaveRelation(edge){return String(edge?.relation||'').toUpperCase()}
function execweaveIsSpawn(edge){const value=execweaveRelation(edge);return value==='SPAWNED_AGENT'||value.includes('SPAWNED_AGENT')||value.includes('SPAWN_AGENT')}
function execweaveIsStopped(edge){const value=execweaveRelation(edge);return value==='SUBAGENT_STOPPED'||value.includes('SUBAGENT_STOPPED')}
function execweaveIsRoot(node){const a=execweaveAttrs(node);return node?.type==='agent'&&(a.agent_role==='root'||a.root_agent_path==='/root'||a.agent_path==='/root'||execweaveAgentPath(node)==='/root')}
function execweaveLane(node){
  const type=String(node?.type||'').toLowerCase();
  if(type==='agent')return execweaveIsRoot(node)?'root':'agent';
  if(type.includes('model')||type.includes('inference')||type.includes('llm'))return'model';
  if(type.includes('tool'))return'tool';
  if(type.includes('file')||type.includes('path'))return'file';
  if(type.includes('network')||type.includes('endpoint')||type.includes('socket')||type.includes('host'))return'endpoint';
  if(type.includes('process')||type.includes('session')||type.includes('runtime')||type.includes('shell'))return'runtime';
  return'other';
}
function execweaveMoment(edge){
  if(Number.isInteger(edge?.first_sequence))return`0:${String(edge.first_sequence).padStart(12,'0')}`;
  if(edge?.first_seen)return`1:${edge.first_seen}`;
  return`2:${edgeId(edge)}`;
}
function execweaveStableNodeSort(a,b){return String(a?.name||a?.id||'').localeCompare(String(b?.name||b?.id||''))||String(a?.id||'').localeCompare(String(b?.id||''))}
function execweaveBuildTopology(){
  const nodes=[...nodeById.values()],edges=[...edgeById.values()],spawnFor=new Map();
  for(const edge of edges){
    if(!execweaveIsSpawn(edge))continue;
    const source=nodeById.get(edge.source),target=nodeById.get(edge.target);
    if(source?.type!=='agent'||target?.type!=='agent')continue;
    const current=spawnFor.get(target.id);if(!current||execweaveMoment(edge)<execweaveMoment(current))spawnFor.set(target.id,edge);
  }
  const roots=nodes.filter(execweaveIsRoot).sort(execweaveStableNodeSort);
  const children=nodes.filter(node=>node.type==='agent'&&!execweaveIsRoot(node)).sort((a,b)=>{
    const ae=spawnFor.get(a.id),be=spawnFor.get(b.id),am=ae?execweaveMoment(ae):'9:',bm=be?execweaveMoment(be):'9:';
    return am.localeCompare(bm)||execweaveAgentPath(a).localeCompare(execweaveAgentPath(b))||execweaveStableNodeSort(a,b);
  });
  const childOrder=new Map(children.map((node,index)=>[node.id,index]));
  const rootY=children.length?100+((children.length-1)*EXECWEAVE_ROW_GAP)/2:100;
  const byLane=new Map();for(const lane of Object.keys(EXECWEAVE_LANES))byLane.set(lane,[]);
  for(const node of nodes)byLane.get(execweaveLane(node)).push(node);
  const agentBarycenter=node=>{
    const touching=edges.filter(edge=>edge.target===node.id&&childOrder.has(edge.source));
    if(!touching.length)return Number.MAX_SAFE_INTEGER;
    return touching.reduce((sum,edge)=>sum+(childOrder.get(edge.source)||0),0)/touching.length;
  };
  for(const lane of ['runtime','model','endpoint','other'])byLane.get(lane).sort(execweaveStableNodeSort);
  byLane.get('tool').sort((a,b)=>{
    const ac=/spawn|send|wait|agent/i.test(String(a?.name||execweaveAttrs(a).tool_name||'')),bc=/spawn|send|wait|agent/i.test(String(b?.name||execweaveAttrs(b).tool_name||''));
    if(ac!==bc)return ac?-1:1;
    const ab=agentBarycenter(a),bb=agentBarycenter(b);if(ab!==bb)return ab-bb;
    return execweaveStableNodeSort(a,b);
  });
  const width=new Map(),height=new Map(),widthByLane=new Map(),occupied=new Set();
  for(const node of nodes){
    const w=execweaveNodeWidth(node),lane=execweaveLane(node);
    width.set(node.id,w);
    height.set(node.id,EXECWEAVE_NODE_H+(execweaveWrapLabel(execweaveNodeLabel(node),w).length>1?EXECWEAVE_LINE_H:0));
    widthByLane.set(lane,Math.max(widthByLane.get(lane)||EXECWEAVE_NODE_W,w));
    occupied.add(lane==='other'?'endpoint':lane);
  }
  // `other` shares a column with `endpoint`, so it must not widen a lane of its own.
  widthByLane.set('endpoint',Math.max(widthByLane.get('endpoint')||EXECWEAVE_NODE_W,widthByLane.get('other')||EXECWEAVE_NODE_W));
  const laneX=execweaveLaneX(widthByLane,occupied);
  const spec=new Map();
  const put=(node,lane,order,y)=>spec.set(node.id,{lane,rank:EXECWEAVE_LANES[lane],order,x:laneX[lane],y});
  roots.forEach((node,index)=>put(node,'root',index,rootY+index*EXECWEAVE_ROW_GAP));
  children.forEach((node,index)=>put(node,'agent',index,100+index*EXECWEAVE_ROW_GAP));
  byLane.get('runtime').forEach((node,index)=>put(node,'runtime',index,rootY+(index-Math.floor(byLane.get('runtime').length/2))*86));
  byLane.get('model').forEach((node,index)=>put(node,'model',index,rootY+(index-Math.floor(byLane.get('model').length/2))*92));
  const tools=byLane.get('tool'),collab=tools.filter(node=>/spawn|send|wait|agent/i.test(String(node?.name||execweaveAttrs(node).tool_name||''))),ordinary=tools.filter(node=>!collab.includes(node));
  collab.forEach((node,index)=>put(node,'tool',index,-170+index*82));
  ordinary.forEach((node,index)=>put(node,'tool',collab.length+index,80+index*130));
  for(const lane of ['file','endpoint','other'])byLane.get(lane).forEach((node,index)=>put(node,lane,index,80+index*104));
  for(const node of nodes)if(!spec.has(node.id))put(node,execweaveLane(node),0,100);

  // Push every component that cannot reach the spine below it. The spine is the
  // component holding the first root; with no root at all it is the largest, which
  // keeps a runtime-only graph from being demoted to its own band.
  const componentOf=execweaveComponents(nodes,edges);
  if(componentOf.size){
    const sizes=new Map();
    for(const value of componentOf.values())sizes.set(value,(sizes.get(value)||0)+1);
    // An agent belongs to the spine whether or not the provider recorded an edge to
    // it. Codex records subagents with no edge back to their root, so reading the
    // graph alone demoted every subagent to the band meant for stray evidence.
    const spineIds=new Set(nodes.filter(node=>node?.type==='agent').map(node=>node.id));
    let primary=roots.length?componentOf.get(roots[0].id):undefined;
    if(primary===undefined){
      let best=-1;
      for(const [value,size] of [...sizes.entries()].sort((a,b)=>a[0]-b[0]))if(size>best){best=size;primary=value}
    }
    const spineComponents=new Set([...componentOf.entries()].filter(entry=>spineIds.has(entry[0])).map(entry=>entry[1]));
    if(primary!==undefined)spineComponents.add(primary);
    const secondary=[...sizes.keys()].filter(value=>!spineComponents.has(value)).sort((a,b)=>a-b);
    if(secondary.length){
      let floor=-Infinity;
      for(const [id,value] of componentOf)if(spineComponents.has(value)){const s=spec.get(id);if(s)floor=Math.max(floor,s.y+(height.get(id)||EXECWEAVE_NODE_H))}
      if(!Number.isFinite(floor))floor=0;
      for(const value of secondary){
        const members=[...componentOf.entries()].filter(entry=>entry[1]===value).map(entry=>entry[0]);
        let top=Infinity,bottom=-Infinity;
        for(const id of members){const s=spec.get(id);if(s){top=Math.min(top,s.y);bottom=Math.max(bottom,s.y+(height.get(id)||EXECWEAVE_NODE_H))}}
        if(!Number.isFinite(top))continue;
        const shift=floor+EXECWEAVE_BAND_GAP-top;
        for(const id of members){const s=spec.get(id);if(s)s.y+=shift}
        floor=bottom+shift;
      }
    }
  }

  const bundleGroups=new Map();
  for(const edge of edges){
    const source=nodeById.get(edge.source),target=nodeById.get(edge.target);
    if(source?.type!=='agent'||!['tool','model'].includes(execweaveLane(target))||execweaveIsSpawn(edge)||execweaveIsStopped(edge))continue;
    const key=`${edge.target}\u0000${String(edge.relation||'')}`;
    if(!bundleGroups.has(key))bundleGroups.set(key,[]);bundleGroups.get(key).push(edge);
  }
  const bundleByEdge=new Map(),sourceEdges=new Map(),targetEdges=new Map();
  const sortedGroups=[...bundleGroups.entries()].sort((a,b)=>{
    const as=spec.get(a[1][0]?.target),bs=spec.get(b[1][0]?.target);
    return (as?.y??0)-(bs?.y??0)||a[0].localeCompare(b[0]);
  });
  sortedGroups.forEach(([key,members],groupIndex)=>{
    members.sort((a,b)=>(childOrder.get(a.source)??Number.MAX_SAFE_INTEGER)-(childOrder.get(b.source)??Number.MAX_SAFE_INTEGER)||edgeId(a).localeCompare(edgeId(b)));
    members.forEach((edge,index)=>bundleByEdge.set(edgeId(edge),{key,size:members.length,index,representative:index===0,groupIndex}));
  });
  for(const edge of edges){
    if(!sourceEdges.has(edge.source))sourceEdges.set(edge.source,[]);sourceEdges.get(edge.source).push(edge);
    if(!targetEdges.has(edge.target))targetEdges.set(edge.target,[]);targetEdges.get(edge.target).push(edge);
  }
  const sourcePort=new Map(),targetPort=new Map();
  for(const list of sourceEdges.values()){
    list.sort((a,b)=>{const at=spec.get(a.target),bt=spec.get(b.target);return (at?.y??0)-(bt?.y??0)||(at?.rank??0)-(bt?.rank??0)||edgeId(a).localeCompare(edgeId(b))});
    list.forEach((edge,index)=>sourcePort.set(edgeId(edge),{index,total:list.length}));
  }
  for(const list of targetEdges.values()){
    list.sort((a,b)=>{const as=spec.get(a.source),bs=spec.get(b.source);return (as?.y??0)-(bs?.y??0)||(as?.rank??0)-(bs?.rank??0)||edgeId(a).localeCompare(edgeId(b))});
    list.forEach((edge,index)=>targetPort.set(edgeId(edge),{index,total:list.length}));
  }
  return{spec,bundleByEdge,sourcePort,targetPort,width,height,laneX,crowded:edges.length>=16||nodes.length>=12};
}
function execweaveComponents(nodes,edges){
  const adjacent=new Map();
  for(const node of nodes)adjacent.set(node.id,[]);
  for(const edge of edges){
    if(!adjacent.has(edge.source)||!adjacent.has(edge.target))continue;
    adjacent.get(edge.source).push(edge.target);adjacent.get(edge.target).push(edge.source);
  }
  const componentOf=new Map();let index=0;
  for(const node of [...nodes].sort(execweaveStableNodeSort)){
    if(componentOf.has(node.id))continue;
    const queue=[node.id];componentOf.set(node.id,index);
    while(queue.length){
      const id=queue.pop();
      for(const next of adjacent.get(id)||[])if(!componentOf.has(next)){componentOf.set(next,index);queue.push(next)}
    }
    index++;
  }
  return componentOf;
}
function execweavePortY(position,port,id){const h=execweaveHeightOf(id);if(!port||port.total<=1)return position.y+h/2;const span=h-20;return position.y+10+(span*port.index)/(port.total-1)}
function execweaveDesiredPosition(id){const value=execweaveTopology.spec.get(id);return value?{x:value.x,y:value.y}:{x:0,y:0}}
// 74 still clears the tallest node this can produce: 50 plus one wrapped line is 64.
// A third line would need this to grow with the nodes it compares.
function execweaveCollision(position,next,id){for(const [other,p] of next){if(other===id)continue;if(Math.abs(p.x-position.x)<2&&Math.abs(p.y-position.y)<74)return true}return false}
function execweavePlaceStable(id,desired,next){let candidate={...desired};while(execweaveCollision(candidate,next,id))candidate.y+=EXECWEAVE_ROW_GAP;return candidate}
fullLayout=function(){
  const prior=positions;execweaveTopology=execweaveBuildTopology();const next=new Map();
  for(const id of nodeById.keys()){
    const desired=execweaveDesiredPosition(id),old=prior.get(id);
    next.set(id,old?{x:old.x,y:old.y}:execweavePlaceStable(id,desired,next,id));
  }
  positions=next;layerRows=new Map();
  for(const [id,p] of positions){const spec=execweaveTopology.spec.get(id);if(spec)layerRows.set(spec.rank,Math.max(layerRows.get(spec.rank)||0,spec.order+1));if(!Number.isFinite(p.x)||!Number.isFinite(p.y))positions.set(id,execweaveDesiredPosition(id))}
  svg.classList.toggle('execweave-crowded',execweaveTopology.crowded);
};
reservePosition=function(depth){const row=layerRows.get(depth)||0;layerRows.set(depth,row+1);const lane=EXECWEAVE_LANE_ORDER[Number(depth)||0];return{x:lane?execweaveLaneXOf(lane):(Number(depth)||0)*270,y:100+row*EXECWEAVE_ROW_GAP}};
nodeDepth=function(id){return execweaveTopology.spec.get(id)?.rank??null};
placeAddedNodes=function(ids){
  execweaveTopology=execweaveBuildTopology();
  for(const id of ids||[]){if(!nodeById.has(id)||positions.has(id))continue;positions.set(id,execweavePlaceStable(id,execweaveDesiredPosition(id),positions,id))}
  svg.classList.toggle('execweave-crowded',execweaveTopology.crowded);
};
function execweaveRoute(edge){
  const id=edgeId(edge),sp=positions.get(edge.source)||{x:0,y:0},tp=positions.get(edge.target)||{x:0,y:0},sourceSpec=execweaveTopology.spec.get(edge.source)||{},targetSpec=execweaveTopology.spec.get(edge.target)||{},bundle=execweaveTopology.bundleByEdge.get(id),sourcePort=execweaveTopology.sourcePort.get(id),targetPort=execweaveTopology.targetPort.get(id);
  if(bundle&&bundle.size>1){
    const sx=sp.x+execweaveWidthOf(edge.source),sy=execweavePortY(sp,sourcePort,edge.source),tx=tp.x,ty=execweavePortY(tp,targetPort,edge.target),trunkX=Math.max(sx+54,tx-82-(bundle.groupIndex%6)*24);
    return{d:`M ${sx} ${sy} H ${trunkX} V ${ty} H ${tx}`,labelX:(trunkX+tx)/2,labelY:ty-8,kind:'bundle',bundle};
  }
  if(execweaveIsSpawn(edge)){
    const sx=sp.x+execweaveWidthOf(edge.source),sy=execweavePortY(sp,sourcePort,edge.source),tx=tp.x,ty=execweaveCentreY(tp,edge.target),bend=Math.max(48,(tx-sx)*.46);
    return{d:`M ${sx} ${sy} C ${sx+bend} ${sy}, ${tx-bend} ${ty}, ${tx} ${ty}`,labelX:(sx+tx)/2,labelY:Math.min(sy,ty)-10,kind:'spawn',bundle:null};
  }
  if(execweaveIsStopped(edge)){
    const sx=sp.x,sy=sp.y+execweaveHeightOf(edge.source)*0.78,tx=tp.x+execweaveWidthOf(edge.target),ty=tp.y+execweaveHeightOf(edge.target)*0.78,offset=62+((sourceSpec.order||0)%4)*11;
    return{d:`M ${sx} ${sy} C ${sx-offset} ${sy+offset}, ${tx+offset} ${ty+offset}, ${tx} ${ty}`,labelX:(sx+tx)/2,labelY:Math.max(sy,ty)+offset*.66,kind:'lifecycle-return',bundle:null};
  }
  const forward=(targetSpec.rank??0)>=(sourceSpec.rank??0);
  const sx=forward?sp.x+execweaveWidthOf(edge.source):sp.x,tx=forward?tp.x:tp.x+execweaveWidthOf(edge.target),sy=execweavePortY(sp,sourcePort,edge.source),ty=execweavePortY(tp,targetPort,edge.target),distance=Math.abs(tx-sx),bend=Math.max(44,distance*.42),sign=forward?1:-1;
  return{d:`M ${sx} ${sy} C ${sx+sign*bend} ${sy}, ${tx-sign*bend} ${ty}, ${tx} ${ty}`,labelX:(sx+tx)/2,labelY:(sy+ty)/2-8,kind:forward?'forward':'reverse',bundle:null};
}
anchor=function(id,right){const p=positions.get(id)||{x:0,y:0};return{x:p.x+(right?execweaveWidthOf(id):0),y:execweaveCentreY(p,id)}};
curve=function(edge){return execweaveRoute(edge).d};
// The base renderer draws every node 160 wide and truncates its label at 28 characters,
// so a label that now has room would still be cut. Both are re-applied here from the
// width the topology computed for this node.
function execweaveFitLabel(text,width){
  const value=String(text||'');
  if(execweaveMeasure(value)+EXECWEAVE_LABEL_PAD<=width)return value;
  let low=0,high=value.length;
  while(low<high){
    const mid=Math.ceil((low+high)/2);
    if(execweaveMeasure(value.slice(0,mid)+'\u2026')+EXECWEAVE_LABEL_PAD<=width)low=mid;else high=mid-1;
  }
  return low>0?value.slice(0,low)+'\u2026':value.slice(0,1);
}
const execweaveBaseUpdateNodeElement=updateNodeElement;
updateNodeElement=function(node){
  execweaveBaseUpdateNodeElement(node);const group=nodeElements.get(node.id);if(!group)return;
  const width=execweaveWidthOf(node.id);
  const height=execweaveHeightOf(node.id);
  const rect=group.querySelector('rect');if(rect){rect.setAttribute('width',width);rect.setAttribute('height',height)}
  const label=group.querySelector('.name-label');
  if(label){
    const full=execweaveNodeLabel(node);
    const lines=execweaveWrapLabel(full,width);
    label.textContent='';
    if(lines.length>1){
      label.setAttribute('y',32);
      const first=document.createElementNS('http://www.w3.org/2000/svg','tspan');
      first.setAttribute('x',10);first.setAttribute('y',32);first.textContent=lines[0];
      const second=document.createElementNS('http://www.w3.org/2000/svg','tspan');
      second.setAttribute('x',10);second.setAttribute('y',32+EXECWEAVE_LINE_H);
      second.textContent=execweaveFitLabel(lines[1],width);
      label.appendChild(first);label.appendChild(second);
    }else{
      label.setAttribute('y',34);
      label.textContent=execweaveFitLabel(full,width);
    }
    group.dataset.labelLines=String(lines.length);
    group.dataset.fullLabel=full;
    let title=group.querySelector('title');
    if(!title){title=document.createElementNS('http://www.w3.org/2000/svg','title');group.appendChild(title)}
    title.textContent=full;
  }
  group.dataset.nodeWidth=String(width);group.dataset.nodeHeight=String(height);
  const spec=execweaveTopology.spec.get(node.id);if(!spec)return;
  group.dataset.layoutLane=spec.lane;group.dataset.layoutRank=String(spec.rank);group.dataset.layoutOrder=String(spec.order);
};
const execweaveBaseUpdateEdgeElement=updateEdgeElement;
updateEdgeElement=function(edge){
  execweaveBaseUpdateEdgeElement(edge);const id=edgeId(edge),els=edgeElements.get(id);if(!els)return;const route=execweaveRoute(edge),bundle=route.bundle;
  els.visible.setAttribute('d',route.d);els.hit.setAttribute('d',route.d);els.visible.dataset.routeKind=route.kind;els.hit.dataset.routeKind=route.kind;
  els.visible.dataset.bundleKey=bundle?.key||'';els.visible.dataset.bundleSize=String(bundle?.size||1);els.visible.dataset.layoutConstraint=execweaveIsStopped(edge)?'ignored-for-rank':'ranked';
  els.label.setAttribute('x',route.labelX);els.label.setAttribute('y',route.labelY);els.label.dataset.fullRelation=String(edge.relation||'');
  const aggregate=!!bundle&&bundle.size>1&&bundle.representative;
  els.visible.classList.toggle('bundle-member',!!bundle&&bundle.size>1);els.visible.classList.toggle('bundle-representative',aggregate);els.label.classList.toggle('aggregate-label',aggregate);
  els.label.textContent=aggregate?`${edge.relation} ×${bundle.size}`:(edge.count>1?`${edge.relation} ×${edge.count}`:edge.relation);
  if(execweaveTopology.crowded&&!aggregate)els.label.setAttribute('aria-hidden','true');else els.label.removeAttribute('aria-hidden');
};
const execweaveBaseCreateEdgeElement=createEdgeElement;
createEdgeElement=function(edge){
  const id=edgeId(edge),exists=edgeElements.has(id);execweaveBaseCreateEdgeElement(edge);const els=edgeElements.get(id);if(!els||exists||els.hit.dataset.readabilityBound==='1')return;
  els.hit.dataset.readabilityBound='1';els.hit.setAttribute('aria-label',`${edge.relation||'edge'}: ${entityLabel(edge.source)} → ${entityLabel(edge.target)}`);
  els.hit.addEventListener('mouseenter',()=>{els.visible.classList.add('edge-hover');els.label.classList.add('edge-hover')});
  els.hit.addEventListener('mouseleave',()=>{els.visible.classList.remove('edge-hover');els.label.classList.remove('edge-hover')});
};
function execweaveClearContextFocus(){
  for(const els of edgeElements.values()){els.visible.classList.remove('context-dim','context-related');els.label.classList.remove('context-dim','context-visible')}
  for(const group of nodeElements.values())group.classList.remove('context-dim');
}
function execweaveFocusNodeEdges(id){
  const neighborIds=new Set([id]);
  for(const [edgeIdValue,edge] of edgeById){const related=edge.source===id||edge.target===id,els=edgeElements.get(edgeIdValue);if(!els)continue;els.visible.classList.toggle('context-related',related);els.visible.classList.toggle('context-dim',!related);els.label.classList.toggle('context-visible',related);els.label.classList.toggle('context-dim',!related);if(related){neighborIds.add(edge.source);neighborIds.add(edge.target)}}
  for(const [nodeIdValue,group] of nodeElements)group.classList.toggle('context-dim',!neighborIds.has(nodeIdValue));
}
function execweaveFocusOneEdge(id){
  for(const [edgeIdValue,els] of edgeElements){const related=edgeIdValue===id;els.visible.classList.toggle('context-related',related);els.visible.classList.toggle('context-dim',!related);els.label.classList.toggle('context-visible',related);els.label.classList.toggle('context-dim',!related)}
}
const execweaveBaseClearSelection=clearSelection;
clearSelection=function(){execweaveBaseClearSelection();execweaveClearContextFocus()};
const execweaveBaseSelectNode=selectNode;
selectNode=function(id,options={}){execweaveBaseSelectNode(id,options);if(nodeById.has(id))execweaveFocusNodeEdges(id)};
const execweaveBaseSelectEdge=selectEdge;
selectEdge=function(id,options={}){execweaveBaseSelectEdge(id,options);if(edgeById.has(id))execweaveFocusOneEdge(id)};
""".strip()
