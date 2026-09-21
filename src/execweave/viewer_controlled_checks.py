"""Pinned-key verification for built-in byte predicates, never arbitrary task truth."""

from __future__ import annotations

import json as _json

from .controlled_checks import LIMITATION

CONTROLLED_CORE_JS = r"""
(()=>{
'use strict';if(globalThis.__execweaveControlledCore)return;
const FORMAT='execweave.controlled-checks.v1',PROFILE='execweave.verifier-profile.v1',POLICY='execweave.fixed-check-policy.v1';
const DOMAIN='ExecWeave fixed checks v1\0',LIMIT=2*1024*1024,FILE=8*1024*1024;
const own=(v,k)=>Object.prototype.hasOwnProperty.call(v,k),obj=v=>v&&typeof v==='object'&&!Array.isArray(v);
const fail=m=>{throw new Error(m)},match=(v,r)=>typeof v==='string'&&r.exec(v)?.[0]===v;
const hex=v=>match(v,/^[a-f0-9]{64}$/);
function fields(v,keys){if(!obj(v)||Object.keys(v).length!==keys.length||keys.some(k=>!own(v,k)))fail('Unsupported fields.');return v}
function text(v,max){if(typeof v!=='string'||!v.trim()||Array.from(v).length>max)fail('Invalid text.');return v}
function parse(raw,limit=LIMIT,safe=true){
  if(typeof raw!=='string'||new TextEncoder().encode(raw).length>limit)fail('JSON byte limit exceeded.');
  const parser=globalThis.__execweaveArchiveVerifier?.strictJSON;if(!parser)fail('Strict JSON reader unavailable.');
  if(safe){
    const tokens=raw.matchAll(/"(?:\\[\s\S]|[^"\\])*"|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/g);
    for(const token of tokens)if(token[0][0]!=='"'&&!match(token[0],/^-?(?:0|[1-9][0-9]*)$/))fail('Only literal safe JSON integers are supported.');
  }
  const value=parser(raw);
  function walk(v,depth=0){
    if(depth>32)fail('JSON nesting exceeds 32.');
    if(typeof v==='number'&&(!Number.isFinite(v)||(safe&&!Number.isSafeInteger(v))))fail('Only safe JSON integers are supported.');
    if(typeof v==='string'&&Array.from(v).some(c=>c.codePointAt(0)>=0xd800&&c.codePointAt(0)<=0xdfff))fail('Invalid Unicode.');
    if(Array.isArray(v))for(const x of v)walk(x,depth+1);
    else if(obj(v))for(const [k,x] of Object.entries(v)){walk(k,depth+1);walk(x,depth+1)}
  }
  walk(value);return value;
}
async function hash(value){
  if(!globalThis.crypto?.subtle)fail('Native cryptography unavailable.');
  const bytes=typeof value==='string'?new TextEncoder().encode(value):value;
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),v=>v.toString(16).padStart(2,'0')).join('');
}
function unbase64(value,size){
  if(typeof value!=='string'||value.length!==4*Math.ceil(size/3))fail('Invalid signature/key encoding.');
  let raw;try{raw=atob(value)}catch{fail('Invalid signature/key encoding.')}
  if(raw.length!==size||btoa(raw)!==value)fail('Noncanonical signature/key encoding.');
  return Uint8Array.from(raw,c=>c.charCodeAt(0));
}
function path(v){
  text(v,512);
  if(v.normalize('NFC')!==v||/[\\:*?"<>|\x00-\x1f\x7f]/.test(v)||v.split('/').some(p=>!p||p==='.'||p==='..'||/[ .]$/.test(p)||/^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)/i.test(p)))fail('Invalid relative artifact path.');
  return v;
}
function policy(raw){
  const p=fields(parse(raw,128*1024),['format','name','checks']);
  if(p.format!==POLICY)fail('Unsupported fixed-check policy.');text(p.name,256);
  if(!Array.isArray(p.checks)||!p.checks.length||p.checks.length>100)fail('Policy requires 1 to 100 checks.');
  const ids=new Set(),names=new Map();
  for(const c of p.checks){
    fields(c,c?.op==='json_pointer_equals'?['id','path','op','expected','pointer']:['id','path','op','expected']);
    if(!match(c.id,/^[A-Za-z0-9_.-]{1,96}$/)||ids.has(c.id))fail('Invalid or duplicate check identity.');ids.add(c.id);
    path(c.path);const name=c.path.toLowerCase();if(names.has(name)&&names.get(name)!==c.path)fail('Case-colliding policy paths.');names.set(name,c.path);
    if(c.op==='sha256_equals'){if(!hex(c.expected))fail('Invalid expected SHA-256.')}
    else if(c.op==='utf8_contains')text(c.expected,65536);
    else if(c.op==='json_pointer_equals'){
      if(typeof c.pointer!=='string'||Array.from(c.pointer).length>2048||(c.pointer&&!c.pointer.startsWith('/'))||/~(?![01])/.test(c.pointer)||c.pointer.split('/').length-1>32)fail('Invalid JSON pointer.');
      if(c.expected!==null&&!['string','number','boolean'].includes(typeof c.expected))fail('Expected JSON scalar required.');
      if(typeof c.expected==='string'&&Array.from(c.expected).length>65536)fail('Expected scalar exceeds limit.');
    }else fail('Executable or unknown check operation rejected.');
  }
  return p;
}
async function profile(value){
  fields(value,['format','label','key_id','public_key_b64','policy_sha256']);
  if(value.format!==PROFILE||!hex(value.key_id)||!hex(value.policy_sha256))fail('Invalid verifier profile.');text(value.label,256);
  const raw=unbase64(value.public_key_b64,32);if(await hash(raw)!==value.key_id)fail('Profile key fingerprint mismatch.');
  return value;
}
async function verify(envelope,pinned){
  await profile(pinned);fields(envelope,['format','key_id','payload','signature_b64']);
  if(envelope.format!==FORMAT||envelope.key_id!==pinned.key_id)fail('Receipt does not match the independently pinned key.');
  if(typeof envelope.payload!=='string'||new TextEncoder().encode(envelope.payload).length>LIMIT/2)fail('Signed payload exceeds limit.');
  let publicKey;try{publicKey=await crypto.subtle.importKey('raw',unbase64(pinned.public_key_b64,32),'Ed25519',false,['verify'])}catch{fail('Native Ed25519 verification unavailable; no authenticated result.')}
  if(!await crypto.subtle.verify('Ed25519',publicKey,unbase64(envelope.signature_b64,64),new TextEncoder().encode(DOMAIN+envelope.payload)))fail('Signature verification failed.');
  const p=fields(parse(envelope.payload),['format','scope','subject','task_snapshot_json','policy_json','policy_sha256','artifacts','results','execution_id','recorded_at','task_success_implied','limitation']);
  if(p.format!=='execweave.fixed-check-execution.v1'||p.task_success_implied!==false||p.limitation!==__LIMITATION__)fail('Unsupported execution semantics.');
  fields(p.scope,['session_id','run_id','source_path']);text(p.scope.session_id,4096);
  for(const k of ['run_id','source_path'])if(p.scope[k]!==null)text(p.scope[k],4096);
  fields(p.subject,['task_id','task_snapshot_sha256']);text(p.subject.task_id,4096);
  const node=parse(p.task_snapshot_json,1024*1024,false);
  if(!obj(node)||node.id!==p.subject.task_id||node.type!=='task'||[node,obj(node.attributes)?node.attributes:{}].some(o=>['inferred','viewer_only'].some(k=>o[k]!==undefined&&o[k]!==null&&o[k]!==false))||await hash(p.task_snapshot_json)!==p.subject.task_snapshot_sha256)fail('Signed task snapshot mismatch.');
  const plan=policy(p.policy_json),policyHash=await hash(p.policy_json);
  if(policyHash!==p.policy_sha256||policyHash!==pinned.policy_sha256)fail('Policy was not independently approved by this profile.');
  if(!match(p.execution_id,/^[0-9a-f]{32}$/))fail('Invalid execution identity.');text(p.recorded_at,64);
  const m=fields(p.artifacts,['format','entries','manifest_sha256']);
  if(m.format!=='execweave.selected-artifact-versions.v1'||!Array.isArray(m.entries)||!m.entries.length||m.entries.length>100)fail('Invalid signed artifact inventory.');
  const names=new Set(),byPath=new Map();let total=0;
  for(const item of m.entries){
    fields(item,['path','size_bytes','sha256']);path(item.path);const name=item.path.toLowerCase();
    if(names.has(name)||!Number.isSafeInteger(item.size_bytes)||item.size_bytes<0||item.size_bytes>FILE||!hex(item.sha256))fail('Invalid or duplicate signed artifact.');
    names.add(name);byPath.set(item.path,item);total+=item.size_bytes;if(total>64*1024*1024)fail('Artifact inventory exceeds limit.');
  }
  if(await hash(JSON.stringify(m.entries.map(e=>[e.path,e.size_bytes,e.sha256])))!==m.manifest_sha256)fail('Signed artifact manifest mismatch.');
  if(byPath.size!==new Set(plan.checks.map(c=>c.path)).size||plan.checks.some(c=>!byPath.has(c.path)))fail('Policy/artifact coverage mismatch.');
  if(!Array.isArray(p.results)||p.results.length!==plan.checks.length)fail('Missing or extra executed checks.');
  const counts={passed:0,failed:0,error:0},reasons={passed:['predicate_true'],failed:['predicate_false','pointer_missing'],error:['invalid_utf8','invalid_json']};
  for(let i=0;i<p.results.length;i++){
    const r=fields(p.results[i],['id','path','op','artifact_sha256','outcome','reason']),c=plan.checks[i];
    if(['id','path','op'].some(k=>r[k]!==c[k])||r.artifact_sha256!==byPath.get(c.path).sha256||!own(reasons,r.outcome)||!reasons[r.outcome].includes(r.reason))fail('Executed check identity, bytes or outcome mismatch.');
    counts[r.outcome]++;
  }
  return {payload:p,counts,state:counts.passed===p.results.length?'checks_passed':'checks_failed',policy_name:plan.name,signer:pinned.label,key_id:pinned.key_id,receipt_hash:await hash(envelope.payload)};
}
globalThis.__execweaveControlledCore={parse,profile,verify,hash,path};
})();
""".strip()
# Use a JSON string literal rather than inserting executable text.
CONTROLLED_CORE_JS = CONTROLLED_CORE_JS.replace("__LIMITATION__", _json.dumps(LIMITATION))

