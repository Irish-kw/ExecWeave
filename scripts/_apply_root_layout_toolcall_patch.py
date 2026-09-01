from __future__ import annotations

import re
from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one exact match, found {count}")
    return text.replace(old, new, 1)


def sub_once(text: str, pattern: str, repl: str, label: str) -> str:
    result, count = re.subn(pattern, repl, text, count=1, flags=re.DOTALL)
    if count != 1:
        raise SystemExit(f"{label}: expected one regex match, found {count}")
    return result


# Keep exact Antigravity tool input on the semantic tool-call node so the
# presentation layer can expose each invocation without rereading provider state.
path = "src/execweave/antigravity_adapter_base.py"
text = read(path)
old = '''        attributes={
            "provider": "antigravity",
            "tool_name": name,
            "step_index": step,
        },'''
new = '''        attributes={
            "provider": "antigravity",
            "tool_name": name,
            "conversation_id": conversation_id,
            "step_index": step,
            "arguments": canonical_args,
            "arguments_observed": isinstance(args, dict),
        },'''
text = replace_once(text, old, new, "Antigravity semantic tool-call attributes")
write(path, text)


# Give the full-fidelity observation the same exact conversation+step seam,
# allowing semantic and content observations of the same invocation to dedupe.
path = "src/execweave/antigravity_full_fidelity_base.py"
text = read(path)
old = '''            "attributes": {"provider": "antigravity", "tool_name": name},'''
new = '''            "attributes": {
                "provider": "antigravity",
                "tool_name": name,
                "conversation_id": payload.get("conversationId"),
                "step_index": payload.get("stepIdx"),
            },'''
text = replace_once(text, old, new, "Antigravity full-fidelity tool observation identity")
write(path, text)


# Replace the Dashboard projection in one piece. Raw evidence remains embedded;
# only the display graph is canonicalized. Tool calls and tool-call observations are
# deduped by provider-native invocation identity and surfaced as inspectable occurrences.
path = "src/execweave/viewer_dashboard_clean.py"
text = read(path)
new_dashboard_js = r'''_DASHBOARD_JS = r"""
function execweaveDashboardGraph(data){
  const allNodes=Array.isArray(data?.nodes)?data.nodes:[],allEdges=Array.isArray(data?.edges)?data.edges:[];
  const allById=new Map(allNodes.filter(node=>node&&node.id).map(node=>[node.id,node]));
  const hiddenTypes=new Set(['observed_content','tool_call','tool_call_observation','agent_turn','conversation_item','provider_session','permission_request','context_compaction','agent_turn_stop','compaction','compaction_request','terminal_operation']);
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
  const invocationMap=new Map();
  for(const call of allNodes){
    if(!['tool_call','tool_call_observation'].includes(String(call?.type||''))||!call.id)continue;
    const owner=ownerFor(call),tool=toolFor(call);if(!owner||!tool)continue;
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
    const source=canonicalId.get(edge.source)||edge.source,target=canonicalId.get(edge.target)||edge.target;
    if(!nodeIds.has(source)||!nodeIds.has(target))return null;
    if(source===edge.source&&target===edge.target)return edge;
    return{...edge,source,target,viewer_canonicalized:true,viewer_original_source:edge.source,viewer_original_target:edge.target};
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
""".strip()'''
text = sub_once(text, r'_DASHBOARD_JS = r""".*?"""\.strip\(\)', lambda _m: new_dashboard_js, "Dashboard projection block")
write(path, text)


