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
const EXECWEAVE_LANES={runtime:0,root:1,agent:2,model:3,tool:4,endpoint:5,other:5};
const EXECWEAVE_LANE_X={runtime:0,root:270,agent:540,model:820,tool:1100,endpoint:1380,other:1380};
let execweaveTopology={spec:new Map(),bundleByEdge:new Map(),sourcePort:new Map(),targetPort:new Map(),crowded:false};
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
  if(type.includes('network')||type.includes('endpoint')||type.includes('socket')||type.includes('host')||type.includes('file')||type.includes('path'))return'endpoint';
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
  const spec=new Map();
  const put=(node,lane,order,y)=>spec.set(node.id,{lane,rank:EXECWEAVE_LANES[lane],order,x:EXECWEAVE_LANE_X[lane],y});
  roots.forEach((node,index)=>put(node,'root',index,rootY+index*EXECWEAVE_ROW_GAP));
  children.forEach((node,index)=>put(node,'agent',index,100+index*EXECWEAVE_ROW_GAP));
  byLane.get('runtime').forEach((node,index)=>put(node,'runtime',index,rootY+(index-Math.floor(byLane.get('runtime').length/2))*86));
  byLane.get('model').forEach((node,index)=>put(node,'model',index,rootY+(index-Math.floor(byLane.get('model').length/2))*92));
  const tools=byLane.get('tool'),collab=tools.filter(node=>/spawn|send|wait|agent/i.test(String(node?.name||execweaveAttrs(node).tool_name||''))),ordinary=tools.filter(node=>!collab.includes(node));
  collab.forEach((node,index)=>put(node,'tool',index,-170+index*82));
  ordinary.forEach((node,index)=>put(node,'tool',collab.length+index,80+index*130));
  const tail=[...byLane.get('endpoint'),...byLane.get('other')];tail.forEach((node,index)=>put(node,execweaveLane(node),index,80+index*104));
  for(const node of nodes)if(!spec.has(node.id))put(node,execweaveLane(node),0,100);

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
  return{spec,bundleByEdge,sourcePort,targetPort,crowded:edges.length>=16||nodes.length>=12};
}
function execweavePortY(position,port){if(!port||port.total<=1)return position.y+25;const span=30;return position.y+10+(span*port.index)/(port.total-1)}
function execweaveDesiredPosition(id){const value=execweaveTopology.spec.get(id);return value?{x:value.x,y:value.y}:{x:0,y:0}}
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
reservePosition=function(depth){const row=layerRows.get(depth)||0;layerRows.set(depth,row+1);return{x:(Number(depth)||0)*270,y:100+row*EXECWEAVE_ROW_GAP}};
nodeDepth=function(id){return execweaveTopology.spec.get(id)?.rank??null};
placeAddedNodes=function(ids){
  execweaveTopology=execweaveBuildTopology();
  for(const id of ids||[]){if(!nodeById.has(id)||positions.has(id))continue;positions.set(id,execweavePlaceStable(id,execweaveDesiredPosition(id),positions,id))}
  svg.classList.toggle('execweave-crowded',execweaveTopology.crowded);
};
function execweaveRoute(edge){
  const id=edgeId(edge),sp=positions.get(edge.source)||{x:0,y:0},tp=positions.get(edge.target)||{x:0,y:0},sourceSpec=execweaveTopology.spec.get(edge.source)||{},targetSpec=execweaveTopology.spec.get(edge.target)||{},bundle=execweaveTopology.bundleByEdge.get(id),sourcePort=execweaveTopology.sourcePort.get(id),targetPort=execweaveTopology.targetPort.get(id);
  if(bundle&&bundle.size>1){
    const sx=sp.x+EXECWEAVE_NODE_W,sy=execweavePortY(sp,sourcePort),tx=tp.x,ty=execweavePortY(tp,targetPort),trunkX=Math.max(sx+54,tx-82-(bundle.groupIndex%6)*24);
    return{d:`M ${sx} ${sy} H ${trunkX} V ${ty} H ${tx}`,labelX:(trunkX+tx)/2,labelY:ty-8,kind:'bundle',bundle};
  }
  if(execweaveIsSpawn(edge)){
    const sx=sp.x+EXECWEAVE_NODE_W,sy=execweavePortY(sp,sourcePort),tx=tp.x,ty=tp.y+25,bend=Math.max(48,(tx-sx)*.46);
    return{d:`M ${sx} ${sy} C ${sx+bend} ${sy}, ${tx-bend} ${ty}, ${tx} ${ty}`,labelX:(sx+tx)/2,labelY:Math.min(sy,ty)-10,kind:'spawn',bundle:null};
  }
  if(execweaveIsStopped(edge)){
    const sx=sp.x,sy=sp.y+39,tx=tp.x+EXECWEAVE_NODE_W,ty=tp.y+39,offset=62+((sourceSpec.order||0)%4)*11;
    return{d:`M ${sx} ${sy} C ${sx-offset} ${sy+offset}, ${tx+offset} ${ty+offset}, ${tx} ${ty}`,labelX:(sx+tx)/2,labelY:Math.max(sy,ty)+offset*.66,kind:'lifecycle-return',bundle:null};
  }
  const forward=(targetSpec.rank??0)>=(sourceSpec.rank??0);
  const sx=forward?sp.x+EXECWEAVE_NODE_W:sp.x,tx=forward?tp.x:tp.x+EXECWEAVE_NODE_W,sy=execweavePortY(sp,sourcePort),ty=execweavePortY(tp,targetPort),distance=Math.abs(tx-sx),bend=Math.max(44,distance*.42),sign=forward?1:-1;
  return{d:`M ${sx} ${sy} C ${sx+sign*bend} ${sy}, ${tx-sign*bend} ${ty}, ${tx} ${ty}`,labelX:(sx+tx)/2,labelY:(sy+ty)/2-8,kind:forward?'forward':'reverse',bundle:null};
}
anchor=function(id,right){const p=positions.get(id)||{x:0,y:0};return{x:p.x+(right?EXECWEAVE_NODE_W:0),y:p.y+25}};
curve=function(edge){return execweaveRoute(edge).d};
const execweaveBaseUpdateNodeElement=updateNodeElement;
updateNodeElement=function(node){
  execweaveBaseUpdateNodeElement(node);const group=nodeElements.get(node.id),spec=execweaveTopology.spec.get(node.id);if(!group||!spec)return;
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
