from __future__ import annotations

_FOCUS_JS = r"""
const execweaveDashboardGraphBase=execweaveDashboardGraph;
execweaveDashboardGraph=function(data){
  const projected=execweaveDashboardGraphBase(data);
  const contextTypes=new Set(['agent_trace_capability','model','session','directory','network_endpoint','process','command','inference_call','code_cell','agent_message']);
  const textOf=node=>{const attrs=node?.attributes||{};return [node?.id,node?.name,attrs.path,attrs.file_path,attrs.source_path,attrs.target_path,attrs.real_path].map(value=>String(value||'')).join(' ')};
  const internalNode=node=>{const value=textOf(node).replaceAll('\\\\','/').toLowerCase();return value.includes('.execweave-content-')||value.includes('.git/')||value.includes('.execweave/')||value.includes('content/sha256/')||value.includes('codex-rollout-trace/')};
  const before=Array.isArray(projected.nodes)?projected.nodes:[];
  let focused=before.filter(node=>node&&!contextTypes.has(String(node.type||''))&&!internalNode(node)).map(node=>{
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
  let ids=new Set(focused.map(node=>node.id));
  let edges=(projected.edges||[]).filter(edge=>edge&&ids.has(edge.source)&&ids.has(edge.target));
  const incident=new Set();for(const edge of edges){incident.add(edge.source);incident.add(edge.target)}
  const beforeOrphanFiles=focused.length;
  focused=focused.filter(node=>node.type!=='file'||incident.has(node.id));
  ids=new Set(focused.map(node=>node.id));edges=edges.filter(edge=>ids.has(edge.source)&&ids.has(edge.target));
  return{...projected,nodes:focused,edges,node_count:focused.length,edge_count:edges.length,dashboard_projection:{...(projected.dashboard_projection||{}),hidden_context_node_count:before.length-beforeOrphanFiles,hidden_orphan_file_node_count:beforeOrphanFiles-focused.length}};
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
