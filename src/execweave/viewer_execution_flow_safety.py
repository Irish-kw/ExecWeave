from __future__ import annotations


_DIRECT_ASSIGN = "    ['ASSIGNED_AGENT_TASK','assign_agent_task'],\n"
_DIRECT_SUBTASK = "    ['REQUESTED_SUBTASK','assign_agent_task'],\n"
_ASSIGN_TARGET = "    ['assign_agent_task','ASSIGNED_AGENT_TASK'],"
_SAFE_ASSIGN_TARGET = "    ['assign_agent_task','TARGETED_AGENT'],"
_ACTION_NAME = """  const actionName=value=>{
    const text=String(value||'').trim().toLowerCase().replace(/[\\s-]+/g,'_');
    return ACTION_ALIASES.get(text)||null;
  };"""
_SAFE_ACTION_NAME = """  const actionName=value=>{
    const raw=value&&typeof value==='object'&&typeof value.type==='string'?value.type:value;
    const text=String(raw||'').trim().toLowerCase().replace(/[\\s-]+/g,'_');
    return ACTION_ALIASES.get(text)||null;
  };"""
_TOOL_RESOLVE = "        if(relation(edge)!=='USES_TOOL')continue;"
_SAFE_TOOL_RESOLVE = "        if(!['USES_TOOL','RESOLVED_TOOL'].includes(relation(edge)))continue;"
_TOOL_CONSUME = "          if(relation(edge)==='USES_TOOL')actionToolIds.add(edge.target);"
_SAFE_TOOL_CONSUME = "          if(['USES_TOOL','RESOLVED_TOOL'].includes(relation(edge)))actionToolIds.add(edge.target);"
_MODEL_ONLY_ACTIVATION = (
    "    if(!occurrences.length&&![...modelEventsByAgent.values()].some(list=>list.length))return display;"
)
_ACTION_ONLY_ACTIVATION = "    if(!occurrences.length)return display;"
_TARGETED_ACTIVATION = """    const resolvedOccurrences=occurrences.filter(occurrence=>occurrence.targets.size>0);
    if(!resolvedOccurrences.length)return display;"""
_WAIT_AWARE_ACTIVATION = """    const providerObservedEdge=edge=>{
      const evidence=attrsOf(edge);
      return edge?.viewer_only===true||Boolean(
        evidence.provider||evidence.evidence_source||evidence.attribution||
        evidence.provider_event||evidence.provider_event_type
      );
    };
    const spawnEdges=rawEdges.filter(edge=>
      providerObservedEdge(edge)&&['SPAWNED_AGENT','SPAWNED_SUBAGENT'].includes(relation(edge))&&
      agents.has(agentForAnchor(edge.source))&&agents.has(agentForAnchor(edge.target))
    );
    const terminalEdges=rawEdges.filter(edge=>
      providerObservedEdge(edge)&&['SUBAGENT_STOPPED','CLOSED_AGENT'].includes(relation(edge))
    );
    for(const occurrence of occurrences){
      if(occurrence.kind!=='wait_agent'||occurrence.targets.size)continue;
      const at=moment(occurrence.item);
      for(const spawn of spawnEdges){
        const owner=agentForAnchor(spawn.source),child=agentForAnchor(spawn.target);
        if(owner!==occurrence.owner||!child||child===owner||!momentLE(moment(spawn),at))continue;
        const ended=terminalEdges.some(edge=>{
          const r=relation(edge),a=agentForAnchor(edge.source),b=agentForAnchor(edge.target);
          const touches=r==='SUBAGENT_STOPPED'?a===child&&b===owner:a===owner&&b===child;
          return touches&&momentLE(moment(edge),at);
        });
        if(!ended)occurrence.targets.add(child);
      }
    }
    // The branch model answers "which model does this target agent belong to?".
    // Prefer a unanimous target-agent model context over the actor's current model.
    // This keeps old children under gpt-5.5 even if /root later switches to Luna.
    for(const occurrence of occurrences){
      if(!occurrence.targets.size)continue;
      const targetModels=new Set(
        [...occurrence.targets].map(target=>resolveModel(target,occurrence.item)).filter(Boolean)
      );
      if(targetModels.size===1)occurrence.modelId=[...targetModels][0];
    }
    const resolvedOccurrences=occurrences.filter(occurrence=>occurrence.targets.size>0);
    if(!resolvedOccurrences.length)return display;
    const flowKey=occurrence=>`${occurrence.owner}\\u0000${occurrence.kind}\\u0000${occurrence.modelId||''}`;
    const resolvedKeys=new Set(resolvedOccurrences.map(flowKey));
    // Once a group is justified by at least one resolved target, retain target-less
    // provider call occurrences from that same owner/model/action group as evidence.
    // This lets the projected action consume the original tool-call/tool definition
    // instead of drawing a second visual spawn/send/wait node beside it.
    const groupedOccurrences=occurrences.filter(occurrence=>
      occurrence.targets.size>0||resolvedKeys.has(flowKey(occurrence))
    );"""
