from __future__ import annotations

# Ollama has no observed subagent Task contract. Records already reduce a
# cumulative request to the current user + assistant turn. The panel must not
# invent Task/Thinking folds.

OLLAMA_CHILD_ROUNDS_JS = r"""
function execweaveOllamaChildRounds(messages,path){
  const prompts=messages.filter(message=>isObserved(message)&&!isInjected(message)&&(String(message?.kind||'')==='user_message'||String(message?.sender||'')==='user')&&(!message?.recipient||String(message.recipient)===path));
  return windows(messages,prompts).map(window=>{
    const inside=window.messages;
    const finals=inside.filter(message=>isObserved(message)&&!isInjected(message)&&own(message,path)&&(String(message?.content_role||'')==='ollama_response_surface'||String(message?.kind||'').startsWith('assistant')));
    return{
      key:messageKey(window.opener),
      start:stampOf(window.opener),
      cards:[['Prompt',displayText(window.opener)],['Final response',displayText(finals.at(-1))]],
    };
  });
}
""".strip()
