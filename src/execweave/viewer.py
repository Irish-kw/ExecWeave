from __future__ import annotations

import json
import webbrowser
from pathlib import Path
from typing import Any

from .graph_ops import load_graph


def _safe_embedded_json(payload: dict[str, Any]) -> str:
    # Prevent user-controlled graph strings from terminating the application/json
    # script element while keeping the viewer fully local and dependency-free.
    return (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def render_graph_html(graph: dict[str, Any]) -> str:
    data = _safe_embedded_json(graph)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ExecWeave — Execution Graph</title>
<style>
:root {{
  color-scheme: light dark;
  --bg: #0b0f14;
  --panel: #111821;
  --panel-2: #18222e;
  --text: #e8edf3;
  --muted: #8ea0b5;
  --border: #2a3949;
  --edge: #72869c;
  --causal: #70d6a6;
  --noncausal: #f2b76d;
  --selected: #73b7ff;
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; width: 100%; height: 100%; overflow: hidden; background: var(--bg); color: var(--text); font: 14px/1.4 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
#app {{ display: grid; grid-template-columns: minmax(0, 1fr) 340px; grid-template-rows: 54px minmax(0, 1fr); width: 100%; height: 100%; }}
header {{ grid-column: 1 / 3; display: flex; align-items: center; gap: 16px; padding: 0 18px; border-bottom: 1px solid var(--border); background: var(--panel); }}
header strong {{ font-size: 16px; }}
header .stats {{ color: var(--muted); white-space: nowrap; }}
header input {{ width: min(420px, 38vw); margin-left: auto; border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; background: var(--panel-2); color: var(--text); outline: none; }}
header input:focus {{ border-color: var(--selected); }}
#canvas-wrap {{ position: relative; min-width: 0; min-height: 0; overflow: hidden; }}
#graph {{ width: 100%; height: 100%; display: block; cursor: grab; user-select: none; }}
#graph.panning {{ cursor: grabbing; }}
aside {{ overflow: auto; border-left: 1px solid var(--border); background: var(--panel); padding: 16px; }}
aside h2 {{ margin: 0 0 12px; font-size: 15px; }}
aside h3 {{ margin: 18px 0 8px; font-size: 13px; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }}
#details pre {{ margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; color: var(--text); }}
.legend {{ display: flex; flex-wrap: wrap; gap: 8px 12px; margin-top: 6px; }}
.legend span {{ display: inline-flex; align-items: center; gap: 5px; color: var(--muted); font-size: 12px; }}
.dot {{ width: 9px; height: 9px; border-radius: 50%; display: inline-block; }}
.controls {{ position: absolute; top: 12px; left: 12px; z-index: 5; display: flex; gap: 6px; }}
.controls button {{ border: 1px solid var(--border); background: var(--panel); color: var(--text); border-radius: 7px; padding: 6px 9px; cursor: pointer; }}
.controls button:hover {{ border-color: var(--selected); }}
.node rect {{ stroke: var(--border); stroke-width: 1.2; rx: 9; ry: 9; }}
.node text {{ pointer-events: none; fill: var(--text); }}
.node .node-type {{ fill: var(--muted); font-size: 10px; text-transform: uppercase; }}
.node.selected rect {{ stroke: var(--selected); stroke-width: 2.5; }}
.node.dim {{ opacity: .16; }}
.edge {{ fill: none; stroke: var(--edge); stroke-width: 1.4; opacity: .75; cursor: pointer; }}
.edge.causal {{ stroke: var(--causal); }}
.edge.noncausal {{ stroke: var(--noncausal); stroke-dasharray: 6 5; }}
.edge.dim {{ opacity: .08; }}
.edge-hit {{ fill: none; stroke: transparent; stroke-width: 12; cursor: pointer; }}
.edge-label {{ fill: var(--muted); font-size: 9px; pointer-events: none; }}
.empty {{ color: var(--muted); }}
@media (max-width: 820px) {{
  #app {{ grid-template-columns: 1fr; grid-template-rows: 54px minmax(0, 1fr) 230px; }}
  header {{ grid-column: 1; }}
  aside {{ border-left: 0; border-top: 1px solid var(--border); }}
}}
</style>
</head>
<body>
<div id="app">
<header>
  <strong>ExecWeave</strong>
  <span class="stats" id="stats"></span>
  <input id="search" placeholder="Search node id, name, type…" autocomplete="off">
</header>
<div id="canvas-wrap">
  <div class="controls">
    <button id="fit">Fit</button>
    <button id="reset">Reset</button>
  </div>
  <svg id="graph" aria-label="ExecWeave execution graph">
    <defs>
      <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke"></path>
      </marker>
    </defs>
    <g id="viewport"><g id="edges"></g><g id="labels"></g><g id="nodes"></g></g>
  </svg>
</div>
<aside>
  <h2>Selection</h2>
  <div id="details" class="empty">Click a node or edge.</div>
  <h3>Edge semantics</h3>
  <div class="legend">
    <span><i class="dot" style="background:var(--causal)"></i>Causal evidence</span>
    <span><i class="dot" style="background:var(--noncausal)"></i>Non-causal observation</span>
    <span><i class="dot" style="background:var(--edge)"></i>Mixed / unspecified</span>
  </div>
  <h3>Navigation</h3>
  <div class="empty">Wheel to zoom. Drag background to pan. Drag nodes to rearrange.</div>
</aside>
</div>
<script type="application/json" id="graph-data">{data}</script>
<script>
(() => {{
  const graph = JSON.parse(document.getElementById('graph-data').textContent);
  const svg = document.getElementById('graph');
  const viewport = document.getElementById('viewport');
  const edgeLayer = document.getElementById('edges');
  const labelLayer = document.getElementById('labels');
  const nodeLayer = document.getElementById('nodes');
  const details = document.getElementById('details');
  const search = document.getElementById('search');
  const stats = document.getElementById('stats');
  const nodeById = new Map((graph.nodes || []).map(n => [n.id, n]));
  const edges = graph.edges || [];
  const positions = new Map();
  const nodeElements = new Map();
  const edgeElements = [];
  let transform = {{x: 40, y: 40, scale: 1}};
  let panStart = null;
  let dragNode = null;

  stats.textContent = `${{graph.node_count ?? graph.nodes?.length ?? 0}} nodes · ${{graph.edge_count ?? edges.length}} edges · ${{graph.event_count ?? 0}} events`;

  function colorForType(type) {{
    let hash = 0;
    for (const ch of String(type || 'unknown')) hash = ((hash << 5) - hash + ch.charCodeAt(0)) | 0;
    const hue = Math.abs(hash) % 360;
    return `hsl(${{hue}} 38% 27%)`;
  }}

  function labelFor(node) {{
    const raw = node.name || node.id || node.type || 'node';
    return raw.length > 28 ? raw.slice(0, 25) + '…' : raw;
  }}

  function computeLayout() {{
    const ids = [...nodeById.keys()];
    const indegree = new Map(ids.map(id => [id, 0]));
    const outgoing = new Map(ids.map(id => [id, []]));
    for (const edge of edges) {{
      if (!nodeById.has(edge.source) || !nodeById.has(edge.target)) continue;
      indegree.set(edge.target, (indegree.get(edge.target) || 0) + 1);
      outgoing.get(edge.source).push(edge.target);
    }}
    const roots = ids.filter(id => (indegree.get(id) || 0) === 0);
    if (!roots.length && ids.length) roots.push(ids[0]);
    const depth = new Map();
    const queue = roots.map(id => [id, 0]);
    for (const [id, d] of queue) if (!depth.has(id)) depth.set(id, d);
    for (let i = 0; i < queue.length; i++) {{
      const [id, d] = queue[i];
      for (const next of outgoing.get(id) || []) {{
        const nextDepth = d + 1;
        if (!depth.has(next) || nextDepth < depth.get(next)) {{
          depth.set(next, nextDepth);
          queue.push([next, nextDepth]);
        }}
      }}
    }}
    const maxDepth = Math.max(0, ...depth.values());
    for (const id of ids) if (!depth.has(id)) depth.set(id, maxDepth + 1);
    const layers = new Map();
    for (const id of ids) {{
      const d = depth.get(id);
      if (!layers.has(d)) layers.set(d, []);
      layers.get(d).push(id);
    }}
    for (const [d, layer] of [...layers.entries()].sort((a,b) => a[0]-b[0])) {{
      layer.sort((a,b) => String(nodeById.get(a).type).localeCompare(String(nodeById.get(b).type)) || a.localeCompare(b));
      layer.forEach((id, i) => positions.set(id, {{x: d * 250, y: i * 88}}));
    }}
  }}

  function applyTransform() {{
    viewport.setAttribute('transform', `translate(${{transform.x}} ${{transform.y}}) scale(${{transform.scale}})`);
  }}

  function nodeAnchor(id, side) {{
    const p = positions.get(id) || {{x:0,y:0}};
    return {{x: p.x + (side === 'right' ? 170 : 0), y: p.y + 29}};
  }}

  function edgePath(edge) {{
    const a = nodeAnchor(edge.source, 'right');
    const b = nodeAnchor(edge.target, 'left');
    const bend = Math.max(45, Math.abs(b.x - a.x) * .45);
    return `M ${{a.x}} ${{a.y}} C ${{a.x + bend}} ${{a.y}}, ${{b.x - bend}} ${{b.y}}, ${{b.x}} ${{b.y}}`;
  }}

  function renderEdges() {{
    edgeLayer.replaceChildren();
    labelLayer.replaceChildren();
    edgeElements.length = 0;
    for (const edge of edges) {{
      if (!positions.has(edge.source) || !positions.has(edge.target)) continue;
      const visible = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      visible.setAttribute('d', edgePath(edge));
      visible.setAttribute('marker-end', 'url(#arrow)');
      visible.classList.add('edge');
      if (edge.causal === true) visible.classList.add('causal');
      else if (edge.causal === false) visible.classList.add('noncausal');
      edgeLayer.appendChild(visible);

      const hit = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      hit.setAttribute('d', edgePath(edge));
      hit.classList.add('edge-hit');
      hit.addEventListener('click', ev => {{ ev.stopPropagation(); showDetails('Edge', edge); }});
      edgeLayer.appendChild(hit);

      const a = nodeAnchor(edge.source, 'right');
      const b = nodeAnchor(edge.target, 'left');
      const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('x', String((a.x + b.x) / 2));
      text.setAttribute('y', String((a.y + b.y) / 2 - 7));
      text.setAttribute('text-anchor', 'middle');
      text.classList.add('edge-label');
      text.textContent = edge.count > 1 ? `${{edge.relation}} ×${{edge.count}}` : edge.relation;
      labelLayer.appendChild(text);
      edgeElements.push({{edge, visible, hit, text}});
    }}
  }}

  function renderNodes() {{
    nodeLayer.replaceChildren();
    nodeElements.clear();
    for (const node of graph.nodes || []) {{
      const p = positions.get(node.id);
      if (!p) continue;
      const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      group.classList.add('node');
      group.setAttribute('transform', `translate(${{p.x}} ${{p.y}})`);
      group.dataset.id = node.id;

      const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      rect.setAttribute('width', '170'); rect.setAttribute('height', '58');
      rect.setAttribute('fill', colorForType(node.type));
      group.appendChild(rect);

      const type = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      type.setAttribute('x', '12'); type.setAttribute('y', '18');
      type.classList.add('node-type'); type.textContent = node.type || 'unknown';
      group.appendChild(type);

      const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      label.setAttribute('x', '12'); label.setAttribute('y', '39');
      label.textContent = labelFor(node);
      group.appendChild(label);

      group.addEventListener('pointerdown', ev => {{
        ev.stopPropagation();
        const pt = svgPoint(ev);
        dragNode = {{id: node.id, dx: pt.x - p.x, dy: pt.y - p.y}};
        group.setPointerCapture(ev.pointerId);
      }});
      group.addEventListener('pointermove', ev => {{
        if (!dragNode || dragNode.id !== node.id) return;
        const pt = svgPoint(ev);
        positions.set(node.id, {{x: pt.x - dragNode.dx, y: pt.y - dragNode.dy}});
        group.setAttribute('transform', `translate(${{pt.x - dragNode.dx}} ${{pt.y - dragNode.dy}})`);
        renderEdges();
      }});
      group.addEventListener('pointerup', ev => {{
        dragNode = null;
        try {{ group.releasePointerCapture(ev.pointerId); }} catch (_) {{}}
      }});
      group.addEventListener('click', ev => {{
        ev.stopPropagation();
        document.querySelectorAll('.node.selected').forEach(el => el.classList.remove('selected'));
        group.classList.add('selected');
        showDetails('Node', node);
      }});
      nodeLayer.appendChild(group);
      nodeElements.set(node.id, group);
    }}
  }}

  function svgPoint(ev) {{
    const rect = svg.getBoundingClientRect();
    return {{
      x: (ev.clientX - rect.left - transform.x) / transform.scale,
      y: (ev.clientY - rect.top - transform.y) / transform.scale,
    }};
  }}

  function showDetails(kind, value) {{
    details.classList.remove('empty');
    details.replaceChildren();
    const title = document.createElement('strong'); title.textContent = kind;
    const pre = document.createElement('pre'); pre.textContent = JSON.stringify(value, null, 2);
    details.append(title, document.createElement('br'), document.createElement('br'), pre);
  }}

  function fit() {{
    if (!positions.size) return;
    const xs = [...positions.values()].map(p => p.x);
    const ys = [...positions.values()].map(p => p.y);
    const minX = Math.min(...xs), maxX = Math.max(...xs) + 170;
    const minY = Math.min(...ys), maxY = Math.max(...ys) + 58;
    const box = svg.getBoundingClientRect();
    const width = Math.max(1, maxX - minX), height = Math.max(1, maxY - minY);
    const scale = Math.min(1.25, Math.max(.08, Math.min((box.width - 70) / width, (box.height - 70) / height)));
    transform = {{x: 35 - minX * scale, y: 35 - minY * scale, scale}};
    applyTransform();
  }}

  function applySearch() {{
    const q = search.value.trim().toLowerCase();
    if (!q) {{
      nodeElements.forEach(el => el.classList.remove('dim'));
      edgeElements.forEach(item => {{ item.visible.classList.remove('dim'); item.text.classList.remove('dim'); }});
      return;
    }}
    const matched = new Set();
    for (const node of graph.nodes || []) {{
      const haystack = `${{node.id}} ${{node.name || ''}} ${{node.type || ''}}`.toLowerCase();
      if (haystack.includes(q)) matched.add(node.id);
    }}
    nodeElements.forEach((el, id) => el.classList.toggle('dim', !matched.has(id)));
    edgeElements.forEach(item => {{
      const keep = matched.has(item.edge.source) || matched.has(item.edge.target) || String(item.edge.relation).toLowerCase().includes(q);
      item.visible.classList.toggle('dim', !keep);
      item.text.classList.toggle('dim', !keep);
    }});
  }}

  svg.addEventListener('pointerdown', ev => {{
    if (ev.target.closest?.('.node')) return;
    panStart = {{x: ev.clientX, y: ev.clientY, tx: transform.x, ty: transform.y}};
    svg.classList.add('panning');
    svg.setPointerCapture(ev.pointerId);
  }});
  svg.addEventListener('pointermove', ev => {{
    if (!panStart) return;
    transform.x = panStart.tx + ev.clientX - panStart.x;
    transform.y = panStart.ty + ev.clientY - panStart.y;
    applyTransform();
  }});
  svg.addEventListener('pointerup', ev => {{
    panStart = null; svg.classList.remove('panning');
    try {{ svg.releasePointerCapture(ev.pointerId); }} catch (_) {{}}
  }});
  svg.addEventListener('wheel', ev => {{
    ev.preventDefault();
    const rect = svg.getBoundingClientRect();
    const mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
    const old = transform.scale;
    const next = Math.min(4, Math.max(.08, old * Math.exp(-ev.deltaY * .0012)));
    const gx = (mx - transform.x) / old, gy = (my - transform.y) / old;
    transform.scale = next;
    transform.x = mx - gx * next; transform.y = my - gy * next;
    applyTransform();
  }}, {{passive:false}});
  svg.addEventListener('click', () => {{
    document.querySelectorAll('.node.selected').forEach(el => el.classList.remove('selected'));
  }});
  search.addEventListener('input', applySearch);
  document.getElementById('fit').addEventListener('click', fit);
  document.getElementById('reset').addEventListener('click', () => {{ computeLayout(); renderNodes(); renderEdges(); fit(); }});
  window.addEventListener('resize', fit);

  computeLayout();
  renderNodes();
  renderEdges();
  applyTransform();
  requestAnimationFrame(fit);
}})();
</script>
</body>
</html>
"""


def write_graph_html(
    graph: dict[str, Any],
    path: str | Path,
    *,
    open_browser: bool = False,
) -> Path:
    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.stat().st_size > 0:
        raise FileExistsError(f"ExecWeave viewer output already exists: {output}")
    output.write_text(render_graph_html(graph), encoding="utf-8")
    if open_browser:
        webbrowser.open(output.as_uri())
    return output


def build_viewer_from_graph(
    graph_path: str | Path,
    output_path: str | Path,
    *,
    open_browser: bool = False,
) -> Path:
    graph = load_graph(graph_path)
    return write_graph_html(graph, output_path, open_browser=open_browser)
