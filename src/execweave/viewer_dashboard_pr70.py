from __future__ import annotations

from .viewer_projection_bridges import PROJECTION_SCRIPT
from .viewer_layout_geometry import LAYOUT_GEOMETRY_SCRIPT


PR70_DASHBOARD_SCRIPT = PROJECTION_SCRIPT + "\n" + LAYOUT_GEOMETRY_SCRIPT + "\n" + r"""
(function(){
  let geometryTopology=null,geometrySignature='';
  function signature(topo){
    return [...positions].map(([id,p])=>`${id}:${p.x},${p.y},${topo.width?.get(id)},${topo.height?.get(id)}`).join('|');
  }
  function pr70Ports(edge,topo,placement){
    const sp=placement.get(edge.source)||{x:0,y:0},tp=placement.get(edge.target)||{x:0,y:0};
    const sw=topo.width?.get(edge.source)||execweaveWidthOf(edge.source),tw=topo.width?.get(edge.target)||execweaveWidthOf(edge.target);
    const forward=tp.x+tw/2>=sp.x+sw/2;
    const y=(id,p,port)=>{const h=topo.height?.get(id)||execweaveHeightOf(id);return p.y+(!port||port.total<=1?h/2:10+(h-20)*port.index/(port.total-1))};
    const source={x:forward?sp.x+sw:sp.x,y:y(edge.source,sp,topo.sourcePort.get(edgeId(edge)))};
    const target={x:forward?tp.x:tp.x+tw,y:y(edge.target,tp,topo.targetPort.get(edgeId(edge)))};
    return{source,target,forward};
  }
  function retarget(points,source,target){
    const first=points[0],last=points[points.length-1];
    return points.map((point,index)=>{
      const t=index/(points.length-1),u=1-t;
      // Affinely map the Dagre corridor onto the actual side ports. Translating
      // endpoints alone preserves obsolete vertical excursions after lane packing.
      const axis=(key)=>Math.abs(last[key]-first[key])>1e-7
        ?source[key]+(point[key]-first[key])/(last[key]-first[key])*(target[key]-source[key])
        :point[key]+(source[key]-first[key])*u+(target[key]-last[key])*t;
      return{x:axis('x'),y:axis('y')};
    });
  }
  function pr70RetargetDagreRoutePoints(topo){
    if(!(topo?.routePoints instanceof Map))return topo;
    // Never retarget an already retargeted path. These immutable points remain the
    // provenance of every subsequent render, collision adjustment and manual drag.
    if(!topo.rawDagreRoutePoints)topo.rawDagreRoutePoints=new Map([...topo.routePoints].map(([k,p])=>[k,p.map(v=>({...v}))]));
    const representatives=new Map();
    for(const edge of [...edgeById.values()].sort((a,b)=>edgeId(a).localeCompare(edgeId(b)))){
      const key=`${edge.source}\u0000${edge.target}`;if(!representatives.has(key))representatives.set(key,edge);
    }
    for(const [key,points] of topo.rawDagreRoutePoints){
      const edge=representatives.get(key);if(!edge||points.length<2)continue;
      const ports=pr70Ports(edge,topo,topo.spec);
      topo.routePoints.set(key,retarget(points,ports.source,ports.target));
    }
    return topo;
  }
  function syncGeometry(){
    const topo=execweaveTopology,next=signature(topo);
    if(geometryTopology===topo&&geometrySignature===next)return;
    for(const [id,p] of positions){const s=topo.spec.get(id);if(s){s.x=p.x;s.y=p.y}}
    if(typeof execweaveRecomputePorts==='function')execweaveRecomputePorts(topo);
    pr70RetargetDagreRoutePoints(topo);
    geometryTopology=topo;geometrySignature=next;
  }
  const pr70BuildTopologyBase=execweaveBuildTopology;
  execweaveBuildTopology=function(){
    const topo=pr70BuildTopologyBase();
    return optimize(pr70RetargetDagreRoutePoints(topo));
  };
  const pr70RouteBase=execweaveRoute;
  const routeCache=new Map();
  function route(edge){
    const topo=execweaveTopology,bundle=topo.bundleByEdge.get(edgeId(edge));
    if(bundle&&bundle.size>1){
      const base=pr70RouteBase(edge),pts=execweaveGeometry.polyline(base.d);
      if(!pts||pts.length!==4)return base;
      const [a,,,b]=pts,rail=pts[1].x;
      const boxes=[...positions].filter(([id])=>id!==edge.source&&id!==edge.target).map(([id,p])=>
        ({x:p.x,y:p.y,w:topo.width?.get(id)||execweaveWidthOf(id),h:topo.height?.get(id)||execweaveHeightOf(id)}));
      const candidates=[rail,...boxes.flatMap(box=>[box.x-2,box.x+box.w+2])]
        .filter(x=>x>=Math.min(a.x,b.x)&&x<=Math.max(a.x,b.x)).sort((x,y)=>Math.abs(x-rail)-Math.abs(y-rail)||x-y);
      for(const x of candidates){
        const p={x,y:a.y},q={x,y:b.y};
        if(boxes.some(box=>execweaveGeometry.throughBox(a,p,box)||execweaveGeometry.throughBox(p,q,box)||execweaveGeometry.throughBox(q,b,box)))continue;
        return{...base,d:`M ${a.x} ${a.y} H ${x} V ${b.y} H ${b.x}`,labelX:(x+b.x)/2};
      }
      return base;
    }
    if(typeof execweaveIsStopped==='function'&&execweaveIsStopped(edge))return pr70RouteBase(edge);
    const points=topo.rawDagreRoutePoints?.get(`${edge.source}\u0000${edge.target}`);
    if(!points||points.length<2)return pr70RouteBase(edge);
    const ports=pr70Ports(edge,topo,positions),adjusted=retarget(points,ports.source,ports.target);
    const boxes=[...positions].filter(([id])=>id!==edge.source&&id!==edge.target).map(([id,p])=>
      ({id,x:p.x,y:p.y,w:topo.width?.get(id)||execweaveWidthOf(id),h:topo.height?.get(id)||execweaveHeightOf(id)}));
    const cacheKey=JSON.stringify([adjusted,boxes]);
    let clearance=routeCache.get(cacheKey);
    if(!clearance){clearance=execweaveGeometry.avoidNodes(adjusted,boxes);if(routeCache.size>=2048)routeCache.delete(routeCache.keys().next().value);routeCache.set(cacheKey,clearance)}
    const d=clearance.points.map((p,i)=>`${i?'L':'M'} ${p.x} ${p.y}`).join(' ');
    const label=clearance.points[Math.floor(clearance.points.length/2)];
    const spawn=typeof execweaveIsSpawn==='function'&&execweaveIsSpawn(edge);
    return{d,labelX:label.x,labelY:label.y-8,kind:spawn?'spawn':(ports.forward?'forward':'reverse'),
      geometryKind:'dagre-polyline',bundle:null,usesDagrePoints:true,obstacleDetours:clearance.detours,obstructedDagreGuides:clearance.obstructedGuides};
  }
  execweaveRoute=function(edge){syncGeometry();return route(edge)};

  function currentMetrics(){
    syncGeometry();
    const nodes=[...positions].filter(([id])=>nodeById.has(id)).map(([id,p])=>({id,x:p.x,y:p.y,w:execweaveWidthOf(id),h:execweaveHeightOf(id)}));
    const edges=[...edgeById.values()].filter(e=>positions.has(e.source)&&positions.has(e.target)).map(e=>({...e,d:route(e).d}));
    return execweaveGeometry.measure(nodes,edges);
  }
  function paint(){
    syncGeometry();
    for(const [id,p] of positions){const group=nodeElements.get(id);if(group)group.setAttribute('transform',`translate(${p.x} ${p.y})`)}
    for(const edge of edgeById.values())updateEdgeElement(edge);
  }
  function restore(priorY,topo){
    if(!priorY.size)return{restored:false,reason:'initial'};
    const next=new Map([...positions].map(([id,p])=>[id,{...p}]));
    const newMetrics=currentMetrics(),newCrossings=newMetrics.EDGE_CROSSINGS;
    for(const [id,y] of priorY){const p=positions.get(id);if(p&&Number.isFinite(y))p.y=y}
    if(typeof execweaveSeparateOverlappingNodes==='function')execweaveSeparateOverlappingNodes({spec:positions});
    const priorMetrics=currentMetrics(),priorCrossings=priorMetrics.EDGE_CROSSINGS;
    const restored=priorCrossings<=newCrossings&&priorMetrics.NODE_OVERLAPS===0&&priorMetrics.EDGE_NODE_INTERSECTIONS<=newMetrics.EDGE_NODE_INTERSECTIONS;
    if(!restored)positions=next;
    syncGeometry();
    topo.liveDecross={restored,priorCrossings,newCrossings,priorMetrics,newMetrics};
    return topo.liveDecross;
  }
  const layoutCache=new Map();
  function optimize(topo){
    if(typeof document==='undefined'||typeof nodeById==='undefined'||!topo.spec?.size)return topo;
    const previousTopology=execweaveTopology,previousPositions=positions;
    execweaveTopology=topo;
    positions=new Map([...topo.spec].map(([id,s])=>[id,{x:s.x,y:s.y}]));
    geometryTopology=null;
    try{
      const inputKey=JSON.stringify({nodes:[...topo.spec].map(([id,s])=>[id,s.x,s.y,topo.width.get(id),topo.height.get(id)]).sort(),
        edges:[...edgeById.values()].map(e=>[edgeId(e),e.source,e.target,e.relation]).sort()});
      if(layoutCache.has(inputKey)){
        const hit=layoutCache.get(inputKey);
        for(const [id,y] of hit.ys)positions.get(id).y=y;
        syncGeometry();topo.layoutQuality=hit.diagnostics;return topo;
      }
      const started=performance.now(),postDagre=currentMetrics();
      const dagrePositions=new Map([...positions].map(([id,p])=>[id,{...p}]));
      for(const [id,p] of positions){const before=topo.dagrePipeline?.stages?.PRE_DAGRE?.get(id);if(before)p.y=before.y}
      if(typeof execweaveSeparateOverlappingNodes==='function')execweaveSeparateOverlappingNodes({spec:positions});
      const preLayout=currentMetrics();
      if(postDagre.NODE_OVERLAPS===0&&(preLayout.NODE_OVERLAPS>0||postDagre.EDGE_CROSSINGS<=preLayout.EDGE_CROSSINGS))positions=dagrePositions;
      let best=currentMetrics(),evaluations=0;
      // Bound work by displayed edges, never elapsed time: identical payloads must
      // produce identical geometry on slow and fast hosts. Hitting the budget is
      // diagnostic, not a claim of global optimality.
      const budget=Math.max(24,Math.min(512,Math.floor(24000/Math.max(1,edgeById.size))));
      const crossingCeiling=best.EDGE_CROSSINGS;
      const better=m=>m.NODE_OVERLAPS===0&&m.EDGE_CROSSINGS<=crossingCeiling&&
        (m.EDGE_NODE_INTERSECTIONS<best.EDGE_NODE_INTERSECTIONS||
         m.EDGE_NODE_INTERSECTIONS===best.EDGE_NODE_INTERSECTIONS&&m.EDGE_CROSSINGS<best.EDGE_CROSSINGS);
      const lanes=['model','tool','file','endpoint','agent'];
      const eligible=id=>lanes.includes(topo.spec.get(id)?.lane)&&!topo.secondaryPackedIds?.has(id);
      const attempt=()=>{evaluations++;const m=currentMetrics();if(better(m)){best=m;return true}return false};
      for(let round=0;round<2&&evaluations<budget;round++){
        let changed=false;
        for(const lane of lanes){
          const ids=[...positions.keys()].filter(id=>eligible(id)&&topo.spec.get(id).lane===lane)
            .sort((a,b)=>positions.get(a).y-positions.get(b).y||a.localeCompare(b));
          for(let i=1;i<ids.length&&evaluations<budget;i++){
            const a=positions.get(ids[i]),b=positions.get(ids[i-1]),ay=a.y,by=b.y;
            a.y=by;b.y=ay;if(attempt())changed=true;else{a.y=ay;b.y=by}
          }
        }
        const ids=[...positions.keys()].filter(eligible).sort((a,b)=>lanes.indexOf(topo.spec.get(a).lane)-lanes.indexOf(topo.spec.get(b).lane)||a.localeCompare(b));
        for(const id of ids){
          const p=positions.get(id),old=p.y,h=execweaveHeightOf(id);
          const candidates=[...new Set([...positions].filter(([k])=>k!==id&&!topo.secondaryPackedIds?.has(k))
            .flatMap(([k,v])=>[v.y-h-24,v.y+execweaveHeightOf(k)+24]))]
            .sort((a,b)=>Math.abs(a-old)-Math.abs(b-old)||a-b);
          for(const y of candidates){
            if(evaluations>=budget)break;
            const before=p.y;p.y=y;if(attempt())changed=true;else p.y=before;
          }
        }
        if(!changed)break;
      }
      syncGeometry();
      topo.layoutQuality={pre:preLayout,dagre:postDagre,final:currentMetrics(),evaluations,budget,
        budget_exhausted:evaluations>=budget,elapsed_ms:performance.now()-started};
      if(layoutCache.size>=16)layoutCache.delete(layoutCache.keys().next().value);
      layoutCache.set(inputKey,{ys:[...positions].map(([id,p])=>[id,p.y]),diagnostics:topo.layoutQuality});
      return topo;
    }finally{positions=previousPositions;execweaveTopology=previousTopology;geometryTopology=null}
  }

  function clearLabelFromNodes(label){
    // Solve placement using the rendered text box, never estimated characters.
    // At the existing route-label X, each overlapping node forbids one interval
    // of text-baseline Y values. The nearest endpoint of their merged union is
    // the minimum vertical displacement that keeps the whole label readable.
    // This changes text placement only: topology, node positions and SVG routes
    // remain exactly the ones selected by the layout/port pipeline.
    const box=label.getBBox(),baseline=Number(label.getAttribute('y'));
    if(!(box.width>0&&box.height>0&&Number.isFinite(baseline)))return;
    const padding=2,offset=box.y-baseline,intervals=[];
    for(const [id,p] of positions){
      if(!nodeById.has(id))continue;
      const w=execweaveWidthOf(id),h=execweaveHeightOf(id);
      if(box.x+box.width<=p.x-padding||box.x>=p.x+w+padding)continue;
      intervals.push([p.y-padding-box.height-offset,p.y+h+padding-offset]);
    }
    intervals.sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
    const merged=[];
    for(const current of intervals){
      const last=merged[merged.length-1];
      if(last&&current[0]<=last[1])last[1]=Math.max(last[1],current[1]);
      else merged.push([...current]);
    }
    for(const [lo,hi] of merged){
      if(baseline>lo&&baseline<hi){
        label.setAttribute('y',baseline-lo<=hi-baseline?lo:hi);
        break;
      }
    }
  }

  if(typeof updateEdgeElement==='function'){
  const updateBase=updateEdgeElement;
  updateEdgeElement=function(edge){
    updateBase(edge);const els=edgeElements.get(edgeId(edge));if(!els)return;
    const r=route(edge);els.visible.dataset.geometryKind=r.geometryKind||r.kind;
    els.hit.dataset.geometryKind=r.geometryKind||r.kind;
    clearLabelFromNodes(els.label);
  };
  }
  if(typeof execweaveRefreshIncidentEdges==='function')execweaveRefreshIncidentEdges=function(){paint()};
  window.__execweavePr70={projectionRepair:window.__execweaveProjectionRepair,
    crossingCount:()=>currentMetrics().EDGE_CROSSINGS,metrics:currentMetrics,
    routeFor:id=>{const edge=edgeById.get(id);return edge?execweaveRoute(edge):null},
    topology:()=>execweaveTopology,syncGeometry,restorePrior:restore,paint,
    diagnostics:()=>({live:execweaveTopology.liveDecross||null,layout:execweaveTopology.layoutQuality||null})};
})();
// The callsite is in the shared dashboard scope, not inside the installer IIFE.
function execweaveRestorePriorYUnlessWorse(priorY,topo){
  return window.__execweavePr70.restorePrior(priorY,topo);
}
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
