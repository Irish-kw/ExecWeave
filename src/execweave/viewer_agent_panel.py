from __future__ import annotations

from .viewer_fold_state import FOLD_STATE_JS
from .viewer_agent_panel_antigravity import ANTIGRAVITY_CHILD_ROUNDS_JS
from .viewer_agent_panel_claude import CLAUDE_CHILD_ROUNDS_JS
from .viewer_agent_panel_codex import CODEX_CHILD_ROUNDS_JS
from .viewer_agent_panel_cursor import CURSOR_CHILD_ROUNDS_JS
from .viewer_agent_panel_default import DEFAULT_CHILD_ROUNDS_JS
from .viewer_agent_panel_ollama import OLLAMA_CHILD_ROUNDS_JS
from .viewer_agent_panel_opencode import OPENCODE_CHILD_ROUNDS_JS

_AGENT_PANEL_CSS = r"""
#inspector .inspector-section:first-child{display:none!important}
#inspector .inspector-section:nth-child(2)>.eyebrow{display:none!important}
#inspector .raw-toggle{display:none!important}
#open-final{display:none!important}
.execweave-agent-view{display:grid;gap:12px}
.execweave-agent-card{border:1px solid var(--border);border-radius:10px;background:var(--panel2);overflow:hidden}
.execweave-agent-label,.execweave-communication-label{padding:9px 11px;border-bottom:1px solid var(--border);font-size:10px;font-weight:800;letter-spacing:.07em;text-transform:uppercase;color:var(--muted)}
.execweave-agent-body,.execweave-message-body{margin:0;padding:11px 12px;white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:var(--text)}
.execweave-agent-empty{color:var(--muted);font-style:italic}
.execweave-agent-rounds{display:grid;gap:10px}
.execweave-agent-round{display:grid;gap:12px}
:is(.execweave-agent-older,.execweave-agent-latest){border:1px solid var(--border);border-radius:10px;background:var(--panel2)}
:is(.execweave-agent-older,.execweave-agent-latest)>summary{cursor:pointer;list-style:none;padding:9px 11px;font-size:11px;color:var(--muted);overflow-wrap:anywhere}
:is(.execweave-agent-older,.execweave-agent-latest)>summary::-webkit-details-marker{display:none}
:is(.execweave-agent-older,.execweave-agent-latest)>summary::before{content:"\25b8 ";color:var(--muted)}
:is(.execweave-agent-older,.execweave-agent-latest)[open]>summary::before{content:"\25be "}
:is(.execweave-agent-older,.execweave-agent-latest)[open]>summary{border-bottom:1px solid var(--border)}
:is(.execweave-agent-older,.execweave-agent-latest)>.execweave-agent-round{padding:10px 11px 11px}
.execweave-agent-when{font-variant-numeric:tabular-nums;color:var(--text)}
.execweave-message-history{border:1px solid var(--border);border-radius:10px;background:var(--panel2);margin:6px 0}
.execweave-message-history>summary{cursor:pointer;padding:9px 11px;font-size:11px;color:var(--muted);overflow-wrap:anywhere}
""".strip()

