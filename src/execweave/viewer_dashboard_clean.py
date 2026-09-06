from __future__ import annotations

import argparse
import os

# How many nodes of one foldable type stay drawn before the older ones collapse.
# Twelve is a starting point, not a measurement: the runs this was built against
# touch a handful of files. A deployment that writes hundreds will want its own
# number, so the value is a setting rather than a constant.
DEFAULT_FOLD_BUDGET = 12
FOLD_BUDGET_ENV = "EXECWEAVE_FOLD_BUDGET"


def resolve_fold_budget(raw: str | None = None) -> int:
    """Read the budget a run was started with, falling back to the default.

    The command line validates its own value and refuses a bad one there, where the
    user can see it. This function is called while rendering, often at the end of a
    long run, so an unusable environment value falls back rather than costing the
    reader the viewer.
    """
    value = os.environ.get(FOLD_BUDGET_ENV) if raw is None else raw
    if value is None:
        return DEFAULT_FOLD_BUDGET
    try:
        budget = int(str(value).strip())
    except ValueError:
        return DEFAULT_FOLD_BUDGET
    return budget if budget >= 1 else DEFAULT_FOLD_BUDGET


def fold_budget_option(value: str) -> int:
    """Parse --fold-budget, refusing a value the reader would not understand."""
    try:
        budget = int(str(value).strip())
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"fold budget must be a whole number, not {value!r}"
        ) from None
    if budget < 1:
        raise argparse.ArgumentTypeError(
            f"fold budget must be at least 1, not {budget}; a large value effectively "
            "turns folding off"
        )
    return budget


def add_fold_budget_argument(parser: argparse.ArgumentParser) -> None:
    """Offer the budget on any command that renders a dashboard."""
    parser.add_argument(
        "--fold-budget",
        type=fold_budget_option,
        default=None,
        metavar="N",
        help=(
            "How many nodes of one crowded type stay drawn before the older ones "
            f"collapse into a single node that still lists them (default: "
            f"{DEFAULT_FOLD_BUDGET}). Set it high to effectively turn folding off. "
            f"Also readable from {FOLD_BUDGET_ENV}."
        ),
    )


def apply_fold_budget(budget: int | None) -> None:
    """Publish the chosen budget so every renderer in this run agrees on it.

    The value travels in the environment rather than through each render call: a run
    resolves one budget, the renderers are reached from several entry points, and top
    launches the live server as a child process that has to agree with its parent.
    """
    if budget is not None:
        os.environ[FOLD_BUDGET_ENV] = str(int(budget))


def fold_budget_bootstrap(budget: int | None = None) -> str:
    """The one statement a rendered page needs so its fold budget is the run's."""
    resolved = resolve_fold_budget() if budget is None else budget
    return f"window.__execweaveFoldBudget={int(resolved)};"


