from __future__ import annotations


_STARTUP_SEAM = "applyTheme(initialTheme());applyTransform();poll();"

EDGE_DECROSS_SCRIPT = r"""
(function(){
  if(typeof execweaveRoute!=='function'||typeof execweaveGeometry==='undefined')return;
  const baseRoute=execweaveRoute;
  const relation=edge=>String(edge?.relation||'').toUpperCase();
  const nodeType=id=>String(typeof nodeById!=='undefined'?nodeById.get(id)?.type||'':'').toLowerCase();
  const isNetworkEdge=edge=>relation(edge)==='CONNECTED_TO'||
    nodeType(edge?.source)==='network_endpoint'||nodeType(edge?.target)==='network_endpoint';
  const routePoints=edge=>{
    const route=baseRoute(edge);
    const points=route?.d?execweaveGeometry.polyline(route.d):null;
    return{route,points};
  };
  const segments=points=>{
    const result=[];
    for(let i=1;i<(points?.length||0);i++)result.push({a:points[i-1],b:points[i]});
    return result;
  };
  const crossesAny=(points,protectedSegments)=>{
    for(let i=1;i<(points?.length||0);i++)for(const segment of protectedSegments)
      if(execweaveGeometry.crosses(points[i-1],points[i],segment.a,segment.b))return true;
    return false;
  };

  execweaveRoute=function(edge){
    const {route,points}=routePoints(edge);
    if(!route||!points||points.length<2||isNetworkEdge(edge)||route.kind==='bundle'||route.kind==='lifecycle-return')return route;
    if(typeof edgeById==='undefined'||typeof positions==='undefined'||!execweaveTopology)return route;

    const protectedSegments=[];
    for(const peer of edgeById.values()){
      if(edgeId(peer)===edgeId(edge)||!isNetworkEdge(peer))continue;
      const peerPoints=routePoints(peer).points;
      if(peerPoints?.length>=2)protectedSegments.push(...segments(peerPoints));
    }
    if(!protectedSegments.length||!crossesAny(points,protectedSegments))return route;

    const boxes=[...positions]
      .filter(([id])=>id!==edge.source&&id!==edge.target&&nodeById.has(id))
      .map(([id,p])=>({
        id,x:p.x,y:p.y,
        w:execweaveTopology.width?.get(id)||execweaveWidthOf(id),
        h:execweaveTopology.height?.get(id)||execweaveHeightOf(id),
      }));
    const detour=execweaveGeometry.avoidCrossings(points,boxes,protectedSegments,8);
    if(!detour||detour.crossingsAvoided<=0||detour.points.length<2)return route;
    const d=detour.points.map((point,index)=>`${index?'L':'M'} ${point.x} ${point.y}`).join(' ');
    const label=detour.points[Math.floor(detour.points.length/2)];
    return{
      ...route,d,labelX:label.x,labelY:label.y-8,
      geometryKind:'edge-decrossover',
      edgeCrossingDetours:detour.detours,
      protectedNetworkCrossingsAvoided:detour.crossingsAvoided,
    };
  };

  if(typeof updateEdgeElement==='function'){
    const updateBase=updateEdgeElement;
    updateEdgeElement=function(edge){
      // The existing PR70 wrapper already computes label placement and then clears
      // it from rendered node boxes. Do not overwrite that cleared label position.
      updateBase(edge);
      const route=execweaveRoute(edge);
      if(route?.geometryKind!=='edge-decrossover'||!route.d)return;
      const els=edgeElements.get(edgeId(edge));if(!els)return;
      // The base renderer normally sees the dynamically replaced execweaveRoute.
      // Reapply only the path as a final authority guard; leave the label untouched.
      els.visible.setAttribute('d',route.d);els.hit.setAttribute('d',route.d);
      els.visible.dataset.geometryKind=route.geometryKind;
      els.hit.dataset.geometryKind=route.geometryKind;
    };
  }

  const renderedMetrics=()=>{
    if(typeof positions==='undefined'||typeof edgeById==='undefined'||typeof nodeById==='undefined')return null;
    const nodes=[...positions]
      .filter(([id])=>nodeById.has(id))
      .map(([id,p])=>({
        id,x:p.x,y:p.y,
        w:execweaveTopology?.width?.get(id)||execweaveWidthOf(id),
        h:execweaveTopology?.height?.get(id)||execweaveHeightOf(id),
      }));
    const edges=[...edgeById.values()]
      .filter(edge=>positions.has(edge.source)&&positions.has(edge.target))
      .map(edge=>({...edge,d:execweaveRoute(edge).d}));
    return execweaveGeometry.measure(nodes,edges);
  };

  // PR70's optimizer deliberately keeps its own pre-decrossover route family, but
  // public metrics are a rendered-SVG diagnostic contract. Report the final paths
  // users actually see so metric parity cannot drift after this local routing pass.
  if(window.__execweavePr70&&typeof window.__execweavePr70.metrics==='function'){
    const metricsBase=window.__execweavePr70.metrics.bind(window.__execweavePr70);
    window.__execweavePr70.metrics=()=>renderedMetrics()||metricsBase();
    window.__execweavePr70.crossingCount=()=>window.__execweavePr70.metrics().EDGE_CROSSINGS;
  }

  window.__execweaveEdgeDecross={
    version:2,
    routeFor:id=>{const edge=typeof edgeById!=='undefined'?edgeById.get(id):null;return edge?execweaveRoute(edge):null},
    metrics:renderedMetrics,
  };
})();
""".strip()


def inject_edge_decross(html: str) -> str:
    """Prefer local route detours over moving nodes across network evidence edges."""

    if html.count(_STARTUP_SEAM) != 1:
        raise RuntimeError("edge-decrossover startup seam changed")
    return html.replace(_STARTUP_SEAM, EDGE_DECROSS_SCRIPT + "\n" + _STARTUP_SEAM, 1)
