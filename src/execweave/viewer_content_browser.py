"""Bounded, verified, on-demand reading of the inspector's archived content.

This component consumes reference metadata already rendered by the shared panel.
It does not discover owners, parse tool output as routes, change graph evidence,
or read arbitrary workspace paths. Offline reading requires an explicit user
selection of an exported run folder; no content is embedded or silently fetched.
"""
from __future__ import annotations

from .viewer_recorded_sources import inject_recorded_sources

CONTENT_BROWSER_CSS = r"""
.execweave-content-actions{display:flex;flex-wrap:wrap;gap:6px;padding:10px}
.execweave-content-actions button{font:inherit;cursor:pointer;padding:6px 10px}
#execweave-content-dialog{width:min(900px,90vw);max-height:85vh;box-sizing:border-box;border:1px solid var(--border,#888);border-radius:10px;background:var(--panel,#fff);color:var(--text,#111);padding:16px}
#execweave-content-dialog::backdrop{background:rgba(0,0,0,.4)}
#execweave-content-dialog header,.execweave-content-controls{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:10px}
#execweave-content-title{flex:1;margin:0;font-size:18px}
#execweave-content-meta{overflow-wrap:anywhere;font-size:12px}
#execweave-content-status{white-space:pre-wrap;overflow-wrap:anywhere}
#execweave-content-text{white-space:pre-wrap;overflow-wrap:anywhere;overflow:auto;max-height:45vh;font:14px/1.5 ui-monospace,monospace;tab-size:4}
#execweave-content-dialog button,#execweave-content-dialog input{font:inherit;padding:6px}
""".strip()