_DASHBOARD_JS = r"""
function execweaveDashboardGraph(data){
  const allNodes=Array.isArray(data?.nodes)?data.nodes:[],allEdges=Array.isArray(data?.edges)?data.edges:[];
  const allById=new Map(allNodes.filter(node=>node&&node.id).map(node=>[node.id,node]));
  const hiddenTypes=new Set(['agent_execution','observed_content','tool_call','agent_turn','tool_call_observation','conversation_item','provider_session','permission_request','context_compaction','agent_turn_stop','compaction','compaction_request','terminal_operation']);
  const hiddenDetailIds=new Set(allNodes.filter(node=>node&&hiddenTypes.has(String(node.type||''))).map(node=>node.id).filter(Boolean));
  const internalStaging=node=>{
    const type=String(node?.type||'');
    if(type!=='file'&&type!=='directory')return false;
    const attrs=node?.attributes||{},values=[node?.name,attrs.path,attrs.file_path,attrs.source_path,attrs.target_path,attrs.real_path];
    return values.some(value=>/(^|[\\/])\.execweave-content-[^\\/]+$/.test(String(value||'')));
  };
  const internalStagingIds=new Set(allNodes.filter(node=>node&&internalStaging(node)).map(node=>node.id).filter(Boolean));
  const hiddenIds=new Set([...hiddenDetailIds,...internalStagingIds]);
  const incoming=new Map(),outgoing=new Map();
  for(const edge of allEdges){
    if(!edge)continue;
    if(!incoming.has(edge.target))incoming.set(edge.target,[]);
    if(!outgoing.has(edge.source))outgoing.set(edge.source,[]);
    incoming.get(edge.target).push(edge);outgoing.get(edge.source).push(edge);
  }
  const provider=node=>String(node?.attributes?.provider||'unknown').toLowerCase();
  const toolName=node=>String(node?.attributes?.tool_name||node?.attributes?.native_name||node?.name||'tool');
  const toolKey=node=>`${provider(node)}\u0000${toolName(node).trim().toLowerCase()}`;
  const toolNodesByKey=new Map();
  for(const node of allNodes){
    if(node?.type!=='tool'||!node.id)continue;
    const key=toolKey(node);if(!toolNodesByKey.has(key))toolNodesByKey.set(key,[]);toolNodesByKey.get(key).push(node);
  }
  const toolCanonicalId=new Map(),toolRepresentativeByKey=new Map(),toolMembersByRepresentative=new Map();
  for(const [key,members] of toolNodesByKey){
    members.sort((a,b)=>String(a.id).localeCompare(String(b.id)));
    const representative=members[0];toolRepresentativeByKey.set(key,representative.id);toolMembersByRepresentative.set(representative.id,members);
    for(const member of members)toolCanonicalId.set(member.id,representative.id);
  }
  const attrsOf=node=>node&&typeof node.attributes==='object'&&node.attributes?node.attributes:{};
  const callConversation=call=>{
    const attrs=attrsOf(call),direct=attrs.conversation_id||attrs.antigravity_conversation_id||attrs.session_id||attrs.provider_session_id;
    if(direct!==null&&direct!==undefined&&String(direct).trim())return String(direct).trim();
    const match=String(call?.id||'').match(/^tool-call(?:-observation)?:antigravity:([^:]+):/i);
    return match?match[1]:'';
  };
  function ownerFor(call){
    const edges=incoming.get(call.id)||[];
    for(const edge of edges){const source=allById.get(edge.source);if(source?.type==='agent')return edge.source}
    for(const edge of edges){
      const turn=allById.get(edge.source);if(turn?.type!=='agent_turn')continue;
      for(const parent of incoming.get(edge.source)||[]){const source=allById.get(parent.source);if(source?.type==='agent')return parent.source}
    }
    const conversation=callConversation(call);
    if(conversation){
      const exact=`agent:antigravity:conversation:${conversation}`;
      if(allById.has(exact))return exact;
    }
    for(const edge of edges){
      const source=allById.get(edge.source);
      if(source&&!hiddenTypes.has(String(source.type||''))&&source.type!=='tool')return edge.source;
    }
    return null;
  }
  function toolFor(call){
    for(const edge of outgoing.get(call.id)||[]){
      const target=allById.get(edge.target);
      if(target?.type==='tool')return toolCanonicalId.get(target.id)||target.id;
    }
    return toolRepresentativeByKey.get(toolKey(call))||null;
  }
  const seq=(edge,key)=>Number.isInteger(edge?.[key])?edge[key]:null;
  const earlier=(a,b)=>!a?b:!b?a:(String(a)<=String(b)?a:b);
  const later=(a,b)=>!a?b:!b?a:(String(a)>=String(b)?a:b);
  const firstValue=(attrs,keys)=>{for(const key of keys){if(attrs[key]!==undefined&&attrs[key]!==null)return attrs[key]}return null};
  const callIdentity=call=>{
    const attrs=attrsOf(call),native=firstValue(attrs,['tool_use_id','tool_call_id','call_id','provider_call_id','invocation_id']);
    if(native!==null&&String(native).trim())return `${provider(call)}\u0000native\u0000${String(native)}`;
    const conversation=callConversation(call),step=firstValue(attrs,['step_index','antigravity_step_index','stepIdx']);
    if(conversation&&step!==null&&step!==undefined)return `${provider(call)}\u0000conversation-step\u0000${conversation}\u0000${step}\u0000${toolName(call).toLowerCase()}`;
    return `${provider(call)}\u0000id\u0000${call.id}`;
  };
  const adjacentContent=call=>{
    const rows=[];
    for(const edge of [...(incoming.get(call.id)||[]),...(outgoing.get(call.id)||[])]){
      const otherId=edge.source===call.id?edge.target:edge.source,other=allById.get(otherId);
      if(other?.type!=='observed_content')continue;
      const attrs=attrsOf(other);
      rows.push({relation:edge.relation||null,content_kind:attrs.content_kind||other.name||null,sha256:attrs.sha256||attrs.content_sha256||null,path:attrs.path||attrs.content_path||null,size_bytes:attrs.size_bytes??attrs.content_size_bytes??null,media_type:attrs.media_type||attrs.content_media_type||null});
    }
    return rows;
  };
  const toolCallToTool=new Map(),invocationMap=new Map();
  for(const call of allNodes){
    if(!['tool_call','tool_call_observation'].includes(String(call?.type||''))||!call.id)continue;
    const owner=ownerFor(call),tool=toolFor(call);if(!owner||!tool)continue;
    toolCallToTool.set(call.id,tool);
    const key=`${owner}\u0000${tool}\u0000${callIdentity(call)}`,attrs=attrsOf(call),evidence=[...(incoming.get(call.id)||[]),...(outgoing.get(call.id)||[])];
    let occurrence=invocationMap.get(key);
    if(!occurrence){
      occurrence={invocation_id:callIdentity(call),owner_id:owner,tool_id:tool,call_ids:[],first_sequence:null,last_sequence:null,first_seen:call.first_seen||null,last_seen:call.last_seen||null,input:null,output:null,content_references:[]};
      invocationMap.set(key,occurrence);
    }
    if(!occurrence.call_ids.includes(call.id))occurrence.call_ids.push(call.id);
    occurrence.first_seen=earlier(occurrence.first_seen,call.first_seen);occurrence.last_seen=later(occurrence.last_seen,call.last_seen);
    if(occurrence.input===null)occurrence.input=firstValue(attrs,['arguments','args','tool_input','input','parameters','request']);
    if(occurrence.output===null)occurrence.output=firstValue(attrs,['output','result','tool_output','response']);
    for(const edge of evidence){
      const first=seq(edge,'first_sequence'),last=seq(edge,'last_sequence');
      if(first!==null)occurrence.first_sequence=occurrence.first_sequence===null?first:Math.min(occurrence.first_sequence,first);
      if(last!==null)occurrence.last_sequence=occurrence.last_sequence===null?last:Math.max(occurrence.last_sequence,last);
      occurrence.first_seen=earlier(occurrence.first_seen,edge.first_seen);occurrence.last_seen=later(occurrence.last_seen,edge.last_seen);
    }
    for(const ref of adjacentContent(call))if(!occurrence.content_references.some(item=>JSON.stringify(item)===JSON.stringify(ref)))occurrence.content_references.push(ref);
  }
  const groups=new Map(),toolOccurrences=new Map();
  for(const occurrence of invocationMap.values()){
    const key=`${occurrence.owner_id}\u0000${occurrence.tool_id}`;
    let group=groups.get(key);if(!group){group={owner:occurrence.owner_id,tool:occurrence.tool_id,count:0,first_sequence:null,last_sequence:null,first_seen:null,last_seen:null,occurrences:[]};groups.set(key,group)}
    group.occurrences.push(occurrence);group.count+=1;
    if(occurrence.first_sequence!==null)group.first_sequence=group.first_sequence===null?occurrence.first_sequence:Math.min(group.first_sequence,occurrence.first_sequence);
    if(occurrence.last_sequence!==null)group.last_sequence=group.last_sequence===null?occurrence.last_sequence:Math.max(group.last_sequence,occurrence.last_sequence);
    group.first_seen=earlier(group.first_seen,occurrence.first_seen);group.last_seen=later(group.last_seen,occurrence.last_seen);
    if(!toolOccurrences.has(occurrence.tool_id))toolOccurrences.set(occurrence.tool_id,[]);toolOccurrences.get(occurrence.tool_id).push(occurrence);
  }
  const occurrenceOrder=(a,b)=>{
    if(a.first_sequence!==null&&b.first_sequence!==null&&a.first_sequence!==b.first_sequence)return a.first_sequence-b.first_sequence;
    const byTime=String(a.first_seen||'').localeCompare(String(b.first_seen||''));return byTime||String(a.invocation_id).localeCompare(String(b.invocation_id));
  };
  for(const group of groups.values())group.occurrences.sort(occurrenceOrder);
  for(const list of toolOccurrences.values())list.sort(occurrenceOrder);
  let visibleNodes=allNodes.filter(node=>node&&node.id&&!hiddenIds.has(node.id)).filter(node=>node.type!=='tool'||toolCanonicalId.get(node.id)===node.id).map(node=>{
    if(node.type!=='tool')return node;
    const occurrences=toolOccurrences.get(node.id)||[],members=toolMembersByRepresentative.get(node.id)||[node];
    if(!occurrences.length&&members.length===1)return node;
    const firstSeen=members.reduce((value,item)=>earlier(value,item.first_seen),node.first_seen||null),lastSeen=members.reduce((value,item)=>later(value,item.last_seen),node.last_seen||null);
    return{...node,first_seen:firstSeen||node.first_seen,last_seen:lastSeen||node.last_seen,attributes:{...(node.attributes||{}),viewer_canonicalized:members.length>1||undefined,viewer_occurrence_count:occurrences.length,viewer_occurrence_ids:occurrences.map(item=>item.invocation_id),viewer_occurrences:occurrences,viewer_tool_call_occurrences:occurrences,viewer_aggregated_tool_call_count:occurrences.length,viewer_tool_entity_ids:members.map(item=>item.id)}};
  });

  const canonicalTypes=new Set(['process','file']);
  const foldableTypes=new Set(['process','file','network_endpoint']);
  const declaredBudget=Number(globalThis.__execweaveFoldBudget);
  const FOLD_BUDGET=Number.isFinite(declaredBudget)&&declaredBudget>=1?Math.floor(declaredBudget):12;
  const canonicalGroups=new Map();
  const canonicalKey=node=>{
    const type=String(node?.type||'');
    if(!canonicalTypes.has(type))return `id\u0000${node.id}`;
    const name=String(node?.name||'').trim().toLowerCase();
    return name?`${type}\u0000${name}`:`id\u0000${node.id}`;
  };
  for(const node of visibleNodes){const key=canonicalKey(node);if(!canonicalGroups.has(key))canonicalGroups.set(key,[]);canonicalGroups.get(key).push(node)}
  const canonicalId=new Map(toolCanonicalId);
  const nodes=[];
  let canonicalizedProcessOccurrenceCount=0;
  for(const group of canonicalGroups.values()){
    group.sort((a,b)=>String(a.first_seen||'').localeCompare(String(b.first_seen||''))||String(a.id).localeCompare(String(b.id)));
    const base=group[0];
    for(const item of group)canonicalId.set(item.id,base.id);
    if(group.length===1){nodes.push(base);continue}
    canonicalizedProcessOccurrenceCount+=group.length-1;
    const occurrenceRows=group.map(item=>{
      const attrs=item.attributes||{};
      return{id:item.id,first_seen:item.first_seen||null,last_seen:item.last_seen||null,pid:attrs.pid??attrs.process_id??null,ppid:attrs.ppid??attrs.parent_pid??null};
    });
    const pids=[...new Set(occurrenceRows.map(item=>item.pid).filter(value=>value!==null&&value!==undefined))];
    const ppids=[...new Set(occurrenceRows.map(item=>item.ppid).filter(value=>value!==null&&value!==undefined))];
    const firstSeen=group.reduce((value,item)=>earlier(value,item.first_seen),null),lastSeen=group.reduce((value,item)=>later(value,item.last_seen),null);
    nodes.push({...base,first_seen:firstSeen||base.first_seen,last_seen:lastSeen||base.last_seen,attributes:{...(base.attributes||{}),viewer_canonicalized:true,viewer_occurrence_count:group.length,viewer_occurrence_ids:group.map(item=>item.id),viewer_occurrences:occurrenceRows,viewer_pids:pids,viewer_ppids:ppids}});
  }

  let foldedNodeCount=0;
  const byType=new Map();
  for(const node of nodes){const type=String(node?.type||'');if(!foldableTypes.has(type))continue;if(!byType.has(type))byType.set(type,[]);byType.get(type).push(node)}
  const folds=[];
  for(const[type,members]of byType){
    if(members.length<=FOLD_BUDGET)continue;
    const recency=node=>String(node?.last_seen||node?.first_seen||'');
    const ordered=[...members].sort((a,b)=>recency(b).localeCompare(recency(a)));
    const older=ordered.slice(FOLD_BUDGET);if(!older.length)continue;
    const keep=new Set(ordered.slice(0,FOLD_BUDGET).map(node=>node.id));
    const foldId=`viewer:folded:${type}`;
    for(const node of older)canonicalId.set(node.id,foldId);
    foldedNodeCount+=older.length;
    folds.push({id:foldId,type,name:`${older.length} earlier ${type.replace(/_/g,' ')}${older.length===1?'':'s'}`,first_seen:older.reduce((value,node)=>earlier(value,node.first_seen),null),last_seen:older.reduce((value,node)=>later(value,node.last_seen),null),attributes:{viewer_folded:true,viewer_folded_type:type,viewer_folded_count:older.length,viewer_folded_members:older.map(node=>({id:node.id,name:node.name||node.id,first_seen:node.first_seen||null,last_seen:node.last_seen||null}))}});
    for(let index=nodes.length-1;index>=0;index--)if(!keep.has(nodes[index].id)&&String(nodes[index].type||'')===type)nodes.splice(index,1);
  }
  nodes.push(...folds);

  let nodeIds=new Set(nodes.map(node=>node.id));
  let edges=allEdges.map(edge=>{
    if(!edge)return null;
    const declaredTool=edge.relation==='DECLARED_TARGET'?toolCallToTool.get(edge.source):null;
    const rawSource=declaredTool||edge.source;
    const source=canonicalId.get(rawSource)||rawSource,target=canonicalId.get(edge.target)||edge.target;
    if(!nodeIds.has(source)||!nodeIds.has(target))return null;
    if(source===edge.source&&target===edge.target)return edge;
    return{...edge,source,target,viewer_canonicalized:true,viewer_original_source:edge.source,viewer_original_target:edge.target,viewer_reanchored_from_tool_call:rawSource!==edge.source||undefined};
  }).filter(Boolean);
  for(const group of groups.values()){
    const owner=canonicalId.get(group.owner)||group.owner,tool=canonicalId.get(group.tool)||group.tool;
    if(!nodeIds.has(owner)||!nodeIds.has(tool))continue;
    edges.push({id:`viewer:${owner}--CALLED_TOOL-->${tool}`,source:owner,target:tool,relation:'CALLED_TOOL',count:group.count,first_sequence:group.first_sequence,last_sequence:group.last_sequence,first_seen:group.first_seen,last_seen:group.last_seen,causal:null,inferred:false,viewer_only:true,attributions:['viewer_tool_call_aggregation'],evidence_call_count:group.count,viewer_tool_call_occurrences:group.occurrences});
  }
  const incident=new Set();for(const edge of edges){incident.add(edge.source);incident.add(edge.target)}
  visibleNodes=nodes.filter(node=>node.type!=='tool'||incident.has(node.id));
  nodeIds=new Set(visibleNodes.map(node=>node.id));edges=edges.filter(edge=>nodeIds.has(edge.source)&&nodeIds.has(edge.target));
  return{...data,nodes:visibleNodes,edges,node_count:visibleNodes.length,edge_count:edges.length,dashboard_projection:{hidden_detail_node_count:hiddenDetailIds.size,hidden_internal_staging_node_count:internalStagingIds.size,canonicalized_process_occurrence_count:canonicalizedProcessOccurrenceCount,canonicalized_tool_entity_count:[...toolMembersByRepresentative.values()].reduce((sum,members)=>sum+Math.max(0,members.length-1),0),folded_node_count:foldedNodeCount,collapsed_tool_call_count:invocationMap.size,raw_tool_call_detail_count:allNodes.filter(node=>['tool_call','tool_call_observation'].includes(String(node?.type||''))).length}};
}
""".strip()

