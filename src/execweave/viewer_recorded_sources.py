"""Expose exact graph-backed source references in the shared inspector.

This is a content navigation surface, not a new conversation/ownership policy.
Only explicit graph edges are followed; names, message bodies and shared model
membership never select another agent's sources.
"""
from __future__ import annotations

RECORDED_SOURCES_JS = r"""
(()=>{
'use strict';
if(window.__execweaveRecordedSources)return;
const inspector=document.getElementById('details');
if(!inspector)return;
const PAGE=25,limits=new Map();
let panel=null,signature='',scheduled=false;
const list=value=>Array.isArray(value)?value:[];
const attr=node=>node?.attributes&&typeof node.attributes==='object'?node.attributes:{};
const make=(tag,text)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node};
function rowsFor(raw,display,id){
  const byId=new Map();
  for(const node of list(raw?.nodes)){
    if(typeof node?.id!=='string')continue;
    // Ambiguous raw identities must not become a last-writer-wins content join.
    byId.set(node.id,byId.has(node.id)?null:node);
  }
  const shown=list(display?.nodes).find(node=>node?.id===id),selected=byId.get(id);
  const owners=new Set();
  if(selected)owners.add(id);
  if(shown?.type==='agent')for(const alias of list(attr(shown).viewer_agent_member_ids)){
    if(typeof alias==='string'&&byId.get(alias)?.type==='agent')owners.add(alias);
  }
  if(!owners.size)return [];
  const links=list(raw?.edges),subjects=new Map([...owners].map(owner=>[owner,null]));
  const callRelations=new Set(['REQUESTED_TOOL_CALL','REQUESTS_TOOL_CALL','REQUESTS_MODEL_CALL']);
  for(const edge of links){
    if(!edge||!owners.has(edge.source)||byId.get(edge.source)?.type!=='agent')continue;
    const target=byId.get(edge.target);
    if(callRelations.has(edge.relation)&&['tool_call','model_call','inference_request'].includes(target?.type)){
      subjects.set(edge.target,edge);
    }
    if(edge.relation==='TASK_CREATED'&&target?.type==='task')subjects.set(edge.target,edge);
  }
  // Assignment evidence has the opposite direction. Never walk through a model
  // resource to all its callers or through a parent to its children.
  for(const edge of links)if(edge&&owners.has(edge.target)&&
    ['ASSIGNED_TO','ASSIGNED_AGENT_TASK'].includes(edge.relation)&&byId.get(edge.source)?.type==='task'){
    subjects.set(edge.source,edge);
  }
  const rows=[];
  for(const [index,edge] of links.entries()){
    if(!edge)continue;
    const forward=subjects.has(edge.source),subject=forward?edge.source:edge.target;
    if(!subjects.has(subject))continue;
    const content=byId.get(forward?edge.target:edge.source);
    if(content?.type!=='observed_content')continue;
    const parent=subjects.get(subject),node=byId.get(subject),a=attr(content);
    rows.push({
      key:JSON.stringify([index,edge.id,edge.source,edge.target,edge.relation]),
      source_id:subject,source_name:node?.name||subject,
      source_relation:parent?.relation||null,
      edge_id:edge.id||null,relation:String(edge.relation||'CONTENT'),
      first_sequence:Number.isInteger(edge.first_sequence)?edge.first_sequence:null,
      timestamp:edge.first_seen||content.first_seen||null,
      count:edge.count??null,
      reference:{...a,id:content.id,relation:String(edge.relation||'CONTENT')}
    });
  }
  return rows.sort((a,b)=>{
    if(a.first_sequence!==null&&b.first_sequence!==null&&a.first_sequence!==b.first_sequence)return b.first_sequence-a.first_sequence;
    return String(b.timestamp||'').localeCompare(String(a.timestamp||''))||a.key.localeCompare(b.key);
  });
}
function refresh(){
  scheduled=false;
  const selected=document.querySelector('#nodes .node.selected');
  const reader=window.__execweaveContentBrowser;
  if(!selected||!reader?.attach){panel?.remove();panel=null;signature='';return}
  const core=window.__execweaveCore,raw=core?.getGraph?.()||window.__execweaveStaticGraph||{};
  const display=core?.getDisplayGraph?.()||raw,id=String(selected.dataset.id||'');
  const rows=rowsFor(raw,display,id);
  if(!rows.length){panel?.remove();panel=null;signature='';return}
  const key=JSON.stringify([raw.run_id,raw.session_id,raw.source_path,id]);
  const cap=limits.get(key)||PAGE,nextSignature=JSON.stringify([key,cap,rows]);
  if(signature===nextSignature&&panel?.isConnected)return;
  signature=nextSignature;panel?.remove();
  panel=make('section');panel.id='execweave-recorded-sources';panel.dataset.sourceId=id;
  panel.append(make('h3','Recorded source content'));
  const notice=make('p',`Showing ${Math.min(cap,rows.length)} of ${rows.length} registered source references. Content is checked when opened; these records do not establish message delivery or task success.`);
  notice.className='execweave-source-notice';panel.append(notice);
  for(const row of rows.slice(0,cap)){
    const card=make('section');card.className='execweave-source-card';card.dataset.sourceId=row.source_id;
    const label=make('strong',[row.timestamp,row.source_name,row.relation].filter(Boolean).join(' · '));
    const provenance=make('p',[row.source_id,row.source_relation,row.edge_id,
      row.count!==null?`${row.count} recorded observation(s)`:null,
      row.reference.content_kind].filter(Boolean).join(' · '));
    card.append(label,provenance);
    reader.attach(card,[row.reference],[id,row.source_id,row.edge_id,row.relation].filter(Boolean).join(' · '));
    panel.append(card);
  }
  if(cap<rows.length){
    const more=make('button','Load more sources');more.type='button';
    more.onclick=()=>{limits.set(key,cap+PAGE);if(limits.size>128)limits.delete(limits.keys().next().value);refresh()};
    panel.append(more);
  }
  inspector.append(panel);
}
function schedule(){if(scheduled)return;scheduled=true;queueMicrotask(refresh)}
new MutationObserver(records=>{
  if(records.some(record=>!panel?.contains(record.target)))schedule();
}).observe(inspector,{childList:true,subtree:true});
const nodes=document.getElementById('nodes');
if(nodes)new MutationObserver(schedule).observe(nodes,{childList:true,subtree:true,attributes:true,attributeFilter:['class','data-id']});
const previous=window.__execweaveDashboard||{};
window.__execweaveDashboard={...previous,
  onPayload(...args){previous.onPayload?.(...args);schedule()},
  onFinished(...args){previous.onFinished?.(...args);schedule()}
};
window.__execweaveRecordedSources={refresh,rowsFor};refresh();
})();
""".strip()

RECORDED_SOURCES_CSS = r"""
#execweave-recorded-sources{margin-top:16px;overflow-wrap:anywhere}
#execweave-recorded-sources h3{font-size:15px}
#execweave-recorded-sources .execweave-source-notice{font-size:12px;color:var(--muted)}
#execweave-recorded-sources .execweave-source-card{padding:10px;margin:8px 0;border:1px solid var(--border,#888);border-radius:8px}
#execweave-recorded-sources .execweave-source-card strong{font-size:13px}
#execweave-recorded-sources .execweave-source-card p{font-size:12px}
""".strip()


def inject_recorded_sources(html: str) -> str:
    if 'id="execweave-recorded-sources-script"' in html:
        return html
    if "</body>" not in html:
        raise RuntimeError("recorded sources require a dashboard body")
    return html.replace(
        "</body>",
        '<style>' + RECORDED_SOURCES_CSS + '</style>'
        '<script id="execweave-recorded-sources-script">' + RECORDED_SOURCES_JS
        + '</script>\n</body>',
        1,
    )
