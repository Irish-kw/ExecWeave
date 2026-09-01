from __future__ import annotations

# Current shared child Task/Thinking/Response rules. Phase 1 copies this verbatim;
# provider modules must call it rather than changing isTask here.

DEFAULT_CHILD_ROUNDS_JS = r"""
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
      cards:[['Task',displayText(spoken||window.opener)],['Thinking',uniqueTexts(thoughts).join('\n\n')],['Response',displayText(responses.at(-1))]],
    };
  });
}
""".strip()