CONTROLLED_VIEW_JS = r"""
(()=>{
'use strict';if(window.__execweaveControlledChecks)return;
const core=window.__execweaveControlledCore,make=(t,s)=>{const e=document.createElement(t);if(s!==undefined)e.textContent=String(s);return e};
const button=(s,f)=>{const e=make('button',s);e.type='button';e.onclick=f;return e};
const graph=()=>window.__execweaveCore?.getGraph?.()||window.__execweaveStaticGraph||{};
const scope=()=>{const g=graph();return JSON.stringify([g.session_id??null,g.run_id??null,g.source_path??null])};
let lastScope=scope(),latest=null,dialog,entry,status,body,trustInfo,trustPicker,receiptPicker,confirm,invoker,proposed=null,trusted=null,generation=0;
const records=new Map();
function target(p){
  const g=graph(),a=latest||g.run_assessment||window.__execweaveStaticRunAssessment;
  if(!p||g.live_payload_compact||!a||a.schema_version!=='0.1'||a.scope!=='published_graph_metadata'||a.inspection?.state!=='declared_graph')return false;
  const aScope=JSON.stringify([a.session_id??null,a.run_id??null,a.source_path??null]);
  if(aScope!==scope()||JSON.stringify([p.scope?.session_id??null,p.scope?.run_id??null,p.scope?.source_path??null])!==scope())return false;
  const rows=a.task_validation?.external_report_subjects;
  if(!Array.isArray(rows))return false;const found=rows.filter(s=>s.task_id===p.subject?.task_id);
  return found.length===1&&found[0].task_snapshot_sha256===p.subject.task_snapshot_sha256;
}
function clearTrust(){generation++;proposed=null;trusted=null;records.clear();if(confirm)confirm.checked=false;if(receiptPicker)receiptPicker.value='';if(body)body.replaceChildren();if(trustInfo)trustInfo.textContent='No verifier key is trusted in this tab.'}
function reconcile(){
  if(scope()!==lastScope){lastScope=scope();latest=null;clearTrust();dialog?.close();return}
  let removed=false;for(const [id,r] of records)if(!target(r.payload)){records.delete(id);removed=true}
  if(removed){generation++;if(status)status.textContent='Task evidence changed; prior accepted checks were revoked.'}
}
function close(){generation++;for(const r of records.values())delete r.comparison;dialog?.close();body?.replaceChildren();invoker?.focus()}
async function inputJSON(file,max){if(!file||file.size>max)throw new Error('File missing or above input limit.');const raw=await file.arrayBuffer();if(raw.byteLength!==file.size||raw.byteLength>max)throw new Error('File changed or exceeded its limit.');return core.parse(new TextDecoder('utf-8',{fatal:true}).decode(raw),max)}
function draw(){
  if(!dialog?.open)return;body.replaceChildren();
  for(const [id,r] of records){
    const card=make('article');card.className='execweave-controlled-result';card.dataset.state=r.state;
    card.append(make('h3',r.policy_name),make('strong',r.state==='checks_passed'?'Specified fixed checks passed':'Specified fixed checks did not all pass'),
      make('p',`Pinned signer: ${r.signer}. ${r.counts.passed} passed; ${r.counts.failed} failed; ${r.counts.error} input errors. Signature verified under the profile you selected.`),
      make('p','Task: '+r.payload.subject.task_id+' · snapshot '+r.payload.subject.task_snapshot_sha256),
      make('p','Execution: '+r.payload.execution_id+' · signer-recorded time '+r.payload.recorded_at),make('p',r.payload.limitation));
    const details=make('details');details.append(make('summary','Approved policy, signed task and executed checks'),make('pre',r.payload.policy_json),make('pre',r.payload.task_snapshot_json));
    for(const row of r.payload.results)details.append(make('p',`${row.id} · ${row.path} · ${row.op} · ${row.outcome} · ${row.reason}`));card.append(details);
    const compare=make('section');compare.className='execweave-controlled-comparison';compare.dataset.state=r.comparison?.state||'not_compared';
    compare.append(make('h4','Compare delivered files with the evaluated bytes'),make('p',r.comparison?.message||'Not compared. The signature describes the evaluated snapshot, not your current directory.'));
    const picker=make('input');picker.type='file';picker.multiple=true;picker.setAttribute('webkitdirectory','');picker.className='execweave-controlled-folder';picker.setAttribute('aria-label','Select delivered artifact folder');
    picker.onchange=()=>compareFiles(id,Array.from(picker.files||[]));compare.append(picker);card.append(compare);body.append(card);
  }
  if(!records.size)body.append(make('p','No signed check execution is accepted for this run/task and trusted policy. External reports remain separate.'));
}
async function compareFiles(id,files){
  reconcile();const r=records.get(id),pin=trusted,token=++generation,start=scope();if(!r||!pin)return;
  const valid=()=>token===generation&&start===scope()&&dialog.open&&records.get(id)===r&&trusted===pin&&target(r.payload);
  r.comparison={state:'checking',message:'Comparing only the listed evaluated bytes…'};draw();
  try{
    if(!files.length||files.length>10000)throw new Error('Select one folder with at most 10,000 files.');
    let root=null;const mapped=new Map(),names=new Set();
    for(const f of files){
      const parts=f.webkitRelativePath?.split('/');if(!parts||parts.length<2)throw new Error('Directory identity unavailable.');
      const top=parts.shift();if(!top||(root!==null&&top!==root))throw new Error('Select exactly one directory.');root=top;
      const path=core.path(parts.join('/'));if(names.has(path.toLowerCase()))throw new Error('Duplicate selected relative path.');names.add(path.toLowerCase());mapped.set(path,f);
    }
    let matched=0;const lines=[];
    for(const a of r.payload.artifacts.entries){
      const f=mapped.get(a.path);let state='missing';if(f){
        if(f.size!==a.size_bytes)state='size_mismatch';else{const raw=await f.arrayBuffer();if(!valid())return;
          if(raw.byteLength!==a.size_bytes)throw new Error('File changed while reading.');state=await core.hash(raw)===a.sha256?'match':'hash_mismatch';if(!valid())return}
      }
      if(state==='match')matched++;lines.push(a.path+': '+state);
    }
    if(!valid())return;const count=r.payload.artifacts.entries.length;
    r.comparison={state:matched===count?'match':'mismatch',message:`${matched}/${count} evaluated files match this selection. ${lines.join('; ')}. Unlisted files are not inspected. Past byte comparison only; no whole-task certification.`};draw();
  }catch(e){if(valid()){r.comparison={state:'unavailable',message:'Comparison not completed: '+e.message};draw()}}
}
function ensure(){
  if(dialog)return;dialog=make('dialog');dialog.id='execweave-controlled-dialog';dialog.setAttribute('aria-labelledby','execweave-controlled-title');
  const head=make('header'),title=make('h2','Signed fixed-check executions');title.id='execweave-controlled-title';head.append(title,button('Close signed checks',close));
  const intro=make('p','Run python -m execweave.controlled_checks --help on a trusted verifier host. These are built-in byte predicates, not imported JUnit or arbitrary program tests. Never obtain trust solely from the result you are checking.');
  trustPicker=make('input');trustPicker.type='file';trustPicker.accept='.json';trustPicker.id='execweave-controlled-profile';trustPicker.setAttribute('aria-label','Select independently trusted verifier profile');
  trustInfo=make('p','No verifier key is trusted in this tab.');trustInfo.id='execweave-controlled-profile-info';
  confirm=make('input');confirm.type='checkbox';confirm.id='execweave-controlled-trust-confirm';
  const label=make('label');label.append(confirm,document.createTextNode(' I independently trust this verifier key and approved policy fingerprint.'));
  receiptPicker=make('input');receiptPicker.type='file';receiptPicker.accept='.json';receiptPicker.id='execweave-controlled-receipt';receiptPicker.setAttribute('aria-label','Select signed check receipt');
  status=make('p');status.id='execweave-controlled-status';status.setAttribute('role','status');body=make('div');body.id='execweave-controlled-results';
  trustPicker.onchange=async()=>{
    reconcile();clearTrust();draw();const token=generation,start=scope();status.textContent='Checking the separately selected verifier profile…';
    try{const p=await core.profile(await inputJSON(trustPicker.files?.[0],128*1024));
      if(token!==generation||start!==scope()||!dialog.open)return;proposed=p;
      trustInfo.textContent=`${p.label} · public key SHA-256 ${p.key_id} · approved policy SHA-256 ${p.policy_sha256}`;
      status.textContent='Profile loaded but not trusted. Compare its fingerprints through a separate trusted channel, then confirm.';
    }catch(e){if(token===generation&&start===scope()&&dialog.open)status.textContent='Profile not accepted: '+e.message}
  };
  confirm.onchange=()=>{generation++;records.clear();trusted=confirm.checked&&proposed?proposed:null;if(!trusted)confirm.checked=false;status.textContent=trusted?'Verifier profile explicitly trusted in this tab. Select a signed result.':'No verifier profile approved.';draw()};
  receiptPicker.onchange=async()=>{
    reconcile();const token=++generation,start=scope(),pin=trusted;status.textContent='Verifying signature, approved policy, exact task and executed checks…';
    try{
      if(!pin)throw new Error('An independently selected and confirmed verifier profile is required.');
      const value=await inputJSON(receiptPicker.files?.[0],2*1024*1024),r=await core.verify(value,pin);
      if(token!==generation||start!==scope()||trusted!==pin||!dialog.open)return;
      if(!target(r.payload))throw new Error('Receipt is not bound to the current exact task snapshot.');
      if(!records.has(r.receipt_hash)&&records.size>=5)throw new Error('Five-result limit reached; clear results first.');
      records.set(r.receipt_hash,r);status.textContent='Signed execution accepted under the pinned key and policy. Only the specified checks are authenticated; the whole task is not certified.';draw();mount();
    }catch(e){if(token===generation&&start===scope()&&dialog.open)status.textContent='Signed execution not accepted: '+e.message}
  };
  dialog.append(head,intro,trustPicker,trustInfo,label,make('p','Choose the result separately. Keys embedded in a result cannot establish trust.'),receiptPicker,
    button('Forget verifier and signed results',()=>{clearTrust();status.textContent='Verifier trust and results cleared.';draw();mount()}),status,body);
  dialog.addEventListener('keydown',e=>{if(e.key==='Escape')e.stopPropagation()});dialog.addEventListener('cancel',e=>{e.preventDefault();close()});document.body.append(dialog);
}
function open(){reconcile();ensure();invoker=document.activeElement;status.textContent=trusted?'Select a signed execution for the trusted policy.':'Select and independently confirm a verifier profile first.';dialog.showModal();draw()}
function mount(){reconcile();const host=document.querySelector('#execweave-run-assessment [data-axis="task"]');if(!host)return;
  if(!entry?.isConnected||entry.parentElement!==host){entry?.remove();entry=make('div');entry.id='execweave-controlled-entry';entry.append(button('Review signed fixed checks',open));host.append(entry)}
}
const prior=window.__execweaveDashboard||{};
function changed(packet){reconcile();const a=packet?.run_assessment||packet?.graph?.run_assessment;if(a)latest=a;reconcile();mount();draw()}
window.__execweaveDashboard={...prior,onPayload(...a){prior.onPayload?.(...a);changed(a[0])},onFinished(...a){prior.onFinished?.(...a);changed()}};
window.addEventListener('pagehide',()=>{clearTrust();latest=null;dialog?.close()});
window.__execweaveControlledChecks={open,close};mount();
})();
""".strip()