# Replace focus projection so Antigravity root promotion is based on normalized
# positive parent scope (bare conversation id OR full agent id), not the generic node.
path = "src/execweave/viewer_dashboard_focus.py"
text = read(path)
new_focus_js = r'''_FOCUS_JS = r"""
const execweaveDashboardGraphBase=execweaveDashboardGraph;
execweaveDashboardGraph=function(data){
  const projected=execweaveDashboardGraphBase(data);
  const hiddenTypes=new Set(['agent_trace_capability','session','command','inference_call','code_cell','agent_message']);
  const mergeTypes=new Set(['model','directory','network_endpoint']);
  const providerRootIds=new Set(['agent:Claude Code','agent:OpenAI Codex','agent:Codex','agent:Cursor','agent:OpenCode','agent:Gemini CLI','agent:Antigravity','agent:antigravity','agent:Ollama','agent:ollama']);
  const before=Array.isArray(projected.nodes)?projected.nodes:[];
  const isAgyScoped=node=>node?.type==='agent'&&String(node?.attributes?.provider||'').toLowerCase()==='antigravity'&&String(node?.id||'').toLowerCase().startsWith('agent:antigravity:conversation:');
  let prepared=before.filter(node=>node&&!hiddenTypes.has(String(node.type||''))).map(node=>{
    const attrs=node.attributes||{};let name=node.name;
    if(node.type==='agent'){
      const provider=String(attrs.provider||'').toLowerCase();
      const agentPath=String(attrs.agent_path||attrs.child_agent_path||attrs.root_agent_path||'').trim();
      const agentId=String(attrs.agent_id||attrs.subagent_id||'');
      const conversationId=String(attrs.conversation_id||'').trim();
      const nickname=String(attrs.agent_nickname||'').trim();
      const nativeLabel=String(nickname||attrs.agent_type||attrs.subagent_type||attrs.native_agent_name||'').trim();
      const explicitChild=!!String(attrs.parent_agent_path||'').trim();
      const scopedAgy=provider==='antigravity'&&isAgyScoped(node);
      const explicitRoot=!explicitChild&&(attrs.agent_role==='root'||String(attrs.root_agent_path||'')==='/root'||providerRootIds.has(String(node.id||'')));
      if(explicitRoot&&!scopedAgy)name='/root';
      else if(provider==='antigravity'&&nativeLabel&&!['default','agent','subagent','antigravity subagent'].includes(nativeLabel.toLowerCase()))name=nativeLabel;
      else if(agentPath&&!(scopedAgy&&agentPath==='/root'))name=agentPath;
      else if(provider==='antigravity'&&conversationId)name=`conversation · ${conversationId.slice(0,8)}`;
      else if(['default','agent','subagent','antigravity conversation'].includes(String(node.name||'').toLowerCase())){
        if(nickname)name=`subagent · ${nickname}`;
        else if(nativeLabel)name=`subagent · ${nativeLabel}`;
        else if(agentId)name=`subagent · ${agentId.slice(0,13)}`;
        else name=`agent · ${String(node.id||'').split(':').at(-1).slice(0,13)}`;
      }
    }
    const occurrenceCount=Number(attrs.viewer_occurrence_count||0);
    if(['process','tool'].includes(String(node.type||''))&&occurrenceCount>1&&!/\s×\d+$/.test(String(name||'')))name=`${name||node.id} ×${occurrenceCount}`;
    return name===node.name?node:{...node,name};
  });
  const presentationAlias=new Map();
  const agyScopeToken=value=>{
    let text=String(value||'').trim();if(!text)return'';
    const prefix='agent:antigravity:conversation:';
    if(text.toLowerCase().startsWith(prefix))text=text.slice(prefix.length);
    return text.toLowerCase();
  };
  const antigravityScoped=prepared.filter(isAgyScoped);
  const antigravityGeneric=prepared.filter(node=>node?.type==='agent'&&String(node?.attributes?.provider||'').toLowerCase()==='antigravity'&&!isAgyScoped(node));
  const parentScopes=new Set();
  for(const node of antigravityScoped){
    const attrs=node?.attributes||{};
    if(!String(attrs.parent_agent_path||'').trim()&&!String(attrs.parent_scope_id||'').trim())continue;
    for(const value of [attrs.parent_scope_id,attrs.parent_native_id,attrs.parent_conversation_id]){const token=agyScopeToken(value);if(token)parentScopes.add(token)}
  }
  const evidenceMains=antigravityScoped.filter(node=>{
    const attrs=node?.attributes||{};if(String(attrs.parent_agent_path||'').trim())return false;
    const tokens=[agyScopeToken(node.id),agyScopeToken(attrs.conversation_id)].filter(Boolean);
    return tokens.some(token=>parentScopes.has(token));
  });
  const fallbackMains=antigravityScoped.filter(node=>{const attrs=node?.attributes||{};return !String(attrs.parent_agent_path||'').trim()&&!attrs.routing_identity_only;});
  const uniqueById=list=>[...new Map(list.map(node=>[String(node.id),node])).values()];
  const antigravityMains=uniqueById(evidenceMains.length?evidenceMains:(fallbackMains.length===1?fallbackMains:[]));
  if(antigravityMains.length===1){
    const main=antigravityMains[0];
    for(const generic of antigravityGeneric)presentationAlias.set(generic.id,main.id);
    prepared=prepared.filter(node=>!antigravityGeneric.some(generic=>generic.id===node.id)).map(node=>{
      if(!isAgyScoped(node))return node;
      const root=node.id===main.id;
      return{...node,name:root?'/root':node.name,attributes:{...(node.attributes||{}),viewer_root:root,viewer_root_selection:root?(evidenceMains.length?'positive_parent_scope':'unique_parentless_conversation'):'not_selected'}};
    });
  }else if(antigravityScoped.length){
    prepared=prepared.filter(node=>!antigravityGeneric.some(generic=>generic.id===node.id)).map(node=>isAgyScoped(node)?{...node,attributes:{...(node.attributes||{}),viewer_root:false,viewer_root_selection:'ambiguous'}}:node);
  }
  const ollamaRoots=prepared.filter(node=>node?.type==='agent'&&['agent:Ollama','agent:ollama'].includes(String(node.id||'')));
  const ollamaRuntimes=prepared.filter(node=>node?.type==='model_runtime'&&String(node?.attributes?.provider||'').toLowerCase()==='ollama');
  if(ollamaRoots.length===1&&ollamaRuntimes.length===1){
    const root=ollamaRoots[0],runtime=ollamaRuntimes[0];presentationAlias.set(runtime.id,root.id);
    prepared=prepared.filter(node=>node.id!==runtime.id).map(node=>node.id===root.id?{...node,name:'/root'}:node);
  }
  const normalized=value=>String(value||'').trim().replaceAll('\\\\','/').replace(/\/+$/,'').toLowerCase();
  const canonicalKey=node=>{
    const type=String(node?.type||''),attrs=node?.attributes||{};
    if(!mergeTypes.has(type))return `id\u0000${node.id}`;
    if(type==='model')return `${type}\u0000${normalized(attrs.provider)}\u0000${normalized(attrs.model||attrs.model_name||node.name)}`;
    if(type==='directory')return `${type}\u0000${normalized(attrs.path||attrs.directory||attrs.cwd||attrs.real_path||node.name)}`;
    const host=attrs.host||attrs.hostname||attrs.address||attrs.ip||attrs.remote_host||'',port=attrs.port||attrs.remote_port||'';
    return `${type}\u0000${normalized(host||attrs.endpoint||node.name)}\u0000${normalized(port)}`;
  };
  const groups=new Map();for(const node of prepared){const key=canonicalKey(node);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(node)}
  const canonicalId=new Map(presentationAlias),nodes=[];let mergedContextNodeCount=0;
  const earlier=(a,b)=>!a?b:!b?a:(String(a)<=String(b)?a:b),later=(a,b)=>!a?b:!b?a:(String(a)>=String(b)?a:b);
  for(const group of groups.values()){
    group.sort((a,b)=>String(a.first_seen||'').localeCompare(String(b.first_seen||''))||String(a.id).localeCompare(String(b.id)));
    const base=group[0];for(const item of group)canonicalId.set(item.id,base.id);
    if(group.length===1){nodes.push(base);continue}
    mergedContextNodeCount+=group.length-1;
    const firstSeen=group.reduce((value,item)=>earlier(value,item.first_seen),null),lastSeen=group.reduce((value,item)=>later(value,item.last_seen),null);
    const baseName=String(base.name||base.id).replace(/\s×\d+$/,'');
    nodes.push({...base,name:`${baseName} ×${group.length}`,first_seen:firstSeen||base.first_seen,last_seen:lastSeen||base.last_seen,attributes:{...(base.attributes||{}),viewer_canonicalized:true,viewer_occurrence_count:group.length,viewer_occurrence_ids:group.map(item=>item.id),viewer_occurrences:group.map(item=>({id:item.id,name:item.name||null,first_seen:item.first_seen||null,last_seen:item.last_seen||null}))}});
  }
  const ids=new Set(nodes.map(node=>node.id));
  const remapped=[];for(const edge of(projected.edges||[])){
    if(!edge)continue;const source=canonicalId.get(edge.source)||edge.source,target=canonicalId.get(edge.target)||edge.target;
    if(!ids.has(source)||!ids.has(target)||source===target)continue;
    remapped.push(source===edge.source&&target===edge.target?edge:{...edge,source,target,viewer_canonicalized:true,viewer_original_source:edge.source,viewer_original_target:edge.target});
  }
  const edgeGroups=new Map();
  for(const edge of remapped){const key=`${edge.source}\u0000${edge.relation||''}\u0000${edge.target}`,existing=edgeGroups.get(key);if(!existing){edgeGroups.set(key,{...edge,viewer_edge_occurrence_count:1,viewer_edge_occurrence_ids:[edge.id]});continue}existing.viewer_edge_occurrence_count+=1;existing.viewer_edge_occurrence_ids.push(edge.id);existing.count=Number(existing.count||1)+Number(edge.count||1);if(Number.isInteger(edge.first_sequence))existing.first_sequence=Number.isInteger(existing.first_sequence)?Math.min(existing.first_sequence,edge.first_sequence):edge.first_sequence;if(Number.isInteger(edge.last_sequence))existing.last_sequence=Number.isInteger(existing.last_sequence)?Math.max(existing.last_sequence,edge.last_sequence):edge.last_sequence;existing.first_seen=earlier(existing.first_seen,edge.first_seen);existing.last_seen=later(existing.last_seen,edge.last_seen)}
  const edges=[...edgeGroups.values()];
  return{...projected,nodes,edges,node_count:nodes.length,edge_count:edges.length,dashboard_projection:{...(projected.dashboard_projection||{}),hidden_context_node_count:before.length-prepared.length,merged_context_node_count:mergedContextNodeCount,hidden_orphan_file_node_count:0}};
};
""".strip()'''
text = sub_once(text, r'_FOCUS_JS = r""".*?"""\.strip\(\)', lambda _m: new_focus_js, "Dashboard focus block")
write(path, text)


