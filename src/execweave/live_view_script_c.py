from __future__ import annotations

LIVE_SCRIPT_C = r"""function graphBounds(){if(!positions.size)return null;let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;positions.forEach(p=>{if(p.x<minX)minX=p.x;if(p.x>maxX)maxX=p.x;if(p.y<minY)minY=p.y});return{minX,maxX:maxX+160,minY,maxY:maxY+50}}
function fit(animate=true){const bounds=graphBounds();if(!bounds)return;const box=svg.getBoundingClientRect(),w=Math.max(1,bounds.maxX-bounds.minX),h=Math.max(1,bounds.maxY-bounds.minY),scale=Math.min(1.2,Math.max(.07,Math.min((box.width-72)/w,(box.height-72)/h))),next={x:36-bounds.minX*scale,y:36-bounds.minY*scale,scale};if(animate)animateTo(next);else{transform=next;applyTransform()}}
function latestScreenPoint(){if(!latestNodeId||!positions.has(latestNodeId))return null;const p=positions.get(latestNodeId);return{x:transform.x+(p.x+80)*transform.scale,y:transform.y+(p.y+25)*transform.scale}}
function latestInsideSafeZone(){const point=latestScreenPoint();if(!point)return true;const box=svg.getBoundingClientRect(),mx=box.width*.18,my=box.height*.18;return point.x>=mx&&point.x<=box.width-mx&&point.y>=my&&point.y<=box.height-my}
function followLatest(force=false){if(!latestNodeId||!positions.has(latestNodeId))return;if(!force&&latestInsideSafeZone())return;const box=svg.getBoundingClientRect(),p=positions.get(latestNodeId),next={x:box.width*.5-(p.x+80)*transform.scale,y:box.height*.5-(p.y+25)*transform.scale,scale:transform.scale};animateTo(next,240)}
function focusNode(id){if(!id||!positions.has(id))return;if(cameraMode!=='manual')setCameraMode('manual',{apply:false});const box=svg.getBoundingClientRect(),p=positions.get(id),scale=Math.min(1.2,Math.max(.72,transform.scale)),next={x:box.width*.5-(p.x+80)*scale,y:box.height*.5-(p.y+25)*scale,scale};animateTo(next,220);setTimeout(updateJumpLatest,230)}
function scheduleCamera(force=false){clearTimeout(cameraTimer);cameraTimer=setTimeout(()=>{if(cameraMode==='fit')fit(true);else if(cameraMode==='follow')followLatest(force);updateJumpLatest()},180)}
function setCameraMode(mode,{apply=true}={}){cameraMode=['manual','fit','follow'].includes(mode)?mode:'manual';document.querySelectorAll('[data-camera]').forEach(button=>button.classList.toggle('active',button.dataset.camera===cameraMode));cameraLabel.textContent=cameraMode==='manual'?'Manual':cameraMode==='fit'?'Fit graph':'Follow latest';if(apply){if(cameraMode==='fit')fit(true);else if(cameraMode==='follow')followLatest(true)}updateJumpLatest()}
function updateJumpLatest(){jumpLatest.hidden=!latestNodeId||latestInsideSafeZone()||cameraMode==='follow'}
function userTookCamera(){if(cameraMode!=='manual')setCameraMode('manual',{apply:false})}
function zoomBy(factor){userTookCamera();const box=svg.getBoundingClientRect(),mx=box.width/2,my=box.height/2,old=transform.scale,nextScale=Math.min(4,Math.max(.07,old*factor)),gx=(mx-transform.x)/old,gy=(my-transform.y)/old;animateTo({x:mx-gx*nextScale,y:my-gy*nextScale,scale:nextScale},140)}
function applySearch(){const q=search.value.trim().toLowerCase(),matched=new Set();document.querySelectorAll('.node').forEach(el=>{const ok=!q||el.dataset.search.includes(q);el.classList.toggle('dim',!ok);if(ok)matched.add(el.dataset.id)});document.querySelectorAll('.edge').forEach(el=>{const keep=!q||matched.has(el.dataset.source)||matched.has(el.dataset.target)||el.dataset.relation.includes(q);el.classList.toggle('dim',!keep)})}
async function poll(){try{const response=await fetch(`/live.json?after=${liveSequence}`,{cache:'no-store'});if(!response.ok)throw new Error(String(response.status));const data=await response.json();if(data.kind==='snapshot'){liveSequence=Number(data.sequence)||0;setSnapshot(data.graph||{});}else if(data.kind==='delta'){if(Number(data.base_sequence)!==liveSequence){liveSequence=-1;setStatus('RESYNCING','resyncing');setTimeout(poll,0);return}for(const update of data.updates||[]){if(Number(update.sequence)!==liveSequence+1){liveSequence=-1;setStatus('RESYNCING','resyncing');setTimeout(poll,0);return}applyDelta(update);liveSequence=Number(update.sequence)}if(!(data.updates||[]).length)liveSequence=Number(data.sequence)||liveSequence;}else if(data.kind==='noop'){liveSequence=Number(data.sequence)||liveSequence;updateStats(data);}window.__execweaveDashboard?.onPayload?.(data);updateEvidence(data);const finished=!!data.live_finished;setStatus(finished?'FINISHED':(protectedMode?'PROTECTED':'LIVE'),finished?'finished':protectedMode?'reconnecting':'');if(finished){window.__execweaveDashboard?.onFinished?.();return}}catch(_){setStatus('RECONNECTING','reconnecting')}setTimeout(poll,500)}
svg.onpointerdown=e=>{if(e.target.closest?.('.node'))return;userTookCamera();stopAnimation();pan={x:e.clientX,y:e.clientY,tx:transform.x,ty:transform.y,travelled:false};svg.classList.add('panning');svg.setPointerCapture(e.pointerId)};svg.onpointermove=e=>{if(!pan)return;if(Math.abs(e.clientX-pan.x)>3||Math.abs(e.clientY-pan.y)>3)pan.travelled=true;transform.x=pan.tx+e.clientX-pan.x;transform.y=pan.ty+e.clientY-pan.y;applyTransform();updateJumpLatest()};svg.onpointerup=e=>{const dragged=!!pan?.travelled;pan=null;svg.classList.remove('panning');try{svg.releasePointerCapture(e.pointerId)}catch(_){}if(!dragged&&!e.target.closest?.('.node'))window.__execweaveClearFocus?.()};svg.addEventListener('wheel',e=>{e.preventDefault();userTookCamera();stopAnimation();const rect=svg.getBoundingClientRect(),mx=e.clientX-rect.left,my=e.clientY-rect.top,old=transform.scale,next=Math.min(4,Math.max(.07,old*Math.exp(-e.deltaY*.0012))),gx=(mx-transform.x)/old,gy=(my-transform.y)/old;transform.scale=next;transform.x=mx-gx*next;transform.y=my-gy*next;applyTransform();updateJumpLatest()},{passive:false});
function focusRawLogEvent(event){const target=event?.target?.id,source=event?.source?.id;if(target&&nodeById.has(target)){selectNode(target,{syncLog:false});focusNode(target);return}if(source&&nodeById.has(source)){selectNode(source,{syncLog:false});focusNode(source)}}
// Focus is only exitable if something offers the exit. The control appears with the
// focus it clears, so the graph never shows a button that does nothing.
//
// This script is injected more than once into a page, so nothing here may declare a
// top-level const or let: a second copy would throw on the duplicate binding and take
// the rest of the file's initialisation down with it. The block is a guarded IIFE and
// publishes its one entry point on window.
(function(){
  if(window.__execweaveClearFocusReady)return;
  window.__execweaveClearFocusReady=true;
  const baseSelectNode=selectNode,baseSelectEdge=selectEdge;
  const focusIsActive=()=>!!selectedNodeId||!!selectedEdgeId;
  const syncClearFocus=()=>{const button=document.getElementById('clear-focus');if(button)button.hidden=!focusIsActive()};
  window.__execweaveClearFocus=function(){
    if(!focusIsActive())return false;
    clearSelection();
    window.__execweaveFocusConversationAgent?.(null);
    syncClearFocus();
    return true;
  };
  selectNode=function(...args){baseSelectNode(...args);syncClearFocus()};
  selectEdge=function(...args){baseSelectEdge(...args);syncClearFocus()};
  document.addEventListener('keydown',event=>{if(event.key==='Escape')window.__execweaveClearFocus()});
  const button=document.getElementById('clear-focus');if(button)button.onclick=()=>window.__execweaveClearFocus();
})();
search.oninput=applySearch;document.getElementById('fit').onclick=()=>fit(true);document.getElementById('zoom-in').onclick=()=>zoomBy(1.2);document.getElementById('zoom-out').onclick=()=>zoomBy(1/1.2);jumpLatest.onclick=()=>{followLatest(true);if(cameraMode==='manual')updateJumpLatest()};document.querySelectorAll('[data-camera]').forEach(button=>button.onclick=()=>setCameraMode(button.dataset.camera));document.querySelectorAll('[data-filter]').forEach(button=>button.onclick=()=>{activityFilter=button.dataset.filter||'all';document.querySelectorAll('[data-filter]').forEach(item=>item.classList.toggle('active',item===button));renderActivities(false)});document.getElementById('raw-rows')?.addEventListener('dblclick',event=>{const row=event.target.closest?.('.raw-row'),raw=row?.querySelector?.('.raw-json')?.textContent;if(!raw)return;try{focusRawLogEvent(JSON.parse(raw))}catch(_){}});themeToggle.onclick=()=>applyTheme(document.documentElement.dataset.theme==='light'?'dark':'light',true);window.onresize=()=>scheduleCamera(true);window.__execweaveCore={getActivities:()=>activities.slice(),getGraph:()=>graph,getPositions:()=>new Map(positions),selectEdge,selectNode,focusNode,markLatest,setCameraMode};applyTheme(initialTheme());applyTransform();poll();
})();"""
