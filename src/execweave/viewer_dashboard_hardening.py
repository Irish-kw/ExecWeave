from __future__ import annotations


def _replace_once(html: str, old: str, new: str, *, label: str) -> str:
    if old not in html:
        raise RuntimeError(f"dashboard hardening seam changed: {label}")
    return html.replace(old, new, 1)


def harden_dashboard_html(html: str) -> str:
    """Close v0.8.3 live-layout/tool-panel gaps without changing evidence semantics."""

    # PM-003: text measurement is synchronous browser layout work and is requested
    # repeatedly by width, wrapping and ellipsis calculations on every live topology
    # rebuild. Cache by the exact string while keeping real browser measurement as the
    # authority. The label font does not change with the light/dark theme; cap the cache
    # so a long-running session with ever-changing paths cannot grow it without bound.
    html = _replace_once(
        html,
        "let execweaveRuler=null;",
        "let execweaveRuler=null,execweaveMeasureCache=new Map();",
        label="measurement cache state",
    )
    html = _replace_once(
        html,
        """function execweaveMeasure(text){
  const value=String(text||'');
  if(!value)return 0;
  try{
    if(!execweaveRuler){
      execweaveRuler=document.createElementNS('http://www.w3.org/2000/svg','text');
      execweaveRuler.classList.add('name-label');
      execweaveRuler.setAttribute('visibility','hidden');
      execweaveRuler.setAttribute('x','-9999');
      execweaveRuler.setAttribute('y','-9999');
      svg.appendChild(execweaveRuler);
    }
    execweaveRuler.textContent=value;
    const measured=execweaveRuler.getComputedTextLength();
    if(Number.isFinite(measured)&&measured>0)return measured;
  }catch(_){}
  return value.length*7.1;
}""",
        """function execweaveRememberMeasure(value,measured){
  if(execweaveMeasureCache.size>=4096)execweaveMeasureCache.clear();
  execweaveMeasureCache.set(value,measured);return measured;
}
function execweaveMeasure(text){
  const value=String(text||'');
  if(!value)return 0;
  if(execweaveMeasureCache.has(value))return execweaveMeasureCache.get(value);
  try{
    if(!execweaveRuler){
      execweaveRuler=document.createElementNS('http://www.w3.org/2000/svg','text');
      execweaveRuler.classList.add('name-label');
      execweaveRuler.setAttribute('visibility','hidden');
      execweaveRuler.setAttribute('x','-9999');
      execweaveRuler.setAttribute('y','-9999');
      svg.appendChild(execweaveRuler);
    }
    execweaveRuler.textContent=value;
    const measured=execweaveRuler.getComputedTextLength();
    if(Number.isFinite(measured)&&measured>0)return execweaveRememberMeasure(value,measured);
  }catch(_){}
  return execweaveRememberMeasure(value,value.length*7.1);
}""",
        label="measurement function",
    )

    # PM-004: childOrder is intentionally child-local for chronological subagent
    # placement, but evidence-lane barycentres need every visible spine agent. Give the
    # root an order coordinate at the centre where it is actually placed and use that
    # broader map only for source-driven evidence ordering/bundle ordering.
    html = _replace_once(
        html,
        """  const childOrder=new Map(children.map((node,index)=>[node.id,index]));
  const rootY=children.length?100+((children.length-1)*EXECWEAVE_ROW_GAP)/2:100;""",
        """  const childOrder=new Map(children.map((node,index)=>[node.id,index]));
  const agentOrder=new Map(childOrder),rootOrder=children.length?(children.length-1)/2:0;
  roots.forEach((node,index)=>agentOrder.set(node.id,rootOrder+index));
  const rootY=children.length?100+((children.length-1)*EXECWEAVE_ROW_GAP)/2:100;""",
        label="root evidence order",
    )
    html = _replace_once(
        html,
        """  const agentBarycenter=node=>{
    const touching=edges.filter(edge=>edge.target===node.id&&childOrder.has(edge.source));
    if(!touching.length)return Number.MAX_SAFE_INTEGER;
    return touching.reduce((sum,edge)=>sum+(childOrder.get(edge.source)||0),0)/touching.length;
  };""",
        """  const agentBarycenter=node=>{
    const touching=edges.filter(edge=>edge.target===node.id&&agentOrder.has(edge.source));
    if(!touching.length)return Number.MAX_SAFE_INTEGER;
    return touching.reduce((sum,edge)=>sum+(agentOrder.get(edge.source)||0),0)/touching.length;
  };""",
        label="tool barycentre source domain",
    )
    html = _replace_once(
        html,
        """  const sourceBarycentre=node=>{
    const touching=edges.filter(edge=>edge.target===node.id&&childOrder.has(edge.source));
    if(!touching.length)return Number.MAX_SAFE_INTEGER;
    return touching.reduce((sum,edge)=>sum+(childOrder.get(edge.source)||0),0)/touching.length;
  };""",
        """  const sourceBarycentre=node=>{
    const touching=edges.filter(edge=>edge.target===node.id&&agentOrder.has(edge.source));
    if(!touching.length)return Number.MAX_SAFE_INTEGER;
    return touching.reduce((sum,edge)=>sum+(agentOrder.get(edge.source)||0),0)/touching.length;
  };""",
        label="evidence barycentre source domain",
    )
    html = _replace_once(
        html,
        "members.sort((a,b)=>(childOrder.get(a.source)??Number.MAX_SAFE_INTEGER)-(childOrder.get(b.source)??Number.MAX_SAFE_INTEGER)||edgeId(a).localeCompare(edgeId(b)));",
        "members.sort((a,b)=>(agentOrder.get(a.source)??Number.MAX_SAFE_INTEGER)-(agentOrder.get(b.source)??Number.MAX_SAFE_INTEGER)||edgeId(a).localeCompare(edgeId(b)));",
        label="bundle source order",
    )

    # PM-001: adaptive lane x is recomputed from current labels. Preserve stable y, not
    # stale x. The delta path must also move already-rendered nodes and reroute their
    # edges when lane geometry changes; updating only newly-added nodes leaves the DOM
    # visually attached to the previous lane table.
    html = _replace_once(
        html,
        """  for(const id of nodeById.keys()){
    const desired=execweaveDesiredPosition(id),old=prior.get(id);
    next.set(id,old?{x:old.x,y:old.y}:execweavePlaceStable(id,desired,next,id));
  }""",
        """  for(const id of nodeById.keys()){
    const desired=execweaveDesiredPosition(id),old=prior.get(id),stable=old?{x:desired.x,y:old.y}:desired;
    next.set(id,execweavePlaceStable(id,stable,next));
  }""",
        label="full-layout adaptive x",
    )
    html = _replace_once(
        html,
        """placeAddedNodes=function(ids){
  execweaveTopology=execweaveBuildTopology();
  for(const id of ids||[]){if(!nodeById.has(id)||positions.has(id))continue;positions.set(id,execweavePlaceStable(id,execweaveDesiredPosition(id),positions,id))}
  svg.classList.toggle('execweave-crowded',execweaveTopology.crowded);
};""",
        """placeAddedNodes=function(ids){
  const priorLaneX={...(execweaveTopology.laneX||{})};
  execweaveTopology=execweaveBuildTopology();
  const laneShifted=EXECWEAVE_LANE_ORDER.some(lane=>priorLaneX[lane]!==execweaveTopology.laneX[lane]);
  if(laneShifted){
    const next=new Map();
    for(const [id,old] of positions){
      if(!nodeById.has(id))continue;
      const desired=execweaveDesiredPosition(id);
      next.set(id,execweavePlaceStable(id,{x:desired.x,y:old.y},next));
    }
    positions=next;
  }
  for(const id of ids||[]){if(!nodeById.has(id)||positions.has(id))continue;positions.set(id,execweavePlaceStable(id,execweaveDesiredPosition(id),positions))}
  if(laneShifted){
    for(const [id] of nodeElements){const node=nodeById.get(id);if(node)updateNodeElement(node)}
    for(const edge of edgeById.values())updateEdgeElement(edge);
  }
  svg.classList.toggle('execweave-crowded',execweaveTopology.crowded);
};""",
        label="delta adaptive x",
    )

    # PM-002: camera geometry must come from the same authoritative dimensions used by
    # the renderer. This also fixes the pre-existing maxY omission that adaptive height
    # made visible.
    html = _replace_once(
        html,
        """function graphBounds(){if(!positions.size)return null;let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;positions.forEach(p=>{if(p.x<minX)minX=p.x;if(p.x>maxX)maxX=p.x;if(p.y<minY)minY=p.y});return{minX,maxX:maxX+160,minY,maxY:maxY+50}}
function fit(animate=true){const bounds=graphBounds();if(!bounds)return;const box=svg.getBoundingClientRect(),w=Math.max(1,bounds.maxX-bounds.minX),h=Math.max(1,bounds.maxY-bounds.minY),scale=Math.min(1.2,Math.max(.07,Math.min((box.width-72)/w,(box.height-72)/h))),next={x:36-bounds.minX*scale,y:36-bounds.minY*scale,scale};if(animate)animateTo(next);else{transform=next;applyTransform()}}
function latestScreenPoint(){if(!latestNodeId||!positions.has(latestNodeId))return null;const p=positions.get(latestNodeId);return{x:transform.x+(p.x+80)*transform.scale,y:transform.y+(p.y+25)*transform.scale}}
function latestInsideSafeZone(){const point=latestScreenPoint();if(!point)return true;const box=svg.getBoundingClientRect(),mx=box.width*.18,my=box.height*.18;return point.x>=mx&&point.x<=box.width-mx&&point.y>=my&&point.y<=box.height-my}
function followLatest(force=false){if(!latestNodeId||!positions.has(latestNodeId))return;if(!force&&latestInsideSafeZone())return;const box=svg.getBoundingClientRect(),p=positions.get(latestNodeId),next={x:box.width*.5-(p.x+80)*transform.scale,y:box.height*.5-(p.y+25)*transform.scale,scale:transform.scale};animateTo(next,240)}
function focusNode(id){if(!id||!positions.has(id))return;if(cameraMode!=='manual')setCameraMode('manual',{apply:false});const box=svg.getBoundingClientRect(),p=positions.get(id),scale=Math.min(1.2,Math.max(.72,transform.scale)),next={x:box.width*.5-(p.x+80)*scale,y:box.height*.5-(p.y+25)*scale,scale};animateTo(next,220);setTimeout(updateJumpLatest,230)}""",
        """function execweaveCameraWidth(id){try{const value=execweaveWidthOf(id);return Number.isFinite(value)?value:160}catch(_){return 160}}
function execweaveCameraHeight(id){try{const value=execweaveHeightOf(id);return Number.isFinite(value)?value:50}catch(_){return 50}}
function graphBounds(){if(!positions.size)return null;let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;positions.forEach((p,id)=>{const w=execweaveCameraWidth(id),h=execweaveCameraHeight(id);if(p.x<minX)minX=p.x;if(p.x+w>maxX)maxX=p.x+w;if(p.y<minY)minY=p.y;if(p.y+h>maxY)maxY=p.y+h});return{minX,maxX,minY,maxY}}
function fit(animate=true){const bounds=graphBounds();if(!bounds)return;const box=svg.getBoundingClientRect(),w=Math.max(1,bounds.maxX-bounds.minX),h=Math.max(1,bounds.maxY-bounds.minY),scale=Math.min(1.2,Math.max(.07,Math.min((box.width-72)/w,(box.height-72)/h))),next={x:36-bounds.minX*scale,y:36-bounds.minY*scale,scale};if(animate)animateTo(next);else{transform=next;applyTransform()}}
function latestScreenPoint(){if(!latestNodeId||!positions.has(latestNodeId))return null;const p=positions.get(latestNodeId),w=execweaveCameraWidth(latestNodeId),h=execweaveCameraHeight(latestNodeId);return{x:transform.x+(p.x+w/2)*transform.scale,y:transform.y+(p.y+h/2)*transform.scale}}
function latestInsideSafeZone(){const point=latestScreenPoint();if(!point)return true;const box=svg.getBoundingClientRect(),mx=box.width*.18,my=box.height*.18;return point.x>=mx&&point.x<=box.width-mx&&point.y>=my&&point.y<=box.height-my}
function followLatest(force=false){if(!latestNodeId||!positions.has(latestNodeId))return;if(!force&&latestInsideSafeZone())return;const box=svg.getBoundingClientRect(),p=positions.get(latestNodeId),w=execweaveCameraWidth(latestNodeId),h=execweaveCameraHeight(latestNodeId),next={x:box.width*.5-(p.x+w/2)*transform.scale,y:box.height*.5-(p.y+h/2)*transform.scale,scale:transform.scale};animateTo(next,240)}
function focusNode(id){if(!id||!positions.has(id))return;if(cameraMode!=='manual')setCameraMode('manual',{apply:false});const box=svg.getBoundingClientRect(),p=positions.get(id),w=execweaveCameraWidth(id),h=execweaveCameraHeight(id),scale=Math.min(1.2,Math.max(.72,transform.scale)),next={x:box.width*.5-(p.x+w/2)*scale,y:box.height*.5-(p.y+h/2)*scale,scale};animateTo(next,220);setTimeout(updateJumpLatest,230)}""",
        label="camera dynamic geometry",
    )

    # PM-006: build relation indexes once per raw graph collection instead of scanning
    # E and then N for every card lookup. applyDelta replaces graph node/edge arrays, so
    # reference+length invalidation is exact for the live path and static viewers remain
    # stable.
    html = _replace_once(
        html,
        """function rawGraph(){const core=window.__execweaveCore;return core?.getGraph?.()||displayGraph()}
function rawEdges(){return Array.isArray(rawGraph().edges)?rawGraph().edges:[]}
function rawNode(id){return (rawGraph().nodes||[]).find(node=>String(node?.id||'')===String(id))||null}
function relatedTo(id,relation,{from=true}={}){
  const wanted=String(relation).toUpperCase();
  return rawEdges()
    .filter(edge=>String(edge?.relation||'').toUpperCase()===wanted&&String(from?edge?.source:edge?.target)===String(id))
    .map(edge=>rawNode(from?edge.target:edge.source))
    .filter(Boolean);
}""",
        """function rawGraph(){const core=window.__execweaveCore;return core?.getGraph?.()||displayGraph()}
let rawIndexedGraph=null,rawIndexedNodesRef=null,rawIndexedEdgesRef=null,rawIndexedNodeCount=-1,rawIndexedEdgeCount=-1,rawNodeById=new Map(),rawOutById=new Map(),rawInById=new Map(),rawIndexedEdges=[];
function ensureRawIndex(){
  const graph=rawGraph(),nodes=Array.isArray(graph.nodes)?graph.nodes:[],edges=Array.isArray(graph.edges)?graph.edges:[];
  if(graph===rawIndexedGraph&&nodes===rawIndexedNodesRef&&edges===rawIndexedEdgesRef&&nodes.length===rawIndexedNodeCount&&edges.length===rawIndexedEdgeCount)return{nodes:rawNodeById,out:rawOutById,incoming:rawInById,edges:rawIndexedEdges};
  rawIndexedGraph=graph;rawIndexedNodesRef=nodes;rawIndexedEdgesRef=edges;rawIndexedNodeCount=nodes.length;rawIndexedEdgeCount=edges.length;rawIndexedEdges=edges;
  rawNodeById=new Map(nodes.map(node=>[String(node?.id||''),node]));rawOutById=new Map();rawInById=new Map();
  for(const edge of edges){const source=String(edge?.source||''),target=String(edge?.target||'');if(!rawOutById.has(source))rawOutById.set(source,[]);rawOutById.get(source).push(edge);if(!rawInById.has(target))rawInById.set(target,[]);rawInById.get(target).push(edge)}
  return{nodes:rawNodeById,out:rawOutById,incoming:rawInById,edges:rawIndexedEdges};
}
function rawEdges(){return ensureRawIndex().edges}
function rawNode(id){return ensureRawIndex().nodes.get(String(id))||null}
function relatedToAny(id,relations,{from=true}={}){
  const index=ensureRawIndex(),wanted=new Set(relations.map(value=>String(value).toUpperCase())),key=String(id),candidates=(from?index.out:index.incoming).get(key)||[],seen=new Set(),out=[];
  for(const edge of candidates){if(!wanted.has(String(edge?.relation||'').toUpperCase()))continue;const node=index.nodes.get(String(from?edge.target:edge.source));if(!node)continue;const nodeId=String(node?.id||'');if(seen.has(nodeId))continue;seen.add(nodeId);out.push(node)}
  return out;
}
function relatedTo(id,relation,options={}){return relatedToAny(id,[relation],options)}""",
        label="raw graph indexes",
    )

    # PM-005: presentation may group the repository's supported ownership relations,
    # but it must not rewrite raw evidence. De-duplicate by call node ID if more than one
    # compatible relation names the same logical call.
    html = _replace_once(
        html,
        """function toolCallsFor(agentId){
  const calls=relatedTo(agentId,'REQUESTED_TOOL_CALL');
  if(!calls.length)return '';
  const ordered=[...calls].sort((a,b)=>String(b?.first_seen||'').localeCompare(String(a?.first_seen||'')));
  const stamps=ordered.map(call=>String(call?.first_seen||'')).filter(Boolean);
  const sameDay=stamps.length<2||stamps.every(value=>value.slice(0,10)===stamps[0].slice(0,10));
  return ordered.map(call=>toolCallLine(call,sameDay)).join('\\n');
}
function callersOf(toolId){
  const calls=rawEdges().filter(edge=>String(edge?.relation||'').toUpperCase()==='USES_TOOL'&&String(edge?.target)===String(toolId))
    .map(edge=>rawNode(edge.source)).filter(Boolean);
  const names=new Set();
  for(const call of calls)for(const agent of relatedTo(call.id,'REQUESTED_TOOL_CALL',{from:false}))names.add(agent?.name||agent?.id);
  return{count:calls.length,agents:[...names].sort()};
}""",
        """const TOOL_CALL_OWNERSHIP_RELATIONS=['REQUESTED_TOOL_CALL','OBSERVED_TOOL_CALL','OWNED_TOOL_CALL'];
function toolCallsFor(agentId){
  const calls=relatedToAny(agentId,TOOL_CALL_OWNERSHIP_RELATIONS);
  if(!calls.length)return '';
  const ordered=[...calls].sort((a,b)=>String(b?.first_seen||'').localeCompare(String(a?.first_seen||''))||String(a?.id||'').localeCompare(String(b?.id||'')));
  const stamps=ordered.map(call=>String(call?.first_seen||'')).filter(Boolean);
  const sameDay=stamps.length<2||stamps.every(value=>value.slice(0,10)===stamps[0].slice(0,10));
  return ordered.map(call=>toolCallLine(call,sameDay)).join('\\n');
}
function callersOf(toolId){
  const calls=rawEdges().filter(edge=>String(edge?.relation||'').toUpperCase()==='USES_TOOL'&&String(edge?.target)===String(toolId))
    .map(edge=>rawNode(edge.source)).filter(Boolean),uniqueCalls=new Map(calls.map(call=>[String(call?.id||''),call]));
  const names=new Set();
  for(const call of uniqueCalls.values())for(const agent of relatedToAny(call.id,TOOL_CALL_OWNERSHIP_RELATIONS,{from:false}))names.add(agent?.name||agent?.id);
  return{count:uniqueCalls.size,agents:[...names].sort()};
}""",
        label="tool-call ownership relations",
    )

    return html
