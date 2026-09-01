from __future__ import annotations

# Codex-only child Task/Thinking/Response. Do not copy this into default or other
# providers. Assignments are often kind=user_message from parent path to child path.

CODEX_CHILD_ROUNDS_JS = r"""
function execweaveCodexChildRounds(messages,path){
  const parent=path.includes('/')?(path.slice(0,path.lastIndexOf('/'))||'/root'):'/root';
  const isTask=message=>{
    const sender=String(message?.sender||'');
    const kind=String(message?.kind||'');
    const phase=String(message?.phase||'');
    return isObserved(message)&&!isInjected(message)&&String(message?.recipient||'')===path&&sender!==path&&(!sender||sender==='user'||sender===parent)&&(kind==='user_message'||/task|assign/i.test(kind)||phase==='assignment');
  };
  const openers=messages.filter(isTask);
  return windows(messages,openers).map(window=>{
    const inside=window.messages;
    const thoughts=inside.filter(message=>isObserved(message)&&!isInjected(message)&&own(message,path)&&(/reason|think|commentary/i.test(`${message?.kind||''} ${message?.phase||''}`)));
    let responses=inside.filter(message=>isObserved(message)&&!isInjected(message)&&own(message,path)&&(String(message?.phase||'')==='final_answer'||/subagent_final_response|final[_ -]?response/i.test(String(message?.kind||''))));
    if(!responses.length)responses=inside.filter(message=>isObserved(message)&&!isInjected(message)&&own(message,path)&&!thoughts.includes(message)&&String(message?.recipient||'')!==path&&!/task|assign|user_message/i.test(String(message?.kind||'')));
    return{
      key:messageKey(window.opener),
      start:stampOf(window.opener),
      cards:[['Task',displayText(window.opener)],['Thinking',uniqueTexts(thoughts).join('\n\n')],['Response',displayText(responses.at(-1))]],
    };
  });
}
""".strip()
