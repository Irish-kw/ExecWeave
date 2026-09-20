"""Explicit local external-test-report review; never replaces task truth."""
from __future__ import annotations

TASK_REPORT_JS = r"""
(()=>{
'use strict';if(window.__execweaveTaskReports)return;
const LIMIT=2*1024*1024,MAX_FILE=8*1024*1024;
const make=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);return n};
const button=(text,fn)=>{const n=make('button',text);n.type='button';n.onclick=fn;return n};
const list=v=>Array.isArray(v)?v:[],obj=v=>v&&typeof v==='object'&&!Array.isArray(v);
const text=(v,max)=>typeof v==='string'&&v.trim().length>0&&Array.from(v).length<=max;
const graph=()=>window.__execweaveCore?.getGraph?.()||window.__execweaveStaticGraph||{};
const scope=()=>{const g=graph();return [g.session_id??null,g.run_id??null,g.source_path??null]};
const key=()=>JSON.stringify(scope());
let lastKey=key(),assessment=null,dialog=null,status,body,picker,invoker=null,generation=0;
const reports=new Map();let section=null;
function fail(message){throw new Error(message)}
function inspectXML(xml){
  if(typeof xml!=='string'||new TextEncoder().encode(xml).length>LIMIT)fail('Report exceeds 2 MiB.');
  if(/<!\s*(?:DOCTYPE|ENTITY)\b/i.test(xml)||xml.includes('\0'))fail('DTD/entities are not supported.');
  const enc=/<\?xml[^>]*\bencoding\s*=\s*['"]([^'"]+)/i.exec(xml);
  if(enc&&!['utf-8','utf8'].includes(enc[1].toLowerCase()))fail('Only UTF-8 reports are supported.');
  const documentXML=new DOMParser().parseFromString(xml,'application/xml');
  if(documentXML.querySelector('parsererror'))fail('Malformed XML report.');
  const root=documentXML.documentElement;if(!['testsuite','testsuites'].includes(root.tagName))fail('Expected testsuite/testsuites.');
  const empty=()=>({tests:0,passed:0,failures:0,errors:0,skipped:0});
  const seen=new Set(),cases=[];let elements=0;
  function visit(e,depth,parent){
    if(++elements>50000||depth>32)fail('XML structure exceeds inspection budget.');
    const tag=e.tagName,c=empty(),children=[...e.children];
    if(e.namespaceURI||tag.includes(':'))fail('Namespaced XML is not supported.');
    if(tag==='testcase'){
      if(parent!=='testsuite'||!text(e.getAttribute('name'),4096))fail('Invalid testcase identity.');
      const name=e.getAttribute('name'),cls=e.getAttribute('classname')||'',id=JSON.stringify([cls,name]);
      if(Array.from(cls).length>4096||seen.has(id))fail('Duplicate or oversized testcase identity.');
      seen.add(id);if(seen.size>10000)fail('Too many testcases.');
      const outcomes=children.filter(x=>['failure','error','skipped'].includes(x.tagName));
      if(outcomes.length>1)fail('Multiple testcase outcomes are ambiguous.');
      for(const child of children){if(!['failure','error','skipped','system-out','system-err','properties'].includes(child.tagName))fail('Unsupported testcase child.');visit(child,depth+1,tag)}
      if(![null,'run'].includes(e.getAttribute('status'))||e.hasAttribute('result'))fail('Unsupported testcase status/result attribute.');
      const state={failure:'failures',error:'errors',skipped:'skipped'}[outcomes[0]?.tagName]||'passed';c.tests=1;c[state]=1;cases.push({name,classname:cls,outcome:state});
    }else if(['testsuite','testsuites'].includes(tag)){
      if(![null,'testsuite','testsuites'].includes(parent)||(tag==='testsuites'&&parent))fail('Unsupported suite nesting.');
      const allowed=['testsuite','properties','system-out','system-err'];if(tag==='testsuite')allowed.push('testcase');
      for(const child of children){if(!allowed.includes(child.tagName))fail('Unsupported suite child.');const sub=visit(child,depth+1,tag);for(const k of Object.keys(c))c[k]+=sub[k]}
      for(const k of ['tests','failures','errors','skipped'])if(e.hasAttribute(k)){const v=e.getAttribute(k);if(!/^[0-9]{1,9}$/.test(v)||Number(v)!==c[k])fail('Suite counter disagrees with case records.')}
    }else if(tag==='properties'){
      if(!['testsuite','testsuites','testcase'].includes(parent))fail('Unsupported properties location.');
      for(const child of children){if(child.tagName!=='property')fail('Unsupported property child.');visit(child,depth+1,tag)}
    }else if(!['failure','error','skipped','system-out','system-err','property'].includes(tag)||children.length)fail('Unsupported XML element.');
    return c;
  }
  const counts=visit(root,0,null),state=counts.failures||counts.errors?'checks_failed':!counts.passed?'no_executed_checks':counts.skipped?'partial':'checks_passed';
  return {state,counts,cases,task_success_implied:false,authority_authenticated:false};
}
function currentAssessment(){
  const g=graph();const a=assessment||g.run_assessment||window.__execweaveStaticRunAssessment;
  return a?.schema_version==='0.1'&&a.scope==='published_graph_metadata'&&a.session_id===g.session_id&&
    (a.run_id??null)===(g.run_id??null)&&(a.source_path??null)===(g.source_path??null)?a:null;
}
function targetMatches(r){
  const a=currentAssessment(),g=graph();
  if(!text(g.session_id,4096)||g.live_payload_compact||a?.inspection?.state!=='declared_graph')return false;
  if(JSON.stringify([r?.scope?.session_id,r?.scope?.run_id??null,r?.scope?.source_path??null])!==key())return false;
  const subjects=list(a?.task_validation?.external_report_subjects),match=subjects.filter(s=>s?.task_id===r?.subject?.task_id);
  return match.length===1&&match[0].task_snapshot_sha256===r?.subject?.task_snapshot_sha256;
}
// Artifact names are lookup keys in an explicitly selected FileList, not paths
// the browser or server may fetch. The report never chooses a local directory.
const ARTIFACT_FORMAT='execweave.selected-artifact-versions.v1',ARTIFACT_FILE=8*1024*1024,ARTIFACT_TOTAL=64*1024*1024;
function artifactPath(v){
  if(!text(v,512)||v.normalize('NFC')!==v||/[\\:*?"<>|\x00-\x1f\x7f]/.test(v)||
     Array.from(v).some(c=>{const n=c.codePointAt(0);return n>=0xd800&&n<=0xdfff})||
     v.split('/').some(p=>!p||p==='.'||p==='..'||/[ .]$/.test(p)||/^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)/i.test(p)))fail('Invalid artifact relative name.');
  return v;
}
async function artifactManifest(value){
  if(!obj(value)||value.format!==ARTIFACT_FORMAT||!Array.isArray(value.entries)||!value.entries.length||value.entries.length>100)fail('Unsupported artifact inventory.');
  const seen=new Set(),entries=[];let total=0;
  for(const item of value.entries){
    if(!obj(item))fail('Invalid artifact entry.');const path=artifactPath(item.path),folded=path.toLowerCase();
    if(seen.has(folded))fail('Duplicate or case-colliding artifact name.');seen.add(folded);
    if(!Number.isSafeInteger(item.size_bytes)||item.size_bytes<0||item.size_bytes>ARTIFACT_FILE||(typeof item.sha256!=='string'||item.sha256.length!==64||!/^[a-f0-9]{64}$/.test(item.sha256)))fail('Invalid artifact size or digest.');
    total+=item.size_bytes;if(total>ARTIFACT_TOTAL)fail('Artifact inventory exceeds 64 MiB.');
    entries.push({path,size_bytes:item.size_bytes,sha256:item.sha256});
  }
  const encoded=new TextEncoder().encode(JSON.stringify(entries.map(e=>[e.path,e.size_bytes,e.sha256])));
  const digest=await artifactDigest(encoded);
  if(digest!==value.manifest_sha256)fail('Artifact manifest hash mismatch.');
  return {format:ARTIFACT_FORMAT,entries,manifest_sha256:digest};
}
async function artifactDigest(bytes){
  if(!globalThis.crypto?.subtle)fail('Native SHA-256 unavailable; artifact bytes not checked.');
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),v=>v.toString(16).padStart(2,'0')).join('');
}
async function compareArtifacts(r,id,files){
  const token=++generation,started=key();
  const valid=()=>token===generation&&started===key()&&dialog?.open&&reports.get(id)===r&&targetMatches(r);
  r.artifact_check={state:'checking',message:'Comparing only the explicitly associated files…',rows:[]};draw();
  try{
    if(!files.length||files.length>10000)fail('Select a nonempty folder with at most 10,000 files.');
    const byPath=new Map(),folded=new Set();let root=null;
    for(const file of files){
      if(typeof file.webkitRelativePath!=='string'||!file.webkitRelativePath.includes('/'))fail('Directory-relative file identity is unavailable.');
      const parts=file.webkitRelativePath.split('/'),folder=parts.shift();
      if(!folder||(root!==null&&root!==folder))fail('Select exactly one folder.');root=folder;
      const path=artifactPath(parts.join('/')),identity=path.toLowerCase();
      if(folded.has(identity))fail('Duplicate or case-colliding selected path.');folded.add(identity);byPath.set(path,file);
    }
    const rows=[];let matched=0,bytesMatched=0;
    for(const item of r.artifacts.entries){
      if(!valid())return;
      const file=byPath.get(item.path);let state;
      if(!file)state='missing';
      else if(file.size!==item.size_bytes)state='size_mismatch';
      else{
        const bytes=await file.arrayBuffer();if(!valid())return;
        if(bytes.byteLength!==item.size_bytes||bytes.byteLength>ARTIFACT_FILE)fail('Selected artifact changed or exceeded its limit.');
        const hash=await artifactDigest(bytes);if(!valid())return;
        state=hash===item.sha256?'match':'hash_mismatch';
      }
      if(state==='match'){matched++;bytesMatched+=item.size_bytes}
      rows.push({path:item.path,state});
    }
    if(!valid())return;
    r.artifact_check={state:matched===rows.length?'match':'mismatch',rows,
      message:`Last selected-file comparison: ${matched}/${rows.length} match; ${bytesMatched} matching bytes. ${files.length-rows.filter(x=>x.state!=='missing').length} other selected files were not read. This does not prove these files were tested.`};
    draw();
  }catch(e){if(valid()){r.artifact_check={state:'unavailable',message:'Artifact comparison not completed: '+e.message,rows:[]};draw()}}
}
function appendArtifacts(card,r,id){
  const box=make('section');box.className='execweave-task-artifacts';
  box.append(make('h4','Associated artifact versions'));
  if(!r.artifacts){box.dataset.state='not_supplied';box.append(make('p','No artifact versions supplied. A task snapshot does not identify the files tested.'));card.append(box);return}
  const result=r.artifact_check||{state:'not_checked',rows:[],message:'Artifact bytes have not been compared in this tab.'};box.dataset.state=result.state;
  box.append(make('p','Operator-associated file versions, not proof of test execution on these files.'),make('p','Manifest SHA-256: '+r.artifacts.manifest_sha256));
  const input=make('input');input.type='file';input.multiple=true;input.setAttribute('webkitdirectory','');input.className='execweave-task-artifact-folder';input.setAttribute('aria-label','Select folder to compare associated artifacts');
  input.onchange=()=>{const files=Array.from(input.files||[]);void compareArtifacts(r,id,files)};
  const message=make('p',result.message);message.className='artifact-comparison-status';message.setAttribute('role','status');box.append(input,message);
  const details=make('details');details.append(make('summary',`${r.artifacts.entries.length} associated file version(s)`));
  for(const entry of r.artifacts.entries)details.append(make('p',`${entry.path} · ${entry.size_bytes} bytes · ${entry.sha256}`));
  box.append(details);for(const row of result.rows)box.append(make('p',row.path+' · '+row.state));
  box.append(make('p','Only the listed files are compared. Extra files, permissions, dependencies and the entire delivered directory are not certified. Results are past comparisons and do not continuously monitor changes.'));
  card.append(box);
}

async function validate(r){
  if(!obj(r)||!['execweave.external-task-report.v1','execweave.external-task-report.v2'].includes(r.format)||r.authority!=='operator_supplied_not_authenticated'||
     !text(r.validator,256)||!text(r.criterion,2048)||!text(r.subject?.task_id,4096)||
     !/^[a-f0-9]{64}$/.test(r.subject?.task_snapshot_sha256||'')||!targetMatches(r))fail('Unsupported report or task/run snapshot mismatch.');
  const summary=inspectXML(r.report?.xml);
  if(r.report?.media_type!=='application/xml; charset=utf-8'||!/^[a-f0-9]{64}$/.test(r.report.sha256||''))fail('Invalid report fingerprint.');
  if(!globalThis.crypto?.subtle)fail('Native SHA-256 unavailable; no report accepted.');
  const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(r.report.xml))),b=>b.toString(16).padStart(2,'0')).join('');
  if(digest!==r.report.sha256)fail('Report hash mismatch.');
  if(r.format==='execweave.external-task-report.v1'&&r.artifacts!==undefined)fail('Artifact binding requires a v2 receipt.');
  const artifacts=r.format==='execweave.external-task-report.v2'?await artifactManifest(r.artifacts):null;
  // Claimed summaries are not evidence. Recount the original XML in this browser.
  return {scope:{...r.scope},subject:{...r.subject},validator:r.validator,criterion:r.criterion,report_hash:digest,summary,artifacts};
}
function clear(){generation++;reports.clear();dialog?.close();body?.replaceChildren();if(picker)picker.value=''}
function reconcile(){
  if(lastKey!==key()){clear();assessment=null;lastKey=key()}
  for(const [id,r] of reports)if(!targetMatches(r))reports.delete(id);
}
function close(){generation++;for(const r of reports.values())if(r.artifact_check?.state==='checking')r.artifact_check={state:'cancelled',message:'Comparison cancelled; no complete version-match result.',rows:[]};dialog?.close();body?.replaceChildren();if(picker)picker.value='';(invoker?.isConnected?invoker:section?.querySelector('button'))?.focus()}
function draw(){
  if(!dialog?.open)return;reconcile();body.replaceChildren();
  for(const [id,r] of reports){
    const card=make('article');card.className='execweave-task-report';card.dataset.state=r.summary.state;
    const labels={checks_passed:'Report: checks passed',checks_failed:'Report: checks failed',partial:'Report: incomplete coverage',no_executed_checks:'Report: no executed passing checks'};
    card.append(make('h3',labels[r.summary.state]),make('p','Task: '+r.subject.task_id),make('p','Operator-named verifier: '+r.validator),make('p','Operator-stated criterion: '+r.criterion));
    const c=r.summary.counts;card.append(make('p',`${c.tests} case records: ${c.passed} passed, ${c.failures} failures, ${c.errors} errors, ${c.skipped} skipped.`),make('p','Report SHA-256: '+r.report_hash));
    card.append(make('p','Report bytes verified and cases recounted. The report author, tested artifact version, execution and adequacy of these checks are not authenticated. This is not proof that the whole task succeeded.'));
    appendArtifacts(card,r,id);
    const details=make('details');details.append(make('summary','Case details (first 50)'));
    for(const item of r.summary.cases.slice(0,50))details.append(make('p',[item.outcome,item.classname,item.name].join(' · ')));
    if(r.summary.cases.length>50)details.append(make('p','Detail preview limited to 50; all supported cases were counted.'));
    card.append(details);body.append(card);
  }
  if(!reports.size)body.append(make('p','No external report accepted for this exact run/task snapshot. Agent completion text and exit code 0 are not test evidence.'));
}
function ensure(){
  if(dialog)return;dialog=make('dialog');dialog.id='execweave-task-reports-dialog';dialog.setAttribute('aria-labelledby','execweave-task-reports-title');
  const header=make('header'),title=make('h2','External task check reports');title.id='execweave-task-reports-title';header.append(title,button('Close task reports',close));
  const intro=make('p','Explicit operator import only. Create a receipt with python -m execweave.task_validation --help. Selecting it does not run commands, upload files, modify the original archive or authenticate an independent verifier. Report text stays in this tab and may contain sensitive test names.');
  picker=make('input');picker.type='file';picker.accept='.json';picker.id='execweave-task-report-file';picker.setAttribute('aria-label','Select external task report receipt');
  status=make('p');status.id='execweave-task-report-status';status.setAttribute('role','status');
  body=make('div');body.id='execweave-task-report-results';
  picker.onchange=async()=>{
    reconcile();const file=picker.files?.[0],token=++generation,started=key();if(!file)return;
    status.textContent='Checking report bytes, cases and task binding…';
    try{
      if(file.size>MAX_FILE)fail('Receipt exceeds 8 MiB.');
      if(!window.__execweaveArchiveVerifier?.strictJSON)fail('Strict JSON reader unavailable.');
      const bytes=await file.arrayBuffer();if(bytes.byteLength>MAX_FILE)fail('Receipt exceeds 8 MiB.');
      const value=window.__execweaveArchiveVerifier.strictJSON(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
      const accepted=await validate(value);
      if(token!==generation||started!==key()||!dialog.open)return;
      if(!targetMatches(accepted))fail('Task changed during report verification.');
      const id=JSON.stringify([accepted.subject,accepted.report_hash,accepted.validator,accepted.criterion,accepted.artifacts?.manifest_sha256??null]);
      if(!reports.has(id)&&reports.size>=20)fail('20-report limit reached; clear imported reports first.');
      reports.set(id,accepted);status.textContent='Report accepted as operator-supplied evidence; task success is not inferred.';draw();mount();
    }catch(e){if(token===generation&&started===key()&&dialog.open)status.textContent='Report not accepted: '+e.message}
  };
  dialog.append(header,intro,picker,button('Clear imported reports',()=>{clear();mount();invoker?.focus()}),status,body);
  dialog.addEventListener('keydown',e=>{if(e.key==='Escape')e.stopPropagation()});dialog.addEventListener('cancel',e=>{e.preventDefault();close()});document.body.append(dialog);
}
function open(){reconcile();ensure();invoker=document.activeElement;status.textContent='Reports are separate from native task completion claims.';dialog.showModal();draw()}
function mount(){
  reconcile();const host=document.querySelector('#execweave-run-assessment [data-axis="task"]');if(!host)return;
  if(!section?.isConnected||section.parentElement!==host){section?.remove();section=make('div');section.id='execweave-task-report-entry';section.append(button('Review external task reports',open),make('p'));host.append(section)}
  section.querySelector('p').textContent=reports.size?`${reports.size} operator-supplied report(s) loaded; no automatic task-success verdict.`:'No authenticated independent task result is available.';
}
const prior=window.__execweaveDashboard||{};
function changed(packet){reconcile();const a=packet?.run_assessment||packet?.graph?.run_assessment;if(a)assessment=a;reconcile();mount();if(dialog?.open)draw()}
window.__execweaveDashboard={...prior,onPayload(...args){prior.onPayload?.(...args);changed(args[0])},onFinished(...args){prior.onFinished?.(...args);changed()}};
window.addEventListener('pagehide',()=>{clear();assessment=null});
window.__execweaveTaskReports={inspectXML,open,close};mount();
})();
""".strip()

