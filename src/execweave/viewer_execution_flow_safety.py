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
_PROVIDER_HELPER = "  const provider=node=>String(attrsOf(node).provider||'unknown').toLowerCase();"
_SAFE_PROVIDER_HELPER = """  const provider=node=>String(attrsOf(node).provider||'unknown').toLowerCase();
  const providerObservedEdge=edge=>{
    const evidence=attrsOf(edge);
    const eventTypes=Array.isArray(edge?.event_types)?edge.event_types:[];
    const backends=Array.isArray(edge?.backends)?edge.backends:[];
    const attributions=Array.isArray(edge?.attributions)?edge.attributions:[];
    const lifecycle=Array.isArray(edge?.provider_lifecycle)?edge.provider_lifecycle:[];
    return edge?.viewer_only===true||Boolean(
      evidence.provider||evidence.evidence_source||evidence.attribution||
      evidence.provider_event||evidence.provider_event_type||
      lifecycle.length||attributions.length||
      backends.some(value=>String(value).toLowerCase()==='semantic')||
      eventTypes.some(value=>String(value).toLowerCase().startsWith('semantic.'))
    );
  };"""
_OWNER_FOR_NODE = """    const uniqueOwner=candidates=>{
      const ids=[...new Set((candidates||[]).filter(Boolean))];
      return ids.length===1?ids[0]:null;
    };
    const ownerForNode=node=>{
      if(!node?.id)return null;
      const direct=[];
      for(const edge of incoming.get(node.id)||[])if(agents.has(edge.source))direct.push(edge.source);
      const directOwner=uniqueOwner(direct);
      if(directOwner)return directOwner;
      if(direct.length)return null; // ambiguous direct owners
      const viaTurn=[];
      for(const edge of incoming.get(node.id)||[]){
        const parent=rawById.get(edge.source);
        if(parent?.type!=='agent_turn')continue;
        for(const grand of incoming.get(parent.id)||[])if(agents.has(grand.source))viaTurn.push(grand.source);
      }
      const turnOwner=uniqueOwner(viaTurn);
      if(turnOwner)return turnOwner;
      if(viaTurn.length)return null;
      const attrs=attrsOf(node);
      const attrOwners=[];
      for(const key of ['owner_agent_id','agent_id','source_agent_id','thread_id','agent_path']){
        const found=resolveAgent(attrs[key]);if(found)attrOwners.push(found);
      }
      return uniqueOwner(attrOwners);
    };"""
_SAFE_OWNER_FOR_NODE = """    const uniqueOwner=candidates=>{
      const ids=[...new Set((candidates||[]).filter(Boolean))];
      return ids.length===1?ids[0]:null;
    };
    const ownerForNode=node=>{
      if(!node?.id)return null;
      const candidates=new Set();
      for(const edge of incoming.get(node.id)||[])if(agents.has(edge.source))candidates.add(edge.source);
      for(const edge of incoming.get(node.id)||[]){
        const parent=rawById.get(edge.source);
        if(parent?.type!=='agent_turn')continue;
        for(const grand of incoming.get(parent.id)||[])if(agents.has(grand.source))candidates.add(grand.source);
      }
      const attrs=attrsOf(node);
      for(const key of ['owner_agent_id','agent_id','source_agent_id','thread_id','agent_path']){
        const found=resolveAgent(attrs[key]);if(found)candidates.add(found);
      }
      return candidates.size===1?[...candidates][0]:null;
    };"""
_MODEL_EDGE_LOOP = """    for(const edge of rawEdges){
      if(!agents.has(edge?.source)||!models.has(edge?.target)||!MODEL_RELATIONS.has(relation(edge)))continue;
      addModelEvent(edge.source,edge.target,edge);
    }"""
_SAFE_MODEL_EDGE_LOOP = """    for(const edge of rawEdges){
      if(!models.has(edge?.target)||!MODEL_RELATIONS.has(relation(edge))||!providerObservedEdge(edge))continue;
      const owner=agentForAnchor(edge.source);
      if(owner)addModelEvent(owner,edge.target,edge);
    }"""
