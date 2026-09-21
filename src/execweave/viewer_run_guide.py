"""Role-first discovery and selected-content priority without graph filtering."""

from __future__ import annotations

RUN_GUIDE_JS = r"""
(()=>{
'use strict';if(window.__execweaveRunGuide)return;
const make=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);return n};
const button=(label,fn)=>{const b=make('button',label);b.type='button';b.onclick=fn;return b};
const list=x=>Array.isArray(x)?x:[],label=x=>typeof x==='string'?x.slice(0,256):'';
const raw=()=>window.__execweaveCore?.getGraph?.()||window.__execweaveStaticGraph||{};
const protectedView=()=>document.getElementById('protective')?.hidden===false;
const scope=()=>JSON.stringify([raw().run_id??null,raw().session_id??null,raw().source_path??null]);
let roleInventoryCurrent=Array.isArray(raw().nodes)&&raw().live_payload_compact!==true;
const inventoryBlocked=()=>protectedView()&&!roleInventoryCurrent;
function payloadGraph(args){const value=args?.[0];return value?.graph&&typeof value.graph==='object'?value.graph:value}
function observePayload(args){const value=payloadGraph(args);if(value?.live_payload_compact===true)roleInventoryCurrent=false;else if(Array.isArray(value?.nodes))roleInventoryCurrent=true}
function evidenceCounts(id,index){
  if(index?.schema_version!=='0.1'||index?.scope!=='recorded_event_investigation')return null;
  const related=row=>row?.owner_id===id||row?.target_id===id||list(row?.relations).some(e=>e?.source===id||e?.target===id);
  return {handoffs:list(index.messages).filter(related).length,calls:list(index.calls).filter(related).length,artifacts:list(index.artifacts).filter(related).length};
}
function roles(graph){
  const nodes=list(graph.nodes),byId=new Map(),bad=new Set();let invalid=0;
  for(const n of nodes.slice(0,100000)){
    if(!n||typeof n.id!=='string'||!n.id||n.id.length>4096){invalid++;continue}
    if(byId.has(n.id)){bad.add(n.id);continue}
    // Register every identity first. A runtime/agent ID collision is not a role.
    byId.set(n.id,n);
  }
  const rows=[];
  for(const [id,n] of byId){
    if(bad.has(id)||n.type!=='agent')continue;
    rows.push({id,name:label(n.name)||id,role:label(n.attributes?.role)||label(n.attributes?.agent_role),
      provider:label(n.attributes?.provider)||label(n.attributes?.framework)});
    if(rows.length>=10000)break;
  }
  rows.sort((a,b)=>a.name.localeCompare(b.name)||a.id.localeCompare(b.id));
  return {rows,ambiguous:bad.size,partial:invalid>0||bad.size>0||nodes.length>100000||rows.length>=10000||
    !!graph.live_payload_compact||!!graph.viewer_projection};
}
const section=document.getElementById('details')?.closest('.inspector-section');if(!section)return;
const host=make('details');host.id='execweave-run-guide';host.open=true;
const summary=make('summary','Start with roles');
const search=make('input');search.type='search';search.placeholder='Find a recorded role';search.setAttribute('aria-label','Find role in run guide');
const status=make('p');status.id='execweave-run-guide-status';status.setAttribute('role','status');
const rowsHost=make('div');rowsHost.id='execweave-run-guide-roles';
const actions=make('div');actions.className='run-guide-actions';
for(const [tab,name] of [['agents','All roles'],['calls','Browse calls'],['messages','Browse handoffs'],['artifacts','Browse artifacts']]){
  actions.append(button(name,()=>{if(!window.__execweaveInvestigation?.openTab?.(tab))status.textContent='The investigation reader is unavailable.'}));
}
const selected=make('div');selected.className='run-guide-selected';selected.hidden=true;
const selectedLabel=make('p');selected.append(selectedLabel);
let selectedRole=null;
function openSelected(tab){
  if(!selectedRole||!window.__execweaveInvestigation?.openForAgent?.(tab,selectedRole.id)){
    status.textContent='No unique accepted evidence index is available for this selected role.';return;
  }
}
for(const [tab,name] of [['messages','Handoffs for selected role'],['calls','Calls for selected role'],['artifacts','Artifacts for selected role']])selected.append(button(name,()=>openSelected(tab)));
selected.append(button('Content health',()=>{if(!window.__execweaveContentHealth?.open)status.textContent='Content health is unavailable.';else window.__execweaveContentHealth.open()}));
let pinned=null,lastScope=scope(),lastKey='',pending=false;
const refreshButton=button('Refresh role list',()=>{if(inventoryBlocked()){update();return}capture();draw()});actions.append(refreshButton);
host.append(summary,search,status,rowsHost,selected,actions);section.prepend(host);
// Discovery comes first only when there is no selected evidence to read.
// Move the existing guide, never close/recreate it: search, focus, buttons and
// disclosure intent survive selection and live history refreshes.
const evidence=document.getElementById('details'),empty=document.getElementById('details-empty');
function placeGuide(){
  const reading=roleInventoryCurrent&&evidence.childElementCount>0&&empty?.hidden!==false;
  const assessment=document.getElementById('execweave-run-assessment');
  if(reading){
    if(evidence.nextSibling!==host)evidence.after(host);
    if(assessment?.parentElement===section&&host.nextSibling!==assessment)host.after(assessment);
  }else{
    if(section.firstChild!==host)section.prepend(host);
    if(assessment?.parentElement===section&&host.nextSibling!==assessment)host.after(assessment);
  }
  // The separate delivery summary is deliberately not moved. Export/sync
  // failures stay ahead of the selected body while full assessment stays reachable.
}
new MutationObserver(placeGuide).observe(evidence,{childList:true});
if(empty)new MutationObserver(placeGuide).observe(empty,{attributes:true,attributeFilter:['hidden']});
const protection=document.getElementById('protective');
if(protection)new MutationObserver(placeGuide).observe(protection,{attributes:true,attributeFilter:['hidden']});
placeGuide();
function capture(){
  pinned=roles(raw());
  const index=window.__execweaveInvestigation?.getIndex?.();
  pinned.rows=pinned.rows.map(r=>({...r,evidence:evidenceCounts(r.id,index)}));
  lastKey=JSON.stringify(roles(raw()));pending=false
}
function inspect(id){
  if(inventoryBlocked()){update();return}
  if(scope()!==lastScope){update();return}
  const current=roles(raw()).rows.filter(r=>r.id===id);
  if(current.length!==1){status.textContent='This exact role is no longer unique. Refresh the role list; no same-name replacement is used.';return}
  const core=window.__execweaveCore;
  if(protectedView()){
    const matches=list(raw().nodes).filter(n=>n?.type==='agent'&&n.id===id);
    if(matches.length!==1){status.textContent='This exact role is not uniquely available in the current full snapshot.';return}
    window.__execweaveDashboard?.agentPanel?.render?.(matches[0]);
    status.textContent='Canvas rendering is paused for safety; showing this exact role from the current full snapshot.';
  }else{
    const display=core?.getDisplayGraph?.()||raw();
    const matches=list(display.nodes).filter(n=>n?.type==='agent'&&(n.id===id||list(n.attributes?.viewer_agent_member_ids).includes(id)));
    if(matches.length!==1){status.textContent='This role is not uniquely represented in the current canvas. All roles retains its indexed evidence.';return}
    core?.selectNode?.(matches[0].id);window.__execweaveDashboard?.agentPanel?.render?.(matches[0]);
  }
  selectedRole=(pinned?.rows||[]).find(r=>r.id===id)||current[0];selected.hidden=false;
  const c=selectedRole.evidence;
  selectedLabel.textContent='Selected exact role: '+selectedRole.name+(c?` · ${c.handoffs} handoff(s) · ${c.calls} call(s) · ${c.artifacts} artifact(s)`: ' · accepted detailed inventory unavailable');
  // A role selection is an explicit action; bring its body into view without
  // fitting the graph or changing the camera mode.
  document.getElementById('details')?.scrollIntoView({block:'nearest'});
}
function draw(){
  if(!pinned)return;
  const q=search.value.toLocaleLowerCase(),matches=pinned.rows.filter(r=>!q||[r.id,r.name,r.role,r.provider].some(v=>v.toLocaleLowerCase().includes(q)));
  const shown=matches.slice(0,q?25:6);rowsHost.replaceChildren();
  for(const r of shown){
    const counts=r.evidence,total=counts?counts.handoffs+counts.calls+counts.artifacts:0;
    const suffix=counts&&total?` · ${counts.handoffs} handoff · ${counts.calls} call · ${counts.artifacts} artifact`:'';
    const b=button([r.name,r.role,r.provider].filter(Boolean).join(' · ')+suffix,()=>inspect(r.id));
    b.dataset.agentId=r.id;b.title=r.id;rowsHost.append(b);
  }
  status.textContent=`${matches.length} recorded role(s); showing ${shown.length}. `+
    (pinned.partial?'Partial published inventory. ':'')+
    (pinned.ambiguous?`${pinned.ambiguous} ambiguous identities withheld. `:'')+
    (pending?'Updated roles are available; refresh to replace this list. ':'')+
    'The complete graph and runtime evidence are unchanged.';
}
function update(){
  const blocked=inventoryBlocked();search.disabled=blocked;
  for(const b of actions.querySelectorAll('button'))b.disabled=blocked;
  if(blocked){pinned=null;selectedRole=null;selected.hidden=true;rowsHost.replaceChildren();status.textContent='Large-graph protection received a compact/stale payload. The retained graph is not used as the current role inventory.';return}
  const now=scope();
  if(now!==lastScope){lastScope=now;search.value='';selectedRole=null;selected.hidden=true;capture();draw();return}
  if(!pinned){capture();draw();return}
  if(JSON.stringify(roles(raw()))!==lastKey){pending=true;status.textContent='Updated roles are available. Refresh the role list; current search and buttons are retained.';return}
  if(protectedView())status.textContent='Large-graph canvas rendering is paused. Role discovery remains available from the current full snapshot; raw evidence is unchanged.';
}
search.addEventListener('input',draw);
const previous=window.__execweaveDashboard||{};
window.__execweaveDashboard={...previous,onPayload(...args){previous.onPayload?.(...args);observePayload(args);update()},onFinished(...args){previous.onFinished?.(...args);update()}};
window.addEventListener('pagehide',()=>{pinned=null;selectedRole=null;selected.hidden=true;rowsHost.replaceChildren();search.value=''});
window.__execweaveRunGuide={roles,refresh:()=>{if(inventoryBlocked()){update();return}capture();draw()}};update();
})();
""".strip()

