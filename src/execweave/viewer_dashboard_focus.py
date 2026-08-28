from __future__ import annotations

_FOCUS_JS = r"""
const execweaveDashboardGraphBase=execweaveDashboardGraph;
execweaveDashboardGraph=function(data){
  const projected=execweaveDashboardGraphBase(data);
  const hiddenTypes=new Set(['agent_trace_capability','session','process','command','inference_call','code_cell','agent_message']);
  const mergeTypes=new Set(['model','directory','network_endpoint']);
  const textOf=node=>{const attrs=node?.attributes||{};return [node?.id,node?.name,attrs.path,attrs.file_path,attrs.source_path,attrs.target_path,attrs.real_path].map(value=>String(value||'')).join(' ')};
  const internalNode=node=>{const value=textOf(node).replaceAll('\\\\','/').toLowerCase();return value.includes('.execweave-content-')||value.includes('.git/')||value.includes('.execweave/')||value.includes('content/sha256/')||value.includes('codex-rollout-trace/')};
  const before=Array.isArray(projected.nodes)?projected.nodes:[];
  const prepared=before.filter(node=>node&&!hiddenTypes.has(String(node.type||''))&&!internalNode(node)).map(node=>{
    const attrs=node.attributes||{};
    let name=node.name;
    if(node.type==='agent'){
      const agentPath=typeof attrs.agent_path==='string'?attrs.agent_path.trim():'';
      const agentId=String(attrs.agent_id||'');
      const provider=String(attrs.provider||'').toLowerCase();
      if(agentPath)name=agentPath;
      else if(node.id==='agent:OpenAI Codex'||(provider==='codex'&&String(node.name||'')==='OpenAI Codex'))name='/root';
      else if(agentId&&String(node.name||'').toLowerCase()==='default')name=`subagent · ${agentId.slice(0,8)}`;
    }
    return name===node.name?node:{...node,name};
  });
  const normalized=value=>String(value||'').trim().replaceAll('\\\\','/').replace(/\/+$/,'').toLowerCase();
  const canonicalKey=node=>{
    const type=String(node?.type||''),attrs=node?.attributes||{};
    if(!mergeTypes.has(type))return `id\u0000${node.id}`;
    if(type==='model')return `${type}\u0000${normalized(attrs.provider)}\u0000${normalized(attrs.model||attrs.model_name||node.name)}`;
    if(type==='directory')return `${type}\u0000${normalized(attrs.path||attrs.directory||attrs.cwd||node.name)}`;
    const host=attrs.host||attrs.hostname||attrs.address||attrs.ip||'',port=attrs.port||attrs.remote_port||'';
    return `${type}\u0000${normalized(host||node.name)}\u0000${normalized(port)}`;
  };
  const groups=new Map();for(const node of prepared){const key=canonicalKey(node);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(node)}
  const canonicalId=new Map(),nodes=[];let mergedContextNodeCount=0;
  const earlier=(a,b)=>!a?b:!b?a:(String(a)<=String(b)?a:b),later=(a,b)=>!a?b:!b?a:(String(a)>=String(b)?a:b);
  for(const group of groups.values()){
    group.sort((a,b)=>String(a.first_seen||'').localeCompare(String(b.first_seen||''))||String(a.id).localeCompare(String(b.id)));
    const base=group[0];for(const item of group)canonicalId.set(item.id,base.id);
    if(group.length===1){nodes.push(base);continue}
    mergedContextNodeCount+=group.length-1;
    const firstSeen=group.reduce((value,item)=>earlier(value,item.first_seen),null),lastSeen=group.reduce((value,item)=>later(value,item.last_seen),null);
    nodes.push({...base,name:`${base.name||base.id} ×${group.length}`,first_seen:firstSeen||base.first_seen,last_seen:lastSeen||base.last_seen,attributes:{...(base.attributes||{}),viewer_canonicalized:true,viewer_occurrence_count:group.length,viewer_occurrence_ids:group.map(item=>item.id),viewer_occurrences:group.map(item=>({id:item.id,name:item.name||null,first_seen:item.first_seen||null,last_seen:item.last_seen||null}))}});
  }
  let ids=new Set(nodes.map(node=>node.id));
  const remapped=[];for(const edge of (projected.edges||[])){
    if(!edge)continue;const source=canonicalId.get(edge.source)||edge.source,target=canonicalId.get(edge.target)||edge.target;
    if(!ids.has(source)||!ids.has(target)||source===target)continue;
    remapped.push(source===edge.source&&target===edge.target?edge:{...edge,source,target,viewer_canonicalized:true,viewer_original_source:edge.source,viewer_original_target:edge.target});
  }
  const edgeGroups=new Map();
  for(const edge of remapped){const key=`${edge.source}\u0000${edge.relation||''}\u0000${edge.target}`,existing=edgeGroups.get(key);if(!existing){edgeGroups.set(key,{...edge,viewer_edge_occurrence_count:1,viewer_edge_occurrence_ids:[edge.id]});continue}existing.viewer_edge_occurrence_count+=1;existing.viewer_edge_occurrence_ids.push(edge.id);existing.count=Number(existing.count||1)+Number(edge.count||1);if(Number.isInteger(edge.first_sequence))existing.first_sequence=Number.isInteger(existing.first_sequence)?Math.min(existing.first_sequence,edge.first_sequence):edge.first_sequence;if(Number.isInteger(edge.last_sequence))existing.last_sequence=Number.isInteger(existing.last_sequence)?Math.max(existing.last_sequence,edge.last_sequence):edge.last_sequence;existing.first_seen=earlier(existing.first_seen,edge.first_seen);existing.last_seen=later(existing.last_seen,edge.last_seen)}
  let edges=[...edgeGroups.values()];
  const incident=new Set();for(const edge of edges){incident.add(edge.source);incident.add(edge.target)}
  const beforeOrphanFiles=nodes.length;
  const focused=nodes.filter(node=>node.type!=='file'||incident.has(node.id));
  ids=new Set(focused.map(node=>node.id));edges=edges.filter(edge=>ids.has(edge.source)&&ids.has(edge.target));
  return{...projected,nodes:focused,edges,node_count:focused.length,edge_count:edges.length,dashboard_projection:{...(projected.dashboard_projection||{}),hidden_context_node_count:before.length-prepared.length,merged_context_node_count:mergedContextNodeCount,hidden_orphan_file_node_count:beforeOrphanFiles-focused.length}};
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