_STATIC_MATERIALIZED = """function materializedGraph(){
  const hiddenClusterEdges=new Set();
  expandedClusters.forEach(id=>{const entry=expansionClusters[id];if(entry&&entry.cluster_edge_id)hiddenClusterEdges.add(entry.cluster_edge_id)});
  let nodes=baseNodes.filter(node=>!expandedClusters.has(node.id));
  let edges=baseEdges.filter(edge=>!hiddenClusterEdges.has(edge.id));
  expandedClusters.forEach(id=>{const entry=expansionClusters[id];if(!entry)return;nodes=nodes.concat(entry.nodes||[]);edges=edges.concat(entry.edges||[])});
  return{nodes:uniqueById(nodes),edges:uniqueById(edges)};
}"""

_STATIC_MATERIALIZED_CLEAN = """function materializedGraph(){
  const hiddenClusterEdges=new Set();
  expandedClusters.forEach(id=>{const entry=expansionClusters[id];if(entry&&entry.cluster_edge_id)hiddenClusterEdges.add(entry.cluster_edge_id)});
  let nodes=baseNodes.filter(node=>!expandedClusters.has(node.id));
  let edges=baseEdges.filter(edge=>!hiddenClusterEdges.has(edge.id));
  expandedClusters.forEach(id=>{const entry=expansionClusters[id];if(!entry)return;nodes=nodes.concat(entry.nodes||[]);edges=edges.concat(entry.edges||[])});
  return execweaveDashboardGraph({nodes:uniqueById(nodes),edges:uniqueById(edges)});
}"""

