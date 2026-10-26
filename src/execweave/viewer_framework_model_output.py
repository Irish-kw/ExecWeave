"""Surface captured framework model output without replacing reported outcomes."""
from __future__ import annotations

FRAMEWORK_MODEL_OUTPUT_JS = r"""
let frameworkModelOutputView=null;
window.addEventListener('pagehide',()=>{frameworkModelOutputView=null});
function frameworkModelOutputKey(node){
  const g=rawGraph()||{};
  return JSON.stringify([g.run_id??null,g.session_id??null,g.source_path??null,node?.id??null]);
}
function frameworkModelOutputRows(node){
  if(node?.type!=='agent'||attrs(node).conversation_scope!=='framework_agent')return [];
  const kinds=new Set(['metagpt.model_response','autogen.model_response','camel.model_response']);
  const rows=entries.filter(e=>e?.source_id===node.id&&e.source_type==='agent'&&
    e.relation==='HAS_MODEL_CONTENT'&&kinds.has(e.content_kind)&&
    e.model_response_preview?.schema_version==='1'&&e.model_response_preview.source_id===node.id);
  if(!rows.length)return [];
  // No name/path/root fallback or shared-model inference establishes an owner.
  const paths=new Set(rows.map(e=>e.model_response_preview.agent_path));
  if(paths.size!==1||![...paths][0])return [];
  // Keep only fields this reader renders or passes to the existing body reader.
  // The merged conversation projection is independent and must not drive updates.
  const fields=['source_id','source_type','relation','content_kind','path','sha256',
    'size_bytes','media_type','representation','complete_from_source','first_sequence',
    'last_sequence','first_seen','last_seen','model_response_preview'];
  return rows.map(e=>Object.fromEntries(fields.map(k=>[k,e[k]??null])));
}
function frameworkModelOutputSnapshot(node,visible=25){
  const signature=JSON.stringify(frameworkModelOutputRows(node));
  return {key:frameworkModelOutputKey(node),signature,rows:JSON.parse(signature),visible};
}
function frameworkModelOutputChanged(node){
  if(!node||node.type!=='agent')return;
  const current=details.querySelector('.execweave-framework-model-output');
  if(current&&frameworkModelOutputView?.key===frameworkModelOutputKey(node)){
    current.__execweaveUpdateNotice?.();return;
  }
  if(current){current.remove();frameworkModelOutputView=null}
  const next=frameworkModelOutputSection(node);
  if(next){const history=details.querySelector('.execweave-history-entry');
    if(history)history.after(next);else details.prepend(next)}
}
function frameworkModelOutputSection(node){
  if(node?.type!=='agent'||attrs(node).conversation_scope!=='framework_agent')return null;
  const key=frameworkModelOutputKey(node);
  if(!frameworkModelOutputView||frameworkModelOutputView.key!==key)
    frameworkModelOutputView=frameworkModelOutputSnapshot(node);
  const view=frameworkModelOutputView,rows=view.rows;
  if(!rows.length&&!frameworkModelOutputRows(node).length)return null;
  const section=document.createElement('section');section.className='execweave-framework-model-output';
  section.dataset.agentId=String(node.id);
  const title=document.createElement('div');title.className='execweave-agent-label';title.textContent='Captured model output';
  const note=document.createElement('p');note.className='history-provenance';
  note.textContent='Model response previews for this exact agent, not a verified task result or a replacement for the reported response below. Previews may be limited to 6,000 characters per message and 80 messages per record; open the source for captured bytes and integrity checks.';
  const notice=document.createElement('p');notice.className='history-provenance';notice.setAttribute('role','status');
  const refresh=document.createElement('button');refresh.type='button';refresh.textContent='Refresh captured model output';
  function updateNotice(){
    if(view.key!==frameworkModelOutputKey(selectedNode))return;
    const changed=JSON.stringify(frameworkModelOutputRows(node))!==view.signature;
    notice.textContent=changed?'Updated captured model output is available. The displayed preview is an earlier snapshot until you refresh it.':'';
    notice.hidden=!changed;refresh.hidden=!changed;
  }
  refresh.onclick=()=>{
    if(!section.isConnected||view.key!==frameworkModelOutputKey(selectedNode))return;
    // Include default-open folds: a newer latest record must not close the one
    // the reader was already inspecting. Store booleans, not response bodies.
    const state=foldStateFor(node);
    for(const fold of section.querySelectorAll('details[data-fold-key]'))state.set(fold.dataset.foldKey,fold.open);
    frameworkModelOutputView=frameworkModelOutputSnapshot(node,view.visible);
    const next=frameworkModelOutputSection(node);
    if(next)section.replaceWith(next);else section.remove();
  };
  section.__execweaveUpdateNotice=updateNotice;
  section.append(title,note,notice,refresh);updateNotice();
  const ordered=rows.slice().sort((a,b)=>String(b.first_seen||'').localeCompare(String(a.first_seen||''))||
    (Number(b.first_sequence)||0)-(Number(a.first_sequence)||0));
  const state=foldStateFor(node);let shown=0;
  const more=document.createElement('button');more.type='button';more.textContent='Show more model output records';
  const count=document.createElement('p');count.className='history-provenance';
  function appendPage(){
    for(const e of ordered.slice(shown,shown+25)){
      const fold=document.createElement('details');fold.className='execweave-agent-older execweave-framework-model-record';
      const key='model-output:'+JSON.stringify([node.id,e.path,e.first_sequence,e.first_seen]);
      bindFold(fold,state,key,shown===0&&e===ordered[0]);
      const summary=document.createElement('summary');
      summary.textContent=[moment(e.first_seen),e.content_kind,'Captured response record'].filter(Boolean).join(' · ');
      fold.appendChild(summary);
      let populated=false;
      function populate(){
        if(populated)return;populated=true;
        const p=e.model_response_preview;
        const messages=Array.isArray(p.messages)?p.messages:[];
        for(const message of messages.slice(0,80)){
          if(message?.sender!==p.agent_path)continue;
          const body=document.createElement('pre');body.className='execweave-agent-body';
          body.textContent=isEncrypted(message)?ENCRYPTED_NOTICE:typeof message.text==='string'?message.text.slice(0,6000):'Plaintext not available in this preview.';
          fold.appendChild(body);
        }
        if(!messages.length)fold.appendChild(card('Preview','Plaintext not available in this preview. Open the recorded source to check its content.'));
        if(p.messages_truncated||messages.length>80)fold.appendChild(card('Preview limit','Additional messages are not included in this preview.'));
        window.__execweaveContentBrowser?.attach(fold,[e],String(node.id));
      }
      summary.addEventListener('click',()=>{if(!fold.open)populate()});
      if(fold.open)populate();
      fold.addEventListener('toggle',()=>{if(fold.isConnected&&fold.open)populate()});
      section.insertBefore(fold,count);
    }
    shown=Math.min(shown+25,ordered.length);view.visible=Math.max(view.visible,shown);
    count.textContent=`Showing ${shown}/${ordered.length} captured model-response records, not unique invocation counts.`;
    more.hidden=shown===ordered.length;
  }
  section.append(count,more);more.onclick=appendPage;
  const initialLimit=view.visible;do{appendPage()}while(shown<Math.min(initialLimit,ordered.length));
  return section;
}
""".strip()


def inject_framework_model_output(html: str) -> str:
    """Add the response reader inside the existing agent-panel closure."""
    if "function frameworkModelOutputSection(node){" in html:
        return html
    render = "function render(node){\n  if(!node)return false;"
    entry = "  details.appendChild(historyBrowser.buttonFor(node));"
    update = "const previousSignature=selectedConversationSignature;entries=candidate;historyBrowser.changed();"
    if html.count(render) != 1 or html.count(entry) != 1 or html.count(update) != 1:
        raise RuntimeError("framework model-output inspector seam changed")
    return html.replace(render, FRAMEWORK_MODEL_OUTPUT_JS + "\n" + render, 1).replace(
        entry,
        entry + "\n  const modelOutput=frameworkModelOutputSection(node);"
        "if(modelOutput)details.appendChild(modelOutput);",
        1,
    ).replace(update, update + "frameworkModelOutputChanged(selectedNode);", 1)
