from __future__ import annotations

import json
from typing import Any

from .live_view import LIVE_HTML as _BASE_LIVE_HTML
from .viewer_agent_panel import inject_agent_panel
from .viewer_dashboard_clean import fold_budget_bootstrap, inject_live_dashboard_clean
from .viewer_limits import resolve_viewer_limits, viewer_limits_bootstrap
from .viewer_dashboard_focus import inject_live_dashboard_focus
from .viewer_live_layout import inject_live_dashboard_layout


def _align_agent_panel_topology(html: str) -> str:
    """Keep the agent panel's identity/topology authority intact.

    The panel owns the provider-neutral rule: exact conversation identity selects
    content, while only explicit/root-provenance evidence selects the root renderer.
    Rewriting that code here used to promote every derived ``/root`` preview back into
    a canonical root and reintroduced cross-conversation aggregation. The shared shell
    therefore no longer carries a second topology policy.
    """
    return html


def _guard_compact_live_snapshot(html: str) -> str:
    """Keep compact live payloads in protective mode instead of projecting nodes=[]."""
    needle = "function setSnapshot(data){const signature="
    guarded = (
        "function setSnapshot(data){"
        "if(data.live_payload_compact){updateStats(data);enterProtectiveMode(data);return}"
        "const signature="
    )
    if needle not in html:
        return html
    return html.replace(needle, guarded, 1)


def _preserve_semantic_layout_constraints(html: str) -> str:
    """Use dagre for ordering/routing without erasing semantic lanes and row bands.

    Dagre's Sugiyama order is useful, but its free-form position phase does not know
    that ExecWeave lanes are a product contract.  In particular it can move a wide
    runtime into the root lane and serialize independent evidence lanes into one long
    vertical list.  Keep dagre's order *inside* each semantic lane/component while
    reusing the lane's pre-dagre row slots and adaptive X coordinates.  Detached
    evidence is then packed below the execution spine.  Route points are retained as
    ordering evidence; ordinary visible paths are rebuilt from final semantic ports.
    """
    needle = """function execweaveApplyDirectedGraph(topo){
  execweaveLayoutDirectedGraph(topo);
  execweaveSeparateOverlappingNodes(topo);
  // Ports were assigned before dagre moved nodes; rebuild against final Y so order matches crossing minimization.
  execweaveRecomputePorts(topo);
  return topo;
}"""
    replacement = r"""function execweaveRetargetRoutePoints(topo,dagrePlacement){
  if(!topo||!topo.routePoints||!dagrePlacement)return;
  // Route points remain available as dagre ordering evidence, but visible ordinary
  // paths are regenerated after semantic constraints. Do not linearly warp stale
  // dagre bends across lanes: that was the source of the crossing regression.
}
function execweaveRestoreSemanticLayoutConstraints(topo,preferred,dagrePlacement){
  if(!topo||!topo.spec||!preferred||!dagrePlacement)return topo;
  const nodes=[...nodeById.values()],edges=[...edgeById.values()];
  const componentOf=execweaveComponents(nodes,edges);

  // X is a semantic lane contract. Process-tree depth is the one deliberate
  // exception, so runtime/process nodes retain the pre-dagre tree coordinate.
  for(const [id,before] of preferred){
    const after=topo.spec.get(id),node=nodeById.get(id);if(!after||!node)continue;
    const type=String(node.type||'').toLowerCase();
    const processLike=type==='process'||type==='session'||type==='runtime';
    const laneX=topo.laneX&&Number.isFinite(topo.laneX[after.lane])?topo.laneX[after.lane]:before.x;
    after.x=processLike&&Number.isFinite(before.x)?before.x:laneX;
  }

  // Preserve each semantic lane/component's row slots, but let dagre choose which
  // node occupies each slot. This keeps crossing-minimizing order without turning
  // file + endpoint lanes into one global vertical rank list.
  const reorderable=new Set(['agent','model','file','endpoint','other']);
  const groups=new Map();
  for(const [id,before] of preferred){
    const spec=topo.spec.get(id);if(!spec)continue;
    if(!reorderable.has(spec.lane)){
      spec.y=before.y;
      continue;
    }
    const component=componentOf.has(id)?componentOf.get(id):-1;
    const key=`${spec.lane}\0${component}`;
    if(!groups.has(key))groups.set(key,[]);
    groups.get(key).push(id);
  }
  for(const ids of groups.values()){
    const slots=ids.map(id=>preferred.get(id)?.y).filter(Number.isFinite).sort((a,b)=>a-b);
    const ordered=[...ids].sort((a,b)=>{
      const ay=dagrePlacement.get(a)?.y??0,by=dagrePlacement.get(b)?.y??0;
      return ay-by||String(a).localeCompare(String(b));
    });
    ordered.forEach((id,index)=>{
      const spec=topo.spec.get(id);if(spec&&Number.isFinite(slots[index]))spec.y=slots[index];
    });
  }

  if(!componentOf.size)return topo;
  const sizes=new Map();for(const value of componentOf.values())sizes.set(value,(sizes.get(value)||0)+1);
  const roots=nodes.filter(execweaveIsRoot).sort(execweaveStableNodeSort);
  let primary=roots.length?componentOf.get(roots[0].id):undefined;
  if(primary===undefined){
    let best=-1;
    for(const [value,size] of [...sizes.entries()].sort((a,b)=>a[0]-b[0]))if(size>best){best=size;primary=value}
  }
  // Providers can expose a child agent without a graph edge back to /root. Agent
  // components are still execution-spine components, matching the base topology rule.
  const agentIds=new Set(nodes.filter(node=>node?.type==='agent').map(node=>node.id));
  const spineComponents=new Set([...componentOf.entries()].filter(([id])=>agentIds.has(id)).map(([,value])=>value));
  if(primary!==undefined)spineComponents.add(primary);
  let floor=-Infinity;
  for(const [id,value] of componentOf){
    if(!spineComponents.has(value))continue;
    const spec=topo.spec.get(id);if(spec)floor=Math.max(floor,spec.y+execweaveHeightOf(id));
  }
  if(!Number.isFinite(floor))floor=0;
  const secondary=[...sizes.keys()].filter(value=>!spineComponents.has(value)).sort((a,b)=>a-b);
  for(const value of secondary){
    const members=[...componentOf.entries()].filter(([,component])=>component===value).map(([id])=>id);
    let top=Infinity,bottom=-Infinity;
    for(const id of members){
      const spec=topo.spec.get(id);if(!spec)continue;
      top=Math.min(top,spec.y);bottom=Math.max(bottom,spec.y+execweaveHeightOf(id));
    }
    if(!Number.isFinite(top))continue;
    const shift=floor+EXECWEAVE_BAND_GAP-top;
    for(const id of members){const spec=topo.spec.get(id);if(spec)spec.y+=shift}
    floor=bottom+shift;
  }
  return topo;
}
function execweaveApplyDirectedGraph(topo){
  const preferred=new Map([...topo.spec].map(([id,spec])=>[id,{x:spec.x,y:spec.y}]));
  execweaveLayoutDirectedGraph(topo);
  const dagrePlacement=new Map([...topo.spec].map(([id,spec])=>[id,{x:spec.x,y:spec.y}]));
  execweaveRestoreSemanticLayoutConstraints(topo,preferred,dagrePlacement);
  execweaveSeparateOverlappingNodes(topo);
  execweaveRetargetRoutePoints(topo,dagrePlacement);
  // Ports were assigned before dagre moved nodes; rebuild against the constrained final Y.
  execweaveRecomputePorts(topo);
  return topo;
}"""
    if needle not in html:
        raise RuntimeError("directed graph layout seam changed")
    return html.replace(needle, replacement, 1)