# Add an explicit Arrange control to the unified live/finished/static Dashboard.
path = "src/execweave/live_view_markup.py"
text = read(path)
old = '''<div class="graph-actions"><button id="zoom-out" type="button" aria-label="Zoom out" title="Zoom out">−</button><button id="zoom-in" type="button" aria-label="Zoom in" title="Zoom in">+</button><button id="fit" type="button" aria-label="Fit once" title="Fit graph once">Fit</button><button id="clear-focus" type="button" aria-label="Clear focus" title="Return to the unfocused graph (Esc)" hidden>Clear focus</button></div>'''
new = '''<div class="graph-actions"><button id="zoom-out" type="button" aria-label="Zoom out" title="Zoom out">−</button><button id="zoom-in" type="button" aria-label="Zoom in" title="Zoom in">+</button><button id="fit" type="button" aria-label="Fit once" title="Fit graph once">Fit</button><button id="arrange" type="button" aria-label="Arrange graph" title="Recompute a clean graph layout">Arrange</button><button id="clear-focus" type="button" aria-label="Clear focus" title="Return to the unfocused graph (Esc)" hidden>Clear focus</button></div>'''
text = replace_once(text, old, new, "Arrange graph control")
write(path, text)


# Extend the live readability layer rather than building a second layout engine.
# viewer_root becomes authoritative when the projection has resolved it. Dragged nodes
# persist across polling; Arrange explicitly discards manual positions and recomputes.
path = "src/execweave/live_view_readability.py"
text = read(path)
text = replace_once(
    text,
    '.label.aggregate-label{fill:var(--text);font-size:9px;font-weight:700}\n',
    '.label.aggregate-label{fill:var(--text);font-size:9px;font-weight:700}\n.node{cursor:grab;touch-action:none}.node.dragging{cursor:grabbing}\n.execweave-tool-occurrences{margin-top:12px;border-top:1px solid var(--border);padding-top:10px}.execweave-tool-occurrences>strong{display:block;margin-bottom:7px}.execweave-tool-occurrence{border:1px solid var(--border);border-radius:8px;background:var(--panel2);margin:6px 0}.execweave-tool-occurrence>summary{cursor:pointer;padding:7px 9px;color:var(--muted);font-size:11px}.execweave-tool-occurrence>pre{margin:0;padding:9px;border-top:1px solid var(--border);max-height:280px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;font:11px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}\n',
    "Readability drag/tool occurrence CSS",
)
old_root = "function execweaveIsRoot(node){const a=execweaveAttrs(node);return node?.type==='agent'&&(a.agent_role==='root'||a.root_agent_path==='/root'||a.agent_path==='/root'||execweaveAgentPath(node)==='/root')}"
new_root = "function execweaveIsRoot(node){const a=execweaveAttrs(node);if(node?.type!=='agent')return false;if(Object.prototype.hasOwnProperty.call(a,'viewer_root'))return a.viewer_root===true;return a.agent_role==='root'||a.root_agent_path==='/root'||a.agent_path==='/root'||execweaveAgentPath(node)==='/root'}"
text = replace_once(text, old_root, new_root, "viewer_root authoritative layout seam")
append = r'''

// Manual placement and automatic arrangement are complementary. Polling preserves a
// reader's manual position, while Arrange deliberately throws manual positions away
// and recomputes the existing topology-aware lane layout.
let execweaveNodeDrag=null;
function execweaveGraphPoint(event){const rect=svg.getBoundingClientRect();return{x:(event.clientX-rect.left-transform.x)/transform.scale,y:(event.clientY-rect.top-transform.y)/transform.scale}}
function execweaveRefreshIncidentEdges(id){const edgeIds=new Set([...(incomingByNode.get(id)||[]),...(outgoingByNode.get(id)||[])]);for(const edgeIdValue of edgeIds){const edge=edgeById.get(edgeIdValue);if(edge)updateEdgeElement(edge)}}
const execweaveBaseCreateNodeElement=createNodeElement;
createNodeElement=function(node){
  const existed=nodeElements.has(node.id);execweaveBaseCreateNodeElement(node);const group=nodeElements.get(node.id);
  if(!group||existed||group.dataset.execweaveDragBound==='1')return;
  group.dataset.execweaveDragBound='1';
  group.addEventListener('click',event=>{if(group.dataset.execweaveSuppressClick==='1'){delete group.dataset.execweaveSuppressClick;event.preventDefault();event.stopImmediatePropagation()}},true);
  group.addEventListener('pointerdown',event=>{
    if(event.button!==0)return;const current=positions.get(node.id);if(!current)return;
    event.stopPropagation();userTookCamera();stopAnimation();const point=execweaveGraphPoint(event);
    execweaveNodeDrag={id:node.id,pointerId:event.pointerId,dx:point.x-current.x,dy:point.y-current.y,startX:event.clientX,startY:event.clientY,moved:false};
    group.classList.add('dragging');try{group.setPointerCapture(event.pointerId)}catch(_){}
  });
  group.addEventListener('pointermove',event=>{
    const drag=execweaveNodeDrag;if(!drag||drag.id!==node.id||drag.pointerId!==event.pointerId)return;
    if(Math.abs(event.clientX-drag.startX)>3||Math.abs(event.clientY-drag.startY)>3)drag.moved=true;
    const point=execweaveGraphPoint(event),next={x:point.x-drag.dx,y:point.y-drag.dy};positions.set(node.id,next);group.setAttribute('transform',`translate(${next.x} ${next.y})`);execweaveRefreshIncidentEdges(node.id);updateJumpLatest();
  });
  const finish=event=>{
    const drag=execweaveNodeDrag;if(!drag||drag.id!==node.id||drag.pointerId!==event.pointerId)return;
    if(drag.moved){group.dataset.execweaveSuppressClick='1';setTimeout(()=>{if(group.dataset.execweaveSuppressClick==='1')delete group.dataset.execweaveSuppressClick},250)}
    execweaveNodeDrag=null;group.classList.remove('dragging');try{group.releasePointerCapture(event.pointerId)}catch(_){}
  };
  group.addEventListener('pointerup',finish);group.addEventListener('pointercancel',finish);
};
function execweaveArrangeGraph(){
  execweaveTopology=execweaveBuildTopology();const next=new Map();
  const ordered=[...nodeById.keys()].sort((a,b)=>{const av=execweaveTopology.spec.get(a)||{},bv=execweaveTopology.spec.get(b)||{};return Number(av.rank||0)-Number(bv.rank||0)||Number(av.order||0)-Number(bv.order||0)||String(a).localeCompare(String(b))});
  for(const id of ordered)next.set(id,execweavePlaceStable(id,execweaveDesiredPosition(id),next,id));
  positions=next;layerRows=new Map();
  for(const [id,p] of positions){const spec=execweaveTopology.spec.get(id);if(spec)layerRows.set(spec.rank,Math.max(layerRows.get(spec.rank)||0,spec.order+1));const group=nodeElements.get(id);if(group)group.setAttribute('transform',`translate(${p.x} ${p.y})`);const node=nodeById.get(id);if(node)updateNodeElement(node)}
  for(const edge of edgeById.values())updateEdgeElement(edge);
  svg.classList.toggle('execweave-crowded',execweaveTopology.crowded);applySearch();fit(true);updateJumpLatest();return new Map(positions);
}
window.__execweaveArrangeGraph=execweaveArrangeGraph;
const execweaveArrangeButton=document.getElementById('arrange');if(execweaveArrangeButton)execweaveArrangeButton.onclick=()=>execweaveArrangeGraph();
function execweaveToolOccurrenceSection(node){
  const occurrences=Array.isArray(execweaveAttrs(node).viewer_tool_call_occurrences)?execweaveAttrs(node).viewer_tool_call_occurrences:[];if(!occurrences.length)return null;
  const section=document.createElement('section');section.className='execweave-tool-occurrences';const title=document.createElement('strong');title.textContent=`Invocations · ${occurrences.length} call${occurrences.length===1?'':'s'}`;section.appendChild(title);
  occurrences.forEach((occurrence,index)=>{const fold=document.createElement('details');fold.className='execweave-tool-occurrence';const summary=document.createElement('summary');const when=prettyTime(occurrence.first_seen||occurrence.last_seen),owner=entityLabel(occurrence.owner_id);summary.textContent=`${when} · ${owner} · call ${index+1}`;const pre=document.createElement('pre');pre.textContent=JSON.stringify({first_seen:occurrence.first_seen,last_seen:occurrence.last_seen,first_sequence:occurrence.first_sequence,last_sequence:occurrence.last_sequence,input:occurrence.input,output:occurrence.output,call_ids:occurrence.call_ids,content_references:occurrence.content_references},null,2);fold.append(summary,pre);section.appendChild(fold)});
  return section;
}
const execweaveBaseShow=show;
show=function(value,kind='Selection'){execweaveBaseShow(value,kind);if(kind==='Node'&&value?.type==='tool'){const section=execweaveToolOccurrenceSection(value);if(section){const raw=details.querySelector('.raw-toggle');if(raw)details.insertBefore(section,raw);else details.appendChild(section)}}};
'''
needle = '''const execweaveBaseSelectEdge=selectEdge;
selectEdge=function(id,options={}){execweaveBaseSelectEdge(id,options);if(edgeById.has(id))execweaveFocusOneEdge(id)};
""".strip()'''
replacement = '''const execweaveBaseSelectEdge=selectEdge;
selectEdge=function(id,options={}){execweaveBaseSelectEdge(id,options);if(edgeById.has(id))execweaveFocusOneEdge(id)};''' + append + '''
""".strip()'''
text = replace_once(text, needle, replacement, "Readability drag/arrange/tool inspector extension")
write(path, text)


