"""Archive receipts, manual offline verification, and final-sync status controls."""
from __future__ import annotations

from .viewer_archive_verifier import ARCHIVE_VERIFIER_JS

DELIVERY_STATUS_JS = r"""
(()=>{
'use strict';
if(window.__execweaveDeliveryStatus)return;
const make=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);return n};
const button=(text,fn)=>{const n=make('button',text);n.type='button';n.onclick=fn;return n};
const graphNow=()=>window.__execweaveCore?.getGraph?.()||window.__execweaveStaticGraph||{};
const scope=()=>{const g=graphNow();return {session_id:g.session_id||null,source_path:g.source_path||null}};
const key=()=>JSON.stringify(scope());
const count=v=>Number.isSafeInteger(v)&&v>=0?String(v):'unknown';
let activeKey=null,receipt=null,offline=null,controller=null,generation=0,host=null,picker=null,lastRender='',disclosure=null,heading=null,expanded=false;
function reconcile(){
  const next=key();if(next===activeKey)return;
  activeKey=next;generation++;controller?.abort();controller=null;receipt=null;offline=null;expanded=false;
  if(disclosure)disclosure.open=false;
  if(picker)picker.value='';
}
function matches(value){const s=scope();return typeof s.session_id==='string'&&value?.session_id===s.session_id&&(value.source_path||null)===s.source_path}
function card(axis,title,state,label,text){
  const n=make('div');n.className='run-assessment-card';n.dataset.axis=axis;n.dataset.state=state;
  n.append(make('h3',title),make('strong',label),make('p',text));host.append(n);return n;
}
const ERRORS={
  missing_file:'A required export or declared content file is missing.',
  hash_mismatch:'A selected file does not match its recorded SHA-256.',
  size_mismatch:'A selected file has a different size from its recorded reference.',
  run_mismatch:'The selected folder belongs to a different run or source.',
  scope_unavailable:'This page has no usable run identity. Verification cannot be bound to it.',
  verification_limit:'Verification reached its file, byte, JSON, or reference limit. No complete verdict is issued.',
  invalid_reference:'An index has an invalid or unsafe content reference.',
  conflicting_reference:'Indexes disagree about the same content file.',
  duplicate_json_key:'A JSON document contains duplicate decoded keys.',
  invalid_json:'An export index or receipt is not strict UTF-8 JSON.',
  invalid_index:'An export index has an unsupported or malformed structure.',
  invalid_receipt:'The receipt lacks valid primary-file fingerprints.',
  unsupported_receipt:'This archive has no supported finalization receipt.',
  invalid_folder:'Select a single exported run folder, not individual files.',
  duplicate_file:'The folder selection contains duplicate archive paths.',
  crypto_unavailable:'Native SHA-256 is unavailable in this browser context. Nothing is marked verified.',
  changed_during_read:'A selected file changed while being read.',
  invalid_lineage:'The redacted derivative lineage manifest is malformed or inconsistent.',
  lineage_mismatch:'The redacted derivative files do not match their lineage manifest.',
  cancelled:'Verification was cancelled. No complete verdict is issued.'
};
function redraw(){
  reconcile();if(!host?.isConnected)return;
  const status=window.__execweaveDashboard?.agentPanel?.getSynchronizationStatus?.();
  const valid=status&&matches(status);
  const state=valid?status.state:'unknown';
  const archiveState=offline?.state||receipt?.state||'unavailable';
  const brief={embedded:'embedded history',live:'history live',syncing:'history syncing',synced:'history response loaded',failed:'history sync failed',unknown:'history status unknown'};
  const archiveBrief={verified_now:'selected files verified',checking:'checking files',not_verified:'files not verified',complete:'export check passed; not rechecked',incomplete:'export check failed',failed:'export failed',recording:'recording',exporting:'export pending',unavailable:'archive not verified'};
  if(heading)heading.textContent='Delivery checks · '+(brief[state]||brief.unknown)+' · '+(archiveBrief[archiveState]||archiveBrief.unavailable);
  if(disclosure)disclosure.dataset.state=state==='failed'||['incomplete','failed','not_verified'].includes(archiveState)?'incomplete':'not_verified';
  const signature=JSON.stringify([activeKey,status,receipt,offline,!!controller]);
  if(lastRender===signature&&host.childElementCount)return;lastRender=signature;host.replaceChildren();
  const names={embedded:'Embedded history loaded',live:'Final synchronization not requested',syncing:'Final synchronization in progress',synced:'Final history response loaded',failed:'Final synchronization failed',unknown:'Synchronization status unavailable'};
  const sync=card('synchronization','Conversation synchronization',Object.hasOwn(names,state)?state:'unknown',names[state]||names.unknown,
    state==='embedded'?'Static content is loaded from this page. No live-server synchronization is implied.':
    state==='synced'?(status.response_session_checked?'The response session matched this run. ':'The legacy response omitted its session identity. ')+
      'This confirms history retrieval, not source completeness or task success.':
    state==='failed'?'The last history response was not accepted. Existing history is retained; stopping polling is not synchronization.':
    'This reports the existing history synchronizer; it does not start a second polling loop.');
  if(state==='failed')sync.append(button('Retry final synchronization',()=>window.__execweaveDashboard?.agentPanel?.finishConversationPolling?.()));
  let archive;
  if(offline?.state==='verified_now'){
    archive=card('archive','Selected archive verification','verified_now','Selected archive files verified',
      `${offline.primary_file_count} primary files and ${offline.verified_file_count} unique content files (${offline.reference_count} references) verified using native SHA-256. `+
      `Recorded export state: ${offline.recorded_state}. Checked: ${offline.checked_at}.`);
    if(offline.derivation?.state==='verified_now')archive.append(make('p',
      `Redacted derivative lineage verified for ${offline.derivation.mapping_count} source→derived mapping(s). `+
      `Policy SHA-256: ${offline.derivation.policy_sha256}. The source archive itself was declared by fingerprint and was not rechecked from this selected derivative folder.`));
  }else if(offline){
    archive=card('archive','Selected archive verification',offline.state,
      offline.state==='checking'?'Checking selected archive':'Archive not verified',
      offline.state==='checking'?`${count(offline.checked_files)} file(s) checked. No complete verdict yet.`:
      (ERRORS[offline.code]||'Verification failed; no complete verdict is issued.')+(offline.location?' Location: '+offline.location:''));
  }else{
    const r=receipt||{},state=r.state||'unavailable';
    const labels={complete:'Recorded export check passed',incomplete:'Recorded export check failed',failed:'Export failed',recording:'Recording; archive not finalized',exporting:'Export verification pending',unavailable:'Archive not verified in this page'};
    archive=card('archive','Archive verification',state,labels[state]||labels.unavailable,
      state==='complete'?`${count(r.verified_file_count)} unique content files passed the recorded export check. Files have not been rechecked since then.`:
      state==='incomplete'||state==='failed'?`Recorded content errors: ${count(r.error_count)}. Readable top-level files do not establish a complete archive.`:
      'Select the exported run folder to check its primary files and declared content. No files are read automatically.');
    if(r.reason==='inconsistent_finalization_report')archive.append(make('p','The finalization receipt is internally inconsistent; its success claim is not accepted.'));
    for(const code of (Array.isArray(r.diagnostics)?r.diagnostics:[]).slice(0,20))archive.append(make('p',code));
  }
  archive.append(make('p','Scope: selected/declared graph and conversation content only. This is not proof of all raw events, source recall, task quality, or tamper-proof authenticity. A folder check does not attest that the current tab matches its viewer file.'));
  archive.append(button('Verify exported run folder',()=>{ensurePicker();picker.click()}));
  if(controller)archive.append(button('Cancel archive verification',()=>{generation++;controller.abort();controller=null;offline={state:'not_verified',code:'cancelled'};redraw()}));
}
function ensurePicker(){
  if(picker)return;
  picker=make('input');picker.type='file';picker.multiple=true;picker.setAttribute('webkitdirectory','');
  picker.id='execweave-archive-folder';picker.setAttribute('aria-label','Exported run folder for verification');picker.hidden=true;
  picker.onchange=()=>{const selected=Array.from(picker.files||[]);picker.value='';if(selected.length)verifySelected(selected)};
  document.body.append(picker);
}
async function verifySelected(selected){
  reconcile();const run=key(),token=++generation,expected=scope();controller?.abort();
  const active=new AbortController();controller=active;offline={state:'checking',checked_files:0};redraw();
  const timer=setTimeout(()=>active.abort(),120000);
  try{
    const verifier=window.__execweaveArchiveVerifier,files=verifier.filesFromSelection(selected);
    const result=await verifier.verifyArchive(files,expected,{signal:active.signal,onProgress:p=>{
      if(token===generation&&key()===run){offline={state:'checking',...p};redraw()}
    }});
    if(token===generation&&key()===run)offline=result;
  }catch(error){
    if(token===generation&&key()===run)offline={state:'not_verified',code:error.code||'read_failed',location:error.location||''};
  }finally{
    clearTimeout(timer);if(controller===active)controller=null;
    if(token===generation&&key()===run)redraw();
  }
}
function accept(packet){
  reconcile();const candidate=packet?.finalization_assessment||packet?.graph?.finalization_assessment;
  if(candidate){
    const valid=candidate.schema_version==='0.1'&&candidate.scope==='recorded_finalization_result'&&matches(candidate)&&candidate.rechecked_now===false;
    const completeOK=candidate.state!=='complete'||(Number.isSafeInteger(candidate.verified_file_count)&&candidate.verified_file_count>=0&&
      candidate.verified_file_count===candidate.unique_file_count&&candidate.error_count===0&&candidate.reason==='recorded_export_verification');
    receipt=valid&&completeOK?candidate:{state:'unavailable',reason:'inconsistent_finalization_report'};
  }
  redraw();
}
function mount(panel){
  // Keep delivery disclosure separate from the assessment's existing details contract.
  let next=panel.parentElement?.querySelector(':scope > #execweave-delivery-status');
  if(!next){
    next=make('div');next.id='execweave-delivery-status';
    disclosure=make('details');disclosure.open=expanded;heading=make('summary');
    heading.id='execweave-delivery-summary';disclosure.append(heading);
    const body=make('div');body.className='execweave-delivery-body';disclosure.append(body);
    const current=disclosure;current.ontoggle=()=>{if(disclosure===current)expanded=current.open};
    next.append(disclosure);panel.after(next);
  }else{disclosure=next.querySelector('details');heading=disclosure.querySelector('summary')}
  const body=next.querySelector('.execweave-delivery-body');
  if(host!==body)lastRender='';host=body;redraw();
}
window.addEventListener('execweave:conversation-sync',()=>{queueMicrotask(redraw)});
window.addEventListener('pagehide',()=>{generation++;controller?.abort();controller=null;receipt=null;offline=null;if(picker)picker.value=''});
window.__execweaveDeliveryStatus={mount,accept,verifySelected};
})();
""".strip()


def delivery_scripts() -> str:
    return ('<script id="execweave-archive-verifier-script">' + ARCHIVE_VERIFIER_JS
            + '</script><script id="execweave-delivery-status-script">' + DELIVERY_STATUS_JS
            + '</script>')
