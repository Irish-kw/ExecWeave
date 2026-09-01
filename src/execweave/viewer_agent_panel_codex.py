from __future__ import annotations

# Codex-only child Task/Thinking/Response. Do not copy this into default or other
# providers. Assignments are often kind=user_message from parent path to child path.
# A first spawn often emits task (assignment) and new_task for the same job; that
# pair is one round. A later new_task after a child response starts another round.

CODEX_CHILD_ROUNDS_JS = r"""
function execweaveCodexChildRounds(messages,path){
  const parent=path.includes('/')?(path.slice(0,path.lastIndexOf('/'))||'/root'):'/root';
  const childMessages=messages.filter(message=>{
    const sender=String(message?.sender||'');
    const recipient=String(message?.recipient||'');
    return !(sender==='user'&&recipient==='/root');
  });
  const isTaskCandidate=message=>{
    const sender=String(message?.sender||'');
    const kind=String(message?.kind||'');
    const phase=String(message?.phase||'');
    const recipient=String(message?.recipient||'');
    if(sender==='user'&&recipient==='/root')return false;
    return isObserved(message)&&!isInjected(message)&&recipient===path&&sender!==path&&(!sender||sender==='user'||sender===parent)&&(kind==='user_message'||kind==='new_task'||/task|assign/i.test(kind)||phase==='assignment');
  };
  const isChildResponse=message=>isObserved(message)&&!isInjected(message)&&own(message,path)&&(String(message?.phase||'')==='final_answer'||/subagent_final_response|final[_ -]?response/i.test(String(message?.kind||'')));
  const isTask=(message,index,list)=>{
    if(!isTaskCandidate(message))return false;
    if(String(message?.kind||'')!=='new_task')return true;
    for(let cursor=index-1;cursor>=0;cursor--){
      const previous=list[cursor];
      if(isChildResponse(previous))return true;
      if(isTaskCandidate(previous))return false;
    }
    return true;
  };
  const openers=childMessages.filter(isTask);
  return windows(childMessages,openers).map(window=>{
    const inside=window.messages;
    const thoughts=inside.filter(message=>isObserved(message)&&!isInjected(message)&&own(message,path)&&(/reason|think|commentary/i.test(`${message?.kind||''} ${message?.phase||''}`)));
    let responses=inside.filter(message=>isChildResponse(message));
    if(!responses.length)responses=inside.filter(message=>isObserved(message)&&!isInjected(message)&&own(message,path)&&!thoughts.includes(message)&&String(message?.recipient||'')!==path&&!/task|assign|user_message|new_task/i.test(String(message?.kind||'')));
    const taskText=displayText(window.opener);
    return{
      key:messageKey(window.opener),
      start:stampOf(window.opener),
      label:taskText?summarise(taskText):'Task',
      cards:[['Task',taskText],['Thinking',uniqueTexts(thoughts).join('\n\n')],['Response',displayText(responses.at(-1))]],
    };
  });
}
""".strip()
