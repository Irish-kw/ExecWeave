"""Opt-in structural sharing through a strict output allowlist.

This is intentionally not a raw-run export or a promise of anonymization. All
names, original IDs, paths, hosts, bodies, timestamps and arbitrary metadata are
omitted. The original capture and archive hashes are never rewritten.
"""
from __future__ import annotations

STRUCTURE_SHARE_JS = r"""
(()=>{
'use strict';if(window.__execweaveStructureShare)return;
const typeNames={agent:'Agent',session:'Session',task:'Task',agent_task:'Task',tool:'Tool',tool_call:'Tool call',model:'Model',
  model_call:'Model call',inference_request:'Model request',process:'Process',file:'File',directory:'Directory',artifact:'Artifact',
  network_endpoint:'Network endpoint',network_connection:'Network connection',observed_content:'Captured content',message:'Message'};
const relationNames={SPAWNED:'spawn',LAUNCHED:'launch',REQUESTED_TOOL_CALL:'tool request',REQUESTS_TOOL_CALL:'tool request',USES_TOOL:'tool use',
  REQUESTS_MODEL_CALL:'model request',USED_MODEL:'model use',SENT_MESSAGE:'message send',MESSAGE_SENT:'message send',RECEIVED_MESSAGE:'message receipt',
  MESSAGE_RECEIVED:'message receipt',ASSIGNED_TO:'assignment',HAS_CHILD_AGENT_SESSION:'child session',READ:'read',WROTE:'write',CONNECTED_TO:'network connection',
  HAS_TOOL_INPUT:'tool input',HAS_TOOL_OUTPUT:'tool output',OBSERVED_INFERENCE_REQUEST:'model input',OBSERVED_INFERENCE_RESPONSE:'model output',
  OBSERVED_FILE_CONTENT_BEFORE_READ:'file snapshot',CORRELATED_WITH_PROCESS:'process correlation'};
const make=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);return n};
const button=(label,fn)=>{const b=make('button',label);b.type='button';b.onclick=fn;return b};
const list=x=>Array.isArray(x)?x:[],own=(o,k)=>Object.prototype.hasOwnProperty.call(o,k);
const raw=()=>window.__execweaveCore?.getGraph?.()||window.__execweaveStaticGraph||{};
const scope=()=>JSON.stringify([raw().run_id??null,raw().session_id??null,raw().source_path??null]);
function project(graph){
  if(!graph||!Array.isArray(graph.nodes)||!Array.isArray(graph.edges))throw new Error('No graph inventory is available.');
  if(graph.live_payload_compact)throw new Error('A compact payload is not a complete shareable snapshot.');
  if(graph.nodes.length>10000||graph.edges.length>20000)throw new Error('Structural export exceeds the safety limit (10,000 nodes / 20,000 edges).');
  const source=new Map(),ambiguous=new Set();let invalid=0;
  for(const n of graph.nodes){
    if(!n||typeof n!=='object'||typeof n.id!=='string'||!n.id){invalid++;continue}
    if(source.has(n.id))ambiguous.add(n.id);else source.set(n.id,n);
  }
  const identities=new Map(),nodes=[];
  for(const [id,n] of source){if(ambiguous.has(id))continue;const key='node-'+(nodes.length+1),type=own(typeNames,n.type)?typeNames[n.type]:'Other';
    identities.set(id,key);nodes.push({id:key,type,label:type+' '+(nodes.length+1)});
  }
  const edgeIds=new Set(),ambiguousEdges=new Set();
  for(const e of graph.edges)if(typeof e?.id==='string'){if(edgeIds.has(e.id))ambiguousEdges.add(e.id);edgeIds.add(e.id)}
  const edges=[];let omittedEdges=0;
  for(const e of graph.edges){
    if(!e||typeof e!=='object'||ambiguousEdges.has(e.id)||!identities.has(e.source)||!identities.has(e.target)){omittedEdges++;continue}
    const inferred=e.inferred===true||e.attributes?.inferred===true;
    const knownFlags=[e.inferred,e.attributes?.inferred,e.viewer_only,e.attributes?.viewer_only,e.causal,e.attributes?.causal].every(v=>v===undefined||v===null||typeof v==='boolean');
    const presentation=e.viewer_only===true||e.attributes?.viewer_only===true;
    const causal=knownFlags&&!inferred&&!presentation&&e.causal===true&&e.attributes?.causal!==false;
    edges.push({id:'edge-'+(edges.length+1),source:identities.get(e.source),target:identities.get(e.target),
      relation:own(relationNames,e.relation)?relationNames[e.relation]:'other recorded relationship',
      evidence:presentation?'presentation only':inferred?'inferred correlation':causal?'recorded causal edge':'causality not established'});
  }
  return {schema_version:'1',scope:'structure_only_derived_summary',original_ids_included:false,content_included:false,
    names_paths_hosts_timestamps_included:false,inventory_partial:!!graph.viewer_projection||invalid>0||ambiguous.size>0||omittedEdges>0,
    omitted_nodes:graph.nodes.length-nodes.length,ambiguous_node_ids:ambiguous.size,omitted_edges:omittedEdges,nodes,edges,
    limitation:'Topology and counts can still identify a sensitive workflow. Review before sharing. This is not the original archive, proof of completeness, or a guarantee of anonymity.'};
}
const escape=x=>String(x).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
function renderDocument(data){
  // Accept only freshly projected data in production; escape again for defense
  // in depth. No raw graph object, external URL, script, or imported template.
  return '<!doctype html><html lang="en"><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"><title>ExecWeave structural summary</title>'+ 
    '<style>body{font:16px/1.5 system-ui;max-width:1100px;margin:32px auto;padding:16px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #888;text-align:left;padding:8px}p{overflow-wrap:anywhere}</style>'+ 
    '<h1>ExecWeave structural summary</h1><p>'+escape(data.limitation)+'</p><p>Original content, names, IDs, paths, hosts and timestamps are not included.</p>'+ 
    '<p>'+data.nodes.length+' nodes; '+data.edges.length+' relationships; inventory '+(data.inventory_partial?'partial':'derived from the selected published graph')+'.</p>'+ 
    '<h2>Participants and resources</h2><table><tr><th>Pseudonymous ID</th><th>Category</th></tr>'+data.nodes.map(n=>'<tr><td>'+escape(n.id)+'</td><td>'+escape(n.type)+'</td></tr>').join('')+'</table>'+ 
    '<h2>Recorded relationships</h2><table><tr><th>From</th><th>Relationship</th><th>To</th><th>Evidence boundary</th></tr>'+ 
    data.edges.map(e=>'<tr><td>'+escape(e.source)+'</td><td>'+escape(e.relation)+'</td><td>'+escape(e.target)+'</td><td>'+escape(e.evidence)+'</td></tr>').join('')+'</table></html>';
}
let dialog=null,body,status,confirmation,downloads,prepareButton,invoker=null,currentScope=scope(),generation=0,prepared=null;
const urls=new Set();
function discard(){generation++;prepared=null;if(prepareButton)prepareButton.disabled=false;for(const url of urls)URL.revokeObjectURL(url);urls.clear();if(downloads)for(const b of downloads.children)b.disabled=true}
function close(){discard();dialog?.close();body?.replaceChildren();if(confirmation)confirmation.checked=false;invoker?.focus()}
function checkScope(){if(scope()===currentScope)return true;currentScope=scope();close();return false}
function save(name,value,type){
  if(!checkScope()||!prepared||!confirmation.checked)return;
  const link=make('a'),url=URL.createObjectURL(new Blob([value],{type}));urls.add(url);link.href=url;link.download=name;
  document.body.append(link);link.click();link.remove();setTimeout(()=>{URL.revokeObjectURL(url);urls.delete(url)},1000);
}
async function prepare(){
  if(!checkScope())return;discard();const token=generation,started=scope();body.replaceChildren();confirmation.checked=false;prepareButton.disabled=true;
  status.textContent='Preparing a separate allowlisted summary; the original run is not changed.';
  try{
    if(document.getElementById('protective')?.hidden===false)throw new Error('Large-graph protection is active. A stale canvas cannot be exported as the current run.');
    const data=project(raw()),json=JSON.stringify(data,null,2)+'\n',html=renderDocument(data);
    if(!globalThis.crypto?.subtle)throw new Error('Native SHA-256 is unavailable in this browser context. No export was prepared.');
    const digest=async s=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s))),x=>x.toString(16).padStart(2,'0')).join('');
    const jsonHash=await digest(json),htmlHash=await digest(html);
    if(token!==generation||started!==scope()||!dialog.open)return;
    prepared={json,html,checksum:jsonHash+'  execweave-structure.json\n'+htmlHash+'  execweave-structure.html\n'};
    status.textContent=`Prepared ${data.nodes.length} pseudonymous nodes and ${data.edges.length} relationships. ${data.inventory_partial?'Partial inventory. ':''}These hashes cover the new derived files, not the source archive.`;
    body.append(make('p','JSON SHA-256: '+jsonHash),make('p','HTML SHA-256: '+htmlHash),make('pre',json));
  }catch(e){if(token===generation)status.textContent=String(e.message||'Unable to prepare summary.');}
  finally{if(token===generation)prepareButton.disabled=false}
}
function ensure(){
  if(dialog)return;dialog=make('dialog');dialog.id='execweave-share-dialog';dialog.setAttribute('aria-labelledby','execweave-share-title');
  const header=make('header'),title=make('h2','Share structure only');title.id='execweave-share-title';header.append(title,button('Close structural sharing',close));
  const warning=make('p','This mode omits all original names, IDs, paths, hosts, timestamps, conversation bodies, tool arguments/results and arbitrary metadata. It preserves only pseudonymous graph structure and fixed relationship categories. Topology and counts may still be sensitive. This is not an anonymization guarantee or a replacement for a full audit archive.');
  status=make('p');status.id='execweave-share-status';status.setAttribute('role','status');
  prepareButton=button('Prepare structural preview',prepare);
  confirmation=make('input');confirmation.type='checkbox';confirmation.id='execweave-share-confirm';
  const label=make('label');label.append(confirmation,document.createTextNode(' I reviewed the derived structure and accept that topology and counts may still be sensitive.'));
  downloads=make('div');downloads.className='share-actions';
  downloads.append(button('Save structural JSON',()=>save('execweave-structure.json',prepared?.json,'application/json')),
    button('Save structural HTML',()=>save('execweave-structure.html',prepared?.html,'text/html')),
    button('Save derived checksums',()=>save('execweave-structure.sha256',prepared?.checksum,'text/plain')));
  confirmation.onchange=()=>{for(const b of downloads.children)b.disabled=!prepared||!confirmation.checked};
  body=make('div');body.id='execweave-share-preview';dialog.append(header,warning,prepareButton,status,label,downloads,body);
  dialog.addEventListener('keydown',e=>{if(e.key==='Escape')e.stopPropagation()});dialog.addEventListener('cancel',e=>{e.preventDefault();close()});document.body.append(dialog);discard();
}
function open(){checkScope();ensure();invoker=document.activeElement;status.textContent='Nothing is exported until you prepare, review, confirm and save.';dialog.showModal()}
const launch=button('Share structure',open);launch.id='execweave-share-launcher';const host=document.getElementById('execweave-workflow-controls');if(host)host.append(launch);else{const anchor=document.getElementById('theme-toggle');anchor?.parentElement?.insertBefore(launch,anchor)};
const prior=window.__execweaveDashboard||{};window.__execweaveDashboard={...prior,onPayload(...args){prior.onPayload?.(...args);checkScope()},onFinished(...args){prior.onFinished?.(...args);checkScope()}};
window.addEventListener('pagehide',close);window.__execweaveStructureShare={project,renderDocument,open,close};
})();
""".strip()

STRUCTURE_SHARE_CSS = """
#execweave-share-dialog{width:min(1000px,94vw);max-height:88vh;border:1px solid var(--border);border-radius:12px;padding:18px;background:var(--panel);color:var(--text)}
#execweave-share-dialog::backdrop{background:rgba(0,0,0,.45)}#execweave-share-dialog header,.share-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
#execweave-share-title{flex:1;font-size:20px}#execweave-share-dialog button{font:inherit;padding:7px}
#execweave-share-dialog p,#execweave-share-dialog label{font-size:13px;line-height:1.5;overflow-wrap:anywhere}
#execweave-share-preview{max-height:42vh;overflow:auto}#execweave-share-preview pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}
#execweave-share-launcher{font:inherit;padding:6px 10px;cursor:pointer}.share-actions{margin:10px 0}
""".strip()


def inject_structure_share(html: str) -> str:
    if 'id="execweave-structure-share-script"' in html:
        return html
    if "</body>" not in html:
        raise RuntimeError("structural sharing requires a dashboard body")
    return html.replace("</body>", "<style>" + STRUCTURE_SHARE_CSS + '</style><script id="execweave-structure-share-script">' + STRUCTURE_SHARE_JS + "</script></body>", 1)