_GROUP_LOOP = "    for(const occurrence of occurrences){"
_TARGETED_GROUP_LOOP = "    for(const occurrence of resolvedOccurrences){"
_EVIDENCE_GROUP_LOOP = "    for(const occurrence of groupedOccurrences){"
_EAGER_CONTEXTS = """    for(const [owner,list] of modelEventsByAgent){
      for(const modelId of new Set(list.map(item=>item.modelId)))ensureContext(owner,modelId);
    }

"""
_DIRECT_ACTION_LOOP = """    for(const edge of rawEdges){
      const kind=DIRECT_ACTION_RELATIONS.get(relation(edge));
      if(!kind)continue;
      const owner=agentForAnchor(edge.source),target=agentForAnchor(edge.target);
      if(owner&&target&&owner!==target)pushOccurrence(kind,owner,[target],edge,[],[edge.id].filter(Boolean));
    }"""
_SAFE_DIRECT_ACTION_LOOP = """    for(const edge of rawEdges){
      const kind=DIRECT_ACTION_RELATIONS.get(relation(edge));
      if(!kind)continue;
      const evidence=attrsOf(edge);
      const providerObserved=edge.viewer_only===true||Boolean(
        evidence.provider||evidence.evidence_source||evidence.attribution||
        evidence.provider_event||evidence.provider_event_type
      );
      if(!providerObserved)continue;
      const owner=agentForAnchor(edge.source),target=agentForAnchor(edge.target);
      if(owner&&target&&owner!==target)pushOccurrence(kind,owner,[target],edge,[],[edge.id].filter(Boolean));
    }"""


def harden_execution_flow_projection(html: str) -> str:
    """Fail closed on ambiguous or evidence-poor execution-flow projection.

    A model context is shown only for orchestration that resolves to real target agents.
    The target agents' evidenced model context is authoritative when all resolved targets
    agree; the actor model is only a fallback. Explicit targets are preferred.
    Target-less ``wait_agent`` calls may use the provider-evidenced active-child set:
    children spawned before the wait and without stop/close evidence before that wait.
    Once an action group has real targets, target-less call evidence from the same
    owner/model/action is folded into that single viewer action so the raw collaboration
    tool is not rendered as a duplicate. Provider tool-call vocabularies ``USES_TOOL``
    and ``RESOLVED_TOOL`` are equivalent call-to-tool support for this presentation-only
    consumption step. Bare tool names and ambiguous provider subtask/profile evidence
    never rewrite the main hierarchy.
    """

    for unsafe in (_DIRECT_ASSIGN, _DIRECT_SUBTASK):
        if unsafe not in html:
            raise RuntimeError("execution-flow assignment safety seam changed")
        html = html.replace(unsafe, "", 1)
    if _ASSIGN_TARGET not in html:
        raise RuntimeError("execution-flow assignment target seam changed")
    html = html.replace(_ASSIGN_TARGET, _SAFE_ASSIGN_TARGET, 1)

    if _ACTION_NAME not in html:
        raise RuntimeError("execution-flow tagged action-name seam changed")
    html = html.replace(_ACTION_NAME, _SAFE_ACTION_NAME, 1)
    if _TOOL_RESOLVE not in html or _TOOL_CONSUME not in html:
        raise RuntimeError("execution-flow tool-resolution seam changed")
    html = html.replace(_TOOL_RESOLVE, _SAFE_TOOL_RESOLVE, 1)
    html = html.replace(_TOOL_CONSUME, _SAFE_TOOL_CONSUME, 1)

    if _MODEL_ONLY_ACTIVATION not in html:
        raise RuntimeError("execution-flow activation seam changed")
    html = html.replace(_MODEL_ONLY_ACTIVATION, _ACTION_ONLY_ACTIVATION, 1)
    if _ACTION_ONLY_ACTIVATION not in html:
        raise RuntimeError("execution-flow targeted activation seam changed")
    html = html.replace(_ACTION_ONLY_ACTIVATION, _TARGETED_ACTIVATION, 1)
    if _TARGETED_ACTIVATION not in html:
        raise RuntimeError("execution-flow wait target seam changed")
    html = html.replace(_TARGETED_ACTIVATION, _WAIT_AWARE_ACTIVATION, 1)

    if _GROUP_LOOP not in html:
        raise RuntimeError("execution-flow resolved occurrence seam changed")
    html = html.replace(_GROUP_LOOP, _TARGETED_GROUP_LOOP, 1)
    if _TARGETED_GROUP_LOOP not in html:
        raise RuntimeError("execution-flow evidence merge seam changed")
    html = html.replace(_TARGETED_GROUP_LOOP, _EVIDENCE_GROUP_LOOP, 1)

    if _EAGER_CONTEXTS not in html:
        raise RuntimeError("execution-flow eager model-context seam changed")
    html = html.replace(_EAGER_CONTEXTS, "", 1)

    if _DIRECT_ACTION_LOOP not in html:
        raise RuntimeError("execution-flow direct action evidence seam changed")
    return html.replace(_DIRECT_ACTION_LOOP, _SAFE_DIRECT_ACTION_LOOP, 1)
