"""Inspect recorded runtime neighborhoods without asserting semantic ownership.

The navigator reads the already-published graph only. Correlation remains labeled
as correlation, disconnected evidence remains searchable, and no workspace path
or remote endpoint is ever opened. Graph geometry and raw data are not mutated.
"""
from __future__ import annotations

RUNTIME_EVIDENCE_JS = r"""
(()=>{
'use strict';
if(window.__execweaveRuntimeEvidence)return;
const PAGE=25,MAX_RECORDS=100000,MAX_ROWS=10000,MAX_RELATIONS=100,MAX_DEPTH=4;
const runtimeTypes=new Set(['process','file','directory','artifact','network_endpoint','network_connection','socket','provider','runtime','model_runtime','inference_runtime','inference_gateway','host']);
const transitTypes=new Set(['process','tool_call','model_call','inference_call','inference_request','agent_execution','agent_turn','command']);
const semanticTypes=new Set(['agent','tool_call','model_call','inference_call','inference_request','agent_execution']);
const list=x=>Array.isArray(x)?x:[],obj=x=>x&&typeof x==='object'&&!Array.isArray(x)?x:{};
const id=x=>typeof x==='string'&&x.length>0&&x.length<=4096?x:null;
const label=x=>typeof x==='string'?x.slice(0,2048):'';
const attrs=x=>obj(x?.attributes);
const viewOnly=x=>[x,attrs(x)].some(o=>o?.viewer_only!==undefined&&o?.viewer_only!==null&&o?.viewer_only!==false);
const inferred=x=>[x,attrs(x)].some(o=>o?.inferred!==undefined&&o?.inferred!==null&&o?.inferred!==false);
const raw=()=>window.__execweaveCore?.getGraph?.()||window.__execweaveStaticGraph||{};
const scope=()=>JSON.stringify([raw().run_id??null,raw().session_id??null,raw().source_path??null]);
const make=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);return n};
const button=(text,action)=>{const b=make('button',text);b.type='button';b.onclick=action;return b};
function buildIndex(graph,anchorIds=[]){
  const byId=new Map(),bad=new Set(),edges=[],edgeIds=new Map(),badEdges=new Set();
  let inspected=0,limited=false,invalid=0,omitted=0;
  const containers=[graph],clusters=obj(obj(graph.expansion).clusters);
  let clusterCount=0;
  for(const cluster of Object.values(clusters)){if(++clusterCount>1000){limited=true;break}if(cluster&&typeof cluster==='object')containers.push(cluster)}
  for(const container of containers)for(const key of ['nodes','edges']){
    if(container[key]!==undefined&&!Array.isArray(container[key])){invalid++;continue}
    for(const item of list(container[key])){
      if(inspected++>=MAX_RECORDS){limited=true;break}
      if(!item||typeof item!=='object'||Array.isArray(item)){invalid++;continue}
      if(viewOnly(item))continue;
      if(key==='nodes'){
        const key=id(item.id);if(!key){invalid++;continue}
        // Conflicting IDs are withheld. Labels never resolve an identity.
        if(byId.has(key)){if(JSON.stringify(byId.get(key))!==JSON.stringify(item))bad.add(key)}else byId.set(key,item);
      }else{
        if(!id(item.source)||!id(item.target)||!id(item.relation)){invalid++;continue}
        const key=id(item.id);
        if(key&&edgeIds.has(key)){if(JSON.stringify(edgeIds.get(key))!==JSON.stringify(item))badEdges.add(key)}else{if(key)edgeIds.set(key,item);edges.push(item)}
      }
    }
  }
  for(const key of bad)byId.delete(key);
  const adjacency=new Map();
  let dangling=0;
  for(const e of edges){
    if(badEdges.has(e.id))continue;
    if(!byId.has(e.source)||!byId.has(e.target)){dangling++;continue}
    for(const key of new Set([e.source,e.target])){if(!adjacency.has(key))adjacency.set(key,[]);adjacency.get(key).push(e)}
  }
  const edgeRow=e=>({id:id(e.id),source:e.source,target:e.target,relation:e.relation,
    inferred:inferred(e),causal:e.causal===true&&attrs(e).causal!==false&&!inferred(e),timestamp:label(e.first_seen),
    count:Number.isSafeInteger(e.count)&&e.count>=0?e.count:null});
  const seeds=[...new Set(list(anchorIds).filter(x=>id(x)&&byId.has(x)))];
  const paths=new Map(seeds.map(x=>[x,[]])),queue=[...seeds];let traversed=0,walkLimited=false;
  for(let at=0;at<queue.length;at++){
    const current=queue[at],path=paths.get(current);
    if(path.length>=MAX_DEPTH){if((adjacency.get(current)||[]).length)walkLimited=true;continue}
    for(const e of adjacency.get(current)||[]){
      if(++traversed>MAX_RECORDS){walkLimited=true;break}
      const next=e.source===current?e.target:e.source,node=byId.get(next);
      if(!node||paths.has(next)||node.type==='agent')continue;
      // Never use shared model/tool/file/network resources to bridge siblings.
      // Calls can be found from a selected shared resource, but not crossed
      // through it while starting from a particular agent or invocation.
      if(!runtimeTypes.has(node.type)&&!transitTypes.has(node.type))continue;
      if(byId.get(current)?.type==='process'&&node.type==='process'&&e.source!==current)continue;
      paths.set(next,[...path,edgeRow(e)]);
      if(transitTypes.has(node.type))queue.push(next);
      if(paths.size>=MAX_ROWS){walkLimited=true;break}
    }
    if(traversed>MAX_RECORDS||paths.size>=MAX_ROWS)break;
  }
  const rows=[];
  for(const [key,n] of byId){
    if(!runtimeTypes.has(n.type))continue;
    if(rows.length>=MAX_ROWS){omitted++;continue}
    const all=adjacency.get(key)||[],a=attrs(n),metadata={};
    // Do not dump arbitrary attributes or fetch a body, file, or URL.
    for(const k of ['pid','ppid','path','host','port','protocol','provider','runtime','executable','operation','status','return_code']){
      const v=a[k];if(typeof v==='string')metadata[k]=label(v);else if(typeof v==='number'&&Number.isFinite(v))metadata[k]=v;else if(typeof v==='boolean')metadata[k]=v;
    }
    const links=all.map(edgeRow),direct=all.some(e=>semanticTypes.has(byId.get(e.source===key?e.target:e.source)?.type));
    rows.push({id:key,name:label(n.name)||key,type:n.type,first_seen:label(n.first_seen),last_seen:label(n.last_seen),metadata,
      path:paths.get(key)||null,direct_semantic_link:direct,relations:links.slice(0,MAX_RELATIONS),relation_count:links.length});
  }
  return {rows,seeds,requested_anchors:list(anchorIds),inspected:Math.min(inspected,MAX_RECORDS),invalid,
    ambiguous_ids:bad.size,ambiguous_edge_ids:badEdges.size,dangling_edges:dangling,omitted,
    partial:limited||omitted>0||bad.size>0||badEdges.size>0||invalid>0||dangling>0||!!graph.live_payload_compact||!!graph.viewer_projection,
    walk_limited:walkLimited,max_depth:MAX_DEPTH};
}
let dialog=null,search,category,connection,status,notice,body,previous,next,reset;
let pinned=null,anchors=[],currentScope=scope(),page=0,invoker=null,selectionPanel=null,selectionKey='';
const opened=new Set();
function close(){if(dialog){dialog.close();body.replaceChildren();search.value='';notice.textContent=''}pinned=null;anchors=[];invoker?.focus()}
function checkScope(){if(scope()===currentScope)return true;currentScope=scope();opened.clear();close();return false}
function ensure(){
  if(dialog)return;
  dialog=make('dialog');dialog.id='execweave-runtime-dialog';dialog.setAttribute('aria-labelledby','execweave-runtime-title');
  const head=make('header'),title=make('h2','Runtime evidence');title.id='execweave-runtime-title';head.append(title,button('Close runtime evidence',close));
  const boundary=make('p','Recorded graph relationships are navigation evidence, not proof of agent ownership. Inferred correlation stays labeled. Remote-tool internals and unobserved file contents are not reconstructed. Display labels and metadata values are limited to 2,048 characters.');
  const form=make('form');search=make('input');search.type='search';search.setAttribute('aria-label','Search runtime evidence');search.placeholder='Search exact IDs, paths, hosts, processes or relationships';
  category=make('select');category.setAttribute('aria-label','Runtime category');
  for(const [value,title] of [['all','All runtime records'],['process','Processes'],['files','Files and artifacts'],['network','Network'],['other','Providers and other runtime']]){const o=make('option',title);o.value=value;category.append(o)}
  connection=make('select');connection.setAttribute('aria-label','Runtime link filter');
  for(const [value,title] of [['all','All relationship evidence'],['inferred','Has inferred relationship'],['no_direct','No direct agent/call edge']]){const o=make('option',title);o.value=value;connection.append(o)}
  form.onsubmit=e=>{e.preventDefault();page=0;draw()};category.onchange=()=>form.requestSubmit();connection.onchange=()=>form.requestSubmit();form.append(search,category,connection,button('Search runtime',()=>form.requestSubmit()));
  const controls=make('div');controls.className='runtime-controls';
  previous=button('Previous runtime records',()=>{page--;draw()});next=button('Next runtime records',()=>{page++;draw()});
  reset=button('Show all runtime evidence',()=>{anchors=[];pinned=buildIndex(raw());page=0;search.value='';notice.textContent='';draw()});
  controls.append(previous,next,reset,button('Refresh runtime snapshot',()=>{if(checkScope()){pinned=buildIndex(raw(),anchors);notice.textContent='';draw()}}));
  status=make('p');status.id='execweave-runtime-status';status.setAttribute('role','status');notice=make('p');notice.id='execweave-runtime-updates';notice.setAttribute('role','status');
  body=make('div');body.id='execweave-runtime-rows';dialog.append(head,boundary,form,controls,status,notice,body);
  dialog.addEventListener('cancel',e=>{e.preventDefault();close()});document.body.append(dialog);
}
function inspect(id){
  if(!checkScope())return;
  const core=window.__execweaveCore,display=core?.getDisplayGraph?.()||raw();
  const matches=list(display.nodes).filter(n=>n?.id===id);
  if(matches.length!==1){notice.textContent='This exact node is collapsed or absent in the current canvas. Its recorded identity and relationships remain readable here.';return}
  close();core?.selectNode?.(id);
}
function rowCard(row){
  const card=make('details');card.className='execweave-runtime-row';card.dataset.runtimeId=row.id;
  card.append(make('summary',[row.type,row.name,row.id].join(' · ')));
  let rendered=false;
  function render(){
    if(rendered)return;rendered=true;card.append(make('p','Exact recorded identity: '+row.id));
    card.append(button('Inspect this runtime node',()=>inspect(row.id)));
    for(const [key,value] of Object.entries(row.metadata))card.append(make('p',key+': '+value));
    if(row.first_seen||row.last_seen)card.append(make('p','Observed: '+row.first_seen+' — '+row.last_seen));
    if(anchors.length){
      card.append(make('p','Recorded navigation path from the selected source (not an ownership claim):'));
      for(const e of row.path||[])card.append(make('p',[e.source,e.relation,e.target,e.inferred?'INFERRED / CORRELATED':'Recorded relationship',e.id||'Edge ID unavailable'].join(' · ')));
    }
    if(!row.direct_semantic_link)card.append(make('p','No direct agent/call edge was recorded for this node. Indirect relationships may exist; no owner is invented.'));
    card.append(make('p',`${row.relation_count} recorded incident relationship(s); showing ${Math.min(row.relation_count,MAX_RELATIONS)}.`));
    for(const e of row.relations)card.append(make('p',[e.source,e.relation,e.target,e.inferred?'INFERRED / CORRELATED — not observed causality':e.causal?'Recorded causal edge':'Recorded relationship — causality not established',e.id||'Edge ID unavailable',e.timestamp].filter(Boolean).join(' · ')));
    if(row.relation_count>MAX_RELATIONS)card.append(make('p','Relationship preview limit reached. The original graph is unchanged.'));
  }
  card.open=opened.has(row.id);if(card.open)render();
  card.addEventListener('toggle',()=>{if(!card.isConnected)return;if(card.open){opened.add(row.id);render();while(opened.size>512)opened.delete(opened.values().next().value)}else opened.delete(row.id)});
  return card;
}
function draw(){
  if(!dialog?.open||!pinned||!checkScope())return;
  const q=search.value.toLocaleLowerCase(),c=category.value,f=connection.value;
  const rows=pinned.rows.filter(r=>{
    if(anchors.length&&r.path===null)return false;
    const group=r.type==='process'?'process':['file','directory','artifact'].includes(r.type)?'files':['network_endpoint','network_connection','socket'].includes(r.type)?'network':'other';
    if(c!=='all'&&c!==group)return false;
    if(f==='inferred'&&!r.relations.some(e=>e.inferred)&&!list(r.path).some(e=>e.inferred))return false;
    if(f==='no_direct'&&r.direct_semantic_link)return false;
    return !q||JSON.stringify(r).toLocaleLowerCase().includes(q);
  });
  const pages=Math.max(1,Math.ceil(rows.length/PAGE));page=Math.max(0,Math.min(page,pages-1));previous.disabled=page===0;next.disabled=page===pages-1;
  reset.hidden=!anchors.length;
  status.textContent=`${rows.length} matching / ${pinned.rows.length} indexed runtime nodes. Page ${page+1}/${pages}. `+
    (anchors.length?'Selected source(s): '+anchors.join(', ')+`. Paths are limited to ${MAX_DEPTH} edges; shared resources do not bridge agents. `:'All indexed runtime nodes, including disconnected evidence. ')+
    (pinned.partial?'Partial published inventory; counts are lower bounds, not total capture or attribution recall. ':'Counts describe this published graph, not real-world activity recall. ')+
    (pinned.walk_limited?'Navigation boundary reached. ':'')+
    (pinned.invalid||pinned.ambiguous_ids||pinned.ambiguous_edge_ids||pinned.dangling_edges?`Excluded: ${pinned.invalid} malformed records, ${pinned.ambiguous_ids} conflicting node IDs, ${pinned.ambiguous_edge_ids} conflicting edge IDs, ${pinned.dangling_edges} unresolved edges. `:'')+
    (pinned.omitted?`${pinned.omitted} runtime rows exceed the output limit. `:'');
  if(anchors.length&&pinned.seeds.length!==anchors.length)status.textContent+='One or more selected identities are missing or ambiguous in raw evidence; names are not substituted.';
  body.replaceChildren();body.scrollTop=0;for(const row of rows.slice(page*PAGE,(page+1)*PAGE))body.append(rowCard(row));
  if(!rows.length)body.append(make('p','No matching recorded runtime path. This does not prove no runtime activity occurred. Show all runtime evidence to inspect unlinked records.'));
}
function open(ids=[]){checkScope();ensure();invoker=document.activeElement;anchors=typeof ids==='string'?[ids]:list(ids).filter(x=>id(x));pinned=buildIndex(raw(),anchors);page=0;search.value='';category.value='all';connection.value='all';notice.textContent='';dialog.showModal();draw()}
function attachSelection(){
  const selected=document.querySelector('#nodes .node.selected'),details=document.getElementById('details');
  if(!selected||!details){selectionPanel?.remove();selectionPanel=null;selectionKey='';return}
  const id=selected.dataset.id,g=window.__execweaveCore?.getDisplayGraph?.()||raw(),node=list(g.nodes).find(n=>n?.id===id);
  if(!node){selectionPanel?.remove();selectionPanel=null;selectionKey='';return}
  const members=list(attrs(node).viewer_agent_member_ids);
  // A projected agent can only refer to raw agent identities, never runtime
  // nodes or a same-named peer. Missing members remain unresolved seeds.
  const ids=node.type==='agent'&&members.length?members.filter(key=>{const n=list(raw().nodes).find(n=>n?.id===key);return !n||n.type==='agent'}):[id];
  if(!ids.length)ids.push(id);
  const key=JSON.stringify([scope(),id,ids]);if(selectionPanel?.isConnected&&selectionKey===key)return;
  selectionPanel?.remove();selectionKey=key;selectionPanel=make('section');selectionPanel.id='execweave-runtime-selection';
  selectionPanel.append(button('Runtime evidence for selection',()=>open(ids)));details.append(selectionPanel);
}
let scheduled=false;
function schedule(){if(scheduled)return;scheduled=true;queueMicrotask(()=>{scheduled=false;attachSelection()})}
const details=document.getElementById('details');if(details)new MutationObserver(records=>{if(records.some(r=>!selectionPanel?.contains(r.target)))schedule()}).observe(details,{childList:true,subtree:true});
const nodes=document.getElementById('nodes');if(nodes)new MutationObserver(schedule).observe(nodes,{childList:true,subtree:true,attributes:true,attributeFilter:['class','data-id']});
const launch=button('Runtime evidence',()=>open());launch.id='execweave-runtime-launcher';const anchor=document.getElementById('theme-toggle');if(anchor?.parentElement)anchor.parentElement.insertBefore(launch,anchor);
const prior=window.__execweaveDashboard||{};
function changed(){if(!checkScope())return;if(dialog?.open)notice.textContent='New graph evidence is available. The current runtime snapshot remains pinned until you refresh it.';schedule()}
window.__execweaveDashboard={...prior,onPayload(...args){prior.onPayload?.(...args);changed()},onFinished(...args){prior.onFinished?.(...args);changed()}};
window.addEventListener('pagehide',()=>{close();opened.clear()});
window.__execweaveRuntimeEvidence={open,close,buildIndex};schedule();
})();
""".strip()