# Permanent regression: intentionally uses shapes that the v0.8.6 test did not.
test_path = Path("tests/test_dashboard_root_layout_toolcall_aggregation.py")
test_path.write_text(r'''from __future__ import annotations

import os
from pathlib import Path

import pytest

from execweave.viewer_projection import write_graph_html

MAIN = "main-real-wire"
CHILD = "child-real-wire"
MAIN_ID = f"agent:antigravity:conversation:{MAIN}"
CHILD_ID = f"agent:antigravity:conversation:{CHILD}"


def _edge(edge_id: str, source: str, target: str, relation: str, sequence: int, second: int) -> dict[str, object]:
    stamp = f"2026-09-01T08:00:{second:02d}Z"
    return {"id": edge_id, "source": source, "target": target, "relation": relation, "count": 1, "first_sequence": sequence, "last_sequence": sequence, "first_seen": stamp, "last_seen": stamp}


def _graph() -> dict[str, object]:
    generic = {"id": "agent:antigravity", "type": "agent", "name": "Antigravity", "attributes": {"provider": "antigravity", "agent_role": "root"}}
    main = {"id": MAIN_ID, "type": "agent", "name": "Antigravity conversation", "attributes": {"provider": "antigravity", "conversation_id": MAIN, "agent_role": "root", "agent_path": "/root"}}
    # Deliberately carries stale root-looking archive metadata. Positive parent scope must win.
    child = {"id": CHILD_ID, "type": "agent", "name": "worker", "attributes": {"provider": "antigravity", "conversation_id": CHILD, "agent_role": "root", "root_agent_path": "/root", "parent_agent_path": "/root", "parent_scope_id": MAIN_ID, "agent_path": f"/root/{CHILD}"}}
    tool_a = {"id": "tool:antigravity:run_command:a", "type": "tool", "name": "run_command", "attributes": {"provider": "antigravity", "native_name": "run_command"}}
    tool_b = {"id": "tool:antigravity:run_command:b", "type": "tool", "name": "run_command", "attributes": {"provider": "antigravity", "native_name": "run_command"}}
    call_1 = {"id": f"tool-call:antigravity:{MAIN}:one", "type": "tool_call", "name": "run_command", "attributes": {"provider": "antigravity", "tool_name": "run_command", "conversation_id": MAIN, "step_index": 7, "arguments": {"command": "echo one"}, "output": "one"}}
    obs_1 = {"id": f"tool-call-observation:antigravity:{MAIN}:7", "type": "tool_call_observation", "name": "run_command", "attributes": {"provider": "antigravity", "tool_name": "run_command", "conversation_id": MAIN, "step_index": 7}}
    call_2 = {"id": f"tool-call:antigravity:{MAIN}:two", "type": "tool_call", "name": "run_command", "attributes": {"provider": "antigravity", "tool_name": "run_command", "conversation_id": MAIN, "step_index": 8, "arguments": {"command": "echo two"}, "output": "two"}}
    obs_2 = {"id": f"tool-call-observation:antigravity:{MAIN}:8", "type": "tool_call_observation", "name": "run_command", "attributes": {"provider": "antigravity", "tool_name": "run_command", "conversation_id": MAIN, "step_index": 8}}
    input_1 = {"id": "observed-content:input:one", "type": "observed_content", "name": "antigravity.tool_input", "attributes": {"content_kind": "antigravity.tool_input", "sha256": "111", "path": "content/111.json", "size_bytes": 22}}
    input_2 = {"id": "observed-content:input:two", "type": "observed_content", "name": "antigravity.tool_input", "attributes": {"content_kind": "antigravity.tool_input", "sha256": "222", "path": "content/222.json", "size_bytes": 22}}
    nodes = [generic, main, child, tool_a, tool_b, call_1, obs_1, call_2, obs_2, input_1, input_2]
    edges = [
        _edge("spawn", MAIN_ID, CHILD_ID, "SPAWNED_AGENT", 1, 1),
        _edge("request-1", MAIN_ID, call_1["id"], "REQUESTED_TOOL_CALL", 2, 2),
        _edge("uses-1", call_1["id"], tool_a["id"], "USES_TOOL", 3, 3),
        _edge("input-1", obs_1["id"], input_1["id"], "OBSERVED_TOOL_INPUT_AFTER_EXECUTION", 4, 4),
        _edge("request-2", MAIN_ID, call_2["id"], "REQUESTED_TOOL_CALL", 5, 5),
        _edge("uses-2", call_2["id"], tool_b["id"], "USES_TOOL", 6, 6),
        _edge("input-2", obs_2["id"], input_2["id"], "OBSERVED_TOOL_INPUT_AFTER_EXECUTION", 7, 7),
    ]
    return {"graph_schema_version": "0.2", "session_id": "root-layout-tool-aggregation", "event_count": 7, "node_count": len(nodes), "edge_count": len(edges), "nodes": nodes, "edges": edges}


def _required_browser(playwright: object):
    try:
        return playwright.chromium.launch()
    except Exception as error:  # noqa: BLE001
        if os.environ.get("EXECWEAVE_E2E_REQUIRED", "").lower() not in {"", "0", "false"}:
            pytest.fail(f"Chromium required for root/layout/tool-call gate: {error}")
        pytest.skip(f"Chromium unavailable: {error}")


def test_dashboard_source_contains_drag_arrange_and_occurrence_contract() -> None:
    from execweave import live as live_module
    html = live_module._LIVE_HTML
    assert 'id="arrange"' in html
    assert "window.__execweaveArrangeGraph=execweaveArrangeGraph" in html
    assert "execweaveDragBound" in html
    assert "tool_call_observation" in html
    assert "viewer_tool_call_occurrences" in html
    assert "viewer_root_selection" in html


@pytest.mark.viewer_e2e
def test_real_shape_dashboard_root_drag_arrange_and_tool_occurrences(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    viewer = tmp_path / "viewer.html"
    write_graph_html(_graph(), viewer)
    with sync_api.sync_playwright() as playwright:
        browser = _required_browser(playwright)
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1050})
            page.goto(viewer.as_uri())
            page.wait_for_selector(".node")
            display = page.evaluate("()=>window.__execweaveCore.getDisplayGraph()")
            agents = [node for node in display["nodes"] if node.get("type") == "agent"]
            assert [node["id"] for node in agents if node.get("name") == "/root"] == [MAIN_ID]
            assert "agent:antigravity" not in {node["id"] for node in agents}
            main = next(node for node in agents if node["id"] == MAIN_ID)
            child = next(node for node in agents if node["id"] == CHILD_ID)
            assert main["attributes"]["viewer_root"] is True
            assert child["attributes"]["viewer_root"] is False
            assert page.locator(f'.node[data-id="{MAIN_ID}"]').get_attribute("data-layout-lane") == "root"
            assert page.locator(f'.node[data-id="{CHILD_ID}"]').get_attribute("data-layout-lane") == "agent"

            assert not [node for node in display["nodes"] if node.get("type") in {"tool_call", "tool_call_observation"}]
            tools = [node for node in display["nodes"] if node.get("type") == "tool"]
            assert len(tools) == 1
            tool = tools[0]
            assert tool["attributes"]["viewer_occurrence_count"] == 2
            occurrences = tool["attributes"]["viewer_tool_call_occurrences"]
            assert [item["input"]["command"] for item in occurrences] == ["echo one", "echo two"]
            assert [item["output"] for item in occurrences] == ["one", "two"]
            assert all(len(item["call_ids"]) == 2 for item in occurrences)
            tool_edges = [edge for edge in display["edges"] if edge.get("relation") == "CALLED_TOOL"]
            assert len(tool_edges) == 1 and tool_edges[0]["count"] == 2

            tool_id = tool["id"]
            page.locator(f'.node[data-id="{tool_id}"]').click()
            details = page.locator("#details")
            page.wait_for_function("()=>(document.getElementById('details')?.innerText||'').includes('Invocations · 2 calls')")
            assert "Invocations · 2 calls" in details.inner_text()
            folds = details.locator(".execweave-tool-occurrence")
            assert folds.count() == 2
            for index, command in enumerate(("echo one", "echo two")):
                folds.nth(index).locator("summary").click()
                assert command in folds.nth(index).inner_text()

            root = page.locator(f'.node[data-id="{MAIN_ID}"]')
            before = page.evaluate("id=>{const p=window.__execweaveCore.getPositions().get(id);return{x:p.x,y:p.y}}", MAIN_ID)
            box = root.bounding_box(); assert box is not None
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.mouse.down(); page.mouse.move(box["x"] + box["width"] / 2 + 180, box["y"] + box["height"] / 2 + 120, steps=8); page.mouse.up()
            after_drag = page.evaluate("id=>{const p=window.__execweaveCore.getPositions().get(id);return{x:p.x,y:p.y}}", MAIN_ID)
            assert abs(after_drag["x"] - before["x"]) > 50 or abs(after_drag["y"] - before["y"]) > 50

            page.locator("#arrange").click()
            page.wait_for_timeout(350)
            after_arrange = page.evaluate("id=>{const p=window.__execweaveCore.getPositions().get(id);return{x:p.x,y:p.y}}", MAIN_ID)
            assert abs(after_arrange["x"] - after_drag["x"]) > 30 or abs(after_arrange["y"] - after_drag["y"]) > 30
            assert page.locator(f'.node[data-id="{MAIN_ID}"]').get_attribute("data-layout-lane") == "root"
            assert page.locator(f'.node[data-id="{CHILD_ID}"]').get_attribute("data-layout-lane") == "agent"

            page.locator(f'.node[data-id="{tool_id}"]').click()
            screenshot = os.environ.get("EXECWEAVE_REAL_DASHBOARD_SCREENSHOT")
            if screenshot:
                Path(screenshot).parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=screenshot, full_page=True)
        finally:
            browser.close()
''', encoding="utf-8")

print("patched root identity, graph interaction, and tool-call aggregation")
