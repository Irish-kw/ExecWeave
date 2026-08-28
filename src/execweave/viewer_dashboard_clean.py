from __future__ import annotations

_DASHBOARD_JS = r"""
function execweaveDashboardGraph(data){
  const allNodes=Array.isArray(data?.nodes)?data.nodes:[],allEdges=Array.isArray(data?.edges)?data.edges:[];
  const allById=new Map(allNodes.filter(node=>node&&node.id).map(node=>[node.id,node]));
  const hiddenTypes=new Set(['observed_content','tool_call','agent_turn','conversation_item','provider_session','permission_request','context_compaction','agent_turn_stop','compaction','compaction_request','terminal_operation']);
  const hiddenIds=new Set(allNodes.filter(node=>node&&hiddenTypes.has(String(node.type||''))).map(node=>node.id).filter(Boolean));
  const incoming=new Map(),outgoing=new Map();
  for(const edge of allEdges){
    if(!edge)continue;
    if(!incoming.has(edge.target))incoming.set(edge.target,[]);
    if(!outgoing.has(edge.source))outgoing.set(edge.source,[]);
    incoming.get(edge.target).push(edge);outgoing.get(edge.source).push(edge);
  }
  const provider=node=>String(node?.attributes?.provider||'unknown').toLowerCase();
  const toolName=node=>String(node?.attributes?.tool_name||node?.attributes?.native_name||node?.name||'tool');
  const toolKey=node=>`${provider(node)}\u0000${toolName(node).toLowerCase()}`;
  const toolsByKey=new Map();
  for(const node of allNodes)if(node?.type==='tool'&&!toolsByKey.has(toolKey(node)))toolsByKey.set(toolKey(node),node.id);
  function ownerFor(callId){
    const edges=incoming.get(callId)||[];
    for(const edge of edges){const source=allById.get(edge.source);if(source?.type==='agent')return edge.source}
    for(const edge of edges){
      const turn=allById.get(edge.source);if(turn?.type!=='agent_turn')continue;
      for(const parent of incoming.get(edge.source)||[]){const source=allById.get(parent.source);if(source?.type==='agent')return parent.source}
    }
    for(const edge of edges){
      const source=allById.get(edge.source);
      if(source&&!hiddenTypes.has(String(source.type||''))&&source.type!=='tool')return edge.source;
    }
    return null;
  }
  function toolFor(call){
    for(const edge of outgoing.get(call.id)||[]){const target=allById.get(edge.target);if(target?.type==='tool')return edge.target}
    return toolsByKey.get(toolKey(call))||null;
  }
  const groups=new Map(),toolCounts=new Map();
  const seq=(edge,key)=>Number.isInteger(edge?.[key])?edge[key]:null;
  const earlier=(a,b)=>!a?b:!b?a:(String(a)<=String(b)?a:b);
  const later=(a,b)=>!a?b:!b?a:(String(a)>=String(b)?a:b);
  for(const call of allNodes){
    if(call?.type!=='tool_call'||!call.id)continue;
    const owner=ownerFor(call.id),tool=toolFor(call);
    if(!owner||!tool)continue;
    const key=`${owner}\u0000${tool}`,evidence=[...(incoming.get(call.id)||[]),...(outgoing.get(call.id)||[])];
    let group=groups.get(key);
    if(!group){group={owner,tool,count:0,first_sequence:null,last_sequence:null,first_seen:null,last_seen:null};groups.set(key,group)}
    group.count+=1;toolCounts.set(tool,(toolCounts.get(tool)||0)+1);
    for(const edge of evidence){
      const first=seq(edge,'first_sequence'),last=seq(edge,'last_sequence');
      if(first!==null)group.first_sequence=group.first_sequence===null?first:Math.min(group.first_sequence,first);
      if(last!==null)group.last_sequence=group.last_sequence===null?last:Math.max(group.last_sequence,last);
      group.first_seen=earlier(group.first_seen,edge.first_seen);group.last_seen=later(group.last_seen,edge.last_seen);
    }
  }
  let nodes=allNodes.filter(node=>node&&node.id&&!hiddenIds.has(node.id)).map(node=>{
    if(node.type!=='tool'||!toolCounts.has(node.id))return node;
    return{...node,attributes:{...(node.attributes||{}),viewer_aggregated_tool_call_count:toolCounts.get(node.id)}};
  });
  let nodeIds=new Set(nodes.map(node=>node.id));
  let edges=allEdges.filter(edge=>edge&&nodeIds.has(edge.source)&&nodeIds.has(edge.target));
  for(const group of groups.values()){
    if(!nodeIds.has(group.owner)||!nodeIds.has(group.tool))continue;
    edges.push({
      id:`viewer:${group.owner}--CALLED_TOOL-->${group.tool}`,source:group.owner,target:group.tool,
      relation:'CALLED_TOOL',count:group.count,first_sequence:group.first_sequence,last_sequence:group.last_sequence,
      first_seen:group.first_seen,last_seen:group.last_seen,causal:null,inferred:false,viewer_only:true,
      attributions:['viewer_tool_call_aggregation'],evidence_call_count:group.count
    });
  }
  const incident=new Set();for(const edge of edges){incident.add(edge.source);incident.add(edge.target)}
  nodes=nodes.filter(node=>node.type!=='tool'||incident.has(node.id));
  nodeIds=new Set(nodes.map(node=>node.id));edges=edges.filter(edge=>nodeIds.has(edge.source)&&nodeIds.has(edge.target));
  return{...data,nodes,edges,node_count:nodes.length,edge_count:edges.length,dashboard_projection:{hidden_detail_node_count:hiddenIds.size,collapsed_tool_call_count:[...groups.values()].reduce((sum,item)=>sum+item.count,0)}};
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

_LIVE_SET_SNAPSHOT = "function setSnapshot(data){graph=data;nodeById=new Map((data.nodes||[]).map(n=>[n.id,n]));edgeById=new Map((data.edges||[]).map(e=>[edgeId(e),e]));rebuildAdjacency();updateStats(data);if(!withinRenderBudget(data)){enterProtectiveMode(data);return}renderSnapshot();seedActivities();const sortedEdges=[...edgeById.values()].sort((a,b)=>String(a.last_seen||'').localeCompare(String(b.last_seen||''))),sortedNodes=[...nodeById.values()].sort((a,b)=>String(a.last_seen||'').localeCompare(String(b.last_seen||''))),lastEdge=sortedEdges.length?sortedEdges[sortedEdges.length-1]:null,lastNode=sortedNodes.length?sortedNodes[sortedNodes.length-1]:null;markLatest(lastEdge?.target||lastNode?.id||null,lastEdge?edgeId(lastEdge):null);if(!hasFitted&&positions.size){fit(false);hasFitted=true}else scheduleCamera(true)}"
_LIVE_SET_SNAPSHOT_CLEAN = "function setSnapshot(data){graph=data;const display=execweaveDashboardGraph(data);nodeById=new Map((display.nodes||[]).map(n=>[n.id,n]));edgeById=new Map((display.edges||[]).map(e=>[edgeId(e),e]));rebuildAdjacency();updateStats({...data,node_count:display.node_count,edge_count:display.edge_count});if(!withinRenderBudget(display)){enterProtectiveMode(display);return}renderSnapshot();seedActivities();const sortedEdges=[...edgeById.values()].sort((a,b)=>String(a.last_seen||'').localeCompare(String(b.last_seen||''))),sortedNodes=[...nodeById.values()].sort((a,b)=>String(a.last_seen||'').localeCompare(String(b.last_seen||''))),lastEdge=sortedEdges.length?sortedEdges[sortedEdges.length-1]:null,lastNode=sortedNodes.length?sortedNodes[sortedNodes.length-1]:null;markLatest(lastEdge?.target||lastNode?.id||null,lastEdge?edgeId(lastEdge):null);if(!hasFitted&&positions.size){fit(false);hasFitted=true}else scheduleCamera(true)}"

_LIVE_APPLY_DELTA = "function applyDelta(update){updateStats(update);if(update.live_payload_compact||!withinRenderBudget(update)){enterProtectiveMode(update);return}if(protectedMode){liveSequence=-1;return}const addedNodeIds=mergeById(update.nodes_added,nodeById,false);mergeById(update.nodes_updated,nodeById,false);const addedEdgeIds=mergeById(update.edges_added,edgeById,true);const updatedEdgeIds=mergeById(update.edges_updated,edgeById,true);graph={...graph,event_count:update.event_count,node_count:update.node_count,edge_count:update.edge_count,nodes:[...nodeById.values()],edges:[...edgeById.values()]};placeAddedNodes(addedNodeIds);for(const id of addedNodeIds)createNodeElement(nodeById.get(id));for(const n of update.nodes_updated||[])updateNodeElement(n);for(const id of addedEdgeIds)createEdgeElement(edgeById.get(id));for(const e of update.edges_updated||[])updateEdgeElement(e);applySearch();const changedEdges=[...(update.edges_added||[]),...(update.edges_updated||[])];const latestEdge=changedEdges.length?changedEdges[changedEdges.length-1]:null,addedNodes=update.nodes_added||[],updatedNodes=update.nodes_updated||[],latestNode=latestEdge?.target||(addedNodes.length?addedNodes[addedNodes.length-1].id:null)||(updatedNodes.length?updatedNodes[updatedNodes.length-1].id:null)||null;markLatest(latestNode,latestEdge?edgeId(latestEdge):null);const newActivities=changedEdges.length?changedEdges.map(e=>activityFromEdge(e)):((update.nodes_added||[]).map(activityFromNode));addActivities(newActivities);scheduleCamera(false);if(!hasFitted&&positions.size){fit(false);hasFitted=true}}"
_LIVE_APPLY_DELTA_CLEAN = "function applyDelta(update){if(update.live_payload_compact){updateStats(update);enterProtectiveMode(update);return}const rawNodes=new Map((graph.nodes||[]).map(n=>[n.id,n])),rawEdges=new Map((graph.edges||[]).map(e=>[edgeId(e),e]));for(const node of [...(update.nodes_added||[]),...(update.nodes_updated||[])])if(node?.id)rawNodes.set(node.id,node);for(const edge of [...(update.edges_added||[]),...(update.edges_updated||[])])rawEdges.set(edgeId(edge),edge);graph={...graph,event_count:update.event_count,node_count:update.node_count,edge_count:update.edge_count,nodes:[...rawNodes.values()],edges:[...rawEdges.values()]};const display=execweaveDashboardGraph(graph);updateStats({...update,node_count:display.node_count,edge_count:display.edge_count});if(!withinRenderBudget(display)){enterProtectiveMode(display);return}if(protectedMode)leaveProtectiveMode();nodeById=new Map((display.nodes||[]).map(n=>[n.id,n]));edgeById=new Map((display.edges||[]).map(e=>[edgeId(e),e]));rebuildAdjacency();renderSnapshot();seedActivities();const sortedEdges=[...edgeById.values()].sort((a,b)=>String(a.last_seen||'').localeCompare(String(b.last_seen||''))),sortedNodes=[...nodeById.values()].sort((a,b)=>String(a.last_seen||'').localeCompare(String(b.last_seen||''))),lastEdge=sortedEdges.length?sortedEdges[sortedEdges.length-1]:null,lastNode=sortedNodes.length?sortedNodes[sortedNodes.length-1]:null;markLatest(lastEdge?.target||lastNode?.id||null,lastEdge?edgeId(lastEdge):null);scheduleCamera(false);if(!hasFitted&&positions.size){fit(false);hasFitted=true}}"

_LIVE_CORE_EXPORT = "window.__execweaveCore={getActivities:()=>activities.slice(),getGraph:()=>graph,getPositions:()=>new Map(positions),selectEdge,selectNode,focusNode,markLatest,setCameraMode};"
_LIVE_CORE_EXPORT_CLEAN = "window.__execweaveCore={getActivities:()=>activities.slice(),getGraph:()=>graph,getDisplayGraph:()=>({...graph,nodes:[...nodeById.values()],edges:[...edgeById.values()],node_count:nodeById.size,edge_count:edgeById.size}),getPositions:()=>new Map(positions),selectEdge,selectNode,focusNode,markLatest,setCameraMode};"


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
    html = html.replace(_LIVE_SET_SNAPSHOT, _LIVE_SET_SNAPSHOT_CLEAN, 1)
    html = html.replace(_LIVE_APPLY_DELTA, _LIVE_APPLY_DELTA_CLEAN, 1)
    html = html.replace(_LIVE_CORE_EXPORT, _LIVE_CORE_EXPORT_CLEAN, 1)
    html = html.replace(
        "const graph=core.getGraph(),positions=core.getPositions(),steps=sortedGifSteps(graph);",
        "const graph=core.getDisplayGraph?.()||core.getGraph(),positions=core.getPositions(),steps=sortedGifSteps(graph);",
        1,
    )
    return html
