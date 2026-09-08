from __future__ import annotations

_STARTUP_SEAM = "applyTheme(initialTheme());applyTransform();poll();"
_BAND_GAP_SEAM = "const EXECWEAVE_BAND_GAP=170;"
_PACKING_SEAM = """  const columns=Math.max(1,Math.ceil(Math.sqrt(compBoxes.length)));
  const widest=compBoxes.reduce((width,box)=>Math.max(width,box.w),0);
  const packingWidth=Math.max(spineWidth,columns*widest+(columns-1)*bandGap);"""
_PACKING_REPLACEMENT = """  const columns=Math.max(1,Math.ceil(Math.sqrt(compBoxes.length)));
  const widest=compBoxes.reduce((width,box)=>Math.max(width,box.w),0);
  const packingWidth=typeof execweaveLayoutV2PackingWidth==='function'
    ?execweaveLayoutV2PackingWidth(compBoxes,spineWidth,bandGap)
    :Math.max(spineWidth,columns*widest+(columns-1)*bandGap);"""
_SYNC_ORDER_SEAM = """    for(const [id,p] of positions){const s=topo.spec.get(id);if(s){s.x=p.x;s.y=p.y}}
    if(typeof execweaveRecomputePorts==='function')execweaveRecomputePorts(topo);"""
_SYNC_ORDER_REPLACEMENT = """    for(const [id,p] of positions){const s=topo.spec.get(id);if(s){s.x=p.x;s.y=p.y}}
    if(typeof execweaveLayoutV2SyncFinalOrder==='function')execweaveLayoutV2SyncFinalOrder(topo,positions);
    if(typeof execweaveRecomputePorts==='function')execweaveRecomputePorts(topo);"""
_BUS_ROUTE_SEAM = """  function route(edge){
    const topo=execweaveTopology,bundle=topo.bundleByEdge.get(edgeId(edge));
    if(bundle&&bundle.size>1){"""
_BUS_ROUTE_REPLACEMENT = """  function route(edge){
    const topo=execweaveTopology,bundle=topo.bundleByEdge.get(edgeId(edge));
    if(bundle&&bundle.size>1&&typeof execweaveLayoutV2BusRoute==='function'){
      const layoutV2Bus=execweaveLayoutV2BusRoute(edge);
      if(layoutV2Bus)return layoutV2Bus;
    }
    if(bundle&&bundle.size>1){"""
_INPUT_KEY_SEAM = """      const inputKey=JSON.stringify({nodes:[...topo.spec].map(([id,s])=>[id,s.x,s.y,topo.width.get(id),topo.height.get(id)]).sort(),
        edges:[...edgeById.values()].map(e=>[edgeId(e),e.source,e.target,e.relation]).sort()});"""
_INPUT_KEY_REPLACEMENT = """      const layoutMode=(typeof window!=='undefined'&&window.__execweaveLayoutV2Mode)||'live';
      const inputKey=JSON.stringify({mode:layoutMode,nodes:[...topo.spec].map(([id,s])=>[id,s.x,s.y,topo.width.get(id),topo.height.get(id)]).sort(),
        edges:[...edgeById.values()].map(e=>[edgeId(e),e.source,e.target,e.relation]).sort()});"""
_BUDGET_SEAM = "      const budget=Math.max(24,Math.min(512,Math.floor(24000/Math.max(1,edgeById.size))));"
_BUDGET_REPLACEMENT = """      const budget=layoutMode==='arrange'
        ?Math.max(96,Math.min(1024,Math.floor(48000/Math.max(1,edgeById.size))))
        :Math.max(24,Math.min(512,Math.floor(24000/Math.max(1,edgeById.size))));"""
_BETTER_SEAM = """      const crossingCeiling=best.EDGE_CROSSINGS;
      const better=m=>m.NODE_OVERLAPS===0&&m.EDGE_CROSSINGS<=crossingCeiling&&
        (m.EDGE_NODE_INTERSECTIONS<best.EDGE_NODE_INTERSECTIONS||
         m.EDGE_NODE_INTERSECTIONS===best.EDGE_NODE_INTERSECTIONS&&m.EDGE_CROSSINGS<best.EDGE_CROSSINGS);"""
