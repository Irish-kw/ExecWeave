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
.execweave-agent-rounds{display:grid;gap:10px}
.execweave-agent-round{display:grid;gap:12px}
.execweave-agent-older{border:1px solid var(--border);border-radius:10px;background:var(--panel2)}
.execweave-agent-older>summary{cursor:pointer;list-style:none;padding:9px 11px;font-size:11px;color:var(--muted);overflow-wrap:anywhere}
.execweave-agent-older>summary::-webkit-details-marker{display:none}
.execweave-agent-older>summary::before{content:"\25b8 ";color:var(--muted)}
.execweave-agent-older[open]>summary::before{content:"\25be "}
.execweave-agent-older[open]>summary{border-bottom:1px solid var(--border)}
.execweave-agent-older>.execweave-agent-round{padding:10px 11px 11px}
.execweave-agent-when{font-variant-numeric:tabular-nums;color:var(--text)}
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
function aggregate(matches){
  if(!matches.length)return null;
  let base=matches[0],baseCount=-1;
  for(const entry of matches){const count=Array.isArray(entry?.conversation_preview?.messages)?entry.conversation_preview.messages.length:0;if(count>=baseCount){base=entry;baseCount=count}}
  const seen=new Set(),ordered=[];let index=0;
  for(const entry of matches){for(const message of(entry?.conversation_preview?.messages||[])){if(!message||typeof message!=='object')continue;const key=messageKey(message);if(seen.has(key))continue;seen.add(key);ordered.push(messageOrder(message,index++))}}
  ordered.sort((a,b)=>{if(a.stamp&&b.stamp&&a.stamp!==b.stamp)return a.stamp.localeCompare(b.stamp);if(a.ordinal!==b.ordinal)return a.ordinal-b.ordinal;return a.index-b.index});
  const preview=base?.conversation_preview&&typeof base.conversation_preview==='object'?base.conversation_preview:{};
  return{...base,conversation_preview:{...preview,messages:ordered.map(item=>item.message)}};
}
function recordFor(node){
  const path=nodePath(node),nodeId=String(node?.id||'');
  return aggregate(entries.filter(entry=>String(entry?.source_id||'')===nodeId||String(entry?.conversation_preview?.agent_path||'')===path));
}
function recordForPath(path){
  return aggregate(entries.filter(entry=>String(entry?.conversation_preview?.agent_path||'')===String(path)));
}
function uniqueTexts(messages){const seen=new Set(),out=[];for(const message of messages){const text=displayText(message);if(!text||seen.has(text))continue;seen.add(text);out.push(text)}return out}
function card(label,text){const box=document.createElement('section');box.className='execweave-agent-card';const head=document.createElement('div');head.className='execweave-agent-label';head.textContent=label;const body=document.createElement('pre');body.className='execweave-agent-body';body.textContent=text||'Not observed.';if(!text)body.classList.add('execweave-agent-empty');box.append(head,body);return box}
function stampOf(message){return String(message?.timestamp||'')}
function clock(stamp,sameDay){if(!stamp)return '';const at=new Date(stamp);if(Number.isNaN(at.getTime()))return '';
  const pad=value=>String(value).padStart(2,'0');const time=`${pad(at.getHours())}:${pad(at.getMinutes())}`;
  return sameDay?time:`${pad(at.getMonth()+1)}-${pad(at.getDate())} ${time}`}
function summarise(text){const line=String(text||'').split('\n').map(part=>part.trim()).find(Boolean)||'';
  return line.length>52?line.slice(0,52)+'…':line}
