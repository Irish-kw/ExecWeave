"""Searchable investigation workspace without changing graph geometry or evidence."""
from __future__ import annotations

INVESTIGATION_JS = r"""
(()=>{
'use strict';
if(window.__execweaveInvestigation)return;
const make=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);return n};
const list=x=>Array.isArray(x)?x:[],text=x=>typeof x==='string'?x:'';
const graph=()=>window.__execweaveCore?.getGraph?.()||window.__execweaveStaticGraph||{};
const scope=()=>JSON.stringify([graph().session_id||null,graph().source_path||null]);
const keyOf=x=>JSON.stringify([x?.session_id||null,x?.source_path||null]);
const PAGE=25,opened=new Set();
let liveIndex=null,pinned=null,currentScope=scope(),dialog=null,query,kind,status,notice,body,next,prev,refreshButton;
let page=0,focusId='',activeTab='agents',invoker=null;
const button=(label,action)=>{const b=make('button',label);b.type='button';b.onclick=action;return b};
function compatible(value){return typeof value?.session_id==='string'&&value.session_id.length>0&&value.schema_version==='0.1'&&value.scope==='recorded_event_investigation'&&keyOf(value)===scope()&&
  ['agents','messages','calls','artifacts'].every(k=>Array.isArray(value[k])&&value[k].length<=10000&&value[k].every(r=>r&&typeof r==='object'&&!Array.isArray(r)))}
function fallback(){
  const g=graph(),seen=new Map(),agents=[];
  for(const n of list(g.nodes).slice(0,100000))if(n?.type==='agent'&&typeof n.id==='string'){
    seen.set(n.id,seen.has(n.id)?null:n);
  }
  for(const [id,n] of seen)if(n&&agents.length<10000)agents.push({id,name:n.name||id,role:n.attributes?.role||n.attributes?.agent_role||'',provider:n.attributes?.provider||'unknown'});
  return {session_id:g.session_id,source_path:g.source_path,agents,messages:[],calls:[],artifacts:[],inspection:{state:'unavailable'}};
}
function clear(){
  if(dialog){dialog.close();body.replaceChildren();query.value='';notice.textContent=''}
  pinned=null;focusId='';page=0;
}
function checkScope(){
  if(scope()===currentScope)return true;
  currentScope=scope();liveIndex=null;opened.clear();clear();return false;
}
function setIndex(value){
  checkScope();if(!compatible(value)){if(dialog?.open)notice.textContent='Index not accepted: missing, malformed, or different run identity.';return false}liveIndex=value;
  if(dialog?.open)notice.textContent='Index updated. Refresh to inspect the new snapshot; the open page is unchanged.';
}
function current(){return liveIndex|| (compatible(window.__execweaveStaticInvestigation)?window.__execweaveStaticInvestigation:null)||fallback()}
function ensure(){
  if(dialog)return;
  dialog=make('dialog');dialog.id='execweave-investigation-dialog';dialog.setAttribute('aria-labelledby','execweave-investigation-title');
  const head=make('header'),title=make('h2','Explore run');title.id='execweave-investigation-title';
  head.append(title,button('Close exploration',()=>{clear();invoker?.focus()}));
  const tabs=make('nav');tabs.setAttribute('aria-label','Investigation category');
  for(const [name,label] of [['agents','Agents'],['messages','Handoffs'],['calls','Model / tool calls'],['artifacts','Files / artifacts']]){
    const b=button(label,()=>{activeTab=name;page=0;draw()});b.dataset.tab=name;tabs.append(b);
  }
  const form=make('form');query=make('input');query.type='search';query.setAttribute('aria-label','Search investigation');query.placeholder='Search names, exact IDs, events or relations';
  kind=make('select');kind.setAttribute('aria-label','Investigation filter');
  for(const [value,label] of [['all','All records'],['attention','Needs attention']]){const o=make('option',label);o.value=value;kind.append(o)}
  const search=button('Search records',()=>form.requestSubmit());
  form.onsubmit=e=>{e.preventDefault();if(checkScope()){page=0;draw()}};kind.onchange=()=>form.requestSubmit();form.append(query,kind,search);
  const controls=make('div');controls.className='investigation-controls';
  prev=button('Previous page',()=>{page--;draw()});next=button('Next page',()=>{page++;draw()});
  refreshButton=button('Refresh index',async()=>{
    if(!checkScope()||refreshButton.disabled)return;
    refreshButton.disabled=true;
    // Reuse the existing authenticated request and its terminal guard. No timer.
    try{if(!window.__execweaveStaticMode)await window.__execweaveDashboard?.agentPanel?.refresh?.({includeInvestigation:true})}finally{refreshButton.disabled=false}
    if(!checkScope()||!dialog.open)return;pinned=current();notice.textContent='';draw();
  });
  controls.append(prev,next,refreshButton,button('Clear agent filter',()=>{focusId='';page=0;draw()}));
  status=make('p');status.id='execweave-investigation-status';status.setAttribute('role','status');
  notice=make('p');notice.id='execweave-investigation-updates';notice.setAttribute('role','status');
  body=make('div');body.id='execweave-investigation-rows';
  dialog.append(head,tabs,form,controls,status,notice,body);
  dialog.addEventListener('cancel',e=>{e.preventDefault();clear()});document.body.append(dialog);
}
function refs(parent,rows,context){
  for(const item of list(rows)){
    const labels={registered_not_read:'Recorded reference; verify by opening',not_recorded:'No body recorded in this observation',invalid_reference:'Invalid content reference',not_in_graph_inventory:'Reference absent from the exported graph inventory'};
    parent.append(make('p',[item.phase||item.relation,labels[item.state]||item.state,item.timestamp].filter(Boolean).join(' · ')));
    if(item.reference)window.__execweaveContentBrowser?.attach(parent,[item.reference],context);
  }
}
function attention(row){
  if(activeTab==='messages')return !row.identity_bound||!list(row.phases).includes('received');
  if(activeTab==='calls')return list(row.phases).includes('failure')||!list(row.phases).includes('response')||list(row.references).some(x=>x.state!=='registered_not_read');
  if(activeTab==='artifacts')return !list(row.snapshots).some(x=>x.reference);
  return false;
}
function selectedRows(){
  const q=query.value.toLocaleLowerCase();
  return list(pinned?.[activeTab]).filter(row=>{
    if(focusId&&activeTab!=='agents'&&row.owner_id!==focusId&&row.target_id!==focusId&&
      !list(row.relations).some(e=>e.source===focusId||e.target===focusId))return false;
    if(kind.value==='attention'&&!attention(row))return false;
    // Only index metadata is searchable. Do not parse or auto-fetch body text.
    return !q||JSON.stringify(row).toLocaleLowerCase().includes(q);
  });
}
function inspectAgent(row){
  const core=window.__execweaveCore,shown=list(core?.getDisplayGraph?.()?.nodes||graph().nodes);
  const matches=shown.filter(n=>n?.type==='agent'&&(n.id===row.id||list(n.attributes?.viewer_agent_member_ids).includes(row.id)));
  if(matches.length===1){clear();core?.selectNode?.(matches[0].id);window.__execweaveDashboard?.agentPanel?.render?.(matches[0]);return}
  notice.textContent='This agent is not uniquely represented in the current canvas. Its indexed evidence remains available here.';
}
function card(row){
  const tab=activeTab;
  const article=make('details');article.className='investigation-row';article.dataset.recordId=row.key||row.id;
  let summary;
  if(tab==='agents')summary=[row.name,row.role,row.provider].filter(Boolean).join(' · ');
  else if(tab==='artifacts')summary=[row.name,row.snapshot_count?'Snapshot reference recorded':'No file snapshot recorded'].join(' · ');
  else if(tab==='messages')summary=[row.source_name+' → '+row.target_name,list(row.phases).includes('received')?'Receipt observed':'Receipt not observed',row.native_id||'Message ID unavailable'].join(' · ');
  else summary=[row.source_name,row.kind,row.target_name,list(row.phases).join(' / '),row.native_id||'Call ID unavailable'].join(' · ');
  article.append(make('summary',summary));
  const readingKey=JSON.stringify([tab,row.key||row.id]);
  let rendered=false;
  article.addEventListener('toggle',()=>{
    if(article.open){opened.add(readingKey);if(opened.size>512)opened.delete(opened.values().next().value)}else opened.delete(readingKey);
    if(!article.open||rendered)return;rendered=true;
    if(tab==='agents'){
      article.append(make('p','Exact source: '+row.id),button('Inspect agent',()=>inspectAgent(row)),
        button('Show agent handoffs',()=>{focusId=row.id;activeTab='messages';query.value='';kind.value='all';page=0;draw()}),
        button('Show agent calls',()=>{focusId=row.id;activeTab='calls';query.value='';kind.value='all';page=0;draw()}));return;
    }
    if(tab==='artifacts'){
      article.append(make('p','File identity: '+row.id));
      if(!row.snapshot_count)article.append(make('p','Only a file/path observation is available. The current workspace file is not read or presented as a historical snapshot.'));
      refs(article,row.snapshots,row.id);
      if(row.related_content_count){article.append(make('p','Associated content below has no recognized file-snapshot contract.'));refs(article,row.related_content,row.id)}
      for(const e of list(row.relations))article.append(make('p',[e.source,e.relation,e.target,e.edge_id,e.causal===true?'Recorded causal edge':'Relationship only; no producer/consumer inference'].join(' · ')));
      if(row.relation_count>list(row.relations).length||row.snapshot_count>list(row.snapshots).length)article.append(make('p','Additional relationships exceed this bounded metadata preview. Inspect the original graph for the remainder.'));
      return;
    }
    article.append(make('p','Native occurrence: '+(row.native_id||'Unavailable')+' · '+(row.owner_id||'Unknown owner')+' → '+(row.target_id||'Unknown target')));
    if(tab==='messages')article.append(make('p','Sent, addressed and received are separate observations. Receipt is not proof of consumption, comprehension or successful work. Consumption: not observed by this contract.'));
    else article.append(make('p','Request, response and failure are retained separately. A response does not imply task success. This view does not observe the internals of a remote tool.'));
    if(!row.identity_bound)article.append(make('p','Occurrence/participant identity is incomplete; unrelated records are not joined.'));
    if(row.observation_basis==='explicit_graph_call')article.append(make('p','Graph-backed call identity. Content relationships are not a complete invocation transcript.'));
    if(list(row.owner_candidates).length>1)article.append(make('p','Conflicting owner candidates (not assigned): '+row.owner_candidates.join(', ')));
    refs(article,row.references,row.native_id);
    if(row.reference_count>list(row.references).length)article.append(make('p','Additional references exceed this bounded preview; inspect the original graph for the remainder.'));
    for(const event of list(row.observations))article.append(make('p',[event.phase,event.timestamp,event.event_id,event.stream+':'+event.line,event.capture_mode].filter(Boolean).join(' · ')));
  });
  if(opened.has(readingKey))article.open=true;
  return article;
}
function draw(){
  if(!dialog.open||!checkScope())return;
  const rows=selectedRows(),total=Math.max(1,Math.ceil(rows.length/PAGE));page=Math.min(Math.max(0,page),total-1);
  body.replaceChildren();for(const row of rows.slice(page*PAGE,(page+1)*PAGE))body.append(card(row));
  if(!rows.length)body.append(make('p','No matching indexed records. This does not establish that no activity occurred. Existing agent history and raw evidence remain available.'));
  prev.disabled=page===0;next.disabled=page===total-1;
  for(const b of dialog.querySelectorAll('[data-tab]'))b.setAttribute('aria-pressed',String(b.dataset.tab===activeTab));
  const inventory=pinned?.inspection||{},partial=inventory.state!=='scanned_selected_streams'||inventory.graph_inventory_partial;
  status.textContent=`${rows.length} indexed ${activeTab}; page ${page+1}/${total}. ${focusId?'Agent filter: '+focusId+'. ':''}`+
    (partial?'Partial or unavailable event inventory. ':'Selected recorded streams inspected. ')+
    'Counts refer to indexed records, not provider recall or task success. Body references are verified only when opened.';
  if(inventory.scope_rejected||inventory.invalid_records||inventory.conflicting_event_ids)status.textContent+=
    ` Excluded: ${inventory.scope_rejected||0} foreign-scope, ${inventory.invalid_records||0} invalid, ${inventory.conflicting_event_ids||0} conflicting event ID(s).`;
  if(inventory.limit_reached||inventory.agent_rows_omitted||inventory.call_rows_omitted||inventory.artifact_rows_omitted)status.textContent+=' Inspection/output limit reached; counts are lower bounds.';
  if(activeTab==='calls'&&rows.length){
    const known=rows.filter(r=>r.owner_id).length,outputs=rows.filter(r=>list(r.references).some(x=>x.phase==='response'&&x.state==='registered_not_read')).length;
    status.textContent+=` Visible call inventory: owner identified ${known}/${rows.length}; response-content reference registered ${outputs}/${rows.length}. References have not been read or verified by these counts.`;
  }
  if(activeTab==='messages'&&rows.length){
    const received=rows.filter(r=>list(r.phases).includes('received')).length;
    status.textContent+=` Visible message inventory: receipt evidence ${received}/${rows.length}. Remaining receipts are unobserved, not proven delivery failures.`;
  }
}
function open(){
  checkScope();ensure();invoker=document.activeElement;pinned=current();page=0;notice.textContent='';dialog.showModal();draw();
  if(!window.__execweaveStaticMode&&!liveIndex){
    void window.__execweaveDashboard?.agentPanel?.refresh?.({includeInvestigation:true}).then(()=>{if(dialog.open&&checkScope())notice.textContent='Index request completed. Use Refresh index to load available records.'});
  }
}
const launcher=button('Explore run',open);launcher.id='execweave-explore-run';
const anchor=document.getElementById('theme-toggle');
if(anchor?.parentElement)anchor.parentElement.insertBefore(launcher,anchor);else document.getElementById('inspector')?.prepend(launcher);
const prior=window.__execweaveDashboard||{};
window.__execweaveDashboard={...prior,onPayload(...args){prior.onPayload?.(...args);checkScope()},onFinished(...args){prior.onFinished?.(...args);checkScope()}};
window.addEventListener('pagehide',()=>{clear();liveIndex=null;opened.clear()});
window.__execweaveInvestigation={setIndex,open,close:clear};
})();
""".strip()