_STATIC_TYPE_OPTIONS = "[...new Set(possibleNodes.map(n=>n.type).filter(Boolean))].sort().forEach(v=>option(typeFilter,v));\n[...new Set(possibleEdges.map(e=>e.relation).filter(Boolean))].sort().forEach(v=>option(relationFilter,v));"
_STATIC_TYPE_OPTIONS_CLEAN = "const execweavePossibleGraph=execweaveDashboardGraph({nodes:possibleNodes,edges:possibleEdges});\n[...new Set(execweavePossibleGraph.nodes.map(n=>n.type).filter(Boolean))].sort().forEach(v=>option(typeFilter,v));\n[...new Set(execweavePossibleGraph.edges.map(e=>e.relation).filter(Boolean))].sort().forEach(v=>option(relationFilter,v));"

_LIVE_SET_SNAPSHOT_CLEAN = "function setSnapshot(data){const signature=`${data.node_count||0}:${data.edge_count||0}`;lastSignature=signature;graph=data;const display=execweaveDashboardGraph(data);nodeById=new Map((display.nodes||[]).map(n=>[n.id,n]));edgeById=new Map((display.edges||[]).map(e=>[edgeId(e),e]));rebuildAdjacency();updateStats({...data,node_count:display.node_count,edge_count:display.edge_count});if(!withinRenderBudget(display)){enterProtectiveMode(display);return}renderSnapshot();seedActivities();const sortedEdges=[...edgeById.values()].sort((a,b)=>String(a.last_seen||'').localeCompare(String(b.last_seen||''))),sortedNodes=[...nodeById.values()].sort((a,b)=>String(a.last_seen||'').localeCompare(String(b.last_seen||''))),lastEdge=sortedEdges.length?sortedEdges[sortedEdges.length-1]:null,lastNode=sortedNodes.length?sortedNodes[sortedNodes.length-1]:null;markLatest(lastEdge?.target||lastNode?.id||null,lastEdge?edgeId(lastEdge):null);if(!hasFitted&&positions.size){fit(false);hasFitted=true}else scheduleCamera(true)}"

