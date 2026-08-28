from __future__ import annotations

_FOCUS_JS = r"""
const execweaveDashboardGraphBase=execweaveDashboardGraph;
execweaveDashboardGraph=function(data){
  const projected=execweaveDashboardGraphBase(data);
  const contextTypes=new Set(['agent_trace_capability','model','session','directory','network_endpoint']);
  const before=Array.isArray(projected.nodes)?projected.nodes:[];
  const nodes=before.filter(node=>node&&!contextTypes.has(String(node.type||''))).map(node=>{
    const attrs=node.attributes||{};
    let name=node.name;
    if(node.type==='agent'&&typeof attrs.agent_path==='string'&&attrs.agent_path)name=attrs.agent_path;
    const occurrences=Number(attrs.viewer_occurrence_count||0);
    if(node.type==='process'&&occurrences>1)name=`${node.name||'process'} ×${occurrences}`;
    return name===node.name?node:{...node,name};
  });
  const ids=new Set(nodes.map(node=>node.id));
  const edges=(projected.edges||[]).filter(edge=>edge&&ids.has(edge.source)&&ids.has(edge.target));
  return{...projected,nodes,edges,node_count:nodes.length,edge_count:edges.length,dashboard_projection:{...(projected.dashboard_projection||{}),hidden_context_node_count:before.length-nodes.length}};
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
