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
_MODEL_ONLY_ACTIVATION = (
    "    if(!occurrences.length&&![...modelEventsByAgent.values()].some(list=>list.length))return display;"
)
_ACTION_ONLY_ACTIVATION = "    if(!occurrences.length)return display;"
_TARGETED_ACTIVATION = """    const resolvedOccurrences=occurrences.filter(occurrence=>occurrence.targets.size>0);
    if(!resolvedOccurrences.length)return display;"""
_GROUP_LOOP = "    for(const occurrence of occurrences){"
_TARGETED_GROUP_LOOP = "    for(const occurrence of resolvedOccurrences){"
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

    A model context is shown only for a real orchestration occurrence with at least one
    resolved target agent. Bare tool names, bare topology fixtures, and ambiguous
    subtask/profile evidence remain available in raw/inspector evidence but cannot
    rewrite the main execution hierarchy. Tagged provider enums are normalized before
    action matching so Codex-style ``{"type": ...}`` kinds are handled losslessly.
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

    if _MODEL_ONLY_ACTIVATION not in html:
        raise RuntimeError("execution-flow activation seam changed")
    html = html.replace(_MODEL_ONLY_ACTIVATION, _ACTION_ONLY_ACTIVATION, 1)
    if _ACTION_ONLY_ACTIVATION not in html:
        raise RuntimeError("execution-flow targeted activation seam changed")
    html = html.replace(_ACTION_ONLY_ACTIVATION, _TARGETED_ACTIVATION, 1)

    if _GROUP_LOOP not in html:
        raise RuntimeError("execution-flow resolved occurrence seam changed")
    html = html.replace(_GROUP_LOOP, _TARGETED_GROUP_LOOP, 1)

    if _EAGER_CONTEXTS not in html:
        raise RuntimeError("execution-flow eager model-context seam changed")
    html = html.replace(_EAGER_CONTEXTS, "", 1)

    if _DIRECT_ACTION_LOOP not in html:
        raise RuntimeError("execution-flow direct action evidence seam changed")
    return html.replace(_DIRECT_ACTION_LOOP, _SAFE_DIRECT_ACTION_LOOP, 1)