_LIVE_APPLY_DELTA_CLEAN = "function applyDelta(update){if(update.live_payload_compact){updateStats(update);enterProtectiveMode(update);return}const rawNodes=new Map((graph.nodes||[]).map(n=>[n.id,n])),rawEdges=new Map((graph.edges||[]).map(e=>[edgeId(e),e]));for(const node of [...(update.nodes_added||[]),...(update.nodes_updated||[])])if(node?.id)rawNodes.set(node.id,node);for(const edge of [...(update.edges_added||[]),...(update.edges_updated||[])])rawEdges.set(edgeId(edge),edge);graph={...graph,event_count:update.event_count,node_count:update.node_count,edge_count:update.edge_count,nodes:[...rawNodes.values()],edges:[...rawEdges.values()]};const display=execweaveDashboardGraph(graph);updateStats({...update,node_count:display.node_count,edge_count:display.edge_count});if(!withinRenderBudget(display)){enterProtectiveMode(display);return}if(protectedMode)leaveProtectiveMode();nodeById=new Map((display.nodes||[]).map(n=>[n.id,n]));edgeById=new Map((display.edges||[]).map(e=>[edgeId(e),e]));rebuildAdjacency();renderSnapshot();seedActivities();const sortedEdges=[...edgeById.values()].sort((a,b)=>String(a.last_seen||'').localeCompare(String(b.last_seen||''))),sortedNodes=[...nodeById.values()].sort((a,b)=>String(a.last_seen||'').localeCompare(String(b.last_seen||''))),lastEdge=sortedEdges.length?sortedEdges[sortedEdges.length-1]:null,lastNode=sortedNodes.length?sortedNodes[sortedNodes.length-1]:null;markLatest(lastEdge?.target||lastNode?.id||null,lastEdge?edgeId(lastEdge):null);scheduleCamera(false);if(!hasFitted&&positions.size){fit(false);hasFitted=true}}"

