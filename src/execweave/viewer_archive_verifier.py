"""User-selected offline archive verification; no fetch, execution, or path discovery."""
from __future__ import annotations

ARCHIVE_VERIFIER_JS = r"""
(()=>{
'use strict';
if(globalThis.__execweaveArchiveVerifier)return;
const PRIMARY=['graph.json','conversations.json','viewer.html'];
const PATH=/^content\/sha256\/([0-9a-f]{64})\.(?:txt|json|bin)$/;
const HASH=/^[0-9a-f]{64}$/;
const DEFAULTS={fileBytes:64*1024*1024,totalBytes:256*1024*1024,manifestBytes:16*1024*1024,files:100000,references:100000,jsonTokens:2000000};
const object=v=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const integer=v=>Number.isSafeInteger(v)&&v>=0;
function fail(code,location=''){throw Object.assign(new Error(code),{code,location})}
function check(signal){if(signal?.aborted)fail('cancelled')}
function abortable(promise,signal){
  if(!signal)return promise;check(signal);
  return new Promise((resolve,reject)=>{
    const abort=()=>reject(Object.assign(new Error('cancelled'),{code:'cancelled'}));
    signal.addEventListener('abort',abort,{once:true});
    Promise.resolve(promise).then(value=>{signal.removeEventListener('abort',abort);resolve(value)},
      error=>{signal.removeEventListener('abort',abort);reject(error)});
  });
}
function strictJSON(text,maxTokens=DEFAULTS.jsonTokens){
  // JSON.parse accepts duplicate keys. Detect decoded-key collisions first, so
  // a receipt/index cannot mean something different to the Python verifier.
  let pos=0,tokens=0;
  const number=/-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/y;
  const space=()=>{while(pos<text.length&&' \t\r\n'.includes(text[pos]))pos++};
  function string(key=false){
    const start=pos;if(text[pos++]!=='"')fail('invalid_json');
    while(pos<text.length){const c=text[pos++];if(c==='"')return key?JSON.parse(text.slice(start,pos)):null;if(c==='\\')pos++}
    fail('invalid_json');
  }
  function value(depth){
    if(depth>128||++tokens>maxTokens)fail('verification_limit');space();
    const c=text[pos];
    if(c==='"'){string();return}
    if(c==='{'||c==='['){
      pos++;space();const end=c==='{'?'}':']',keys=new Set();
      if(text[pos]===end){pos++;return}
      while(true){
        space();
        if(c==='{'){const key=string(true);if(keys.has(key))fail('duplicate_json_key');keys.add(key);space();if(text[pos++]!==':')fail('invalid_json')}
        value(depth+1);space();const delimiter=text[pos++];if(delimiter===end)return;if(delimiter!==',')fail('invalid_json');
      }
    }
    for(const literal of ['true','false','null'])if(text.startsWith(literal,pos)){pos+=literal.length;return}
    number.lastIndex=pos;const match=number.exec(text);if(!match)fail('invalid_json');pos=number.lastIndex;
  }
  try{value(0);space();if(pos!==text.length)fail('invalid_json');return JSON.parse(text)}
  catch(error){if(error.code)throw error;fail('invalid_json')}
}
function filesFromSelection(selection){
  const files=new Map(),roots=new Set();let inspected=0;
  for(const file of selection){
    if(++inspected>DEFAULTS.files)fail('verification_limit');
    const relative=file.webkitRelativePath;
    if(typeof relative!=='string'||!relative.includes('/'))fail('invalid_folder');
    const parts=relative.split('/');roots.add(parts.shift());
    if(roots.size!==1||parts.some(p=>!p||p==='.'||p==='..'))fail('invalid_folder');
    const path=parts.join('/');
    if(path!=='finalization.json'&&!PRIMARY.includes(path)&&!PATH.test(path))continue;
    if(files.has(path))fail('duplicate_file',path);files.set(path,file);
  }
  return files;
}
function fingerprint(value){
  return object(value)&&typeof value.sha256==='string'&&HASH.test(value.sha256)&&integer(value.size_bytes);
}
async function verifyArchive(files,scope,{signal,onProgress,limits={}}={}){
  const budget={};for(const [key,value] of Object.entries(DEFAULTS))budget[key]=integer(limits[key])?Math.min(value,limits[key]):value;
  if(!(files instanceof Map)||files.size>budget.files)fail('invalid_folder');
  if(!object(scope)||typeof scope.session_id!=='string'||!scope.session_id)fail('scope_unavailable');
  check(signal);let totalBytes=0,checkedFiles=0;
  async function read(path,expected,asJSON=false,limit=budget.fileBytes){
    check(signal);
    if(path!=='finalization.json'&&!PRIMARY.includes(path)&&!PATH.test(path))fail('invalid_reference',path);
    const file=files.get(path);if(!file)fail('missing_file',path);
    if(!integer(file.size)||file.size>limit||totalBytes+file.size>budget.totalBytes)fail('verification_limit',path);
    if(expected&&!fingerprint(expected))fail('invalid_receipt',path);
    if(expected&&file.size!==expected.size_bytes)fail('size_mismatch',path);
    const bytes=await abortable(file.arrayBuffer(),signal);check(signal);
    if(bytes.byteLength!==file.size)fail('changed_during_read',path);
    totalBytes+=bytes.byteLength;
    if(expected){
      if(!globalThis.crypto?.subtle)fail('crypto_unavailable');
      const hash=await abortable(globalThis.crypto.subtle.digest('SHA-256',bytes),signal);check(signal);
      const actual=Array.from(new Uint8Array(hash),x=>x.toString(16).padStart(2,'0')).join('');
      if(actual!==expected.sha256)fail('hash_mismatch',path);
    }
    checkedFiles++;onProgress?.({checked_files:checkedFiles,checked_bytes:totalBytes});
    if(!asJSON)return;
    let text;try{text=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes)}catch(_){fail('invalid_json',path)}
    return strictJSON(text,budget.jsonTokens);
  }
  const report=await read('finalization.json',null,true,budget.manifestBytes);
  if(!object(report)||report.schema_version!=='0.2'||!object(report.artifacts))fail('unsupported_receipt');
  for(const name of PRIMARY)if(!fingerprint(report.artifacts[name])||report.artifacts[name].size_bytes===0)fail('invalid_receipt',name);
  const graph=await read('graph.json',report.artifacts['graph.json'],true);
  if(!object(graph)||!Array.isArray(graph.nodes))fail('invalid_index','graph.json');
  if(graph.session_id!==scope.session_id||(graph.source_path||null)!==(scope.source_path||null))fail('run_mismatch');
  const conversations=await read('conversations.json',report.artifacts['conversations.json'],true);
  if(!object(conversations)||!Array.isArray(conversations.entries))fail('invalid_index','conversations.json');
  if(typeof conversations.session_id==='string'&&conversations.session_id&&conversations.session_id!==graph.session_id)fail('run_mismatch');
  await read('viewer.html',report.artifacts['viewer.html']);
  const refs=new Map();let referenceCount=0,records=0;
  function register(ref,location){
    if(++referenceCount>budget.references)fail('verification_limit',location);
    if(!object(ref)||typeof ref.path!=='string')fail('invalid_reference',location);
    const match=PATH.exec(ref.path);
    if(!match||match[0]!==ref.path||ref.sha256!==match[1]||('size_bytes' in ref&&!integer(ref.size_bytes)))fail('invalid_reference',location);
    const previous=refs.get(ref.path);
    if(previous?.size_bytes!==undefined&&ref.size_bytes!==undefined&&previous.size_bytes!==ref.size_bytes)fail('conflicting_reference',location);
    refs.set(ref.path,{sha256:ref.sha256,size_bytes:ref.size_bytes??previous?.size_bytes});
  }
  function nodes(items,location){
    if(!Array.isArray(items))fail('invalid_index',location);
    for(let i=0;i<items.length;i++){
      if(++records>budget.files)fail('verification_limit',location);
      if(!object(items[i]))fail('invalid_index',location);
      if(items[i].type==='observed_content')register(items[i].attributes,location+'/'+i);
    }
  }
  nodes(graph.nodes,'graph.json/nodes');
  if(graph.expansion!==undefined){
    if(!object(graph.expansion)||!object(graph.expansion.clusters??{}))fail('invalid_index','graph.json/expansion');
    for(const cluster of Object.values(graph.expansion.clusters||{})){
      if(++records>budget.files)fail('verification_limit');
      nodes(cluster?.nodes,'graph.json/expansion/nodes');
    }
  }
  for(let i=0;i<conversations.entries.length;i++)register(conversations.entries[i],'conversations.json/entries/'+i);
  for(const [path,ref] of refs){
    const file=files.get(path);if(!file)fail('missing_file',path);
    // Legacy references can omit size, but their hash must still be checked.
    await read(path,{sha256:ref.sha256,size_bytes:ref.size_bytes??file.size});
  }
  check(signal);
  return {state:'verified_now',reference_count:referenceCount,verified_file_count:refs.size,
    primary_file_count:3,checked_bytes:totalBytes,checked_at:new Date().toISOString(),
    recorded_state:['recording','exporting','complete','incomplete','failed'].includes(report.state)?report.state:'unknown',
    scope:'declared_graph_and_conversation_content',session_id:graph.session_id,source_path:graph.source_path||null};
}
globalThis.__execweaveArchiveVerifier={verifyArchive,filesFromSelection,strictJSON};
})();
""".strip()