CONTROLLED_CSS = """
#execweave-controlled-entry button{font:inherit;padding:6px;cursor:pointer}
#execweave-controlled-dialog{width:min(980px,94vw);max-height:88vh;box-sizing:border-box;background:var(--panel,#fff);color:var(--text,#111);border:1px solid var(--border,#888);border-radius:10px;padding:16px}
#execweave-controlled-dialog::backdrop{background:rgba(0,0,0,.45)}
#execweave-controlled-dialog header{display:flex;align-items:center;gap:10px}#execweave-controlled-title{flex:1;font-size:20px}
#execweave-controlled-dialog p,#execweave-controlled-dialog label{font-size:14px;line-height:1.5;overflow-wrap:anywhere}
#execweave-controlled-dialog input,#execweave-controlled-dialog button{font:inherit;padding:6px}
#execweave-controlled-dialog pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}
#execweave-controlled-results{max-height:44vh;overflow:auto}.execweave-controlled-result{border:1px solid var(--border,#888);border-radius:8px;padding:12px;margin-top:12px}
""".strip()


def inject_controlled_checks(html: str) -> str:
    if 'id="execweave-controlled-script"' in html:
        return html
    if "</body>" not in html:
        raise RuntimeError("signed checks require the shared Dashboard body")
    return html.replace(
        "</body>",
        "<style>"
        + CONTROLLED_CSS
        + '</style><script id="execweave-controlled-script">'
        + CONTROLLED_CORE_JS
        + "\n"
        + CONTROLLED_VIEW_JS
        + "</script></body>",
        1,
    )
