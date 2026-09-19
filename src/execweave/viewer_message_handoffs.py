"""Connect framework message-group selections to exact indexed handoffs.

Installed inside the investigation reader so it reuses its accepted index,
record cards and authenticated refresh contract. No message ownership is inferred.
"""
from __future__ import annotations

MESSAGE_HANDOFFS_JS = r"""
let messagePanel=null,messageView=null,messageScheduled=false;
const messageScope=()=>JSON.stringify([graph().run_id??null,scope()]);
function selectedMessageRoute(){
  const selected=document.querySelector('#nodes .node.selected');
  const display=window.__execweaveCore?.getDisplayGraph?.()||graph();
  const matches=list(display.nodes).filter(n=>n?.id===selected?.dataset.id);
  if(matches.length!==1||matches[0].type!=='message'||matches[0].attributes?.viewer_framework_messages!==true)return null;
  const n=matches[0],a=n.attributes,g=graph(),source=a.sender_agent_id,target=a.recipient_agent_id;
  const route={key:JSON.stringify([messageScope(),n.id,source,target]),source,target,valid:false};
  if(typeof source!=='string'||!source||typeof target!=='string'||!target||source===target)return route;
  const real=record=>[record,record?.attributes||{}].every(o=>['inferred','viewer_only'].every(k=>o[k]===undefined||o[k]===null||o[k]===false));
  const agents=[source,target].map(id=>list(g.nodes).filter(x=>x?.id===id));
  if(agents.some(xs=>xs.length!==1||xs[0].type!=='agent'||xs[0].attributes?.conversation_scope!=='framework_agent'||!real(xs[0])))return route;
  const evidence=list(a.evidence_edge_ids);
  if(!evidence.length||evidence.length>100||new Set(evidence).size!==evidence.length)return route;
  for(const id of evidence){
    if(typeof id!=='string'||!id)return route;
    const edges=list(g.edges).filter(e=>e?.id===id);
    if(edges.length!==1)return route;
    const e=edges[0];
    if(e.source!==source||e.target!==target||!['MESSAGE_SENT','MESSAGE_RECEIVED'].includes(e.relation)||!real(e))return route;
  }
  return {...route,valid:true};
}
function messageRouteRows(route){
  const index=current();if(!route.valid||!compatible(index))return {rows:[],available:false,excluded:0};
  const counts=new Map();for(const row of index.messages)counts.set(row.key,(counts.get(row.key)||0)+1);
  let excluded=0;
  const rows=index.messages.filter(row=>{
    if(row.owner_id!==route.source||row.target_id!==route.target)return false;
    if(typeof row.key!=='string'||!row.key||counts.get(row.key)!==1||row.identity_bound!==true){excluded++;return false}
    return true;
  });
  // Pin only this directional route. A same-name, sibling or reverse route
  // cannot cause its bodies to appear, nor can an update silently replace them.
  return {rows,available:true,excluded};
}
function clearMessagePanel(){
  if(messageView)messageView.request++;
  messagePanel?.remove();messagePanel=null;messageView=null;
}
function renderMessageRows(view){
  const payload=JSON.parse(view.signature),rows=payload.rows;
  view.rows.replaceChildren();
  for(const row of rows.slice(0,view.limit))view.rows.append(card(row,'messages'));
  view.summary.textContent=!view.route.valid?
    'Message routing evidence is missing, ambiguous or inferred. No content is substituted.':
    !payload.available?'The message investigation index is unavailable. Load the accepted index to inspect this route.':
    `${rows.length} indexed message records for this exact directional route. Receipt is not consumption. `+
      (payload.excluded?`${payload.excluded} ambiguous or unbound records withheld. `:'')+
      (rows.length?'Open a record, then its captured body. References are not verified until read.':'No matching indexed body record; this does not prove that no message was sent.');
  view.more.hidden=rows.length<=view.limit;
  if(!view.more.hidden)view.more.textContent=`Show more message records (${Math.min(view.limit,rows.length)}/${rows.length})`;
}
function updateMessageNotice(){
  if(!messageView)return;
  const route=selectedMessageRoute();
  if(!route||route.key!==messageView.route.key||route.valid!==messageView.route.valid){scheduleMessagePanel();return}
  const signature=JSON.stringify(messageRouteRows(route));
  if(signature!==messageView.signature)messageView.notice.textContent='Updated message records are available. The displayed route snapshot remains pinned until you refresh it.';
}
function attachMessagePanel(){
  const route=selectedMessageRoute(),details=document.getElementById('details');
  if(!route||!details){clearMessagePanel();return}
  if(messageView?.route.key===route.key&&messageView.route.valid===route.valid&&messagePanel?.isConnected){updateMessageNotice();return}
  clearMessagePanel();
  const section=make('section');section.id='execweave-message-handoffs';section.dataset.sourceId=route.source||'';section.dataset.targetId=route.target||'';
  const title=make('strong','Recorded message handoffs'),summary=make('p'),notice=make('p'),rows=make('div');
  notice.setAttribute('role','status');notice.className='message-handoff-notice';
  const refresh=button('Load / refresh message records',async()=>{
    const view=messageView;if(!view||view.busy)return;
    const request=++view.request;view.busy=true;refresh.disabled=true;
    try{
      const selected=selectedMessageRoute();
      if(!selected?.valid||selected.key!==view.route.key)throw new Error('route_changed');
      // A previously accepted versioned index is sufficient for local reading.
      // Missing Live inventory can only be acquired by the shared authenticated reader.
      if(!compatible(current())&&!window.__execweaveStaticMode){
        const ok=await window.__execweaveDashboard?.agentPanel?.refresh?.({includeInvestigation:true});
        if(ok!==true)throw new Error('refresh_failed');
      }
      if(messageView!==view||request!==view.request||selectedMessageRoute()?.key!==view.route.key)return;
      if(!compatible(current()))throw new Error('index_unavailable');
      view.route=selectedMessageRoute();view.signature=JSON.stringify(messageRouteRows(view.route));
      view.notice.textContent='';renderMessageRows(view);
    }catch{
      if(messageView===view&&request===view.request)view.notice.textContent='Message index unavailable or refresh failed. Existing records remain readable; no delivery or capture conclusion is implied.';
    }finally{if(messageView===view&&request===view.request){view.busy=false;refresh.disabled=false}}
  });
  refresh.disabled=!route.valid;
  const more=button('Show more message records',()=>{if(messageView){messageView.limit+=25;renderMessageRows(messageView)}});
  const view={route,signature:JSON.stringify(messageRouteRows(route)),summary,notice,rows,more,limit:25,request:0,busy:false};
  messagePanel=section;messageView=view;
  section.append(title,make('p',`${route.source||'Unknown sender'} → ${route.target||'Unknown recipient'}`),summary,refresh,notice,rows,more);
  // Navigation lives outside the original agent/task response text.
  details.before(section);renderMessageRows(view);
}
function scheduleMessagePanel(){
  if(messageScheduled)return;messageScheduled=true;
  queueMicrotask(()=>{messageScheduled=false;attachMessagePanel()});
}
const messageNodes=document.getElementById('nodes'),messageDetails=document.getElementById('details');
if(messageNodes)new MutationObserver(scheduleMessagePanel).observe(messageNodes,{childList:true,subtree:true,attributes:true,attributeFilter:['class','data-id']});
if(messageDetails)new MutationObserver(scheduleMessagePanel).observe(messageDetails,{childList:true,subtree:true});
window.addEventListener('pagehide',clearMessagePanel);scheduleMessagePanel();
""".strip()