_LIVE_CORE_EXPORT = "window.__execweaveCore={getActivities:()=>activities.slice(),getGraph:()=>graph,getPositions:()=>new Map(positions),selectEdge,selectNode,focusNode,markLatest,setCameraMode};"
_LIVE_CORE_EXPORT_CLEAN = "window.__execweaveCore={getActivities:()=>activities.slice(),getGraph:()=>graph,getDisplayGraph:()=>({...graph,nodes:[...nodeById.values()],edges:[...edgeById.values()],node_count:nodeById.size,edge_count:edgeById.size}),getPositions:()=>new Map(positions),selectEdge,selectNode,focusNode,markLatest,setCameraMode};"

_LIVE_NOOP_STATS = "else if(data.kind==='noop'){liveSequence=Number(data.sequence)||liveSequence;updateStats(data);}"
_LIVE_NOOP_STATS_CLEAN = "else if(data.kind==='noop'){liveSequence=Number(data.sequence)||liveSequence;updateStats(protectedMode?data:{...data,node_count:nodeById.size,edge_count:edgeById.size});}"


def _replace_function(html: str, start: str, following: str, replacement: str) -> str:
    begin = html.find(start)
    if begin < 0:
        return html
    end = html.find(following, begin)
    if end < 0:
        return html
    return html[:begin] + replacement + html[end:]