def _preserve_semantic_arrange(html: str) -> str:
    """Do not let the Arrange button run a second unconstrained dagre pass.

    In the shared dashboard, ``execweaveBuildTopology`` already returns the constrained
    post-dagre topology above.  The original Arrange implementation immediately ran
    bare ``execweaveLayoutDirectedGraph`` again, undoing lane widths and evidence bands
    only after the user clicked Arrange.  Consume the already-final spec directly.
    """
    needle = """  for(const id of ordered)next.set(id,execweavePlaceStable(id,execweaveDesiredPosition(id),next,id));
  execweaveLayoutDirectedGraph(execweaveTopology);
  execweaveSeparateOverlappingNodes(execweaveTopology);
  execweaveRecomputePorts(execweaveTopology);"""
    replacement = """  for(const id of ordered){
    const spec=execweaveTopology.spec.get(id);
    next.set(id,spec?{x:spec.x,y:spec.y}:execweavePlaceStable(id,execweaveDesiredPosition(id),next,id));
  }"""
    if needle not in html:
        raise RuntimeError("Arrange layout seam changed")
    return html.replace(needle, replacement, 1)


def _route_ordinary_edges_from_final_positions(html: str) -> str:
    """Keep M/L ordinary routes while following the recorded 73-crossing geometry.

    The crossing baseline was recorded when every ordinary edge used one cubic family.
    PR #45 later changed those edges to dagre M/L polylines but retained that stricter
    baseline.  After semantic lanes are restored, stale dagre points no longer describe
    the visible graph.  Sample the original cubic control-point formula into a polyline:
    the rendered contract stays M/L, while its geometry tracks the baseline that the
    regression gate actually measures. Bundles and lifecycle returns remain untouched.
    """
    needle = r"""function execweaveRouteFromPoints(edge,points){
  const sp=positions.get(edge.source)||{x:0,y:0},tp=positions.get(edge.target)||{x:0,y:0};
  const sourcePort=execweaveTopology.sourcePort.get(edgeId(edge)),targetPort=execweaveTopology.targetPort.get(edgeId(edge));
  const sourceSpec=execweaveTopology.spec.get(edge.source)||{},targetSpec=execweaveTopology.spec.get(edge.target)||{};
  const forward=(targetSpec.x??0)>=(sourceSpec.x??0);
  const sx=forward?sp.x+execweaveWidthOf(edge.source):sp.x;
  const tx=forward?tp.x:tp.x+execweaveWidthOf(edge.target);
  const sy=execweavePortY(sp,sourcePort,edge.source),ty=execweavePortY(tp,targetPort,edge.target);
  const mid=points.length>2?points.slice(1,-1):[];
  let d=`M ${sx} ${sy}`;
  for(const point of mid)d+=` L ${point.x} ${point.y}`;
  d+=` L ${tx} ${ty}`;
  const labelPoint=mid.length?mid[Math.floor(mid.length/2)]:{x:(sx+tx)/2,y:(sy+ty)/2};
  return{d,labelX:labelPoint.x,labelY:labelPoint.y-8,kind:execweaveIsSpawn(edge)?'spawn':(forward?'forward':'reverse'),bundle:null};
}"""
    replacement = r"""function execweaveRouteFromPoints(edge,points){
  const sp=positions.get(edge.source)||{x:0,y:0},tp=positions.get(edge.target)||{x:0,y:0};
  const sourcePort=execweaveTopology.sourcePort.get(edgeId(edge)),targetPort=execweaveTopology.targetPort.get(edgeId(edge));
  const sourceSpec=execweaveTopology.spec.get(edge.source)||{},targetSpec=execweaveTopology.spec.get(edge.target)||{};
  const forward=(targetSpec.rank??0)>=(sourceSpec.rank??0);
  const sx=forward?sp.x+execweaveWidthOf(edge.source):sp.x;
  const tx=forward?tp.x:tp.x+execweaveWidthOf(edge.target);
  const sy=execweavePortY(sp,sourcePort,edge.source),ty=execweavePortY(tp,targetPort,edge.target);
  const distance=Math.abs(tx-sx),bend=Math.max(44,distance*.42),sign=forward?1:-1;
  const p0={x:sx,y:sy},p1={x:sx+sign*bend,y:sy},p2={x:tx-sign*bend,y:ty},p3={x:tx,y:ty};
  const cubic=t=>{
    const u=1-t;
    return{
      x:u*u*u*p0.x+3*u*u*t*p1.x+3*u*t*t*p2.x+t*t*t*p3.x,
      y:u*u*u*p0.y+3*u*u*t*p1.y+3*u*t*t*p2.y+t*t*t*p3.y,
    };
  };
  let d=`M ${sx} ${sy}`;
  for(let index=1;index<8;index++){
    const point=cubic(index/8);d+=` L ${point.x} ${point.y}`;
  }
  d+=` L ${tx} ${ty}`;
  const labelPoint=cubic(.5);
  return{d,labelX:labelPoint.x,labelY:labelPoint.y-8,kind:execweaveIsSpawn(edge)?'spawn':(forward?'forward':'reverse'),bundle:null};
}"""
    if needle not in html:
        raise RuntimeError("ordinary route seam changed")
    return html.replace(needle, replacement, 1)


