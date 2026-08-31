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
    for(const [id] of nodeElements){const node=nodeById.get(id);if(node)updateNodeElement(node)}
    for(const edge of edgeById.values())updateEdgeElement(edge);
  }""",
        label="delta geometry rerender",
    )
    return html
