from __future__ import annotations

LIVE_SCRIPT_B = r"""function restoreSelectionFocus(){if(selectedNodeId&&nodeById.has(selectedNodeId))execweaveFocusNodeEdges(selectedNodeId);else if(selectedEdgeId&&edgeById.has(selectedEdgeId))execweaveFocusOneEdge(selectedEdgeId)}
const _execweaveBaseFocusNodeEdges=typeof execweaveFocusNodeEdges==='function'?execweaveFocusNodeEdges:null;
execweaveFocusNodeEdges=function(id){
  if(_execweaveBaseFocusNodeEdges)_execweaveBaseFocusNodeEdges(id);
  const neighborIds=new Set();
  for(const edge of edgeById.values()){
    if(edge.source===id&&edge.target!==id)neighborIds.add(edge.target);
    if(edge.target===id&&edge.source!==id)neighborIds.add(edge.source);
  }
  for(const [nodeIdValue,group] of nodeElements){
    group.classList.toggle('context-neighbor',neighborIds.has(nodeIdValue));
  }
};
const _execweaveBaseClearContextFocus=typeof execweaveClearContextFocus==='function'?execweaveClearContextFocus:null;
execweaveClearContextFocus=function(){
  if(_execweaveBaseClearContextFocus)_execweaveBaseClearContextFocus();
  for(const group of nodeElements.values()){
    group.classList.remove('context-neighbor');
  }
};
const _execweaveBaseRoute=typeof execweaveRoute==='function'?execweaveRoute:null;
if(_execweaveBaseRoute){
  execweaveRoute=function(edge){
    const route=_execweaveBaseRoute(edge);
    if(!route||!route.d)return route;
    if(route.kind==='bundle'||route.kind==='lifecycle-return'||(typeof execweaveIsStopped==='function'&&execweaveIsStopped(edge))){
      return route;
    }
    if(route.d.includes('C')){
      const match=route.d.match(/^M\s*([-0-9.]+)\s+([-0-9.]+)\s+C\s*([-0-9.]+)\s+([-0-9.]+)[,\s]+([-0-9.]+)\s+([-0-9.]+)[,\s]+([-0-9.]+)\s+([-0-9.]+)$/);
      if(match){
        const [_,sx,sy,p1x,p1y,p2x,p2y,tx,ty]=match.map(Number);
        let d=`M ${sx} ${sy}`;
        for(let i=1;i<8;i++){
          const t=i/8,u=1-t;
          const x=u*u*u*sx+3*u*u*t*p1x+3*u*t*t*p2x+t*t*t*tx;
          const y=u*u*u*sy+3*u*u*t*p1y+3*u*t*t*p2y+t*t*t*ty;
          d+=` L ${+x.toFixed(1)} ${+y.toFixed(1)}`;
        }
        d+=` L ${tx} ${ty}`;
        return{...route,d};
      }
    }
    return route;
  };
}
function markLatest(nodeIdValue,edgeIdValue){
  if(latestNodeId&&nodeElements.has(latestNodeId)){
    const prevNode=nodeElements.get(latestNodeId);
    prevNode.classList.remove('latest');
    const prevRect=prevNode.querySelector('rect');
    if(prevRect){prevRect.style.animation='none';void prevRect.offsetWidth;prevRect.style.animation=''}
  }
  if(latestEdgeId&&edgeElements.has(latestEdgeId)){
    const prevEdge=edgeElements.get(latestEdgeId);
    prevEdge.visible.classList.remove('latest-edge');
    prevEdge.visible.style.animation='none';void prevEdge.visible.offsetWidth;prevEdge.visible.style.animation='';
  }
  latestNodeId=nodeIdValue&&nodeById.has(nodeIdValue)?nodeIdValue:null;
  latestEdgeId=edgeIdValue&&edgeById.has(edgeIdValue)?edgeIdValue:null;
  if(latestNodeId){
    const nodeEl=nodeElements.get(latestNodeId);
    if(nodeEl){
      nodeEl.classList.add('latest');
      const rect=nodeEl.querySelector('rect');
      if(rect){rect.style.animation='none';void rect.offsetWidth;rect.style.animation=''}
    }
  }
  if(latestEdgeId){
    const edgeEl=edgeElements.get(latestEdgeId);
    if(edgeEl){
      edgeEl.visible.classList.add('latest-edge');
      edgeEl.visible.style.animation='none';void edgeEl.visible.offsetWidth;edgeEl.visible.style.animation='';
    }
  }
  if(latestEdgeId)setCurrentFromEdge(edgeById.get(latestEdgeId));
  else if(latestNodeId)setCurrentFromNode(nodeById.get(latestNodeId));
  updateJumpLatest();
}
function renderSnapshot(){leaveProtectiveMode();fullLayout();edgeLayer.replaceChildren();labelLayer.replaceChildren();nodeLayer.replaceChildren();nodeElements=new Map();edgeElements=new Map();for(const e of edgeById.values())createEdgeElement(e);for(const n of nodeById.values())createNodeElement(n);applySearch();restoreSelectionFocus()}
function setCurrentFromEdge(e){if(!e)return;const target=nodeById.get(e.target),source=nodeById.get(e.source);currentTitle.textContent=e.relation||'Graph transition';currentSub.textContent=`${source?.name||source?.id||e.source} → ${target?.name||target?.id||e.target}`;renderKv(currentKv,[['Kind',nodeCategory(target)],['Last seen',prettyTime(e.last_seen)],['Count',e.count],['Evidence',{label:evidenceLabel(e),raw:e}]])}
function setCurrentFromNode(n){if(!n)return;currentTitle.textContent=n.name||n.id||'Node';currentSub.textContent=n.type||'unknown';renderKv(currentKv,[['Kind',nodeCategory(n)],['Last seen',prettyTime(n.last_seen)],['Events',n.event_count]])}
function activityFromEdge(e,origin='event'){const target=nodeById.get(e.target),source=nodeById.get(e.source);return{id:`a${++activitySerial}`,time:e.last_seen||target?.last_seen||source?.last_seen||'',kind:nodeCategory(target),relation:e.relation||origin,detail:`${source?.name||source?.id||e.source} → ${target?.name||target?.id||e.target}`,evidence:evidenceLabel(e),nodeId:e.target,edgeId:edgeId(e),sequence:e.last_sequence??'',origin}}
function activityFromNode(n){return{id:`a${++activitySerial}`,time:n.last_seen||n.first_seen||'',kind:nodeCategory(n),relation:'NODE',detail:`${n.type||'unknown'} · ${n.name||n.id}`,evidence:'Observed',nodeId:n.id,edgeId:null,sequence:'',origin:'node'}}
function addActivities(items){if(!items.length)return;activities.push(...items);if(activities.length>MAX_ACTIVITY)activities=activities.slice(-MAX_ACTIVITY);renderActivities(true)}
function seedActivities(){const edges=[...edgeById.values()].sort((a,b)=>String(a.last_seen||'').localeCompare(String(b.last_seen||''))).slice(-Math.min(MAX_ACTIVITY,80));activities=edges.map(e=>activityFromEdge(e,'snapshot'));renderActivities(false)}
function renderActivities(scrollLatest=false){const filtered=activities.filter(item=>activityFilter==='all'||item.kind===activityFilter);activityRows.replaceChildren();activityCount.textContent=`${activities.length} transition${activities.length===1?'':'s'}`;if(!filtered.length){const empty=document.createElement('div');empty.className='empty-activity';empty.textContent=activities.length?'No activity matches this filter.':'Waiting for graph activity…';activityRows.appendChild(empty);return}for(const item of filtered){const row=document.createElement('div');row.className='activity-row'+(item.nodeId===latestNodeId?' latest':'');row.dataset.activityId=item.id;row.dataset.nodeId=item.nodeId||'';row.dataset.edgeId=item.edgeId||'';row.title='Double-click to jump to the corresponding graph node';const time=document.createElement('span');time.className='activity-time';time.textContent=prettyTime(item.time);const kind=document.createElement('span');kind.className='activity-kind';kind.textContent=item.kind;const relation=document.createElement('span');relation.className='activity-relation';relation.textContent=shortText(item.relation,24);const detail=document.createElement('span');detail.className='activity-detail';detail.textContent=item.detail;detail.title=item.detail;const evidenceCell=document.createElement('span');evidenceCell.className='activity-evidence';evidenceCell.textContent=item.evidence;row.append(time,kind,relation,detail,evidenceCell);row.onclick=()=>selectActivityRow(item.id,true);row.ondblclick=()=>{selectActivityRow(item.id,true);if(item.nodeId)focusNode(item.nodeId)};activityRows.appendChild(row)}if(scrollLatest){const row=activityRows.lastElementChild;row?.scrollIntoView({block:'nearest'})}}
function selectActivityRow(id,syncGraph=true){document.querySelectorAll('.activity-row.selected').forEach(row=>row.classList.remove('selected'));const row=[...activityRows.children].find(candidate=>candidate.dataset.activityId===id)||null;if(row){row.classList.add('selected');row.scrollIntoView({block:'nearest'})}if(!syncGraph)return;const item=activities.find(value=>value.id===id);if(!item)return;if(item.edgeId&&edgeById.has(item.edgeId))selectEdge(item.edgeId,{syncLog:false});else if(item.nodeId&&nodeById.has(item.nodeId))selectNode(item.nodeId,{syncLog:false});if(row)row.classList.add('selected')}
function setSnapshot(data){graph=data;nodeById=new Map((data.nodes||[]).map(n=>[n.id,n]));edgeById=new Map((data.edges||[]).map(e=>[edgeId(e),e]));rebuildAdjacency();if((selectedNodeId&&!nodeById.has(selectedNodeId))||(selectedEdgeId&&!edgeById.has(selectedEdgeId)))clearSelection();updateStats(data);if(!withinRenderBudget(data)){enterProtectiveMode(data);return}renderSnapshot();seedActivities();const sortedEdges=[...edgeById.values()].sort((a,b)=>String(a.last_seen||'').localeCompare(String(b.last_seen||''))),sortedNodes=[...nodeById.values()].sort((a,b)=>String(a.last_seen||'').localeCompare(String(b.last_seen||''))),lastEdge=sortedEdges.length?sortedEdges[sortedEdges.length-1]:null,lastNode=sortedNodes.length?sortedNodes[sortedNodes.length-1]:null;markLatest(lastEdge?.target||lastNode?.id||null,lastEdge?edgeId(lastEdge):null);if(!hasFitted&&positions.size){fit(false);hasFitted=true}else scheduleCamera(true)}
function mergeById(items,target,isEdge=false){const added=[];for(const item of items||[]){const id=isEdge?edgeId(item):item.id;target.set(id,item);added.push(id);if(isEdge)registerEdgeAdjacency(item)}return added}
function applyDelta(update){updateStats(update);if(update.live_payload_compact||!withinRenderBudget(update)){enterProtectiveMode(update);return}if(protectedMode){liveSequence=-1;return}const addedNodeIds=mergeById(update.nodes_added,nodeById,false);mergeById(update.nodes_updated,nodeById,false);const addedEdgeIds=mergeById(update.edges_added,edgeById,true);const updatedEdgeIds=mergeById(update.edges_updated,edgeById,true);graph={...graph,event_count:update.event_count,node_count:update.node_count,edge_count:update.edge_count,nodes:[...nodeById.values()],edges:[...edgeById.values()]};placeAddedNodes(addedNodeIds);for(const id of addedNodeIds)createNodeElement(nodeById.get(id));for(const n of update.nodes_updated||[])updateNodeElement(n);for(const id of addedEdgeIds)createEdgeElement(edgeById.get(id));for(const e of update.edges_updated||[])updateEdgeElement(e);applySearch();restoreSelectionFocus();const changedEdges=[...(update.edges_added||[]),...(update.edges_updated||[])];const latestEdge=changedEdges.length?changedEdges[changedEdges.length-1]:null,addedNodes=update.nodes_added||[],updatedNodes=update.nodes_updated||[],latestNode=latestEdge?.target||(addedNodes.length?addedNodes[addedNodes.length-1].id:null)||(updatedNodes.length?updatedNodes[updatedNodes.length-1].id:null)||null;markLatest(latestNode,latestEdge?edgeId(latestEdge):null);const newActivities=changedEdges.length?changedEdges.map(e=>activityFromEdge(e)):((update.nodes_added||[]).map(activityFromNode));addActivities(newActivities);scheduleCamera(false);if(!hasFitted&&positions.size){fit(false);hasFitted=true}}
function applyTransform(){viewport.setAttribute('transform',`translate(${transform.x} ${transform.y}) scale(${transform.scale})`)}
function stopAnimation(){if(animationFrame!==null){cancelAnimationFrame(animationFrame);animationFrame=null}}
function animateTo(next,duration=220){stopAnimation();if(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches){transform=next;applyTransform();return}const start={...transform},started=performance.now();const tick=now=>{const t=Math.min(1,(now-started)/duration),eased=1-Math.pow(1-t,3);transform={x:start.x+(next.x-start.x)*eased,y:start.y+(next.y-start.y)*eased,scale:start.scale+(next.scale-start.scale)*eased};applyTransform();if(t<1)animationFrame=requestAnimationFrame(tick);else animationFrame=null};animationFrame=requestAnimationFrame(tick)}
"""