_BETTER_REPLACEMENT = """      const quality=m=>(m.NODE_DENSITY||0)-.10*(m.ASPECT_ERROR||0)-.04*Math.max(0,(m.P95_EDGE_STRETCH||1)-1);
      const better=m=>{
        if(m.NODE_OVERLAPS!==0||m.EDGE_NODE_INTERSECTIONS>best.EDGE_NODE_INTERSECTIONS)return false;
        if(m.EDGE_CROSSINGS>best.EDGE_CROSSINGS)return false;
        if(m.EDGE_NODE_INTERSECTIONS<best.EDGE_NODE_INTERSECTIONS||m.EDGE_CROSSINGS<best.EDGE_CROSSINGS)return true;
        return quality(m)>quality(best)+1e-9;
      };"""
_ROUNDS_SEAM = "      for(let round=0;round<2&&evaluations<budget;round++){"
_ROUNDS_REPLACEMENT = "      for(let round=0;round<(layoutMode==='arrange'?4:2)&&evaluations<budget;round++){"
_ARRANGE_SEAM = """function execweaveArrangePositions(){
  execweaveTopology=execweaveBuildTopology();"""
_ARRANGE_REPLACEMENT = """function execweaveArrangePositions(){
  const execweavePriorLayoutV2Mode=(typeof window!=='undefined'&&window.__execweaveLayoutV2Mode)||'live';
  if(typeof window!=='undefined')window.__execweaveLayoutV2Mode='arrange';
  try{execweaveTopology=execweaveBuildTopology()}
  finally{if(typeof window!=='undefined')window.__execweaveLayoutV2Mode=execweavePriorLayoutV2Mode}"""

