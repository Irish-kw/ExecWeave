"""Lossless, presentation-only composition through hidden evidence details.

Only explicit incoming paths terminating at one visible agent justify composition.
Ambiguous/unattributed observations retain their original source as a visible context;
raw degree-zero nodes and deliberate file filters are never 'repaired' by deletion.
"""

PROJECTION_SCRIPT = r"""
(function(){
  const baseProjection=execweaveDashboardGraph;
  const hiddenTypes=new Set([
    'agent_execution','observed_content','tool_call','agent_turn','tool_call_observation',
    'conversation_item','provider_session','permission_request','context_compaction',
    'agent_turn_stop','compaction','compaction_request','terminal_operation',
    'agent_trace_capability','session','command','inference_call','code_cell','agent_message'
  ]);
  const text=value=>value===null||value===undefined?'':String(value).trim();
  const key=edge=>text(edge.id)||JSON.stringify([edge.source,edge.relation,edge.target]);
  const copy=value=>JSON.parse(JSON.stringify(value));
  const sorted=values=>[...new Set(values)].sort();
  function scope(value){
    const a=value?.attributes||{};
    return{
      provider:text(a.provider||value?.provider).toLowerCase(),
      conversation:text(a.conversation_id||a.antigravity_conversation_id||value?.conversation_id),
      session:text(a.provider_session_id||a.session_id),
      run:text(a.execweave_session_id||a.run_id)
    };
  }
  function joinScope(a,b){
    const result={...a};
    for(const [name,value] of Object.entries(b)){
      if(value&&result[name]&&value!==result[name])return null;
      if(value)result[name]=value;
    }
    return result;
  }
  function supportFor(leaf,visible,byId,incoming){
    const sources=new Set(),edges=new Map([[key(leaf),leaf]]),nodes=new Set([leaf.source,leaf.target]);
    const initial=joinScope(scope(leaf),scope(byId.get(leaf.source)));
    if(!initial)return{sources:[],edges:[leaf],nodes:[...nodes],reason:'identity_conflict'};
    const queue=[[leaf.source,initial]],seen=new Set();let reason='';
    for(let index=0;index<queue.length;index++){
      const [id,identity]=queue[index],state=JSON.stringify([id,identity]);
      if(seen.has(state))continue;seen.add(state);
      for(const edge of incoming.get(id)||[]){
        const source=byId.get(edge.source);
        if(!source){reason='missing_source';continue;}
        const joined=joinScope(identity,scope(edge));
        const next=joined&&joinScope(joined,scope(source));
        if(!next){reason='identity_conflict';continue;}
        edges.set(key(edge),edge);nodes.add(edge.source);
        if(visible.has(source.id)){
          if(source.type==='agent')sources.add(source.id);
          else reason=reason||'non_agent_boundary';
        }else if(hiddenTypes.has(String(source.type||''))){
          queue.push([source.id,next]);
        }else{
          reason=reason||'hidden_or_filtered_owner';
        }
      }
    }
    return{sources:sorted(sources),edges:[...edges.values()].sort((a,b)=>key(a).localeCompare(key(b))),
      nodes:sorted(nodes),reason:reason||(sources.size===1?'':sources.size?'ambiguous_ancestry':'unattributed_observation')};
  }
  function repair(data,display){
    const rawNodes=Array.isArray(data?.nodes)?data.nodes:[],rawEdges=Array.isArray(data?.edges)?data.edges:[];
    const byId=new Map(rawNodes.filter(n=>n?.id).map(n=>[n.id,n])),incoming=new Map();
    for(const edge of rawEdges){
      if(!edge?.source||!edge?.target)continue;
      if(!incoming.has(edge.target))incoming.set(edge.target,[]);
      incoming.get(edge.target).push(edge);
    }
    const nodes=[...(display.nodes||[])],edges=[...(display.edges||[])];
    const visible=new Set(nodes.map(n=>n.id)),aliases=new Map(),groups=new Map(),contexts=new Map();
    for(const node of nodes){
      aliases.set(node.id,node.id);
      const a=node.attributes||{};
      const members=[...(a.viewer_occurrence_ids||[]),...(a.viewer_tool_entity_ids||[]),
        ...(a.viewer_folded_members||[]).map(n=>n.id)];
      for(const id of members)if(byId.has(id)&&byId.get(id)?.type!=='agent')aliases.set(id,node.id);
    }
    const represented=new Set(edges.flatMap(edge=>[edge.id,...(edge.viewer_edge_occurrence_ids||[])]).filter(Boolean));
    const unresolved=[];
    for(const leaf of [...rawEdges].sort((a,b)=>key(a).localeCompare(key(b)))){
      if(leaf?.id&&represented.has(leaf.id))continue;
      const target=aliases.get(leaf?.target),source=byId.get(leaf?.source);
      if(!target||!source||visible.has(source.id)||!hiddenTypes.has(String(source.type||'')))continue;
      const support=supportFor(leaf,visible,byId,incoming);
      if(support.reason){
        // Keep the original source and incident relation. This is not a guessed
        // agent edge: the context exposes why an observation cannot be attributed.
        if(!contexts.has(source.id))contexts.set(source.id,{...copy(source),
          attributes:{...copy(source.attributes||{}),viewer_retained_context:true,
            viewer_context_reason:support.reason,viewer_original_name:source.name||null}});
        unresolved.push({source:source.id,target:leaf.target,reason:support.reason,ancestor_ids:support.sources});
        edges.push({...copy(leaf),target,viewer_only:true,
          viewer_original_target:leaf.target,viewer_retained_context_edge:true});
        continue;
      }
      const owner=support.sources[0],groupKey=JSON.stringify([owner,leaf.relation||'',target]);
      if(!groups.has(groupKey))groups.set(groupKey,{owner,target,relation:leaf.relation||'',leaves:[],supports:[]});
      const group=groups.get(groupKey);group.leaves.push(leaf);group.supports.push(support);
    }
    for(const [groupKey,group] of [...groups].sort(([a],[b])=>a.localeCompare(b))){
      const leaf=group.leaves[0],supportEdges=new Map();
      for(const support of group.supports)for(const edge of support.edges)supportEdges.set(key(edge),edge);
      const evidence=[...supportEdges.values()].sort((a,b)=>key(a).localeCompare(key(b)));
      const hiddenSources=sorted(group.leaves.map(e=>e.source));
      const nodeIds=sorted(group.supports.flatMap(s=>s.nodes));
      const sequences=group.leaves.map(e=>e.first_sequence).filter(Number.isInteger);
      const lastSequences=group.leaves.map(e=>e.last_sequence).filter(Number.isInteger);
      const moments=field=>group.leaves.map(e=>e[field]).filter(v=>text(v)).sort((a,b)=>{
        const x=Date.parse(a),y=Date.parse(b);return Number.isFinite(x)&&Number.isFinite(y)?x-y:text(a).localeCompare(text(b));
      });
      const first=moments('first_seen'),last=moments('last_seen');
      edges.push({...copy(leaf),id:`viewer:hidden-bridge:${groupKey}`,source:group.owner,target:group.target,
        relation:group.relation,viewer_only:true,inferred:true,causal:false,
        attributes:{...copy(leaf.attributes||{}),inferred:true,causal:false},
        count:group.leaves.reduce((n,e)=>n+(Number(e.count)||1),0),
        first_sequence:sequences.length?Math.min(...sequences):null,
        last_sequence:lastSequences.length?Math.max(...lastSequences):null,
        first_seen:first[0]||null,last_seen:last.at(-1)||null,
        evidence_ids:sorted(evidence.flatMap(e=>Array.isArray(e.evidence_ids)?e.evidence_ids:[])),
        viewer_hidden_bridge:true,viewer_hidden_bridge_reason:'unique_visible_agent_ancestor',
        viewer_hidden_bridge_source:hiddenSources[0],viewer_hidden_bridge_sources:hiddenSources,
        viewer_original_targets:sorted(group.leaves.map(e=>e.target)),
        viewer_supporting_edges:copy(evidence),
        viewer_supporting_nodes:nodeIds.filter(id=>byId.has(id)).map(id=>copy(byId.get(id))),
        viewer_supporting_paths:group.leaves.map((e,i)=>({hidden_source:e.source,target:e.target,
          edge_ids:group.supports[i].edges.map(key),node_ids:group.supports[i].nodes}))});
    }
    nodes.push(...[...contexts.values()].sort((a,b)=>text(a.id).localeCompare(text(b.id))));
    const ids=new Set(nodes.map(n=>n.id));
    const keptEdges=edges.filter(e=>ids.has(e.source)&&ids.has(e.target));
    return{...display,nodes,edges:keptEdges,node_count:nodes.length,edge_count:keptEdges.length,
      dashboard_projection:{...(display.dashboard_projection||{}),hidden_bridge_edge_count:groups.size,
        retained_context_node_count:contexts.size,unresolved_hidden_paths:unresolved,
        removed_projection_orphan_count:0,removed_projection_orphan_ids:[]}};
  }
  execweaveDashboardGraph=data=>repair(data,baseProjection(data));
  if(typeof window!=='undefined')window.__execweaveProjectionRepair=repair;
})();
""".strip()