TASK_REPORT_CSS = """
#execweave-task-report-entry button{font:inherit;padding:6px;cursor:pointer}
#execweave-task-reports-dialog{width:min(920px,92vw);max-height:88vh;box-sizing:border-box;background:var(--panel,#fff);color:var(--text,#111);border:1px solid var(--border,#888);border-radius:10px;padding:16px}
#execweave-task-reports-dialog::backdrop{background:rgba(0,0,0,.45)}
#execweave-task-reports-dialog header{display:flex;align-items:center;gap:10px}#execweave-task-reports-title{flex:1;font-size:20px}
#execweave-task-reports-dialog button,#execweave-task-reports-dialog input{font:inherit;padding:7px}
#execweave-task-reports-dialog p{font-size:14px;line-height:1.5;overflow-wrap:anywhere}
#execweave-task-report-results{overflow:auto;max-height:52vh}.execweave-task-report{border:1px solid var(--border,#888);padding:12px;margin-top:10px;border-radius:8px}
""".strip()


def inject_task_reports(html: str) -> str:
    if 'id="execweave-task-reports-script"' in html:
        return html
    if "</body>" not in html:
        raise RuntimeError("task reports require the shared Dashboard body")
    return html.replace("</body>", "<style>" + TASK_REPORT_CSS
                        + '</style><script id="execweave-task-reports-script">' + TASK_REPORT_JS
                        + "</script></body>", 1)
