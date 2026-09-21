"""Versioned, inspectable content-reference coverage, not provider recall."""
from __future__ import annotations

CONTENT_HEALTH_JS = r"""
(()=>{
'use strict';
if(window.__execweaveContentHealth)return;
const list=x=>Array.isArray(x)?x:[],make=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=String(text);return e};
const button=(text,fn)=>{const b=make('button',text);b.type='button';b.onclick=fn;return b};
const raw=()=>window.__execweaveCore?.getGraph?.()||window.__execweaveStaticGraph||{};
const scope=()=>JSON.stringify([raw().run_id??null,raw().session_id??null,raw().source_path??null]);
const validRef=r=>{const m=typeof r?.path==='string'?/^content\/sha256\/([0-9a-f]{64})\.(json|txt|bin)$/.exec(r.path):null;return !!m&&m[0]===r.path&&m[1]===r.sha256&&Number.isSafeInteger(r.size_bytes)&&r.size_bytes>=0};
const labels={registered:'Reference registered; bytes not checked',source_partial:'Source marked incomplete',configured_omission:'Explicit metadata-only capture',not_recorded:'Body not recorded; cause unknown',phase_unobserved:'Phase not observed',invalid:'Invalid or conflicting reference',outside_inventory:'Not in graph inventory',mixed:'Mixed or incomplete references',bounded:'Inspection limit reached'};
function summarize(index){
  const report={denominator_version:'indexed-record-phase-v1',partial:true,groups:[],rows:[],invalid_rows:0};
  if(index?.schema_version!=='0.1'||index.scope!=='recorded_event_investigation'||!['messages','calls','artifacts'].every(k=>Array.isArray(index[k])))return report;
  const inspection=index.inspection||{};
  report.partial=inspection.state!=='scanned_selected_streams'||inspection.graph_inventory_partial===true||inspection.limit_reached===true;
  const definitions=[['model-request','Model request','calls','model','request'],['model-response','Model response','calls','model','response'],
    ['tool-request','Tool arguments','calls','tool','request'],['tool-response','Tool result','calls','tool','response'],
    ['message-sent','Sent message body','messages',null,'sent'],['message-received','Received message body','messages',null,'received'],
    ['artifact','Historical file snapshot','artifacts',null,null]];
  for(const [id,title,tab,kind,phase] of definitions){
    const counts=Object.fromEntries(Object.keys(labels).map(k=>[k,0])),rows=list(index[tab]);
    const group={id,title,total:0,counts,unknown_source_completeness:0};
    const seen=new Map();for(const r of rows.slice(0,10000)){const key=r?.key||r?.id;seen.set(key,(seen.get(key)||0)+1)}
    for(const row of rows.slice(0,10000)){
      if(!row||typeof row!=='object'||Array.isArray(row)||(kind&&row.kind!==kind))continue;
      const key=row.key||row.id;
      if(typeof key!=='string'||!key||seen.get(key)!==1){report.partial=true;report.invalid_rows++;continue}
      const all=tab==='artifacts'?list(row.snapshots):list(row.references).filter(r=>r?.phase===phase);
      const refs=all.slice(0,100),hasPhase=tab==='artifacts'?row.snapshot_count>0:list(row.phases).includes(phase);
      let state;
      if(all.length>100||(tab==='artifacts'&&row.snapshot_count>all.length)||row.reference_count>list(row.references).length)state='bounded';
      else if(!hasPhase&&!refs.length)state='phase_unobserved';
      else if(refs.some(r=>r?.state==='invalid_reference'||(r?.state==='registered_not_read'&&!validRef(r.reference))))state='invalid';
      else if(refs.some(r=>r?.state==='not_in_graph_inventory'))state='outside_inventory';
      else if(refs.length&&refs.every(r=>r?.state==='registered_not_read'&&r.reference&&typeof r.reference.path==='string')){
        state=refs.some(r=>r.reference.complete_from_source===false)?'source_partial':'registered';
        if(refs.some(r=>r.reference.complete_from_source!==true&&r.reference.complete_from_source!==false))group.unknown_source_completeness++;
      }else if(!refs.length||refs.every(r=>r?.state==='not_recorded')){
        const observations=list(row.observations).filter(o=>o?.phase===phase);
        state=observations.length&&observations.every(o=>o.capture_mode==='metadata_only')?'configured_omission':'not_recorded';
      }else state='mixed';
      if(state==='bounded')report.partial=true;
      group.total++;group.counts[state]++;report.rows.push({group:id,tab,key,state,label:row.source_name||row.name||row.native_id||key});
    }
    if(rows.length>10000)report.partial=true;
    report.groups.push(group);
  }
  return report;
}
function verifiedReads(index,ledger){
  const result={denominator_version:'unique-indexed-files-v1',files:0,declared_bytes:0,
    hash_verified_files:0,hash_verified_bytes:0,readable_files:0,readable_bytes:0,
    failed_reads:0,unverified_files:0,conflicting_files:0,partial:false};
  if(document.getElementById('protective')?.hidden===false)return {...result,partial:true};
  const refs=new Map(),bad=new Set();let inspected=0;
  if(index?.schema_version!=='0.1'||index.scope!=='recorded_event_investigation'||
    !['calls','messages','artifacts'].every(k=>Array.isArray(index[k])))return {...result,partial:true};
  const budget=100000;
  outer:for(const tab of ['calls','messages','artifacts'])for(const row of index[tab]){
    if(++inspected>budget){result.partial=true;break outer}
    for(const item of list(tab==='artifacts'?row?.snapshots:row?.references)){
      if(++inspected>budget){result.partial=true;break outer}
      const r=item?.reference;if(!r)continue;
      if(!validRef(r)||item.state!=='registered_not_read'){
        if(typeof r.path==='string')bad.add(r.path);result.partial=true;continue;
      }
      const old=refs.get(r.path);
      if(old&&(old.sha256!==r.sha256||old.size_bytes!==r.size_bytes))bad.add(r.path);
      else refs.set(r.path,r);
    }
  }
  for(const path of bad)refs.delete(path);result.conflicting_files=bad.size;
  const reads=new Map(),duplicate=new Set();
  if(ledger?.schema_version==='1'&&ledger.scope===scope()&&Array.isArray(ledger.records)){
    for(const r of ledger.records.slice(0,10000)){
      if(!r||typeof r.path!=='string')continue;
      if(reads.has(r.path))duplicate.add(r.path);else reads.set(r.path,r);
    }
    if(ledger.evicted||ledger.records.length>10000)result.partial=true;
  }
  // Recheck current graph declarations once, not once per file. A previously
  // verified path cannot override a changed size/hash or conflicting identity.
  const declared=new Map();
  for(const node of list(raw().nodes).slice(0,100000)){
    const a=node?.attributes;
    if(node?.type!=='observed_content'||typeof a?.path!=='string')continue;
    const old=declared.get(a.path);
    if(old===false)continue;
    if(!validRef(a)||(old&&(old.sha256!==a.sha256||old.size_bytes!==a.size_bytes)))declared.set(a.path,false);
    else declared.set(a.path,a);
  }
  if(list(raw().nodes).length>100000)result.partial=true;
  for(const r of refs.values()){
    result.files++;result.declared_bytes+=r.size_bytes;
    const observed=reads.get(r.path),g=declared.get(r.path);
    const bound=observed&&!duplicate.has(r.path)&&observed.sha256===r.sha256&&observed.size_bytes===r.size_bytes&&
      g&&g.sha256===r.sha256&&g.size_bytes===r.size_bytes;
    const verified=bound&&['verified','binary_content'].includes(observed.state)&&observed.hash_verified_bytes===r.size_bytes;
    if(verified){result.hash_verified_files++;result.hash_verified_bytes+=r.size_bytes;
      if(observed.state==='verified'&&observed.readable===true){result.readable_files++;result.readable_bytes+=r.size_bytes}
    }else result.unverified_files++;
    if(bound&&['missing_blob','hash_mismatch','size_mismatch','unauthorized','request_failed','incomplete_response','conflicting_reference','invalid_reference'].includes(observed.state))result.failed_reads++;
  }
  if(!Number.isSafeInteger(result.declared_bytes)){result.declared_bytes=null;result.partial=true}
  const inspection=index.inspection||{};
  result.partial=result.partial||bad.size>0||inspection.state!=='scanned_selected_streams'||
    inspection.graph_inventory_partial===true||inspection.limit_reached===true;
  return result;
}
let pinnedReads=null;
let dialog=null,body,summary,filter,refreshButton,invoker=null,currentScope=scope(),pinned=null,page=0,generation=0;
function close(){generation++;if(refreshButton)refreshButton.disabled=false;dialog?.close();body?.replaceChildren();pinned=null;pinnedReads=null;page=0;invoker?.focus()}
function checkScope(){if(scope()===currentScope)return true;currentScope=scope();close();return false}
function ensure(){
  if(dialog)return;
  dialog=make('dialog');dialog.id='execweave-health-dialog';dialog.setAttribute('aria-labelledby','execweave-health-title');
  const head=make('header'),title=make('h2','Content health');title.id='execweave-health-title';head.append(title,button('Close content health',close));
  const boundary=make('p','Counts describe indexed records and phases, not total provider activity or readable-byte recall. A registered reference has not been read or hash-verified. Source-incomplete, configured omission, missing phase and unknown cause are separate states.');
  summary=make('p');summary.id='execweave-health-summary';summary.setAttribute('role','status');
  filter=make('select');filter.setAttribute('aria-label','Content health category');
  const all=make('option','All categories');all.value='all';filter.append(all);filter.onchange=()=>{page=0;draw()};
  refreshButton=button('Refresh content health',async()=>{
    if(!checkScope()||refreshButton.disabled)return;const request=++generation;refreshButton.disabled=true;
    try{
      if(!window.__execweaveStaticMode){
        const refreshed=await window.__execweaveDashboard?.agentPanel?.refresh?.({includeInvestigation:true});
        // The shared reader reports HTTP, scope and terminal failures as false,
        // not rejected promises. Only its explicit success can replace this view.
        if(refreshed!==true)throw new Error('Index refresh did not complete');
      }
    }
    catch{if(request===generation)summary.textContent='Index refresh failed. The current snapshot is retained.';return}
    finally{if(request===generation)refreshButton.disabled=false}
    if(request!==generation||!checkScope()||!dialog.open)return;capture();draw();
  });
  const controls=make('div');controls.className='health-controls';controls.append(filter,refreshButton,
    button('Previous health records',()=>{page=Math.max(0,page-1);draw()}),button('Next health records',()=>{page++;draw()}));
  body=make('div');body.id='execweave-health-body';dialog.append(head,boundary,summary,controls,body);
  dialog.addEventListener('keydown',e=>{if(e.key==='Escape')e.stopPropagation()});dialog.addEventListener('cancel',e=>{e.preventDefault();close()});document.body.append(dialog);
}
function capture(){
  const index=window.__execweaveInvestigation?.getIndex?.();
  pinned=summarize(index);pinnedReads=verifiedReads(index,window.__execweaveContentBrowser?.getReadOutcomes?.());page=0;
  const chosen=filter.value;while(filter.options.length>1)filter.remove(1);
  for(const g of pinned.groups){const option=make('option',g.title);option.value=g.id;filter.append(option)}
  filter.value=[...filter.options].some(o=>o.value===chosen)?chosen:'all';
}
function draw(){
  if(!pinned||!dialog.open||!checkScope())return;
  body.replaceChildren();
  summary.textContent=`Denominator: ${pinned.denominator_version}. `+(pinned.partial?'Partial or unavailable index; counts are lower bounds. ':'Selected recorded streams inspected. ')+
    'The snapshot stays pinned until Refresh content health. '+(pinned.invalid_rows?`${pinned.invalid_rows} invalid or duplicate record-phase rows withheld. `:'');
  if(!pinned.groups.length){body.append(make('p','No versioned investigation index is available. Refresh to request it. Missing inventory is not zero activity.'));return}
  const reads=pinnedReads,readSummary=make('section');readSummary.id='execweave-health-verified-reads';
  readSummary.append(make('h3','Verified reads in this tab'),
    make('p',`${reads.hash_verified_files}/${reads.files} indexed files hash-verified; ${reads.readable_files} readable as UTF-8. `+
      `${reads.hash_verified_bytes} verified bytes / ${reads.declared_bytes===null?'unknown':reads.declared_bytes} declared bytes; ${reads.readable_bytes} readable verified bytes. `+
      `${reads.failed_reads} latest read failures; ${reads.unverified_files} files without a matching verified result.`),
    make('p','Denominator: '+reads.denominator_version+'. Duplicate references share one byte count, not one invocation. '+
      'Results describe the latest reads in this tab and selected folder, not continuous file integrity, provider recall, task success or an archive certificate. '+
      'Opening another folder or execution resets these results; reloading the page does not retain them. '+
      (reads.partial?'Inventory or retained outcomes are partial. ':'')+`${reads.conflicting_files} conflicting file declaration(s) withheld.`));
  body.append(readSummary);
  const table=make('table');table.id='execweave-health-table';const header=make('tr');
  for(const label of ['Category','Indexed records','Reference registered','Source incomplete','Explicit metadata-only','Other gaps / unknown'])header.append(make('th',label));table.append(header);
  for(const g of pinned.groups){const tr=make('tr');tr.dataset.category=g.id;const c=g.counts;
    for(const value of [g.title,g.total,c.registered,c.source_partial,c.configured_omission,g.total-c.registered-c.source_partial-c.configured_omission])tr.append(make('td',value));table.append(tr)}
  body.append(table,make('p','Registered record-phase entries with unknown source completeness: '+pinned.groups.reduce((n,g)=>n+g.unknown_source_completeness,0)+'. Registration does not certify source completeness.'));
  const rows=pinned.rows.filter(r=>filter.value==='all'||r.group===filter.value),pages=Math.max(1,Math.ceil(rows.length/25));page=Math.min(page,pages-1);
  body.append(make('p',`${rows.length} indexed record-phase rows; page ${page+1}/${pages}. Rows across categories are not unique invocation counts.`));
  for(const row of rows.slice(page*25,(page+1)*25)){
    const card=make('article');card.className='execweave-health-row';card.dataset.state=row.state;
    card.append(make('strong',row.label),make('p',row.group+' · '+labels[row.state]),button('Inspect indexed record',()=>{
      const tab=row.tab,key=row.key;
      if(window.__execweaveInvestigation?.openRecord?.(tab,key))close();
      else summary.textContent='The indexed record changed or is no longer uniquely available. Refresh before inspecting it.';
    }));body.append(card);
  }
}
function open(){checkScope();ensure();invoker=document.activeElement;capture();dialog.showModal();draw()}
const launch=button('Content health',open);launch.id='execweave-content-health-launcher';
const host=document.getElementById('execweave-workflow-controls');if(host)host.append(launch);else{const anchor=document.getElementById('theme-toggle');anchor?.parentElement?.insertBefore(launch,anchor)};
const prior=window.__execweaveDashboard||{};window.__execweaveDashboard={...prior,onPayload(...args){prior.onPayload?.(...args);checkScope()},onFinished(...args){prior.onFinished?.(...args);checkScope()}};
window.addEventListener('pagehide',close);window.__execweaveContentHealth={summarize,verifiedReads,open,close};
})();
""".strip()