RUNTIME_EVIDENCE_CSS = r"""
#execweave-runtime-launcher{font:inherit;cursor:pointer;padding:6px 10px}
#execweave-runtime-selection{margin:10px 0}#execweave-runtime-selection button{font:inherit;cursor:pointer;padding:7px 10px}
#execweave-runtime-dialog{width:min(1100px,94vw);max-height:90vh;box-sizing:border-box;background:var(--panel,#fff);color:var(--text,#111);border:1px solid var(--border,#888);border-radius:12px;padding:18px}
#execweave-runtime-dialog::backdrop{background:rgba(0,0,0,.45)}
#execweave-runtime-dialog header,#execweave-runtime-dialog form,.runtime-controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
#execweave-runtime-title{flex:1;font-size:20px;margin:0}
#execweave-runtime-dialog button,#execweave-runtime-dialog input,#execweave-runtime-dialog select{font:inherit;padding:7px;cursor:pointer}
#execweave-runtime-dialog input{flex:1;min-width:180px}
#execweave-runtime-dialog p{font-size:13px;line-height:1.5;overflow-wrap:anywhere}
#execweave-runtime-rows{max-height:52vh;overflow:auto;overscroll-behavior:contain}
#execweave-runtime-rows details{padding:10px;border:1px solid var(--border,#888);border-radius:8px;margin:8px 0;overflow-wrap:anywhere}
#execweave-runtime-rows summary{font-size:15px;cursor:pointer}
""".strip()


def inject_runtime_evidence(html: str) -> str:
    if 'id="execweave-runtime-script"' in html:
        return html
    if "</body>" not in html:
        raise RuntimeError("runtime evidence requires a dashboard body")
    return html.replace(
        "</body>", "<style>" + RUNTIME_EVIDENCE_CSS
        + '</style><script id="execweave-runtime-script">' + RUNTIME_EVIDENCE_JS
        + "</script>\n</body>", 1,
    )
