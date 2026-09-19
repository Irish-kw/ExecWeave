"""Surface captured framework model output without replacing reported outcomes."""
from __future__ import annotations

FRAMEWORK_MODEL_OUTPUT_JS = r"""
function frameworkModelOutputSection(node){
  if(node?.type!=='agent'||attrs(node).conversation_scope!=='framework_agent')return null;
  const kinds=new Set(['metagpt.model_response','autogen.model_response','camel.model_response']);
  const rows=entries.filter(e=>e?.source_id===node.id&&e.source_type==='agent'&&
    e.relation==='HAS_MODEL_CONTENT'&&kinds.has(e.content_kind)&&
    e.model_response_preview?.schema_version==='1'&&e.model_response_preview.source_id===node.id);
  if(!rows.length)return null;
  // No name/path/root fallback or shared-model inference establishes an owner.
  const paths=new Set(rows.map(e=>e.model_response_preview.agent_path));
  if(paths.size!==1||![...paths][0])return null;
  const section=document.createElement('section');section.className='execweave-framework-model-output';
  section.dataset.agentId=String(node.id);
  const title=document.createElement('div');title.className='execweave-agent-label';title.textContent='Captured model output';
  const note=document.createElement('p');note.className='history-provenance';
  note.textContent='Model response previews for this exact agent, not a verified task result or a replacement for the reported response below. Previews may be limited to 6,000 characters per message and 80 messages per record; open the source for captured bytes and integrity checks.';
  section.append(title,note);
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
    shown=Math.min(shown+25,ordered.length);
    count.textContent=`Showing ${shown}/${ordered.length} captured model-response records, not unique invocation counts.`;
    more.hidden=shown===ordered.length;
  }
  section.append(count,more);more.onclick=appendPage;appendPage();return section;
}
""".strip()


def inject_framework_model_output(html: str) -> str:
    """Add the response reader inside the existing agent-panel closure."""
    if "function frameworkModelOutputSection(node){" in html:
        return html
    render = "function render(node){\n  if(!node)return false;"
    entry = "  details.appendChild(historyBrowser.buttonFor(node));"
    if html.count(render) != 1 or html.count(entry) != 1:
        raise RuntimeError("framework model-output inspector seam changed")
    return html.replace(render, FRAMEWORK_MODEL_OUTPUT_JS + "\n" + render, 1).replace(
        entry,
        entry + "\n  const modelOutput=frameworkModelOutputSection(node);"
        "if(modelOutput)details.appendChild(modelOutput);",
        1,
    )
