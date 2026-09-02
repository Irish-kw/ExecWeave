from __future__ import annotations

# Antigravity-only child rounds. Tasks come from invoke/send_message projection
# (kind=task / subagent_task / assignment), not Codex user_message.

ANTIGRAVITY_CHILD_ROUNDS_JS = r"""
function execweaveAntigravityChildRounds(messages,path){
  const parent=path.includes('/')?(path.slice(0,path.lastIndexOf('/'))||'/root'):'/root';
  const isTask=message=>{
    const sender=String(message?.sender||'');
    const kind=String(message?.kind||'');
    const phase=String(message?.phase||'');
    const role=String(message?.content_role||'');
    return isObserved(message)&&!isInjected(message)&&String(message?.recipient||'')===path&&sender!==path&&(!sender||sender==='user'||sender===parent||sender.startsWith('antigravity:'))&&(role==='antigravity_addressed_task'||kind==='subagent_task'||kind==='send_message'||(/task|assign/i.test(kind)&&kind!=='user_message')||phase==='assignment');
  };
  const openers=messages.filter(isTask);
  return windows(messages,openers).map(window=>{
    const inside=window.messages;
    const thoughts=inside.filter(message=>isObserved(message)&&!isInjected(message)&&own(message,path)&&(/reason|think|commentary/i.test(`${message?.kind||''} ${message?.phase||''}`))&&String(message?.phase||'')!=='planner_response');
    let responses=inside.filter(message=>isObserved(message)&&!isInjected(message)&&own(message,path)&&(String(message?.phase||'')==='planner_response'||String(message?.phase||'')==='final_answer'||/subagent_final_response|final[_ -]?response/i.test(String(message?.kind||''))));
    if(!responses.length)responses=inside.filter(message=>isObserved(message)&&!isInjected(message)&&own(message,path)&&!thoughts.includes(message)&&String(message?.recipient||'')!==path&&!/task|assign|send_message/i.test(String(message?.kind||'')));
    return{
      key:messageKey(window.opener),
      start:stampOf(window.opener),
      cards:[['Task',displayText(window.opener)],['Thinking',uniqueTexts(thoughts).join('\n\n')],['Response',displayText(responses.at(-1))]],
    };
  });
}
""".strip()
