from __future__ import annotations

_FOCUS_JS = r"""
const execweaveDashboardGraphBase=execweaveDashboardGraph;
execweaveDashboardGraph=function(data){
  const projected=execweaveDashboardGraphBase(data);
  const hiddenTypes=new Set(['agent_trace_capability','session','command','inference_call','code_cell','agent_message']);
  const mergeTypes=new Set(['model','directory','network_endpoint']);
  const providerRootIds=new Set(['agent:Claude Code','agent:OpenAI Codex','agent:Codex','agent:Cursor','agent:OpenCode','agent:Gemini CLI','agent:Antigravity','agent:Ollama','agent:ollama']);
  const before=Array.isArray(projected.nodes)?projected.nodes:[];
  let prepared=before.filter(node=>node&&!hiddenTypes.has(String(node.type||''))).map(node=>{
    const attrs=node.attributes||{};
    let name=node.name;
    if(node.type==='agent'){
      const provider=String(attrs.provider||'').toLowerCase();
      const agentPath=String(attrs.agent_path||attrs.child_agent_path||attrs.root_agent_path||'').trim();
      const agentId=String(attrs.agent_id||attrs.subagent_id||'');
      const conversationId=String(attrs.conversation_id||'').trim();
      const nickname=String(attrs.agent_nickname||'').trim();
      const nativeLabel=String(nickname||attrs.agent_type||attrs.subagent_type||attrs.native_agent_name||'').trim();
      const explicitChild=!!String(attrs.parent_agent_path||'').trim();
      const explicitRoot=!explicitChild&&(attrs.agent_role==='root'||String(attrs.root_agent_path||'')==='/root'||providerRootIds.has(String(node.id||'')));
      if(explicitRoot)name='/root';
      else if(provider==='antigravity'&&nativeLabel&&!['default','agent','subagent','antigravity subagent'].includes(nativeLabel.toLowerCase()))name=nativeLabel;
      else if(agentPath)name=agentPath;
      else if(provider==='antigravity'&&conversationId)name=`conversation · ${conversationId.slice(0,8)}`;
      else if(['default','agent','subagent','antigravity conversation'].includes(String(node.name||'').toLowerCase())){
        // Never label by a timestamp-ordered id prefix: siblings spawned in the
        // same millisecond share it and render as the same node.
        if(nickname)name=`subagent · ${nickname}`;
        else if(nativeLabel)name=`subagent · ${nativeLabel}`;
        else if(agentId)name=`subagent · ${agentId.slice(0,13)}`;
        else name=`agent · ${String(node.id||'').split(':').at(-1).slice(0,13)}`;
      }
    }
    const occurrenceCount=Number(attrs.viewer_occurrence_count||0);
    if(node.type==='process'&&occurrenceCount>1&&!/\s×\d+$/.test(String(name||'')))name=`${name||node.id} ×${occurrenceCount}`;
    return name===node.name?node:{...node,name};
  });
  const presentationAlias=new Map();
  const antigravityRoot=prepared.find(node=>String(node?.id||'')==='agent:Antigravity');
  const antigravityScoped=prepared.filter(node=>{
    const attrs=node?.attributes||{};
    return node?.type==='agent'&&String(attrs.provider||'').toLowerCase()==='antigravity'&&
      String(node.id||'').startsWith('agent:antigravity:conversation:');
  });
  const parentScopes=new Set(antigravityScoped.filter(node=>String(node?.attributes?.parent_agent_path||'').trim()).map(node=>String(node?.attributes?.parent_scope_id||'')).filter(Boolean));
  const evidenceMains=antigravityScoped.filter(node=>{const attrs=node?.attributes||{};return !String(attrs.parent_agent_path||'').trim()&&parentScopes.has(String(attrs.conversation_id||''));});
  const fallbackMains=antigravityScoped.filter(node=>{const attrs=node?.attributes||{};return !String(attrs.parent_agent_path||'').trim()&&!attrs.routing_identity_only;});
  const antigravityMains=evidenceMains.length?evidenceMains:fallbackMains;
  if(antigravityRoot&&antigravityMains.length===1){
    const main=antigravityMains[0];presentationAlias.set(antigravityRoot.id,main.id);
    prepared=prepared.filter(node=>node.id!==antigravityRoot.id).map(node=>node.id===main.id?{...node,name:'/root'}:node);
  }else if(antigravityRoot&&antigravityScoped.length){
    prepared=prepared.filter(node=>node.id!==antigravityRoot.id);
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
""".strip()


def _inject(html: str, marker: str) -> str:
    if "execweaveDashboardGraphBase" in html or marker not in html:
        return html
    return html.replace(marker, _FOCUS_JS + "\n" + marker, 1)


def inject_standalone_dashboard_focus(html: str) -> str:
    return _inject(html, "function materializedGraph(){")


def inject_live_dashboard_focus(html: str) -> str:
    return _inject(html, "function setSnapshot(data){")