CONTENT_BROWSER_JS = r"""
(()=>{
'use strict';
if(window.__execweaveContentBrowser)return;
const LIMIT=8*1024*1024,PAGE=16384,TIMEOUT=15000;
const PATH=/^content\/sha256\/([0-9a-f]{64})\.(json|txt|bin)$/;
const inspector=document.getElementById('details');
if(!inspector)return;
let dialog=null,body,status,meta,title,folder,previous,next,search,find,copy;
let generation=0,controller=null,current=null,text=null,page=0,files=new Map(),runKey=null;
const processed=new WeakSet();
function element(tag,id,value){const node=document.createElement(tag);if(id)node.id=id;if(value!==undefined)node.textContent=value;return node}
function button(label,action){const node=element('button',null,label);node.type='button';node.onclick=action;return node}
function graph(){return window.__execweaveCore?.getGraph?.()||window.__execweaveStaticGraph||{}}
function identity(){const g=graph();return JSON.stringify(g.session_id??g.run_id??g.source_path??null)}
function report(state,message){dialog.dataset.state=state;status.textContent=message}
function controls(enabled){for(const node of [previous,next,search,find,copy])node.disabled=!enabled}
function cancel(){generation++;controller?.abort();controller=null;text=null;current=null;page=0;if(body)body.textContent='';if(dialog){controls(false);dialog.close()}}
function reference(value){
  if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('invalid_reference');
  const match=typeof value.path==='string'?PATH.exec(value.path):null;
  if(!match||match[0]!==value.path||value.sha256!==match[1])throw new Error('invalid_reference');
  const nodes=graph().nodes||[];
  const source=nodes.find(node=>node?.type==='observed_content'&&
    ((value.id&&node.id===value.id)||(node.attributes?.path===value.path&&node.attributes?.sha256===value.sha256)));
  const a=source?.attributes||{};
  const result={...a,...value};
  if(result.path!==value.path||result.sha256!==value.sha256)throw new Error('invalid_reference');
  if(result.size_bytes!==undefined&&(!Number.isSafeInteger(result.size_bytes)||result.size_bytes<0))throw new Error('invalid_reference');
  return result;
}
function ensureDialog(){
  if(dialog)return;
  dialog=element('dialog','execweave-content-dialog');dialog.setAttribute('aria-labelledby','execweave-content-title');
  const head=element('header');title=element('h2','execweave-content-title','Recorded content');
  head.append(title,button('Close',cancel));
  meta=element('p','execweave-content-meta');status=element('p','execweave-content-status');status.setAttribute('role','status');
  const actions=element('div');actions.className='execweave-content-controls';
  const load=button('Load / retry',()=>loadCurrent());load.id='execweave-content-load';
  folder=element('input','execweave-content-folder');folder.type='file';folder.multiple=true;folder.setAttribute('webkitdirectory','');folder.setAttribute('aria-label','Choose exported run folder');
  folder.onchange=()=>{
    generation++;controller?.abort();text=null;body.textContent='';controls(false);files=new Map();
    if(folder.files.length>50000){report('folder_limit','Too many files. Choose one exported run folder.');return}
    for(const file of folder.files){
      const relative=String(file.webkitRelativePath||'');
      const slash=relative.indexOf('/');
      const path=slash<0?'':relative.slice(slash+1);
      const match=PATH.exec(path);
      if(match&&match[0]===path)files.set(path,file);
    }
    folder.value='';
    if(!files.size){report('folder_missing','No content/sha256 files found. Choose the exported run folder, not its parent or the content folder.');return}
    loadCurrent();
  };
  const folderLabel=element('label',null,'Offline: choose exported run folder ');folderLabel.append(folder);
  actions.append(load,folderLabel);
  const paging=element('div');paging.className='execweave-content-controls';
  previous=button('Previous page',()=>{page=Math.max(0,page-1);showPage()});
  next=button('Next page',()=>{page++;showPage()});
  search=element('input','execweave-content-search');search.type='search';search.placeholder='Find in full loaded content';search.setAttribute('aria-label','Find in full loaded content');
  find=button('Find',()=>{
    if(text===null)return;
    const index=text.indexOf(search.value);
    if(index<0){report('verified','SHA-256 verified. Search text not found.');return}
    page=Math.floor(index/PAGE);showPage();
  });
  search.onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();find.click()}};
  copy=button('Copy full content',async()=>{
    if(text===null)return;
    const token=generation;
    try{await navigator.clipboard.writeText(text);if(token===generation)report('verified','SHA-256 verified. Full content copied.')}
    catch(_){if(token===generation)report('verified','SHA-256 verified. Clipboard unavailable; select text in the preview.')}
  });
  paging.append(previous,next,search,find,copy);
  body=element('pre','execweave-content-text');
  dialog.append(head,meta,status,actions,paging,body);
  dialog.addEventListener('cancel',event=>{event.preventDefault();cancel()});
  document.body.append(dialog);controls(false);
}
function showPage(){
  if(text===null)return;
  const total=Math.max(1,Math.ceil(text.length/PAGE));page=Math.min(Math.max(0,page),total-1);
  let start=page*PAGE,end=Math.min(text.length,start+PAGE);
  // Keep a supplementary Unicode character intact across page boundaries.
  if(start>0&&/[\uDC00-\uDFFF]/.test(text[start]))start--;
  if(end<text.length&&/[\uD800-\uDBFF]/.test(text[end-1]))end--;
  body.textContent=text.slice(start,end);body.scrollTop=0;
  controls(true);previous.disabled=page===0;next.disabled=page===total-1;
  report('verified',`SHA-256 verified. Page ${page+1}/${total}; full captured file loaded.${text.length===0?' Captured content is empty.':''}`);
}
const ERRORS={
  run_changed:'The active run changed during content retrieval. Reopen the desired reference in the current run.',
  invalid_reference:'Invalid content reference. Only run-local content/sha256 paths matching their recorded hash are allowed.',
  too_large:'Content exceeds the 8 MiB in-browser read limit. No truncated body is being presented as complete; the archived content is unchanged.',
  folder_required:'Offline content is not embedded. Choose the exported run folder to read and verify its captured files.',
  missing_blob:'Recorded content file is missing from this run or selected folder. This is not evidence that the provider never exposed it.',
  unauthorized:'Content access was rejected. Reopen this run with its authorized Dashboard URL, then retry.',
  hash_mismatch:'SHA-256 mismatch. The bytes do not match the recorded reference; content is not displayed.',
  size_mismatch:'Content size does not match the recorded reference; content is not displayed.',
  crypto_unavailable:'SHA-256 verification is unavailable in this browser context. Content is not displayed as verified.',
  binary_content:'The hash matches, but this content is not UTF-8 text. Binary preview is not supported.',
  incomplete_response:'The content server returned a partial response; full-content verification was not performed.',
  stream_unavailable:'Bounded streaming is unavailable in this browser. Content was not loaded.',
  request_failed:'Content could not be loaded. Check the run server and retry; no provider-visibility conclusion is implied.'
};
async function bytesFromResponse(response,signal){
  const length=response.headers.get('content-length');
  if(length!==null&&Number(length)>LIMIT)throw new Error('too_large');
  if(!response.body?.getReader)throw new Error('stream_unavailable');
  const reader=response.body.getReader(),chunks=[];let size=0,complete=false;
  try{
    while(true){
      if(signal.aborted)throw new DOMException('Aborted','AbortError');
      const {done,value}=await reader.read();if(done){complete=true;break}
      size+=value.byteLength;if(size>LIMIT)throw new Error('too_large');chunks.push(value);
    }
  }finally{if(!complete)await reader.cancel().catch(()=>{});reader.releaseLock()}
  const bytes=new Uint8Array(size);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.byteLength}return bytes;
}
async function loadCurrent(){
  if(!current)return;
  const value=current.ref,token=++generation,startedRun=identity();
  controller?.abort();controller=new AbortController();const active=controller;
  const timer=setTimeout(()=>active.abort(),TIMEOUT);
  text=null;page=0;body.textContent='';controls(false);report('loading','Loading recorded content; verification pending.');
  try{
    const ref=reference(value);if(ref.size_bytes>LIMIT)throw new Error('too_large');
    let bytes;
    if(window.__execweaveStaticMode||location.protocol==='file:'){
      if(!files.size)throw new Error('folder_required');
      const file=files.get(ref.path);if(!file)throw new Error('missing_blob');
      if(file.size>LIMIT)throw new Error('too_large');
      bytes=new Uint8Array(await file.arrayBuffer());
    }else{
      const headers={};if(window.__execweaveToken)headers['X-ExecWeave-Token']=window.__execweaveToken;
      const response=await fetch('/'+ref.path,{headers,signal:active.signal,cache:'no-store',credentials:'same-origin',redirect:'error'});
      if(response.status===401||response.status===403)throw new Error('unauthorized');
      if(response.status===404)throw new Error('missing_blob');
      if(response.status===206)throw new Error('incomplete_response');
      if(!response.ok)throw new Error('request_failed');
      bytes=await bytesFromResponse(response,active.signal);
    }
    if(token!==generation)return;
    if(identity()!==startedRun)throw new Error('run_changed');
    if(active.signal.aborted)throw new DOMException('Aborted','AbortError');
    if(ref.size_bytes!==undefined&&bytes.byteLength!==ref.size_bytes)throw new Error('size_mismatch');
    if(!globalThis.crypto?.subtle)throw new Error('crypto_unavailable');
    const digest=await crypto.subtle.digest('SHA-256',bytes);
    if(token!==generation)return;
    if(identity()!==startedRun)throw new Error('run_changed');
    if(active.signal.aborted)throw new DOMException('Aborted','AbortError');
    const actual=Array.from(new Uint8Array(digest),value=>value.toString(16).padStart(2,'0')).join('');
    if(actual!==ref.sha256)throw new Error('hash_mismatch');
    let decoded;try{decoded=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes)}catch(_){throw new Error('binary_content')}
    if(decoded.includes('\u0000'))throw new Error('binary_content');
    text=decoded;showPage();
  }catch(error){
    if(token!==generation)return;
    text=null;body.textContent='';controls(false);
    const state=error?.name==='AbortError'?'cancelled':(ERRORS[error?.message]?error.message:'request_failed');
    report(state,state==='cancelled'?'Content read cancelled or timed out. Retry when ready.':ERRORS[state]);
  }finally{clearTimeout(timer);if(controller===active)controller=null}
}
function open(value,context){
  const key=identity();if(runKey!==null&&key!==runKey){cancel();files=new Map()}runKey=key;
  ensureDialog();generation++;controller?.abort();text=null;body.textContent='';controls(false);current=null;
  title.textContent='Recorded content';meta.textContent=String(context||'');search.value='';
  if(!dialog.open)dialog.showModal();
  try{
    const ref=reference(value);current={ref};
    meta.textContent=[context,ref.content_kind,ref.path,ref.representation,
      ref.complete_from_source===true?'Complete value supplied by source (not proof of hidden provider stages).':
      ref.complete_from_source===false?'Source capture marked partial.':'Source completeness unknown.'
    ].filter(Boolean).join('\n');
    loadCurrent();
  }catch(_){report('invalid_reference',ERRORS.invalid_reference)}
}
function attach(parent,refs,context){
  if(!Array.isArray(refs)||!refs.length)return;
  const actions=element('div');actions.className='execweave-content-actions';
  const seen=new Set();
  for(const ref of refs){
    const key=JSON.stringify([ref?.path,ref?.sha256,ref?.relation]);if(seen.has(key))continue;seen.add(key);
    const relation=String(ref?.relation||ref?.content_kind||'content');
    const label=relation==='HAS_TOOL_INPUT'?'Read input':relation==='HAS_TOOL_OUTPUT'?'Read output':'Read '+relation;
    actions.append(button(label,()=>open(ref,context)));
  }
  parent.append(actions);
}
function refresh(){
  const key=identity();if(runKey!==null&&key!==runKey){cancel();files=new Map()}runKey=key;
  // Only parse metadata containers emitted by the existing inspector. Never parse
  // arbitrary message bodies or tool results to discover paths or owners.
  for(const occurrence of inspector.querySelectorAll('.execweave-tool-occurrence')){
    const pre=occurrence.querySelector(':scope > pre');if(!pre||processed.has(pre))continue;
    processed.add(pre);
    try{const item=JSON.parse(pre.textContent);attach(occurrence,item.content_references,occurrence.querySelector(':scope > summary')?.textContent)}catch(_){}
  }
  for(const occurrence of inspector.querySelectorAll('.execweave-inference-occurrence')){
    for(const card of occurrence.querySelectorAll(':scope > .execweave-agent-card')){
      if(card.querySelector('.execweave-agent-label')?.textContent!=='Content references')continue;
      const pre=card.querySelector('pre');if(!pre||processed.has(pre))continue;processed.add(pre);
      try{attach(card,JSON.parse(pre.textContent),occurrence.querySelector(':scope > summary')?.textContent)}catch(_){}
    }
  }
}
let scheduled=false;
new MutationObserver(()=>{if(scheduled)return;scheduled=true;queueMicrotask(()=>{scheduled=false;refresh()})}).observe(inspector,{childList:true,subtree:true});
window.__execweaveContentBrowser={refresh,close:cancel,attach};refresh();
})();
""".strip()


def inject_content_browser(html: str) -> str:
    """Install one additive component without replacing existing renderer code."""
    if 'id="execweave-content-browser"' in html:
        return inject_recorded_sources(html)
    if "</body>" not in html:
        raise RuntimeError("content browser requires a dashboard body")
    component = (
        '<style id="execweave-content-browser-style">'
        + CONTENT_BROWSER_CSS
        + '</style><script id="execweave-content-browser">'
        + CONTENT_BROWSER_JS
        + "</script>\n"
    )
    return inject_recorded_sources(html.replace("</body>", component + "</body>", 1))
