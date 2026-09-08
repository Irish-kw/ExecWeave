from __future__ import annotations

from .viewer_projection_bridges import PROJECTION_SCRIPT


# PR70 keeps the raw evidence graph untouched.  These repairs run only in the shared
# Dashboard shell, after the normal dashboard projection and Dagre layout have been
# installed.  The projection repair exposes a conservative viewer-only bridge through
# hidden provider/detail nodes; the geometry repair keeps Dagre's real route points and
# lets a live update reflow Y only when it strictly reduces crossings.
PR70_DASHBOARD_SCRIPT = PROJECTION_SCRIPT + "\n" + r"""
(function(){
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
    projectionRepair:window.__execweaveProjectionRepair,
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