_MODEL_FILTER = "      if(contextifiedModels.has(edge.target)&&agents.has(edge.source)&&modelRelation(edge))return false;"
_SAFE_MODEL_FILTER = "      if(contextifiedModels.has(edge.target)&&agentForAnchor(edge.source)&&modelRelation(edge))return false;"
_TOOL_RESOLVE = "        if(relation(edge)!=='USES_TOOL')continue;"
_SAFE_TOOL_RESOLVE = "        if(!['USES_TOOL','RESOLVED_TOOL'].includes(relation(edge)))continue;"
_TOOL_CONSUME = "      const uses=(incoming.get(toolId)||[]).filter(edge=>['USES_TOOL','RESOLVED_TOOL'].includes(relation(edge)));"
_SAFE_TOOL_CONSUME = "      const uses=(incoming.get(toolId)||[]).filter(edge=>['USES_TOOL','RESOLVED_TOOL'].includes(relation(edge)));"
_MODEL_ONLY_ACTIVATION = (
    "    if(!occurrences.length&&![...modelEventsByAgent.values()].some(list=>list.length))return display;"
)
_ACTION_ONLY_ACTIVATION = "    if(!occurrences.length)return display;"
_TARGETED_ACTIVATION = """    const resolvedOccurrences=occurrences.filter(occurrence=>occurrence.targets.size>0);
    if(!resolvedOccurrences.length)return display;"""