// A run is a sequence of rounds, and every panel has to say which one it is showing.
// The root's rounds are the boundaries: a round opens on a user message and runs until
// the next one. A subagent's round is attributed to the root round whose interval
// contains its assignment, so the two panels fold on the same moment and can be read
// side by side.
function rootPrompts(messages,path){return messages.filter(message=>isObserved(message)&&!isInjected(message)&&(String(message?.kind||'')==='user_message'||String(message?.sender||'')==='user')&&(!message?.recipient||String(message.recipient)===path))}
function runRounds(){
  // Every record the root owns, not the first one found: an agent is archived many
  // times and the earliest archives carry nothing.
  const messages=recordForPath('/root')?.conversation_preview?.messages||[];
  return rootPrompts(messages,'/root').map(message=>({start:stampOf(message),label:summarise(messageText(message))}));
}
function roundOf(stamp,rounds){let found=null;for(const round of rounds){if(round.start&&stamp&&round.start<=stamp)found=round}return found||rounds[0]||null}
function sameDayRun(rounds){const days=new Set(rounds.map(round=>String(round.start||'').slice(0,10)).filter(Boolean));return days.size<=1}
function windows(messages,openers){
  if(!openers.length)return[{opener:null,messages}];
  const out=[];
  for(let index=0;index<openers.length;index++){
    const from=messages.indexOf(openers[index]);
    const next=index+1<openers.length?messages.indexOf(openers[index+1]):messages.length;
    out.push({opener:openers[index],messages:messages.slice(from<0?0:from,next<0?messages.length:next)});
  }
  return out;
}
function rootRounds(messages,path){
  return windows(messages,rootPrompts(messages,path)).map(window=>{
    const inside=window.messages;
    const finals=inside.filter(message=>isObserved(message)&&own(message,path)&&(String(message?.phase||'')==='final_answer'||/final[_ -]?response/i.test(String(message?.kind||''))));
    const fallback=inside.filter(message=>isObserved(message)&&own(message,path)&&/assistant|response|message/i.test(String(message?.kind||'')));
    return{
      start:stampOf(window.opener),
      label:summarise(messageText(window.opener)),
      cards:[['Prompt',displayText(window.opener)],['Final response',displayText(finals.at(-1)||fallback.at(-1))]],
    };
  });
}
function childRounds(messages,path){
  const parent=path.includes('/')?(path.slice(0,path.lastIndexOf('/'))||'/root'):'/root';
  const isTask=message=>{const sender=String(message?.sender||'');return isObserved(message)&&!isInjected(message)&&String(message?.recipient||'')===path&&sender!==path&&(/task|assign/i.test(String(message?.kind||''))||String(message?.phase||'')==='assignment')&&(!sender||sender==='user'||sender===parent)};
  // One spawn is recorded twice — in the parent's rollout and in the child's own — and
  // the provider may add its own framing beside it. Those are one assignment, not
  // several rounds, so openers are grouped by the root round they belong to.
  const runs=runRounds();
  const groups=[];
  for(const opener of messages.filter(isTask)){
    const owner=roundOf(stampOf(opener),runs);
    const key=owner?String(owner.start||''):'';
    const last=groups[groups.length-1];
    if(last&&last.key===key)last.openers.push(opener);
    else groups.push({key,openers:[opener]});
  }
  const openers=groups.map(group=>group.openers[0]);
  return windows(messages,openers).map((window,index)=>{
    const inside=window.messages;
    const spoken=groups[index]?.openers.find(opener=>!!messageText(opener));
    const thoughts=inside.filter(message=>isObserved(message)&&!isInjected(message)&&own(message,path)&&(/reason|think|commentary/i.test(`${message?.kind||''} ${message?.phase||''}`)));
    let responses=inside.filter(message=>isObserved(message)&&!isInjected(message)&&own(message,path)&&(String(message?.phase||'')==='final_answer'||/final[_ -]?response|agent_result|result/i.test(String(message?.kind||''))));
    if(!responses.length)responses=inside.filter(message=>isObserved(message)&&!isInjected(message)&&own(message,path)&&!thoughts.includes(message)&&String(message?.recipient||'')!==path&&!/task|assign/i.test(String(message?.kind||'')));
    return{
      start:stampOf(window.opener),
      cards:[['Task',displayText(spoken||window.opener)],['Thinking',uniqueTexts(thoughts).join('\n\n')],['Response',displayText(responses.at(-1))]],
    };
  });
}
function roundView(round){const view=document.createElement('div');view.className='execweave-agent-round';for(const[label,text]of round.cards)view.appendChild(card(label,text));return view}
function foldedRound(round,when,label){
  const fold=document.createElement('details');fold.className='execweave-agent-older';
  const head=document.createElement('summary');
  const time=document.createElement('span');time.className='execweave-agent-when';time.textContent=when;
  head.append(time);
  if(label){head.append(document.createTextNode(` \u00b7 ${label}`))}
  fold.append(head,roundView(round));
  return fold;
}
// A run graph is mostly not agents, and until now selecting one of those nodes showed
// its type and two timestamps. What each kind of node actually carries is listed here,
// and nothing that is not in the data is invented.
function displayGraph(){const core=window.__execweaveCore;return core?.getDisplayGraph?.()||core?.getGraph?.()||{}}
function edgesTouching(id){return (displayGraph().edges||[]).filter(edge=>String(edge?.source||'')===id||String(edge?.target||'')===id)}
function nodeNamed(id){return (displayGraph().nodes||[]).find(node=>String(node?.id||'')===String(id))||null}
function moment(stamp){if(!stamp)return '';const at=new Date(stamp);if(Number.isNaN(at.getTime()))return String(stamp);
  const pad=value=>String(value).padStart(2,'0');
  return `${pad(at.getHours())}:${pad(at.getMinutes())}:${pad(at.getSeconds())}`}