RUN_GUIDE_CSS = r"""
#execweave-run-guide{margin:0 0 14px;padding:10px;border:1px solid var(--border,#888);border-radius:8px;font-size:13px}
#execweave-run-guide summary{font-size:15px;font-weight:600;cursor:pointer;margin-bottom:8px}
#execweave-run-guide input{box-sizing:border-box;width:100%;font:inherit;padding:6px;background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:5px}
#execweave-run-guide p{font-size:12px;line-height:1.4;overflow-wrap:anywhere}
#execweave-run-guide-roles{display:flex;flex-direction:column;gap:5px;max-height:140px;overflow:auto}
#execweave-run-guide button{font:inherit;background:var(--panel2);color:var(--text);border:1px solid var(--border);border-radius:5px;cursor:pointer;padding:6px;text-align:left;overflow-wrap:anywhere}
#execweave-run-guide .run-guide-actions{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}
""".strip()


def inject_run_guide(html: str) -> str:
    if 'id="execweave-run-guide-script"' in html:
        return html
    if "</body>" not in html:
        raise RuntimeError("run guide requires a dashboard body")
    return html.replace(
        "</body>",
        "<style>"
        + RUN_GUIDE_CSS
        + '</style><script id="execweave-run-guide-script">'
        + RUN_GUIDE_JS
        + "</script></body>",
        1,
    )