def inject_standalone_dashboard_clean(html: str) -> str:
    """Keep full evidence embedded while simplifying only the SVG canvas graph."""
    marker = "function uniqueById(values){"
    if "function execweaveDashboardGraph(data){" not in html and marker in html:
        html = html.replace(marker, _DASHBOARD_JS + "\n" + marker, 1)
    html = html.replace(_STATIC_MATERIALIZED, _STATIC_MATERIALIZED_CLEAN, 1)
    html = html.replace(_STATIC_TYPE_OPTIONS, _STATIC_TYPE_OPTIONS_CLEAN, 1)
    return html.replace("execweavePreferAgentView();", "", 1)


def inject_live_dashboard_clean(html: str) -> str:
    """Simplify only the browser canvas; the live JSON protocol remains unchanged."""
    marker = "function renderSnapshot(){"
    if "function execweaveDashboardGraph(data){" not in html and marker in html:
        html = html.replace(marker, _DASHBOARD_JS + "\n" + marker, 1)
    html = _replace_function(
        html,
        "function setSnapshot(data){",
        "function mergeById(",
        _LIVE_SET_SNAPSHOT_CLEAN + "\n",
    )
    html = _replace_function(
        html,
        "function applyDelta(update){",
        "function applyTransform(){",
        _LIVE_APPLY_DELTA_CLEAN + "\n",
    )
    # Static viewer deltas rerender the graph, but an incoming upstream node
    # must not vertically re-pack unrelated existing nodes. Preserve their Y
    # coordinates while allowing semantic lane X shifts.
    html = html.replace(
        "if(protectedMode)leaveProtectiveMode();nodeById=new Map((display.nodes||[]).map(n=>[n.id,n]));",
        "if(protectedMode)leaveProtectiveMode();const priorY=new Map([...positions].map(([id,p])=>[id,p.y]));nodeById=new Map((display.nodes||[]).map(n=>[n.id,n]));",
        1,
    )
    render_marker = "renderSnapshot();seedActivities();const sortedEdges="
    render_replacement = "renderSnapshot();for(const [id,y] of priorY){const p=positions.get(id);if(p&&Number.isFinite(y))p.y=y}if(typeof execweaveSeparateOverlappingNodes==='function')execweaveSeparateOverlappingNodes({spec:positions});for(const [id,p] of positions){const group=nodeElements.get(id);if(group)group.setAttribute('transform',`translate(${p.x} ${p.y})`)}for(const e of edgeById.values())updateEdgeElement(e);seedActivities();const sortedEdges="
    render_index = html.rfind(render_marker)
    if render_index >= 0:
        html = html[:render_index] + html[render_index:].replace(render_marker, render_replacement, 1)
    html = html.replace(_LIVE_CORE_EXPORT, _LIVE_CORE_EXPORT_CLEAN, 1)
    html = html.replace(_LIVE_NOOP_STATS, _LIVE_NOOP_STATS_CLEAN, 1)
    html = html.replace(
        "const graph=core.getGraph(),positions=core.getPositions(),steps=sortedGifSteps(graph);",
        "const graph=core.getDisplayGraph?.()||core.getGraph(),positions=core.getPositions(),steps=sortedGifSteps(graph);",
        1,
    )
    return html