function span(node){const from=moment(node?.first_seen),to=moment(node?.last_seen);
  return from&&to&&from!==to?`${from} → ${to}`:from||to||''}
function commandText(value){
  if(Array.isArray(value))return value.join(' ');
  return value==null?'':String(value);
}
function fileHistory(id){
  const rows=[];
  for(const edge of edgesTouching(id)){
    for(const kind of (edge?.event_types||[])){
      const what=String(kind).replace(/^filesystem\./,'');
      const count=Number(edge?.count||0);
      rows.push(`${moment(edge?.first_seen)}  ${what}${count>1?`  \u00d7${count}`:''}`);
    }
  }
  return rows.sort().join('\n');
}
function reachedBy(id){
  const names=new Set();
  for(const edge of edgesTouching(id)){
    const other=String(edge?.source||'')===id?edge?.target:edge?.source;
    const node=nodeNamed(other);
    if(node&&node.type!=='network_endpoint')names.add(`${node.name||other}`);
  }
  return [...names].join('\n');
}
function nodeCards(node){
  const a=attrs(node),kind=String(node?.type||'');
  const rows=[];
  const add=(label,value)=>{const text=commandText(value);if(text)rows.push([label,text])};
  if(kind==='process'){
    add('Command',a.cmdline);
    add('Executable',a.exe);
    add('Process',[a.pid&&`pid ${a.pid}`,a.ppid&&`parent ${a.ppid}`].filter(Boolean).join('  \u00b7  '));
  }else if(kind==='file'){
    add('Path',node?.name);
    add('Observed',fileHistory(String(node?.id||'')));
  }else if(kind==='tool_call'){
    add('Tool',a.tool_name||node?.name);
    add('Inputs',Array.isArray(a.input_keys)?a.input_keys.join(', '):a.input_keys);
    add('Call',a.tool_use_id);
    add('Model',a.codex_model);
    add('Working directory',a.codex_cwd);
  }else if(kind==='session'){
    add('Command',a.command);
    add('Working directory',a.cwd);
    add('Backend',a.backend);
  }else if(kind==='network_endpoint'){
    add('Address',node?.name);
    add('Reached by',reachedBy(String(node?.id||'')));
  }else{
    add('Name',node?.name);
    add('Provider',a.provider);
    add('Session',a.session_id);
  }
  add('Observed at',span(node));
  return rows;
}
function renderNode(node){
  const rows=nodeCards(node);
  if(!rows.length)return false;
  selectedNode=null;detailsEmpty.hidden=true;details.replaceChildren();
  const view=document.createElement('div');view.className='execweave-agent-view';
  for(const[label,text]of rows)view.appendChild(card(label,text));
  details.appendChild(view);return true;
}
function render(node){
  if(!node)return false;
  if(String(node.type||'')!=='agent')return renderNode(node);
  selectedNode=node;detailsEmpty.hidden=true;details.replaceChildren();
  const path=nodePath(node),preview=recordFor(node)?.conversation_preview||{},messages=Array.isArray(preview.messages)?preview.messages:[];
  const isRoot=path==='/root'||attrs(node).agent_role==='root'||attrs(node).root_agent_path==='/root';
  const rounds=isRoot?rootRounds(messages,path||'/root'):childRounds(messages,path);
  if(rounds.length<2){details.appendChild(roundView(rounds[0]||{cards:isRoot?[['Prompt',''],['Final response','']]:[['Task',''],['Thinking',''],['Response','']]}));return true}
  // A subagent borrows the moment and the wording of the root round it belongs to, so
  // the folds on both panels name the same thing.
  const runs=isRoot?rounds:runRounds();
  const sameDay=sameDayRun(runs.length?runs:rounds);
  const naming=round=>isRoot?round:(roundOf(round.start,runs)||{start:round.start,label:''});
  const list=document.createElement('div');list.className='execweave-agent-rounds';
  const ordered=[...rounds].reverse();
  list.appendChild(roundView(ordered[0]));
  for(const round of ordered.slice(1)){const named=naming(round);list.appendChild(foldedRound(round,clock(named.start||round.start,sameDay),named.label||''))}
  details.appendChild(list);return true;
}
function graphNode(id){const core=window.__execweaveCore;if(!core)return null;const graph=core.getDisplayGraph?.()||core.getGraph?.()||{};return (graph.nodes||[]).find(node=>String(node?.id||'')===String(id||''))||null}
function syncSelection(){const selected=document.querySelector('.node.selected');if(!selected){selectedNode=null;return}const node=graphNode(selected.dataset.id);if(node)render(node);else selectedNode=null}
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