CONTENT_HEALTH_CSS = """
#execweave-health-dialog{width:min(1120px,94vw);max-height:90vh;border:1px solid var(--border);border-radius:12px;padding:18px;background:var(--panel);color:var(--text)}
#execweave-health-dialog::backdrop{background:rgba(0,0,0,.45)}
#execweave-health-dialog header,.health-controls{display:flex;align-items:center;gap:8px;flex-wrap:wrap}#execweave-health-title{flex:1;font-size:20px}
#execweave-health-dialog button,#execweave-health-dialog select{font:inherit;padding:7px}#execweave-health-dialog p{font-size:13px;line-height:1.5;overflow-wrap:anywhere}
#execweave-health-body{overflow:auto;max-height:58vh}#execweave-health-table{border-collapse:collapse;font-size:13px;width:100%;margin:12px 0}
#execweave-health-table th,#execweave-health-table td{padding:8px;text-align:left;border:1px solid var(--border)}
.execweave-health-row{padding:9px;margin:8px 0;border:1px solid var(--border);border-radius:8px;overflow-wrap:anywhere}
#execweave-content-health-launcher{font:inherit;padding:6px 10px;cursor:pointer}
""".strip()


def inject_content_health(html: str) -> str:
    if 'id="execweave-content-health-script"' in html:
        return html
    if "</body>" not in html:
        raise RuntimeError("content health requires a dashboard body")
    return html.replace("</body>", "<style>" + CONTENT_HEALTH_CSS + '</style><script id="execweave-content-health-script">' + CONTENT_HEALTH_JS + "</script></body>", 1)