LAYOUT_V2_SCRIPT = r"""
(function(){
  window.__execweaveLayoutV2Mode=window.__execweaveLayoutV2Mode||'live';

  function execweaveLayoutV2SyncFinalOrder(topo=execweaveTopology,placement=positions){
    if(!topo?.spec||!(placement instanceof Map))return new Map();
    const byLane=new Map();
    for(const [id,p] of placement){
      const spec=topo.spec.get(id);
      if(!spec||!Number.isFinite(p?.y))continue;
      if(!Object.prototype.hasOwnProperty.call(spec,'semanticOrder'))spec.semanticOrder=spec.order;
      const key=String(spec.lane||'other');
      if(!byLane.has(key))byLane.set(key,[]);
      byLane.get(key).push(id);
    }
    const finalOrder=new Map();
    for(const ids of byLane.values()){
      ids.sort((a,b)=>{
        const ap=placement.get(a),bp=placement.get(b);
        return (ap.y-bp.y)||(ap.x-bp.x)||String(a).localeCompare(String(b));
      });
      ids.forEach((id,index)=>{
        const spec=topo.spec.get(id);
        if(spec)spec.order=index;
        finalOrder.set(id,index);
      });
    }
    topo.finalOrder=finalOrder;
    return finalOrder;
  }
  window.execweaveLayoutV2SyncFinalOrder=execweaveLayoutV2SyncFinalOrder;

  function execweaveLayoutV2ViewportAspect(){
    try{
      const el=(typeof svg!=='undefined'&&svg)||document.getElementById('svg');
      const box=el&&typeof el.getBoundingClientRect==='function'?el.getBoundingClientRect():null;
      const value=box&&box.width>0&&box.height>0?box.width/box.height:16/9;
      return Math.max(1.2,Math.min(2.4,value));
    }catch(_){return 16/9}
  }

  function execweaveLayoutV2PackingWidth(boxes,spineWidth,gap){
    if(!Array.isArray(boxes)||!boxes.length)return spineWidth;
    const targetAspect=execweaveLayoutV2ViewportAspect();
    const totalArea=boxes.reduce((sum,box)=>sum+Math.max(1,box.w+gap)*Math.max(1,box.h+gap),0);
    const widest=boxes.reduce((width,box)=>Math.max(width,box.w),0);
    const base=Math.max(spineWidth,widest,Math.sqrt(totalArea*targetAspect));
    const candidates=[spineWidth,widest,...[.78,.9,1,1.12,1.28].map(scale=>base*scale)]
      .map(value=>Math.max(widest,value))
      .sort((a,b)=>a-b)
      .filter((value,index,list)=>index===0||Math.abs(value-list[index-1])>1);
    let bestWidth=candidates[0],bestCost=Infinity;
    for(const width of candidates){
      let x=0,y=0,rowHeight=0,maxRight=0;
      for(const box of boxes){
        if(x>0&&x+box.w>width){x=0;y+=rowHeight+gap;rowHeight=0}
        maxRight=Math.max(maxRight,x+box.w);
        rowHeight=Math.max(rowHeight,box.h);
        x+=box.w+gap;
      }
      const height=Math.max(1,y+rowHeight),usedWidth=Math.max(1,maxRight);
      const area=usedWidth*height;
      const aspectError=Math.abs(Math.log((usedWidth/height)/targetAspect));
      const cost=area*(1+.28*aspectError);
      if(cost<bestCost-1e-6||(Math.abs(cost-bestCost)<=1e-6&&width<bestWidth)){bestCost=cost;bestWidth=width}
    }
    return Math.max(spineWidth,bestWidth);
  }
  window.execweaveLayoutV2PackingWidth=execweaveLayoutV2PackingWidth;

  function execweaveLayoutV2HubInversionRate(){
    if(typeof edgeById==='undefined'||typeof positions==='undefined'||!execweaveTopology?.targetPort)return 0;
    const incoming=new Map();
    for(const edge of edgeById.values()){
      if(!positions.has(edge.source)||!positions.has(edge.target))continue;
      const target=typeof nodeById!=='undefined'?nodeById.get(edge.target):null;
      const lane=target?String(execweaveTopology.spec.get(target.id)?.lane||''):'';
      if(lane!=='tool'&&lane!=='model')continue;
      if(!incoming.has(edge.target))incoming.set(edge.target,[]);
      incoming.get(edge.target).push(edge);
    }
    let worst=0;
    for(const edges of incoming.values()){
      if(edges.length<3)continue;
      const ordered=[...edges].sort((a,b)=>{
        const ap=positions.get(a.source),bp=positions.get(b.source);
        return (ap.y-bp.y)||(ap.x-bp.x)||edgeId(a).localeCompare(edgeId(b));
      });
      const slots=ordered.map(edge=>execweaveTopology.targetPort.get(edgeId(edge))?.index??0);
      let inv=0;
      for(let i=0;i<slots.length;i++)for(let j=0;j<i;j++)if(slots[j]>slots[i])inv++;
      worst=Math.max(worst,inv/Math.max(1,slots.length*(slots.length-1)/2));
    }
    return worst;
  }

  function execweaveLayoutV2OrderMismatches(){
    if(typeof positions==='undefined'||!execweaveTopology?.spec)return 0;
    const byLane=new Map();
    for(const [id,p] of positions){
      const spec=execweaveTopology.spec.get(id);if(!spec)continue;
      const lane=String(spec.lane||'other');
      if(!byLane.has(lane))byLane.set(lane,[]);
      byLane.get(lane).push([id,p,spec]);
    }
    let mismatches=0;
    for(const rows of byLane.values()){
      rows.sort((a,b)=>(a[1].y-b[1].y)||(a[1].x-b[1].x)||String(a[0]).localeCompare(String(b[0])));
      rows.forEach((row,index)=>{if(Number(row[2].order)!==index)mismatches++});
    }
    return mismatches;
  }

  const layoutV2MeasureBase=execweaveGeometry.measure.bind(execweaveGeometry);
  execweaveGeometry.measure=function(nodes,edges){
    const metrics=layoutV2MeasureBase(nodes,edges);
    if(!nodes.length)return{...metrics,CROSSINGS_PER_EDGE:0,CROSSING_SPAN_RATE:0,NODE_DENSITY:0,ASPECT_ERROR:0,P95_EDGE_STRETCH:0,HUB_PORT_INVERSION_RATE:0,FINAL_ORDER_AUTHORITY_MISMATCHES:0};
    const left=Math.min(...nodes.map(n=>n.x)),right=Math.max(...nodes.map(n=>n.x+n.w));
    const top=Math.min(...nodes.map(n=>n.y)),bottom=Math.max(...nodes.map(n=>n.y+n.h));
    const width=Math.max(1,right-left),height=Math.max(1,bottom-top);
    const nodeArea=nodes.reduce((sum,n)=>sum+Math.max(0,n.w*n.h),0);
    const density=nodeArea/(width*height);
    const targetAspect=execweaveLayoutV2ViewportAspect();
    const aspectError=Math.abs(Math.log((width/height)/targetAspect));
    const routes=edges.map(edge=>{
      const points=execweaveGeometry.sample(edge.d);
      return{edge,points,left:Math.min(...points.map(p=>p.x)),right:Math.max(...points.map(p=>p.x)),
        top:Math.min(...points.map(p=>p.y)),bottom:Math.max(...points.map(p=>p.y))};
    });
    let spanPairs=0;
    for(let i=0;i<routes.length;i++)for(let j=0;j<i;j++){
      const a=routes[i],b=routes[j],ae=a.edge,be=b.edge;
      if(ae.source===be.source||ae.source===be.target||ae.target===be.source||ae.target===be.target)continue;
      if(a.right<b.left||b.right<a.left||a.bottom<b.top||b.bottom<a.top)continue;
      spanPairs++;
    }
    const stretch=routes.map(({points})=>{
      let length=0;
      for(let i=1;i<points.length;i++)length+=Math.hypot(points[i].x-points[i-1].x,points[i].y-points[i-1].y);
      const first=points[0],last=points[points.length-1];
      const lower=Math.max(1,Math.hypot(last.x-first.x,last.y-first.y));
      return length/lower;
    }).sort((a,b)=>a-b);
    return{...metrics,
      CROSSINGS_PER_EDGE:metrics.EDGE_CROSSINGS/Math.max(1,edges.length),
      CROSSING_SPAN_RATE:metrics.EDGE_CROSSINGS/Math.max(1,spanPairs),
      NODE_DENSITY:density,
      ASPECT_ERROR:aspectError,
      P95_EDGE_STRETCH:stretch[Math.max(0,Math.ceil(stretch.length*.95)-1)]||0,
      HUB_PORT_INVERSION_RATE:execweaveLayoutV2HubInversionRate(),
      FINAL_ORDER_AUTHORITY_MISMATCHES:execweaveLayoutV2OrderMismatches(),
      GRAPH_BBOX_WIDTH:width,GRAPH_BBOX_HEIGHT:height};
  };

  function execweaveLayoutV2BusRoute(edge){
    if(typeof edgeById==='undefined'||typeof positions==='undefined'||!execweaveTopology?.bundleByEdge)return null;
    if(typeof execweaveIsStopped==='function'&&execweaveIsStopped(edge))return null;
    const bundle=execweaveTopology.bundleByEdge.get(edgeId(edge));
    if(!bundle||bundle.size<2)return null;
    const members=[...edgeById.values()].filter(candidate=>{
      const other=execweaveTopology.bundleByEdge.get(edgeId(candidate));
      return other&&other.size>1&&other.key===bundle.key&&positions.has(candidate.source)&&positions.has(candidate.target);
    }).sort((a,b)=>edgeId(a).localeCompare(edgeId(b)));
    if(members.length<2||new Set(members.map(member=>member.target)).size!==1)return null;
    const topo=execweaveTopology;
    const anchors=members.map(member=>{
      const sp=positions.get(member.source),tp=positions.get(member.target);
      const sw=topo.width?.get(member.source)||execweaveWidthOf(member.source);
      const tw=topo.width?.get(member.target)||execweaveWidthOf(member.target);
      const forward=tp.x+tw/2>=sp.x+sw/2;
      const sx=forward?sp.x+sw:sp.x,tx=forward?tp.x:tp.x+tw;
      const sy=execweavePortY(sp,topo.sourcePort.get(edgeId(member)),member.source);
      const ty=execweavePortY(tp,topo.targetPort.get(edgeId(member)),member.target);
      return{member,forward,sx,sy,tx,ty};
    });
    if(new Set(anchors.map(row=>row.forward)).size!==1)return null;
    const lo=Math.max(...anchors.map(row=>Math.min(row.sx,row.tx)));
    const hi=Math.min(...anchors.map(row=>Math.max(row.sx,row.tx)));
    if(!(hi-lo>=24))return null;
    const groups=new Map();
    for(const candidate of edgeById.values()){
      const group=topo.bundleByEdge.get(edgeId(candidate));
      if(!group||group.size<2||groups.has(group.key)||!positions.has(candidate.target))continue;
      groups.set(group.key,{key:group.key,target:candidate.target,y:positions.get(candidate.target).y});
    }
    const orderedGroups=[...groups.values()].sort((a,b)=>a.y-b.y||a.key.localeCompare(b.key));
    const groupIndex=Math.max(0,orderedGroups.findIndex(group=>group.key===bundle.key));
    const fraction=orderedGroups.length<=1?.55:.36+.32*groupIndex/Math.max(1,orderedGroups.length-1);
    const ideal=lo+(hi-lo)*fraction;
    const boxes=[...positions].filter(([id])=>nodeById.has(id)).map(([id,p])=>({id,x:p.x,y:p.y,w:execweaveWidthOf(id),h:execweaveHeightOf(id)}));
    const candidateXs=[ideal,lo+(hi-lo)*.44,lo+(hi-lo)*.56,
      ...boxes.flatMap(box=>[box.x-6,box.x+box.w+6])]
      .filter(x=>x>=lo&&x<=hi)
      .sort((a,b)=>Math.abs(a-ideal)-Math.abs(b-ideal)||a-b);
    const clear=x=>anchors.every(row=>{
      const ownBoxes=boxes.filter(box=>box.id!==row.member.source&&box.id!==row.member.target);
      const p={x,y:row.sy},q={x,y:row.ty};
      return !ownBoxes.some(box=>execweaveGeometry.throughBox({x:row.sx,y:row.sy},p,box)||
        execweaveGeometry.throughBox(p,q,box)||execweaveGeometry.throughBox(q,{x:row.tx,y:row.ty},box));
    });
    const trunkX=candidateXs.find(clear);
    if(!Number.isFinite(trunkX))return null;
    const row=anchors.find(item=>edgeId(item.member)===edgeId(edge));
    if(!row)return null;
    return{d:`M ${row.sx} ${row.sy} H ${trunkX} V ${row.ty} H ${row.tx}`,
      labelX:(trunkX+row.tx)/2,labelY:row.ty-8,kind:'bundle',
      geometryKind:'shared-resource-bus',bundle};
  }
  window.execweaveLayoutV2BusRoute=execweaveLayoutV2BusRoute;

  window.__execweaveLayoutV2={
    syncFinalOrder:execweaveLayoutV2SyncFinalOrder,
    packingWidth:execweaveLayoutV2PackingWidth,
    hubInversionRate:execweaveLayoutV2HubInversionRate,
    orderMismatches:execweaveLayoutV2OrderMismatches,
    busRoute:execweaveLayoutV2BusRoute,
    mode:()=>window.__execweaveLayoutV2Mode,
  };
})();
""".strip()


