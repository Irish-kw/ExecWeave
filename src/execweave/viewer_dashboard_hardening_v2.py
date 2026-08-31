from __future__ import annotations

from .viewer_dashboard_hardening import harden_dashboard_html as _harden_v1


def _replace_once(html: str, old: str, new: str, *, label: str) -> str:
    if old not in html:
        raise RuntimeError(f"dashboard hardening v2 seam changed: {label}")
    return html.replace(old, new, 1)


def harden_dashboard_html(html: str) -> str:
    """Apply the reviewed v0.8.3 hardening set and its live-delta fixups."""
    html = _harden_v1(html)

    # Fix the ownership-card timestamp filter before the generated JS reaches a browser.
    html = _replace_once(
        html,
        "const stamps=ordered.map(call=>String(call?.first_seen||'').filter(Boolean));",
        "const stamps=ordered.map(call=>String(call?.first_seen||'')).filter(Boolean);",
        label="tool timestamp filter",
    )

    # Only a real browser measurement is authoritative enough to cache. Detached/export
    # contexts can fall back to the character estimate, but caching that estimate would
    # prevent a later attached render from upgrading the same string to measured width.
    html = _replace_once(
        html,
        "return execweaveRememberMeasure(value,value.length*7.1);",
        "return value.length*7.1;",
        label="measurement fallback cache",
    )

    # A node may become wider/taller without moving a lane origin (for example the last
    # occupied lane). Existing edge paths still depend on that dimension, so lane-shift
    # detection alone is not enough to decide whether the rendered geometry is stale.
    html = _replace_once(
        html,
        """  const priorLaneX={...(execweaveTopology.laneX||{})};
  execweaveTopology=execweaveBuildTopology();
  const laneShifted=EXECWEAVE_LANE_ORDER.some(lane=>priorLaneX[lane]!==execweaveTopology.laneX[lane]);""",
        """  const priorLaneX={...(execweaveTopology.laneX||{})},priorWidth=new Map(execweaveTopology.width||[]),priorHeight=new Map(execweaveTopology.height||[]);
  execweaveTopology=execweaveBuildTopology();
  const laneShifted=EXECWEAVE_LANE_ORDER.some(lane=>priorLaneX[lane]!==execweaveTopology.laneX[lane]);
  const dimensionsChanged=[...nodeById.keys()].some(id=>priorWidth.get(id)!==execweaveTopology.width.get(id)||priorHeight.get(id)!==execweaveTopology.height.get(id));
  const geometryChanged=laneShifted||dimensionsChanged;""",
        label="delta dimension change detection",
    )
    html = _replace_once(
        html,
        """  if(laneShifted){
    for(const [id] of nodeElements){const node=nodeById.get(id);if(node)updateNodeElement(node)}
    for(const edge of edgeById.values())updateEdgeElement(edge);
  }""",
        """  if(geometryChanged){
    for(const [id,group] of nodeElements){
      const p=positions.get(id),node=nodeById.get(id);
      if(p)group.setAttribute('transform',`translate(${p.x} ${p.y})`);
      if(node)updateNodeElement(node);
    }
    for(const edge of edgeById.values())updateEdgeElement(edge);
  }""",
        label="delta geometry rerender",
    )

    # PM-008 (discovered while tightening PM-002): GIF replay used the old fixed 160x50
    # node rectangle even after the dashboard became adaptive. Export is a projection of
    # the same graph, so its bounds, edge anchors and drawn rectangles must use the same
    # per-node geometry as Live/Finished/viewer rather than silently reverting to v0.8.2.
    html = _replace_once(
        html,
        "minX=Math.min(minX,p.x);maxX=Math.max(maxX,p.x+160);minY=Math.min(minY,p.y);maxY=Math.max(maxY,p.y+50)",
        "minX=Math.min(minX,p.x);maxX=Math.max(maxX,p.x+execweaveCameraWidth(node.id));minY=Math.min(minY,p.y);maxY=Math.max(maxY,p.y+execweaveCameraHeight(node.id))",
        label="gif adaptive bounds",
    )
    html = _replace_once(
        html,
        "const point=(id,right=false)=>{const p=positions.get(id)||{x:0,y:0};return{x:ox+(p.x+(right?160:0))*scale,y:oy+(p.y+25)*scale}};",
        "const point=(id,right=false)=>{const p=positions.get(id)||{x:0,y:0},w=execweaveCameraWidth(id),h=execweaveCameraHeight(id);return{x:ox+(p.x+(right?w:0))*scale,y:oy+(p.y+h/2)*scale}};",
        label="gif adaptive anchors",
    )
    html = _replace_once(
        html,
        "const x=ox+p.x*scale,y=oy+p.y*scale,w=160*scale,h=50*scale;",
        "const x=ox+p.x*scale,y=oy+p.y*scale,w=execweaveCameraWidth(node.id)*scale,h=execweaveCameraHeight(node.id)*scale;",
        label="gif adaptive rectangles",
    )
    return html