_WAIT_AWARE_ACTIVATION = """    const spawnEdges=rawEdges.filter(edge=>
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
      // Child model lookup ignores the actor tool-call/item hint. Only the child's
      // own model evidence may win, and every target must share one known model.
      const targetModels=[];
      let allKnown=true;
      for(const target of occurrence.targets){
        const modelId=resolveModel(target,null);
        if(!modelId){allKnown=false;break}
        targetModels.push(modelId);
      }
      const unique=new Set(targetModels);
      if(allKnown&&unique.size===1)occurrence.modelId=[...unique][0];
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
_GROUP_BLOCK_START = """    const groups=new Map();
    for(const occurrence of occurrences){"""
_EVIDENCE_GROUP_BLOCK_START = """    const groups=new Map();
    for(const occurrence of groupedOccurrences){"""
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
      if(!kind||!providerObservedEdge(edge))continue;
      const owner=agentForAnchor(edge.source),target=agentForAnchor(edge.target);
      if(owner&&target&&owner!==target)pushOccurrence(kind,owner,[target],edge,[],[edge.id].filter(Boolean));
    }

    // Some providers expose delegation as an exact two-edge chain rather than a
    // direct parent -> child spawn edge: requester -> subtask -> assigned child.
    // Project that chain only when both endpoints are unique and the provider has
    // supplied exact child linkage. This admits real Antigravity/Cursor evidence
    // while continuing to abstain on profile-only or otherwise ambiguous subtasks.
    // The raw subtask and child-session edges remain embedded evidence; they are
    // merely superseded on the main canvas by the single action path.
    const exactAssignmentRelation=['ASSIGNED','AGENT','TASK'].join('_');
    const exactDelegationEdge=edge=>edge?.identity_exact===true||attrsOf(edge).identity_exact===true;
    const seenDelegationSubtasks=new Set();
    for(const assignmentSeed of rawEdges){
      if(relation(assignmentSeed)!==exactAssignmentRelation||!providerObservedEdge(assignmentSeed))continue;
      const subtask=rawById.get(assignmentSeed.source);
      if(subtask?.type!=='subtask'||seenDelegationSubtasks.has(subtask.id))continue;
      seenDelegationSubtasks.add(subtask.id);
      const assignments=(outgoing.get(subtask.id)||[]).filter(edge=>
        relation(edge)===exactAssignmentRelation&&providerObservedEdge(edge)
      );
      const assignmentTargetList=assignments.map(edge=>agentForAnchor(edge.target));
      // Unknown endpoints must fail closed: filter(Boolean) would invent uniqueness.
      if(assignmentTargetList.some(value=>!value))continue;
      const assignmentTargets=new Set(assignmentTargetList);
      if(assignmentTargets.size!==1)continue;
      const target=[...assignmentTargets][0];
      const requests=(incoming.get(subtask.id)||[]).filter(edge=>
        relation(edge)==='REQUESTED_SUBTASK'&&providerObservedEdge(edge)
      );
      const requestOwnerList=requests.map(edge=>agentForAnchor(edge.source));
      if(requestOwnerList.some(value=>!value))continue;
      const requestOwners=new Set(requestOwnerList);
      if(requestOwners.size!==1)continue;
      const owner=[...requestOwners][0];
      if(!owner||!target||owner===target)continue;
      // Explicit identity_exact=false on any request/assignment rejects the chain.
      if([...requests,...assignments].some(edge=>edge?.identity_exact===false||attrsOf(edge).identity_exact===false))continue;
      const subtaskExact=attrsOf(subtask).exact_child_agent_linkage===true;
      if(!subtaskExact&&!(requests.length&&assignments.length&&requests.every(exactDelegationEdge)&&assignments.every(exactDelegationEdge)))continue;
      const scopedProviders=[provider(agents.get(owner)),provider(agents.get(target)),provider(subtask)]
        .filter(value=>value&&value!=='unknown');
      if(new Set(scopedProviders).size>1)continue;
      const childSessionEdges=rawEdges.filter(edge=>
        relation(edge)==='HAS_CHILD_AGENT_SESSION'&&providerObservedEdge(edge)&&
        agentForAnchor(edge.source)===owner&&agentForAnchor(edge.target)===target
      );
      const evidenceEdges=[...requests,...assignments,...childSessionEdges];
      pushOccurrence(
        'assign_agent_task',owner,[target],assignmentSeed,[subtask.id],
        evidenceEdges.map(edge=>edge.id).filter(Boolean)
      );
    }

    // A provider can also expose the exact child directly from an owner-bound tool
    // call. Keep the generic assignment relation disabled: only an exact materialized
    // identity edge plus a unique call owner and real agent target can enter the flow.
    for(const assignment of rawEdges){
      if(relation(assignment)!==exactAssignmentRelation||!providerObservedEdge(assignment)||!exactDelegationEdge(assignment))continue;
      const anchor=rawById.get(assignment.source);
      if(anchor?.type!=='tool_call')continue;
      const owner=agentForAnchor(anchor.id),target=agentForAnchor(assignment.target);
      if(!owner||!target||owner===target)continue;
      const scopedProviders=[provider(agents.get(owner)),provider(agents.get(target)),provider(anchor)]
        .filter(value=>value&&value!=='unknown');
      if(new Set(scopedProviders).size>1)continue;
      const supportEdges=[
        ...(incoming.get(anchor.id)||[]).filter(edge=>
          relation(edge)==='REQUESTED_TOOL_CALL'&&providerObservedEdge(edge)&&agentForAnchor(edge.source)===owner
        ),
        ...(outgoing.get(anchor.id)||[]).filter(edge=>
          ['USES_TOOL','RESOLVED_TOOL'].includes(relation(edge))&&providerObservedEdge(edge)
        ),
        assignment,
      ];
      pushOccurrence(
        'assign_agent_task',owner,[target],assignment,[anchor.id],
        supportEdges.map(edge=>edge.id).filter(Boolean)
      );
    }"""
_HIERARCHY_PARENT_ONLY = "      if(group.kind!=='spawn_agent')continue;"
_HIERARCHY_PARENT_SAFE = "      if(!['spawn_agent','assign_agent_task'].includes(group.kind))continue;"
_HIERARCHY_RANK_ONLY = "        if(group.kind!=='spawn_agent'||!agentRank.has(group.owner))continue;"
_HIERARCHY_RANK_SAFE = "        if(!['spawn_agent','assign_agent_task'].includes(group.kind)||!agentRank.has(group.owner))continue;"
_FLOW_EARLY_RETURN = "    if(ranked.length<2)return topo;"
_FLOW_SAFE_EARLY_RETURN = """    const finalizeFlowGeometry=()=>{
      const previousTopology=execweaveTopology;
      execweaveTopology=topo;
      try{
        // This is the final layout wrapper in the shared Dashboard. Re-run the
        // hard no-overlap gate after execution-flow X columns (or even when no
        // flow ranks exist), because a later presentation column move must never
        // invalidate Layout V2's earlier geometry guarantees.
        if(typeof execweaveSeparateOverlappingNodes==='function')execweaveSeparateOverlappingNodes({spec:topo.spec});
        const placement=new Map([...topo.spec].map(([id,spec])=>[id,{x:spec.x,y:spec.y}]));
        if(typeof execweaveLayoutV2SyncFinalOrder==='function')execweaveLayoutV2SyncFinalOrder(topo,placement);
        if(typeof execweaveRecomputePorts==='function')execweaveRecomputePorts(topo);
      }finally{execweaveTopology=previousTopology}
      return topo;
    };
    if(ranked.length<2)return finalizeFlowGeometry();"""
_FLOW_END = """    if(typeof execweaveRecomputePorts==='function')execweaveRecomputePorts(topo);
    return topo;
  }
  window.execweaveApplyExecutionFlowColumns=execweaveApplyExecutionFlowColumns;"""
_FLOW_SAFE_END = """    return finalizeFlowGeometry();
  }
  window.execweaveApplyExecutionFlowColumns=execweaveApplyExecutionFlowColumns;"""


def harden_execution_flow_projection(html: str) -> str:
    """Fail closed on ambiguous or evidence-poor execution-flow projection.

    A model context is shown only for orchestration that resolves to real target agents.
    The target agents' evidenced model context is authoritative when all resolved targets
    agree; the actor model is only a fallback. Explicit targets are preferred.
    Target-less ``wait_agent`` calls may use the provider-evidenced active-child set:
    children spawned before the wait and without stop/close evidence before that wait.
    Exact requester -> subtask -> assigned-child chains and exact owner-bound tool-call
    assignments are accepted when provider evidence proves a unique owner and child;
    ambiguous/profile-only subtasks and non-exact assignments still fail closed.
    Once an action group has real targets, target-less call evidence from the same
    owner/model/action is folded into that single viewer action so the raw collaboration
    tool is not rendered as a duplicate. Provider tool-call vocabularies ``USES_TOOL``
    and ``RESOLVED_TOOL`` are equivalent call-to-tool support for this presentation-only
    consumption step. Bare tool names never rewrite the main hierarchy. Final execution-
    flow columns re-run the hard node-overlap gate and port/order synchronization.
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
    if _PROVIDER_HELPER not in html:
        raise RuntimeError("execution-flow provider evidence seam changed")
    html = html.replace(_PROVIDER_HELPER, _SAFE_PROVIDER_HELPER, 1)
    if _OWNER_FOR_NODE not in html:
        raise RuntimeError("execution-flow owner uniqueness seam changed")
    html = html.replace(_OWNER_FOR_NODE, _SAFE_OWNER_FOR_NODE, 1)
    if _MODEL_EDGE_LOOP not in html:
        raise RuntimeError("execution-flow model ownership seam changed")
    html = html.replace(_MODEL_EDGE_LOOP, _SAFE_MODEL_EDGE_LOOP, 1)
    if _MODEL_FILTER not in html:
        raise RuntimeError("execution-flow contextified-model filter seam changed")
    html = html.replace(_MODEL_FILTER, _SAFE_MODEL_FILTER, 1)

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

    # Anchor the evidence-group replacement on ``const groups``. Matching the bare
    # loop text is unsafe because the wait/model-resolution block intentionally has
    # earlier ``for(const occurrence of occurrences)`` loops of its own.
    if _GROUP_BLOCK_START not in html:
        raise RuntimeError("execution-flow evidence grouping seam changed")
    html = html.replace(_GROUP_BLOCK_START, _EVIDENCE_GROUP_BLOCK_START, 1)

    if _EAGER_CONTEXTS not in html:
        raise RuntimeError("execution-flow eager model-context seam changed")
    html = html.replace(_EAGER_CONTEXTS, "", 1)

    if _DIRECT_ACTION_LOOP not in html:
        raise RuntimeError("execution-flow direct action evidence seam changed")
    html = html.replace(_DIRECT_ACTION_LOOP, _SAFE_DIRECT_ACTION_LOOP, 1)

    if html.count(_HIERARCHY_PARENT_ONLY) != 1 or html.count(_HIERARCHY_RANK_ONLY) != 1:
        raise RuntimeError("execution-flow hierarchy action seam changed")
    html = html.replace(_HIERARCHY_PARENT_ONLY, _HIERARCHY_PARENT_SAFE, 1)
    html = html.replace(_HIERARCHY_RANK_ONLY, _HIERARCHY_RANK_SAFE, 1)

    if html.count(_FLOW_EARLY_RETURN) != 1 or html.count(_FLOW_END) != 1:
        raise RuntimeError("execution-flow final geometry seam changed")
    html = html.replace(_FLOW_EARLY_RETURN, _FLOW_SAFE_EARLY_RETURN, 1)
    return html.replace(_FLOW_END, _FLOW_SAFE_END, 1)