INVESTIGATION_CSS = r"""
#execweave-explore-run{font:inherit;cursor:pointer;padding:6px 10px}
#execweave-investigation-dialog{width:min(1100px,94vw);max-height:90vh;box-sizing:border-box;background:var(--panel,#fff);color:var(--text,#111);border:1px solid var(--border,#888);border-radius:12px;padding:18px}
#execweave-investigation-dialog::backdrop{background:rgba(0,0,0,.45)}
#execweave-investigation-dialog header,#execweave-investigation-dialog nav,#execweave-investigation-dialog form,.investigation-controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 10px}
#execweave-investigation-title{flex:1;font-size:20px;margin:0}
#execweave-investigation-dialog button,#execweave-investigation-dialog input,#execweave-investigation-dialog select{font:inherit;padding:7px;cursor:pointer}
#execweave-investigation-dialog input{flex:1;min-width:200px}
#execweave-investigation-dialog [aria-pressed=true]{font-weight:700;border-bottom:3px solid currentColor}
#execweave-investigation-status,#execweave-investigation-updates{font-size:13px;line-height:1.5;overflow-wrap:anywhere}
#execweave-investigation-rows{max-height:56vh;overflow:auto;overscroll-behavior:contain}
#execweave-investigation-rows details{padding:10px;border:1px solid var(--border,#888);border-radius:8px;margin:8px 0;overflow-wrap:anywhere}
#execweave-investigation-rows summary{font-size:15px;cursor:pointer}
#execweave-investigation-rows p{font-size:13px;line-height:1.5}
""".strip()


def inject_investigation(html: str) -> str:
    if 'id="execweave-investigation-script"' in html:
        return html
    if "</body>" not in html:
        raise RuntimeError("investigation requires a dashboard body")
    return html.replace("</body>", "<style>" + INVESTIGATION_CSS + '</style><script id="execweave-investigation-script">'
                        + INVESTIGATION_JS + "</script>\n</body>", 1)
