from __future__ import annotations

_AGENT_PANEL_CSS = r"""
#inspector .inspector-section:first-child{display:none!important}
#inspector .inspector-section:nth-child(2)>.eyebrow{display:none!important}
#inspector .raw-toggle{display:none!important}
#open-final{display:none!important}
.execweave-agent-view{display:grid;gap:12px}
.execweave-agent-card{border:1px solid var(--border);border-radius:10px;background:var(--panel2);overflow:hidden}
.execweave-agent-label{padding:9px 11px;border-bottom:1px solid var(--border);font-size:10px;font-weight:800;letter-spacing:.07em;text-transform:uppercase;color:var(--muted)}
.execweave-agent-body{margin:0;padding:11px 12px;white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:var(--text)}
.execweave-agent-empty{color:var(--muted);font-style:italic}
""".strip()

_AGENT_PANEL_JS = r"""
(()=>{
const details=document.getElementById('details'),detailsEmpty=document.getElementById('details-empty');
if(!details||!detailsEmpty)return;
let entries=Array.isArray(window.__execweaveStaticConversations)?window.__execweaveStaticConversations:[];
let selectedNode=null,refreshing=false;
const ENCRYPTED_NOTICE='Observed — plaintext not exposed by provider.';
const attrs=node=>node&&typeof node.attributes==='object'&&node.attributes?node.attributes:{};
const nodePath=node=>String(attrs(node).agent_path||attrs(node).child_agent_path||attrs(node).root_agent_path||node?.name||'').trim();
const messageText=message=>typeof message?.text==='string'?message.text.trim():'';
const isEncrypted=message=>String(message?.content_state||'')==='provider_encrypted';
const isObserved=message=>!!message&&(isEncrypted(message)||!!messageText(message));
const displayText=message=>isEncrypted(message)?ENCRYPTED_NOTICE:messageText(message);
const isInjected=message=>String(message?.content_role||'')==='shared_injected_context';
const own=(message,path)=>!message?.sender||String(message.sender)===path;
function messageKey(message){return JSON.stringify([message?.timestamp??null,message?.ordinal??null,message?.sender??null,message?.recipient??null,message?.kind??null,message?.phase??null,message?.content_state??null,message?.content_role??null,messageText(message)])}
function messageOrder(message,index){const stamp=String(message?.timestamp||''),ordinal=Number.isInteger(message?.ordinal)?message.ordinal:Number.MAX_SAFE_INTEGER;return{message,index,stamp,ordinal}}
function recordFor(node){
  const path=nodePath(node),nodeId=String(node?.id||'');
  const matches=entries.filter(entry=>String(entry?.source_id||'')===nodeId||String(entry?.conversation_preview?.agent_path||'')===path);
  if(!matches.length)return null;
  let base=matches[0],baseCount=-1;
  for(const entry of matches){const count=Array.isArray(entry?.conversation_preview?.messages)?entry.conversation_preview.messages.length:0;if(count>=baseCount){base=entry;baseCount=count}}
  const seen=new Set(),ordered=[];let index=0;
  for(const entry of matches){for(const message of(entry?.conversation_preview?.messages||[])){if(!message||typeof message!=='object')continue;const key=messageKey(message);if(seen.has(key))continue;seen.add(key);ordered.push(messageOrder(message,index++))}}
  ordered.sort((a,b)=>{if(a.stamp&&b.stamp&&a.stamp!==b.stamp)return a.stamp.localeCompare(b.stamp);if(a.ordinal!==b.ordinal)return a.ordinal-b.ordinal;return a.index-b.index});
  const preview=base?.conversation_preview&&typeof base.conversation_preview==='object'?base.conversation_preview:{};
  return{...base,conversation_preview:{...preview,messages:ordered.map(item=>item.message)}};
}
function uniqueTexts(messages){const seen=new Set(),out=[];for(const message of messages){const text=displayText(message);if(!text||seen.has(text))continue;seen.add(text);out.push(text)}return out}
function card(label,text){const box=document.createElement('section');box.className='execweave-agent-card';const head=document.createElement('div');head.className='execweave-agent-label';head.textContent=label;const body=document.createElement('pre');body.className='execweave-agent-body';body.textContent=text||'Not observed.';if(!text)body.classList.add('execweave-agent-empty');box.append(head,body);return box}
function rootFields(messages,path){
  const prompts=messages.filter(message=>isObserved(message)&&!isInjected(message)&&(String(message?.kind||'')==='user_message'||String(message?.sender||'')==='user')&&(!message?.recipient||String(message.recipient)===path));
  const finals=messages.filter(message=>isObserved(message)&&own(message,path)&&(String(message?.phase||'')==='final_answer'||/final[_ -]?response/i.test(String(message?.kind||''))));
  const fallback=messages.filter(message=>isObserved(message)&&own(message,path)&&/assistant|response|message/i.test(String(message?.kind||'')));
  return{prompt:displayText(prompts[0]),response:displayText(finals.at(-1)||fallback.at(-1))};
}
function childFields(messages,path){
  const parent=path.includes('/')?(path.slice(0,path.lastIndexOf('/'))||'/root'):'/root';
  const tasks=messages.filter(message=>{const sender=String(message?.sender||'');return isObserved(message)&&!isInjected(message)&&String(message?.recipient||'')===path&&sender!==path&&(/task|assign/i.test(String(message?.kind||''))||String(message?.phase||'')==='assignment')&&(!sender||sender==='user'||sender===parent)});
  const thoughts=messages.filter(message=>isObserved(message)&&!isInjected(message)&&own(message,path)&&(/reason|think|commentary/i.test(`${message?.kind||''} ${message?.phase||''}`)));
  let responses=messages.filter(message=>isObserved(message)&&!isInjected(message)&&own(message,path)&&(String(message?.phase||'')==='final_answer'||/final[_ -]?response|agent_result|result/i.test(String(message?.kind||''))));
  if(!responses.length)responses=messages.filter(message=>isObserved(message)&&!isInjected(message)&&own(message,path)&&!thoughts.includes(message)&&String(message?.recipient||'')!==path&&!/task|assign/i.test(String(message?.kind||'')));
  return{task:displayText(tasks[0]),thinking:uniqueTexts(thoughts).join('\n\n'),response:displayText(responses.at(-1))};
}
function render(node){
  if(!node||String(node.type||'')!=='agent')return false;
  selectedNode=node;detailsEmpty.hidden=true;details.replaceChildren();
  const path=nodePath(node),preview=recordFor(node)?.conversation_preview||{},messages=Array.isArray(preview.messages)?preview.messages:[];
  const view=document.createElement('div');view.className='execweave-agent-view';
  const root=path==='/root'||attrs(node).agent_role==='root'||attrs(node).root_agent_path==='/root';
  if(root){const fields=rootFields(messages,path||'/root');view.append(card('Prompt',fields.prompt),card('Final response',fields.response))}
  else{const fields=childFields(messages,path);view.append(card('Task',fields.task),card('Thinking',fields.thinking),card('Response',fields.response))}
  details.appendChild(view);return true;
}
function graphNode(id){const core=window.__execweaveCore;if(!core)return null;const graph=core.getDisplayGraph?.()||core.getGraph?.()||{};return (graph.nodes||[]).find(node=>String(node?.id||'')===String(id||''))||null}
function syncSelection(){const selected=document.querySelector('.node.selected');if(!selected){selectedNode=null;return}const node=graphNode(selected.dataset.id);if(node?.type==='agent')render(node);else selectedNode=null}
function setEntries(next){entries=Array.isArray(next)?next:[];if(selectedNode)render(selectedNode)}
async function refresh(){if(window.__execweaveStaticMode||refreshing)return;refreshing=true;try{const headers={};if(window.__execweaveToken)headers['X-ExecWeave-Token']=window.__execweaveToken;const response=await fetch('/conversations.json',{cache:'no-store',headers});if(response.ok){const payload=await response.json();setEntries(payload?.entries)}}catch(_){}finally{refreshing=false}}
const nodes=document.getElementById('nodes');if(nodes)new MutationObserver(syncSelection).observe(nodes,{subtree:true,attributes:true,attributeFilter:['class']});
document.addEventListener('click',event=>{if(event.target.closest?.('.node'))setTimeout(()=>{syncSelection();refresh()},0)},true);
if(!window.__execweaveStaticMode)setInterval(()=>{if(selectedNode)refresh()},800);
const previous=window.__execweaveDashboard||{};window.__execweaveDashboard={...previous,onPayload(data){previous.onPayload?.(data);if(selectedNode)refresh()},onFinished(){previous.onFinished?.();if(selectedNode)refresh()}};
window.__execweaveAgentPanel={render,setEntries,refresh};
})();
""".strip()


def inject_agent_panel(html: str) -> str:
    if "window.__execweaveAgentPanel" in html:
        return html
    html = html.replace("</style>", _AGENT_PANEL_CSS + "\n</style>", 1)
    marker = html.rfind("</script>")
    if marker < 0:
        raise RuntimeError("dashboard script seam changed")
    return html[:marker] + _AGENT_PANEL_JS + "\n" + html[marker:]