def _replace_once(html: str, old: str, new: str, error: str) -> str:
    if html.count(old) != 1:
        raise RuntimeError(error)
    return html.replace(old, new, 1)


def inject_layout_v2(html: str) -> str:
    """Install Layout V2 authority, shared-resource routing and quality objectives."""

    html = _replace_once(
        html, _BAND_GAP_SEAM, "const EXECWEAVE_BAND_GAP=64;", "layout-v2 band-gap seam changed"
    )
    html = _replace_once(
        html, _PACKING_SEAM, _PACKING_REPLACEMENT, "layout-v2 packing seam changed"
    )
    html = _replace_once(
        html, _SYNC_ORDER_SEAM, _SYNC_ORDER_REPLACEMENT, "layout-v2 final-order seam changed"
    )
    html = _replace_once(
        html, _BUS_ROUTE_SEAM, _BUS_ROUTE_REPLACEMENT, "layout-v2 bundle route seam changed"
    )
    html = _replace_once(
        html, _INPUT_KEY_SEAM, _INPUT_KEY_REPLACEMENT, "layout-v2 cache-key seam changed"
    )
    html = _replace_once(
        html, _BUDGET_SEAM, _BUDGET_REPLACEMENT, "layout-v2 optimization budget seam changed"
    )
    html = _replace_once(
        html, _BETTER_SEAM, _BETTER_REPLACEMENT, "layout-v2 objective seam changed"
    )
    html = _replace_once(
        html, _ROUNDS_SEAM, _ROUNDS_REPLACEMENT, "layout-v2 optimization round seam changed"
    )
    html = _replace_once(
        html, _ARRANGE_SEAM, _ARRANGE_REPLACEMENT, "layout-v2 arrange-mode seam changed"
    )
    if html.count(_STARTUP_SEAM) != 1:
        raise RuntimeError("layout-v2 startup seam changed")
    return html.replace(_STARTUP_SEAM, LAYOUT_V2_SCRIPT + "\n" + _STARTUP_SEAM, 1)
