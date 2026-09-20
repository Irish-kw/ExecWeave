from __future__ import annotations

# Shared child Task/Thinking/Response selection. Framework terminal notes are
# additive; provider modules continue to share the existing assignment rules.

DEFAULT_CHILD_ROUNDS_JS = r"""
function execweaveFrameworkTerminalCards(cards,inside,path,response){
  // Interpret the recorded text, not framework completion or task correctness.
  // Restrict the additive excerpt to one exact framework source; do not reuse
  // the inspector's legacy name/path fallback as ownership evidence.
  const node=typeof selectedNode==='undefined'?null:selectedNode;
  if(node?.type!=='agent'||attrs(node).conversation_scope!=='framework_agent'||
     !['autogen','camel','metagpt'].includes(String(attrs(node).framework||attrs(node).provider||'').toLowerCase()))return cards;
  const raw=typeof rawGraph==='function'?rawGraph():{};
  if((Array.isArray(raw.nodes)?raw.nodes:[]).filter(n=>n?.id===node.id).length!==1)return cards;
  const exact=(Array.isArray(entries)?entries:[]).filter(e=>e?.source_id===node.id&&e.conversation_preview);
  if(!exact.length||exact.some(e=>e.conversation_preview.agent_path!==path))return cards;
  const nativeIds=new Set(exact.map(e=>e.conversation_preview.provider_native_id).filter(Boolean));
  if(nativeIds.size>1)return cards;
  const kinds=new Set(['agent_message','agent_result','subagent_final_response']);
  const outgoing=m=>m&&m.sender===path&&m.recipient!==path&&kinds.has(m.kind)&&
    !['request','received','assignment','candidate'].includes(m.phase)&&
    !isEncrypted(m)&&!isInjected(m)&&isObserved(m);
  const marker=m=>m?.text_truncated!==true&&['TERMINATE','<CAMEL_TASK_DONE>'].includes(messageText(m));
  // The selected Response may be a normalized model response rather than a
  // routed message (the default SDK shape in the original CAMEL/AutoGen runs).
  // Annotating its displayed text does not establish that it was sent. Keep
  // outgoing() unchanged for the earlier-message excerpt below.
  const modelResponseText=response?.kind==='assistant_message'&&response.phase==='response'&&
    response.sender===path&&(response.recipient==null||response.recipient==='')&&
    !isEncrypted(response)&&!isInjected(response)&&isObserved(response);
  if((!outgoing(response)&&!modelResponseText)||!marker(response))return cards;
  const at=inside.indexOf(response);if(at<0)return cards;
  // Generic assistant records can be replayed model-request context. Without
  // per-record provenance they are not substituted for an outgoing message.
  const earlier=inside.slice(0,at).filter(m=>outgoing(m)&&
    !['TERMINATE','<CAMEL_TASK_DONE>'].includes(messageText(m))).at(-1);
  const extra=[];
  if(earlier)extra.push(['Earlier observed message',displayText(earlier)]);
  extra.push(['Response interpretation',
    'Termination-marker text match only; not a verified task result. The reported response is preserved below. '+
    (earlier?'The earlier outgoing-message preview is not a replacement final answer. ':'No earlier eligible outgoing message is present in this displayed window. ')+
    'Use Browse observed history for timing, other records and preview limits.']);
  const responseIndex=cards.findIndex(c=>c[0]==='Response');
  return responseIndex<0?cards:[...cards.slice(0,responseIndex),...extra,...cards.slice(responseIndex)];
}
function execweaveDefaultChildRounds(messages,path){
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
      key:messageKey(window.opener),
      start:stampOf(window.opener),
      cards:execweaveFrameworkTerminalCards([['Task',displayText(spoken||window.opener)],['Thinking',uniqueTexts(thoughts).join('\n\n')],['Response',displayText(responses.at(-1))]],inside,path,responses.at(-1)),
    };
  });
}
""".strip()
