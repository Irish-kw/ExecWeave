from __future__ import annotations

# Codex-only child Task/Thinking/Response. Do not copy this into default or other
# providers. Assignments are often kind=user_message from parent path to child path.

CODEX_CHILD_ROUNDS_JS = r"""
function execweaveCodexChildRounds(messages,path){
  const parent=path.includes('/')?(path.slice(0,path.lastIndexOf('/'))||'/root'):'/root';
  const childMessages=messages.filter(message=>{
    const sender=String(message?.sender||'');
    const recipient=String(message?.recipient||'');
    return !(sender==='user'&&recipient==='/root');
  });
  const isTask=message=>{
    const sender=String(message?.sender||'');
    const kind=String(message?.kind||'');
    const phase=String(message?.phase||'');
    const recipient=String(message?.recipient||'');
    if(sender==='user'&&recipient==='/root')return false;
    return isObserved(message)&&!isInjected(message)&&recipient===path&&sender!==path&&(!sender||sender==='user'||sender===parent)&&(kind==='user_message'||kind==='new_task'||/task|assign/i.test(kind)||phase==='assignment');
  };
  const openers=childMessages.filter(isTask);
  return windows(childMessages,openers).map(window=>{
    const inside=window.messages;
    const thoughts=inside.filter(message=>isObserved(message)&&!isInjected(message)&&own(message,path)&&(/reason|think|commentary/i.test(`${message?.kind||''} ${message?.phase||''}`)));
    let responses=inside.filter(message=>isObserved(message)&&!isInjected(message)&&own(message,path)&&(String(message?.phase||'')==='final_answer'||/subagent_final_response|final[_ -]?response/i.test(String(message?.kind||''))));
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