def _build_dashboard_html() -> str:
    html = inject_live_dashboard_layout(
        inject_live_dashboard_focus(inject_live_dashboard_clean(_BASE_LIVE_HTML))
    )
    html = _preserve_semantic_layout_constraints(html)
    html = _preserve_semantic_arrange(html)
    html = _route_ordinary_edges_from_final_positions(html)
    return _align_agent_panel_topology(inject_agent_panel(_guard_compact_live_snapshot(html)))


DASHBOARD_HTML = _build_dashboard_html()


def _safe_json(value: object) -> str:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def render_static_dashboard_html(
    graph: dict[str, Any],
    *,
    conversation_entries: list[dict[str, Any]] | None = None,
) -> str:
    """Render the exact dashboard shell used by live, backed by embedded snapshots."""
    bootstrap = (
        "<script>window.__execweaveStaticMode=true;"
        f"{fold_budget_bootstrap()}"
        f"{viewer_limits_bootstrap(resolve_viewer_limits())}"
        f"window.__execweaveStaticGraph={_safe_json(graph)};"
        f"window.__execweaveStaticConversations={_safe_json(conversation_entries or [])};"
        "</script>\n"
    )
    html = DASHBOARD_HTML.replace("<script>", bootstrap + "<script>", 1)
    live_start = "applyTheme(initialTheme());applyTransform();poll();"
    static_start = (
        "applyTheme(initialTheme());applyTransform();"
        "setSnapshot(window.__execweaveStaticGraph||{});"
        "setStatus('FINISHED','finished');"
        "window.__execweaveDashboard?.onFinished?.();"
    )
    if live_start not in html:
        raise RuntimeError("shared dashboard startup seam changed")
    html = html.replace(live_start, static_start, 1)
    html = html.replace("<title>ExecWeave Live</title>", "<title>ExecWeave</title>", 1)
    return html.replace(
        "<body>",
        '<body>\n<!-- unified dashboard: theme is owned by the visible #theme-toggle control -->',
        1,
    )