_AGENT_PANEL_JS = r"""
(()=>{
const details=document.getElementById('details'),detailsEmpty=document.getElementById('details-empty');
if(!details||!detailsEmpty)return;
let entries=Array.isArray(window.__execweaveStaticConversations)?window.__execweaveStaticConversations:[];
let selectedNode=null,refreshing=false,selectedConversationSignature='';
const foldStateByAgent=new Map();
const ROOT_NODE_IDS=new Set(['agent:Claude Code','agent:OpenAI Codex','agent:Codex','agent:Cursor','agent:OpenCode','agent:Antigravity','agent:Ollama','agent:ollama']);
const ENCRYPTED_NOTICE='Observed — plaintext not exposed by provider.';
const attrs=node=>node&&typeof node.attributes==='object'&&node.attributes?node.attributes:{};
const nodePath=node=>String(attrs(node).agent_path||attrs(node).child_agent_path||attrs(node).root_agent_path||node?.name||'').trim();
const agentKey=node=>String(node?.id||'')||nodePath(node);
const messageText=message=>typeof message?.text==='string'?message.text.trim():'';
const isEncrypted=message=>String(message?.content_state||'')==='provider_encrypted';
const isObserved=message=>!!message&&(isEncrypted(message)||!!messageText(message));
const displayText=message=>isEncrypted(message)?ENCRYPTED_NOTICE:messageText(message);
const isInjected=message=>String(message?.content_role||'')==='shared_injected_context';
const own=(message,path)=>!message?.sender||String(message.sender)===path;
const previewHasRootAuthority=preview=>!!preview&&preview.is_root===true&&String(preview.topology_state||'')!=='derived'&&String(preview.topology_evidence||'')!=='no_parent_evidence_observed';
const previewUsesRootRenderer=preview=>!!preview&&preview.is_root===true&&String(preview.agent_path||'')==='/root';
const nodeHasChildAuthority=node=>!!String(attrs(node).parent_agent_path||'').trim();
const legacyRootSignal=(node,path)=>path==='/root'||attrs(node).agent_role==='root'||attrs(node).root_agent_path==='/root';
const nodeHasRootAuthority=node=>!nodeHasChildAuthority(node)&&(legacyRootSignal(node,nodePath(node))||ROOT_NODE_IDS.has(String(node?.id||'')));
const entryHasRootAuthority=entry=>ROOT_NODE_IDS.has(String(entry?.source_id||''))||previewHasRootAuthority(entry?.conversation_preview);
function messageKey(message){if(message?.occurrence_id)return JSON.stringify(["occurrence",message.occurrence_id,message.sender??null,message.kind??null,message.phase??null,messageText(message)]);return JSON.stringify([message?.timestamp??null,message?.ordinal??null,message?.sender??null,message?.recipient??null,message?.kind??null,message?.phase??null,message?.content_state??null,message?.content_role??null,messageText(message)])}
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
  const nodeId=String(node?.id||'');
  const exact=nodeId?entries.filter(entry=>String(entry?.source_id||'')===nodeId):[];
  const aliases=new Set((Array.isArray(attrs(node).viewer_agent_member_ids)?attrs(node).viewer_agent_member_ids:[]).map(String).filter(alias=>alias&&alias!==nodeId));
  if(aliases.size)exact.push(...entries.filter(entry=>aliases.has(String(entry?.source_id||''))));
  if(exact.length)return aggregate(exact);
  const path=nodePath(node);if(!path)return null;
  return aggregate(entries.filter(entry=>{
    const preview=entry?.conversation_preview;
    if(!preview||!(String(entry?.conversation_preview?.agent_path||'')===path))return false;
    if(String(preview.topology_state||'')==='derived')return false;
    if(path==='/root'&&!entryHasRootAuthority(entry))return false;
    return true;
  }));
}
function canonicalRootRecord(){
  const roots=entries.filter(entryHasRootAuthority);
  const sourceIds=[...new Set(roots.map(entry=>String(entry?.source_id||'')).filter(Boolean))];
  if(sourceIds.length!==1){
    if(sourceIds.length)return null;
    const agy=entries.filter(entry=>{
      const preview=entry?.conversation_preview;
      return String(entry?.provider||'').toLowerCase()==='antigravity'&&!!preview&&
        String(entry?.source_id||'').startsWith('agent:antigravity:conversation:')&&
        !String(preview.parent_agent_path||'').trim();
    });
    const agyIds=[...new Set(agy.map(entry=>String(entry?.source_id||'')).filter(Boolean))];
    if(agyIds.length===1)return aggregate(agy.filter(entry=>String(entry?.source_id||'')===agyIds[0]));
  }
  if(sourceIds.length!==1)return null;
  return aggregate(roots.filter(entry=>String(entry?.source_id||'')===sourceIds[0]));
}
function recordForPath(path){
  if(String(path)==='/root')return canonicalRootRecord();
  return aggregate(entries.filter(entry=>{
    const preview=entry?.conversation_preview;
    return !!preview&&String(entry?.conversation_preview?.agent_path||'')===String(path)&&String(preview.topology_state||'')!=='derived';
  }));
}
function conversationSignature(node){
  if(!node||String(node.type||'')!=='agent')return '';
  const preview=recordFor(node)?.conversation_preview||{};
  const messages=Array.isArray(preview.messages)?preview.messages:[];
  return JSON.stringify([agentKey(node),messages.map(messageKey)]);
}
/*EXECWEAVE_FOLD_STATE*/
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
// side by side. Root boundaries come from one exact root identity, never every record
// whose presentation path happens to be /root.
function rootPrompts(messages,path){return messages.filter(message=>isObserved(message)&&!isInjected(message)&&(String(message?.kind||'')==='user_message'||String(message?.sender||'')==='user')&&(!message?.recipient||String(message.recipient)===path))}
function runRounds(rootRecord=null){
  const record=rootRecord||recordForPath('/root'),preview=record?.conversation_preview||{};
  const messages=Array.isArray(preview.messages)?preview.messages:[];
  const path=String(preview.agent_path||'/root');
  return rootPrompts(messages,path).map(message=>({key:messageKey(message),start:stampOf(message),label:summarise(messageText(message))}));
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
      key:messageKey(window.opener),
      start:stampOf(window.opener),
      label:summarise(messageText(window.opener)),
      cards:[['Prompt',displayText(window.opener)],['Final response',displayText(finals.at(-1)||fallback.at(-1))]],
    };
  });
}
/*EXECWEAVE_CHILD_POLICY*/
function childRounds(messages,path){
  const record=selectedNode?recordFor(selectedNode):null;
  const preview=record?.conversation_preview||{};
  const provider=String(preview.provider||attrs(selectedNode).provider||record?.provider||'').toLowerCase();
  const policy=({
    codex:execweaveCodexChildRounds,
    antigravity:execweaveAntigravityChildRounds,
    claude:execweaveClaudeChildRounds,
    ollama:execweaveOllamaChildRounds,
    cursor:execweaveCursorChildRounds,
    opencode:execweaveOpencodeChildRounds
  })[provider]||execweaveDefaultChildRounds;
  return policy(messages,path);
}
function roundView(round){const view=document.createElement('div');view.className='execweave-agent-round';for(const[label,text]of round.cards)view.appendChild(card(label,text));return view}
function stableRoundKey(round){
  const raw=String(round?.key||'');
  if(raw){
    try{
      const parts=JSON.parse(raw);
      if(Array.isArray(parts)&&parts[0]==='occurrence')return JSON.stringify(parts.slice(0,-1));
      // messageKey starts with observation timestamp followed by the provider
      // ordinal. A cumulative provider snapshot can re-observe the same turn at
      // a later timestamp, but its stable ordinal and content remain unchanged.
      // Fold state is already scoped by exact agent identity, so when an ordinal
      // exists the observation timestamp must not re-identify the historical round.
      if(Array.isArray(parts)&&Number.isInteger(parts[1]))return JSON.stringify(['ordinal',...parts.slice(1)]);
    }catch(_error){}
    return raw;
  }
  return JSON.stringify([round?.start??null,round?.cards?.[0]?.[0]??null,round?.cards?.[0]?.[1]??null]);
}
function foldedRound(round,when,label,state,defaultOpen=false){
  const fold=document.createElement('details');fold.className=defaultOpen?'execweave-agent-latest execweave-agent-round':'execweave-agent-older';
  const key=stableRoundKey(round);bindFold(fold,state,key,defaultOpen);
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
// tool_call and observed_content are hidden from the graph on purpose: a run makes one
// tool_call per invocation and drawing them buries everything else. Hiding them from
// the graph is not a reason to hide them from the reader, and the unprojected graph
// still carries both, so the panel reads that.
function rawGraph(){const core=window.__execweaveCore;return core?.getGraph?.()||displayGraph()}
function rawEdges(){return Array.isArray(rawGraph().edges)?rawGraph().edges:[]}
function rawNode(id){return (rawGraph().nodes||[]).find(node=>String(node?.id||'')===String(id))||null}
function relatedTo(id,relation,{from=true}={}){
  const wanted=String(relation).toUpperCase();
  return rawEdges()
    .filter(edge=>String(edge?.relation||'').toUpperCase()===wanted&&String(from?edge?.source:edge?.target)===String(id))
    .map(edge=>rawNode(from?edge.target:edge.source))
    .filter(Boolean);
}
// What one call actually left behind. The command is a graph attribute and can be
// shown outright; the stored input is a digest and a size, and is described as that
// rather than as content the page has read.
function toolCallLine(call,sameDay){
  const a=attrs(call),name=a.tool_name||call?.name||'tool';
  const when=clock(call?.first_seen||call?.last_seen||'',sameDay);
  const command=relatedTo(call.id,'DECLARED_COMMAND').map(node=>attrs(node).command||node?.name).filter(Boolean)[0];
  const stored=relatedTo(call.id,'HAS_TOOL_INPUT').map(node=>attrs(node))[0];
  const parts=[when,name].filter(Boolean);
  let line=parts.join('  \u00b7  ');
  if(command)line+=`\n    ${commandText(command)}`;
  else if(Array.isArray(a.input_keys)&&a.input_keys.length)line+=`\n    ${a.input_keys.join(', ')}`;
  if(stored?.sha256){
    const size=Number(stored.size_bytes);
    const complete=stored.complete_from_source===true?'complete':'partial';
    line+=`\n    input recorded \u00b7 ${Number.isFinite(size)?size:'?'} bytes \u00b7 ${complete} \u00b7 ${String(stored.sha256).slice(0,12)}`;
  }
  return line;
}
function toolCallsFor(agentId){
  const calls=relatedTo(agentId,'REQUESTED_TOOL_CALL');
  if(!calls.length)return '';
  const ordered=[...calls].sort((a,b)=>String(b?.first_seen||'').localeCompare(String(a?.first_seen||'')));
  const stamps=ordered.map(call=>String(call?.first_seen||'')).filter(Boolean);
  const sameDay=stamps.length<2||stamps.every(value=>value.slice(0,10)===stamps[0].slice(0,10));
  return ordered.map(call=>toolCallLine(call,sameDay)).join('\n');
}
function callersOf(toolId){
  const calls=rawEdges().filter(edge=>String(edge?.relation||'').toUpperCase()==='USES_TOOL'&&String(edge?.target)===String(toolId))
    .map(edge=>rawNode(edge.source)).filter(Boolean);
  const names=new Set();
  for(const call of calls)for(const agent of relatedTo(call.id,'REQUESTED_TOOL_CALL',{from:false}))names.add(agent?.name||agent?.id);
  return{count:calls.length,agents:[...names].sort()};
}
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
function externalEndpointLine(item){
  const address=String(item?.address||'').trim();
  if(!address)return '';
  const bits=[];
  const from=moment(item?.first_seen),to=moment(item?.last_seen);
  if(from&&to&&from!==to)bits.push(`${from} → ${to}`);
  else if(from||to)bits.push(from||to);
  const count=Number(item?.event_count||0);
  if(count)bits.push(`${count} event${count===1?'':'s'}`);
  return bits.length?`${address}\n  ${bits.join('  ·  ')}`:address;
}
function foldedList(a){
  const members=Array.isArray(a.viewer_folded_members)?a.viewer_folded_members:[];
  return members
    .slice()
    .sort((x,y)=>String(y?.last_seen||'').localeCompare(String(x?.last_seen||'')))
    .map(item=>`${moment(item?.last_seen||item?.first_seen)}  ${item?.name||item?.id}`)
    .join('\n');
}
function occurrenceList(a){
  const rows=Array.isArray(a.viewer_occurrences)?a.viewer_occurrences:[];
  if(rows.length<2)return '';
  return rows
    .slice()
    .sort((x,y)=>String(y?.first_seen||'').localeCompare(String(x?.first_seen||'')))
    .map(item=>`${moment(item?.first_seen)}${item?.pid?`  pid ${item.pid}`:''}`)
    .join('\n');
}
// A node the flow layout drew in place of others is still a real node with a panel of
// its own, so it keeps every card it would have had and says what it absorbed at the
// end. A node whose only purpose is to stand for others is the separate `viewer_folded`
// case below, and that one is a list of what it holds and nothing else.
function nodeCards(node){
  const a=attrs(node),rows=execweaveNodeCardsBase(node);
  if(!a.viewer_absorbed||a.viewer_folded)return rows;
  const held=foldedList(a);
  if(held)rows.push(['Also holding',held]);
  return rows;
}
function execweaveNodeCardsBase(node){
  const a=attrs(node),kind=String(node?.type||'');
  const rows=[];
  const add=(label,value)=>{const text=commandText(value);if(text)rows.push([label,text])};
  if(a.viewer_folded){
    // The budget folds the older nodes of a type into this one rather than dropping
    // them, so it has to say what it holds.
    add('Folded',`${a.viewer_folded_count} earlier ${String(a.viewer_folded_type||'').replace(/_/g,' ')} nodes`);
    add('Holding',foldedList(a));
    add('Observed at',span(node));
    return rows;
  }
  if(kind==='process'){
    if(Array.isArray(a.viewer_message_evidence)&&a.viewer_message_evidence.length)add('Unrouted callback messages',`${a.viewer_message_evidence.length} observations; sender/recipient not exposed. Original evidence retained in raw graph.`);
    add('Command',a.cmdline);
    add('Executable',a.exe);
    add('Process',[a.pid&&`pid ${a.pid}`,a.ppid&&`parent ${a.ppid}`].filter(Boolean).join('  \u00b7  '));
    add('Ran',occurrenceList(a));
  }else if(kind==='file'){
    add('Path',node?.name);
    add('Observed',fileHistory(String(node?.id||'')));
  }else if(kind==='tool_call'){
    add('Tool',a.tool_name||node?.name);
    add('Inputs',Array.isArray(a.input_keys)?a.input_keys.join(', '):a.input_keys);
    add('Call',a.tool_use_id);
    add('Model',a.codex_model);
    add('Working directory',a.codex_cwd);
  }else if(kind==='tool'){
    add('Tool',node?.name);
    add('Provider',a.provider);
    const traffic=callersOf(String(node?.id||''));
    const occurrences=Array.isArray(a.viewer_tool_call_occurrences)?a.viewer_tool_call_occurrences:[];
    add('Calls',occurrences.length?String(occurrences.length):(traffic.count?String(traffic.count):''));
    add('Requested by',traffic.agents.join('\n'));
  }else if(kind==='session'){
    add('Command',a.command);
    add('Working directory',a.cwd);
    add('Backend',a.backend);
  }else if(kind==='task'){
    add('Task',a.task_prompt||a.prompt||a.description||node?.name);
    add('Prompt',a.task_prompt||a.prompt||a.description);
    add('Provider',a.provider);
  }else if(kind==='network_endpoint'){
    const endpoints=Array.isArray(a.endpoints)?a.endpoints:[];
    if(endpoints.length){
      add('Endpoints',endpoints.map(externalEndpointLine).filter(Boolean).join('\n'));
    }else{
      add('Address',node?.name);
    }
    add('Reached by',reachedBy(String(node?.id||'')));
  }else{
    add('Name',node?.name);
    add('Provider',a.provider);
    add('Session',a.session_id);
  }
  add('Observed at',span(node));
  return rows;
}
function contentAvailability(occurrence,relation){
  const refs=(occurrence?.content_references||[]).filter(ref=>String(ref?.relation||'')===relation);
  return refs.length?{state:'archived_reference',note:'Full content is in the referenced run artifact; not an empty tool result.',references:refs}:{state:'not_observed',note:'A returned event does not establish that result content was captured.'};
}
function inferenceOccurrenceSection(node){
  const rows=attrs(node).viewer_inference_occurrences;if(!Array.isArray(rows)||!rows.length)return null;
  const section=document.createElement('section');section.className='execweave-inference-history execweave-agent-rounds';
  const title=document.createElement('div');title.className='execweave-agent-label';title.textContent='Inference history';section.appendChild(title);
  const state=foldStateFor(node),ordered=rows.slice().sort((a,b)=>String(a?.first_seen||'').localeCompare(String(b?.first_seen||''))||(Number(a?.first_sequence)||0)-(Number(b?.first_sequence)||0));
  ordered.reverse().forEach((item,index)=>{
    const fold=document.createElement('details');fold.className='execweave-agent-older execweave-inference-occurrence';
    const identity=item?.request_ids||item?.call_ids||[item?.first_seen,item?.first_sequence,ordered.length-index];
    bindFold(fold,state,'inference:'+JSON.stringify(identity),index===0);
    const head=document.createElement('summary');head.textContent=[moment(item?.first_seen||item?.last_seen),`call ${ordered.length-index}`,index===0?'Latest':''].filter(Boolean).join(' · ');fold.appendChild(head);
    for(const message of item?.messages||[]){fold.appendChild(card([message?.sender,message?.kind].filter(Boolean).join(' · ')||'Observed message',String(message?.text||'')));if(message?.text_truncated)fold.appendChild(card('Preview limit','This message preview is truncated. The complete content is in the references below.'))}
    if(item?.content_references?.length)fold.appendChild(card('Content references',JSON.stringify(item.content_references,null,2)));
    if(!item?.messages?.length&&!item?.content_references?.length)fold.appendChild(card('Content','Not observed.'));
    section.appendChild(fold);
  });return section;
}
function toolOccurrenceSection(node){
  const occurrences=Array.isArray(attrs(node).viewer_tool_call_occurrences)?attrs(node).viewer_tool_call_occurrences:[];
  if(!occurrences.length)return null;
  const section=document.createElement('section');section.className='execweave-tool-occurrences';
  const title=document.createElement('strong');title.textContent=`Invocations · ${occurrences.length} call${occurrences.length===1?'':'s'}`;section.appendChild(title);
  occurrences.forEach((occurrence,index)=>{
    const fold=document.createElement('details');fold.className='execweave-tool-occurrence';
    const summary=document.createElement('summary');
    const owner=nodeNamed(occurrence?.owner_id)?.name||occurrence?.owner_id||'unknown';
    const when=moment(occurrence?.first_seen||occurrence?.last_seen);
    summary.textContent=[when,owner,`call ${index+1}`].filter(Boolean).join(' · ');
    const pre=document.createElement('pre');
    pre.textContent=JSON.stringify({
      first_seen:occurrence?.first_seen||null,
      last_seen:occurrence?.last_seen||null,
      first_sequence:occurrence?.first_sequence??null,
      last_sequence:occurrence?.last_sequence??null,
      input:occurrence?.input??contentAvailability(occurrence,'HAS_TOOL_INPUT'),
      output:occurrence?.output??contentAvailability(occurrence,'HAS_TOOL_OUTPUT'),
      call_ids:occurrence?.call_ids||[],
      content_references:occurrence?.content_references||[]
    },null,2);
    bindFold(fold,foldStateFor(node),'tool:'+JSON.stringify(occurrence?.call_ids||[occurrence?.first_sequence,index]));
    fold.append(summary,pre);section.appendChild(fold);
  });
  return section;
}
function execweaveAssignedTaskText(agent){
  if(!agent||String(agent.type||'')!=='agent')return '';
  const projected=attrs(agent),attached=projected.viewer_assigned_task_prompt||projected.viewer_assigned_task_name;
  if(attached)return commandText(attached);
  const graph=rawGraph(),nodes=Array.isArray(graph.nodes)?graph.nodes:[],edges=Array.isArray(graph.edges)?graph.edges:[];
  const nodeMap=new Map(nodes.filter(node=>node&&node.id).map(node=>[String(node.id),node]));
  const exactAssignment=['ASSIGNED','AGENT','TASK'].join('_');
  const direct=edges.filter(edge=>edge&&String(edge.target||'')===String(agent.id||'')&&['ASSIGNED_TO',exactAssignment].includes(String(edge.relation||''))).sort((a,b)=>(Number(a.first_sequence)||0)-(Number(b.first_sequence)||0));
  const owned=edges.filter(edge=>edge&&String(edge.source||'')===String(agent.id||'')&&String(edge.relation||'')==='TASK_CREATED').sort((a,b)=>(Number(a.first_sequence)||0)-(Number(b.first_sequence)||0));
  const started=edges.filter(edge=>edge&&String(edge.source||'')===String(agent.id||'')&&String(edge.relation||'')==='TASK_STARTED').sort((a,b)=>(Number(a.first_sequence)||0)-(Number(b.first_sequence)||0));
  const edge=direct.at(-1)||owned.at(-1)||started.at(-1);if(!edge)return '';
  const taskId=direct.length?edge.source:edge.target,task=nodeMap.get(String(taskId||''));
  if(!task||String(task.type||'')!=='task')return '';
  const a=attrs(task);return commandText(a.task_prompt||a.prompt||a.description||task.name);
}
function execweaveFillAssignedTask(round,node,isRoot){
  const task=execweaveAssignedTaskText(node);if(!task)return round;
  const value=round||{cards:[]},cards=Array.isArray(value.cards)?value.cards.map(card=>[card[0],card[1]]):[];
  const label=isRoot?'Prompt':'Task',index=cards.findIndex(card=>String(card[0]||'')===label);
  if(index<0)cards.unshift([label,task]);else if(!commandText(cards[index][1]))cards[index][1]=task;
  else if(attrs(node).conversation_scope==='framework_agent'&&commandText(cards[index][1])!==task)cards.unshift(['Assigned task',task]);
  return{...value,cards};
}
function agentCommunicationHistory(node,messages){
  // Read only this exact agent's conversation record. Never sweep sibling
  // transcripts into the parent merely because they share a run or a model.
  const candidates=messages.filter(message=>isObserved(message)&&!isInjected(message)&&(
    String(message?.kind||'')==='agent_message'||
    (String(message?.sender||'').startsWith('/')&&String(message?.recipient||'').startsWith('/')&&message.sender!==message.recipient)
  ));
  const byMessage=new Map();
  for(const message of candidates){
    const key=message.message_id?JSON.stringify([message.message_id,message.sender,message.recipient,message.text]):messageKey(message);
    const previous=byMessage.get(key);
    if(!previous||message.phase==='received')byMessage.set(key,message);
  }
  const routed=[...byMessage.values()];
  if(!routed.length)return null;
  const section=document.createElement('section');section.className='execweave-agent-communication';
  section.dataset.agentId=String(node.id);
  const title=document.createElement('div');title.className='execweave-communication-label';title.textContent='Agent communication';section.appendChild(title);
  const state=foldStateFor(node);
  for(const message of [...routed].reverse()){
    const fold=document.createElement('details');fold.className='execweave-message-history';
    const key='message:'+messageKey(message);fold.open=state.get(key)===true;bindFold(fold,state,key);
    const summary=document.createElement('summary');
    summary.textContent=[moment(message.timestamp),`${message.sender||'Unknown sender'} → ${message.recipient||'Recipient not recorded'}`].filter(Boolean).join(' · ');
    const body=document.createElement('pre');body.className='execweave-message-body';body.textContent=displayText(message);
    fold.append(summary,body);section.appendChild(fold);
  }
  return section;
}
function renderNode(node){
  const rows=nodeCards(node);
  if(!rows.length)return false;
  rememberVisibleFoldState();
  selectedNode=null;selectedFoldNode=node;selectedConversationSignature='';detailsEmpty.hidden=true;details.replaceChildren();
  const view=document.createElement('div');view.className='execweave-agent-view';
  for(const[label,text]of rows)view.appendChild(card(label,text));
  details.appendChild(view);
  const occurrences=toolOccurrenceSection(node);if(occurrences)details.appendChild(occurrences);
  const inferences=inferenceOccurrenceSection(node);if(inferences)details.appendChild(inferences);
  return true;
}
function render(node){
  if(!node)return false;
  if(String(node.type||'')!=='agent')return renderNode(node);
  rememberVisibleFoldState();
  selectedNode=node;selectedFoldNode=node;selectedConversationSignature=conversationSignature(node);detailsEmpty.hidden=true;details.replaceChildren();
  const record=recordFor(node),preview=record?.conversation_preview||{},path=String(preview.agent_path||nodePath(node)||'').trim(),messages=Array.isArray(preview.messages)?preview.messages:[];
  const isRoot=nodeHasRootAuthority(node)||previewUsesRootRenderer(preview);
  const rounds=(isRoot?rootRounds(messages,path||'/root'):childRounds(messages,path)).map(round=>execweaveFillAssignedTask(round,node,isRoot));
  const tools=toolCallsFor(String(node.id||''));
  const communication=agentCommunicationHistory(node,messages);
  const appendTools=()=>{if(communication)details.appendChild(communication);if(tools)details.appendChild(card('Tools',tools))};
  if(!rounds.length){const fallback={cards:isRoot?[['Prompt',''],['Final response','']]:[['Task',''],['Thinking',''],['Response','']]};details.appendChild(roundView(rounds[0]||execweaveFillAssignedTask(fallback,node,isRoot)));appendTools();return true}
  // A subagent borrows the moment and the wording of the unique canonical root round
  // it belongs to. If root identity is ambiguous, the child keeps its own timestamp.
  const runs=isRoot?rounds:runRounds();
  const sameDay=sameDayRun(runs.length?runs:rounds);
  const naming=round=>{if(isRoot||round.label)return round;const parentRound=roundOf(round.start,runs);return{start:parentRound?.start||round.start,label:''}};
  const list=document.createElement('div');list.className='execweave-agent-rounds';
  const ordered=[...rounds].reverse(),state=foldStateFor(node);
  const newest=naming(ordered[0]);list.appendChild(foldedRound(ordered[0],clock(newest.start||ordered[0].start,sameDay),'Latest · '+(newest.label||''),state,true));
  for(const round of ordered.slice(1)){const named=naming(round);list.appendChild(foldedRound(round,clock(named.start||round.start,sameDay),named.label||'',state))}
  details.appendChild(list);appendTools();return true;
}
function graphNode(id){const core=window.__execweaveCore;if(!core)return null;const graph=core.getDisplayGraph?.()||core.getGraph?.()||{};return (graph.nodes||[]).find(node=>String(node?.id||'')===String(id||''))||null}
function syncSelection(){const selected=document.querySelector('.node.selected');if(!selected){rememberVisibleFoldState();selectedNode=null;selectedFoldNode=null;selectedConversationSignature='';return}const node=graphNode(selected.dataset.id);if(node)render(node);else selectedNode=null;if(!node)selectedConversationSignature=''}
function setEntries(next){
  const candidate=Array.isArray(next)?next:[];
  if(!selectedNode){entries=candidate;return}
  const previousSignature=selectedConversationSignature;entries=candidate;
  if(conversationSignature(selectedNode)!==previousSignature)render(selectedNode);
}
async function refresh(){if(window.__execweaveStaticMode||refreshing)return;refreshing=true;try{const headers={};if(window.__execweaveToken)headers['X-ExecWeave-Token']=window.__execweaveToken;const response=await fetch('/conversations.json',{cache:'no-store',headers});if(response.ok){const payload=await response.json();setEntries(payload?.entries)}}catch(_){}finally{refreshing=false}}
const nodes=document.getElementById('nodes');if(nodes)new MutationObserver(syncSelection).observe(nodes,{subtree:true,attributes:true,attributeFilter:['class']});
document.addEventListener('click',event=>{if(event.target.closest?.('.node'))setTimeout(()=>{syncSelection();refresh()},0)},true);
if(!window.__execweaveStaticMode)setInterval(()=>{if(selectedNode)refresh()},800);
const previous=window.__execweaveDashboard||{};window.__execweaveDashboard={...previous,onPayload(data){previous.onPayload?.(data);if(selectedNode)refresh()},onFinished(){previous.onFinished?.();if(selectedNode)refresh()}};
window.__execweaveAgentPanel={render,setEntries,refresh};
})();
""".strip().replace("/*EXECWEAVE_FOLD_STATE*/", FOLD_STATE_JS).replace(
    "/*EXECWEAVE_CHILD_POLICY*/",
    "\n".join(
        (
            DEFAULT_CHILD_ROUNDS_JS,
            CODEX_CHILD_ROUNDS_JS,
            ANTIGRAVITY_CHILD_ROUNDS_JS,
            CLAUDE_CHILD_ROUNDS_JS,
            OLLAMA_CHILD_ROUNDS_JS,
            CURSOR_CHILD_ROUNDS_JS,
            OPENCODE_CHILD_ROUNDS_JS,
        )
    ),
    1,
)


def inject_agent_panel(html: str) -> str:
    if "window.__execweaveAgentPanel" in html:
        return html
    html = html.replace("</style>", _AGENT_PANEL_CSS + "\n</style>", 1)
    marker = html.rfind("</script>")
    if marker < 0:
        raise RuntimeError("dashboard script seam changed")
    return html[:marker] + _AGENT_PANEL_JS + "\n" + html[marker:]
