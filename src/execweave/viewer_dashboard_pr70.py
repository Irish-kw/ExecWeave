from __future__ import annotations


# PR70 keeps the raw evidence graph untouched.  These repairs run only in the shared
# Dashboard shell, after the normal dashboard projection and Dagre layout have been
# installed.  The projection repair exposes a conservative viewer-only bridge through
# hidden provider/detail nodes; the geometry repair keeps Dagre's real route points and
# lets a live update reflow Y only when it strictly reduces crossings.
PR70_DASHBOARD_SCRIPT = r"""
(function(){
  const pr70BaseDashboardGraph=execweaveDashboardGraph;
  const pr70BridgeTypes=new Set([
    'agent_execution','agent_turn','agent_turn_stop','context_compaction','conversation_item',
    'observed_content','permission_request','provider_session','terminal_operation','tool_call',
    'tool_call_observation'
  ]);
  const pr70NodeType=node=>String(node?.type||'');
  const pr70RawMaps=data=>{
    const nodes=Array.isArray(data?.nodes)?data.nodes:[],edges=Array.isArray(data?.edges)?data.edges:[];
    const byId=new Map(nodes.filter(node=>node?.id).map(node=>[node.id,node]));
    const incoming=new Map();
    for(const edge of edges){
      if(!edge?.source||!edge?.target)continue;
      if(!incoming.has(edge.target))incoming.set(edge.target,[]);
      incoming.get(edge.target).push(edge);
    }
    return{nodes,edges,byId,incoming};
  };
  function pr70VisibleAgentAncestors(startId,visibleIds,byId,incoming){
    const found=new Set(),seen=new Set(),queue=[startId];
    while(queue.length){
      const current=queue.shift();
      if(!current||seen.has(current))continue;
      seen.add(current);
      for(const edge of incoming.get(current)||[]){
        const sourceId=edge.source,source=byId.get(sourceId);
        if(!sourceId||!source)continue;
        if(visibleIds.has(sourceId)){
          if(pr70NodeType(source)==='agent')found.add(sourceId);
          continue;
        }
        if(pr70BridgeTypes.has(pr70NodeType(source)))queue.push(sourceId);
      }
    }
    return[...found].sort();
  }
  function pr70ProjectionRepair(data,display){
    const raw=pr70RawMaps(data),visibleIds=new Set((display.nodes||[]).map(node=>node?.id).filter(Boolean));
    const existing=new Set((display.edges||[]).map(edge=>`${edge.source}\u0000${edge.relation}\u0000${edge.target}`));
    const bridgeEdges=[];
    for(const edge of raw.edges){
      if(!edge?.source||!edge?.target||!visibleIds.has(edge.target)||visibleIds.has(edge.source))continue;
      const hiddenSource=raw.byId.get(edge.source),target=raw.byId.get(edge.target);
      if(!hiddenSource||!target||!pr70BridgeTypes.has(pr70NodeType(hiddenSource)))continue;
      const targetType=pr70NodeType(target).toLowerCase();
      // Hidden-detail composition is only promoted onto the canvas for model/runtime
      // identity.  Other hidden chains stay raw evidence rather than inventing a
      // stronger visible relation.
      if(!targetType.includes('model')&&!targetType.includes('inference')&&!targetType.includes('llm'))continue;
      const ancestors=pr70VisibleAgentAncestors(edge.source,visibleIds,raw.byId,raw.incoming);
      if(ancestors.length!==1)continue;
      const source=ancestors[0],key=`${source}\u0000${edge.relation}\u0000${edge.target}`;
      if(existing.has(key))continue;
      existing.add(key);
      bridgeEdges.push({
        ...edge,
        id:`viewer:hidden-bridge:${source}:${edge.relation}:${edge.target}:${edge.id||edge.source}`,
        source,
        viewer_only:true,
        inferred:true,
        causal:false,
        viewer_hidden_bridge:true,
        viewer_hidden_bridge_source:edge.source,
        viewer_hidden_bridge_reason:'unique_visible_agent_ancestor',
      });
    }
    const edges=[...(display.edges||[]),...bridgeEdges];
    const incident=new Set(),rawIncident=new Set();
    for(const edge of edges){if(edge?.source)incident.add(edge.source);if(edge?.target)incident.add(edge.target)}
    for(const edge of raw.edges){if(edge?.source)rawIncident.add(edge.source);if(edge?.target)rawIncident.add(edge.target)}
    const removed=[];
    const nodes=(display.nodes||[]).filter(node=>{
      if(!node?.id)return false;
      if(incident.has(node.id)||!rawIncident.has(node.id)||pr70NodeType(node)==='agent')return true;
      removed.push(node.id);return false;
    });
    const kept=new Set(nodes.map(node=>node.id));
    const keptEdges=edges.filter(edge=>kept.has(edge.source)&&kept.has(edge.target));
    const projection={...(display.dashboard_projection||{}),hidden_bridge_edge_count:bridgeEdges.length,removed_projection_orphan_count:removed.length,removed_projection_orphan_ids:removed};
    return{...display,nodes,edges:keptEdges,node_count:nodes.length,edge_count:keptEdges.length,dashboard_projection:projection};
  }
  execweaveDashboardGraph=function(data){return pr70ProjectionRepair(data,pr70BaseDashboardGraph(data))};

  function pr70RetargetDagreRoutePoints(topo){
    const dagre=topo?.dagrePipeline?.stages?.POST_DAGRE;
    if(!(dagre instanceof Map)||!(topo?.routePoints instanceof Map)||!(topo?.spec instanceof Map))return topo;
    for(const [key,points] of topo.routePoints){
      if(!Array.isArray(points)||points.length<2)continue;
      const split=String(key).split('\u0000');if(split.length!==2)continue;
      const [source,target]=split,sourceBefore=dagre.get(source),targetBefore=dagre.get(target),sourceAfter=topo.spec.get(source),targetAfter=topo.spec.get(target);
      if(!sourceBefore||!targetBefore||!sourceAfter||!targetAfter)continue;
      const sdx=sourceAfter.x-sourceBefore.x,sdy=sourceAfter.y-sourceBefore.y,tdx=targetAfter.x-targetBefore.x,tdy=targetAfter.y-targetBefore.y;
      const adjusted=points.map((point,index)=>{
        const t=points.length<=1?0:index/(points.length-1),u=1-t;
        return{x:point.x+sdx*u+tdx*t,y:point.y+sdy*u+tdy*t};
      });
      topo.routePoints.set(key,adjusted);
    }
    return topo;
  }
  const pr70BuildTopologyBase=execweaveBuildTopology;
  execweaveBuildTopology=function(){return pr70RetargetDagreRoutePoints(pr70BuildTopologyBase())};

  function pr70RouteFromPoints(edge,points){
    const sp=positions.get(edge.source)||{x:0,y:0},tp=positions.get(edge.target)||{x:0,y:0};
    const sourceSpec=execweaveTopology.spec.get(edge.source)||{},targetSpec=execweaveTopology.spec.get(edge.target)||{};
    const sourcePort=execweaveTopology.sourcePort.get(edgeId(edge)),targetPort=execweaveTopology.targetPort.get(edgeId(edge));
    const forward=(targetSpec.x??0)>=(sourceSpec.x??0);
    const sx=forward?sp.x+execweaveWidthOf(edge.source):sp.x,tx=forward?tp.x:tp.x+execweaveWidthOf(edge.target);
    const sy=execweavePortY(sp,sourcePort,edge.source),ty=execweavePortY(tp,targetPort,edge.target);
    const mids=points.slice(1,-1).filter(point=>Number.isFinite(point?.x)&&Number.isFinite(point?.y));
    let d=`M ${sx} ${sy}`;
    for(const point of mids)d+=` L ${+point.x.toFixed(2)} ${+point.y.toFixed(2)}`;
    d+=` L ${tx} ${ty}`;
    const label=mids.length?mids[Math.floor(mids.length/2)]:{x:(sx+tx)/2,y:(sy+ty)/2};
    return{d,labelX:label.x,labelY:label.y-8,kind:'dagre-polyline',bundle:null,usesDagrePoints:true};
  }
  const pr70RouteBase=execweaveRoute;
  execweaveRoute=function(edge){
    const bundle=execweaveTopology.bundleByEdge.get(edgeId(edge));
    if(bundle&&bundle.size>1)return pr70RouteBase(edge);
    if(typeof execweaveIsStopped==='function'&&execweaveIsStopped(edge))return pr70RouteBase(edge);
    const points=execweaveTopology.routePoints?.get(`${edge.source}\u0000${edge.target}`);
    if(points&&points.length>=2)return pr70RouteFromPoints(edge,points);
    return pr70RouteBase(edge);
  };

  function pr70Orientation(a,b,c){
    const value=(b.y-a.y)*(c.x-b.x)-(b.x-a.x)*(c.y-b.y);
    if(Math.abs(value)<1e-7)return 0;return value>0?1:2;
  }
  function pr70SegmentsCross(a,b,c,d){
    const o1=pr70Orientation(a,b,c),o2=pr70Orientation(a,b,d),o3=pr70Orientation(c,d,a),o4=pr70Orientation(c,d,b);
    return o1!==0&&o2!==0&&o3!==0&&o4!==0&&o1!==o2&&o3!==o4;
  }
  function pr70StraightCrossings(yOverride=null){
    const segments=[];
    for(const edge of edgeById.values()){
      if(edge.source===edge.target||!positions.has(edge.source)||!positions.has(edge.target))continue;
      const sp=positions.get(edge.source),tp=positions.get(edge.target),sy=yOverride?.has(edge.source)?yOverride.get(edge.source):sp.y,ty=yOverride?.has(edge.target)?yOverride.get(edge.target):tp.y;
      segments.push({edge,a:{x:sp.x+execweaveWidthOf(edge.source)/2,y:sy+execweaveHeightOf(edge.source)/2},b:{x:tp.x+execweaveWidthOf(edge.target)/2,y:ty+execweaveHeightOf(edge.target)/2}});
    }
    let count=0;
    for(let i=0;i<segments.length;i++)for(let j=i+1;j<segments.length;j++){
      const A=segments[i],B=segments[j];
      if(A.edge.source===B.edge.source||A.edge.source===B.edge.target||A.edge.target===B.edge.source||A.edge.target===B.edge.target)continue;
      if(pr70SegmentsCross(A.a,A.b,B.a,B.b))count++;
    }
    return count;
  }
  function execweaveRestorePriorYUnlessWorse(priorY,_topo){
    const newCrossings=pr70StraightCrossings(),priorCrossings=pr70StraightCrossings(priorY);
    if(priorCrossings<=newCrossings){
      for(const [id,y] of priorY){const p=positions.get(id);if(p&&Number.isFinite(y))p.y=y}
      return{restored:true,priorCrossings,newCrossings};
    }
    return{restored:false,priorCrossings,newCrossings};
  }

  if(typeof window!=='undefined')window.__execweavePr70={
    projectionRepair:pr70ProjectionRepair,
    crossingCount:()=>pr70StraightCrossings(),
    routeFor:id=>{const edge=edgeById.get(id);return edge?execweaveRoute(edge):null},
    topology:()=>execweaveTopology,
  };
})();
""".strip()


_PRIOR_Y_RESTORE = (
    "for(const [id,y] of priorY){const p=positions.get(id);"
    "if(p&&Number.isFinite(y))p.y=y}"
)
_PRIOR_Y_GATED = (
    "if(typeof execweaveRestorePriorYUnlessWorse==='function')"
    "execweaveRestorePriorYUnlessWorse(priorY,execweaveTopology);"
    "else " + _PRIOR_Y_RESTORE
)
_STARTUP_SEAM = "applyTheme(initialTheme());applyTransform();poll();"


def inject_pr70_dashboard_repairs(html: str) -> str:
    """Install projection/decross repairs in the shared live + static Dashboard."""
    if _PRIOR_Y_RESTORE not in html:
        raise RuntimeError("PR70 live Y-stability seam changed")
    html = html.replace(_PRIOR_Y_RESTORE, _PRIOR_Y_GATED, 1)
    if _STARTUP_SEAM not in html:
        raise RuntimeError("PR70 dashboard startup seam changed")
    return html.replace(_STARTUP_SEAM, PR70_DASHBOARD_SCRIPT + "\n" + _STARTUP_SEAM, 1)
