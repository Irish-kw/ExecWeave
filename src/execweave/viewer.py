from __future__ import annotations

import json
import webbrowser
from pathlib import Path
from typing import Any

from .graph_ops import load_graph


def _safe_embedded_json(payload: dict[str, Any]) -> str:
    return (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


_VIEWER_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ExecWeave — Execution Graph</title>
<style>
:root{color-scheme:dark;--bg:#0b0f14;--panel:#111821;--panel2:#18222e;--text:#e8edf3;--muted:#8ea0b5;--border:#2a3949;--edge:#72869c;--causal:#70d6a6;--noncausal:#f2b76d;--selected:#73b7ff}
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:var(--bg);color:var(--text);font:14px/1.4 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
#app{display:grid;grid-template-columns:minmax(0,1fr) 340px;grid-template-rows:auto minmax(0,1fr);width:100%;height:100%}
header{grid-column:1/3;display:flex;align-items:center;gap:9px;padding:9px 14px;border-bottom:1px solid var(--border);background:var(--panel);flex-wrap:wrap}
header strong{font-size:16px;margin-right:6px}.stats{color:var(--muted);white-space:nowrap;margin-right:auto}
input,select{border:1px solid var(--border);border-radius:7px;padding:7px 9px;background:var(--panel2);color:var(--text);outline:none}input:focus,select:focus{border-color:var(--selected)}
#search{width:min(300px,35vw)}.toggle{display:inline-flex;align-items:center;gap:5px;color:var(--muted);font-size:12px;white-space:nowrap}.toggle input{accent-color:var(--selected)}
#canvas-wrap{position:relative;min-width:0;min-height:0;overflow:hidden}#graph{width:100%;height:100%;display:block;cursor:grab;user-select:none}#graph.panning{cursor:grabbing}
aside{overflow:auto;border-left:1px solid var(--border);background:var(--panel);padding:16px}aside h2{margin:0 0 12px;font-size:15px}aside h3{margin:18px 0 8px;font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
#details pre{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}.empty{color:var(--muted)}
.controls{position:absolute;top:12px;left:12px;z-index:5;display:flex;gap:6px}.controls button{border:1px solid var(--border);background:var(--panel);color:var(--text);border-radius:7px;padding:6px 9px;cursor:pointer}.controls button:hover{border-color:var(--selected)}
.node rect{stroke:var(--border);stroke-width:1.2;rx:9;ry:9}.node text{pointer-events:none;fill:var(--text)}.node .node-type{fill:var(--muted);font-size:10px}.node.selected rect{stroke:var(--selected);stroke-width:2.5}.node.dim{opacity:.13}
.edge{fill:none;stroke:var(--edge);stroke-width:1.4;opacity:.75;cursor:pointer}.edge.causal{stroke:var(--causal)}.edge.noncausal{stroke:var(--noncausal);stroke-dasharray:6 5}.edge.dim{opacity:.06}.edge-hit{fill:none;stroke:transparent;stroke-width:12;cursor:pointer}.edge-label{fill:var(--muted);font-size:9px;pointer-events:none}.edge-label.dim{opacity:.08}
.legend{display:flex;flex-wrap:wrap;gap:8px 12px}.legend span{display:inline-flex;align-items:center;gap:5px;color:var(--muted);font-size:12px}.dot{width:9px;height:9px;border-radius:50%;display:inline-block}
@media(max-width:900px){#app{grid-template-columns:1fr;grid-template-rows:auto minmax(0,1fr) 220px}header{grid-column:1}aside{border-left:0;border-top:1px solid var(--border)}#search{width:180px}}
</style>
</head>
<body>
<div id="app">
<header>
  <strong>ExecWeave</strong><span class="stats" id="stats"></span>
  <select id="type-filter" title="Node type"><option value="">All node types</option></select>
  <select id="relation-filter" title="Relation"><option value="">All relations</option></select>
  <label class="toggle"><input id="causal-filter" type="checkbox"> causal only</label>
  <input id="search" placeholder="Search visible graph…" autocomplete="off">
</header>
<div id="canvas-wrap">
  <div class="controls"><button id="fit">Fit</button><button id="reset">Reset</button></div>
  <svg id="graph" aria-label="ExecWeave execution graph">
    <defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10z" fill="context-stroke"></path></marker></defs>
    <g id="viewport"><g id="edges"></g><g id="labels"></g><g id="nodes"></g></g>
  </svg>
</div>
<aside>
  <h2>Selection</h2><div id="details" class="empty">Click a node or edge.</div>
  <h3>Filters</h3><div class="empty">Node type and relation filters change the visible subgraph. Search highlights within that subgraph.</div>
  <h3>Edge semantics</h3><div class="legend"><span><i class="dot" style="background:var(--causal)"></i>Causal evidence</span><span><i class="dot" style="background:var(--noncausal)"></i>Non-causal observation</span><span><i class="dot" style="background:var(--edge)"></i>Mixed / unspecified</span></div>
  <h3>Navigation</h3><div class="empty">Wheel to zoom. Drag background to pan. Drag nodes to rearrange.</div>
</aside>
</div>
<script type="application/json" id="graph-data">__GRAPH_DATA__</script>
<script>
(()=>{
const graph=JSON.parse(document.getElementById('graph-data').textContent);
const allNodes=graph.nodes||[],allEdges=graph.edges||[];
const svg=document.getElementById('graph'),viewport=document.getElementById('viewport'),edgeLayer=document.getElementById('edges'),labelLayer=document.getElementById('labels'),nodeLayer=document.getElementById('nodes');
const details=document.getElementById('details'),search=document.getElementById('search'),stats=document.getElementById('stats'),typeFilter=document.getElementById('type-filter'),relationFilter=document.getElementById('relation-filter'),causalFilter=document.getElementById('causal-filter');
let visibleNodes=[],visibleEdges=[],nodeById=new Map(),positions=new Map(),nodeElements=new Map(),edgeElements=[];
let transform={x:40,y:40,scale:1},panStart=null,dragNode=null;

function option(select,value){const o=document.createElement('option');o.value=value;o.textContent=value;select.appendChild(o)}
[...new Set(allNodes.map(n=>n.type).filter(Boolean))].sort().forEach(v=>option(typeFilter,v));
[...new Set(allEdges.map(e=>e.relation).filter(Boolean))].sort().forEach(v=>option(relationFilter,v));
function colorForType(type){let h=0;for(const ch of String(type||'unknown'))h=((h<<5)-h+ch.charCodeAt(0))|0;return `hsl(${Math.abs(h)%360} 38% 27%)`}
function labelFor(node){const raw=node.name||node.id||node.type||'node';return raw.length>30?raw.slice(0,27)+'…':raw}
function applyGraphFilters(){
  const type=typeFilter.value,relation=relationFilter.value,causal=causalFilter.checked;
  let nodes=allNodes.filter(n=>!type||n.type===type);let ids=new Set(nodes.map(n=>n.id));
  let edges=allEdges.filter(e=>ids.has(e.source)&&ids.has(e.target)&&(!relation||e.relation===relation)&&(!causal||e.causal===true));
  if(relation||causal){const connected=new Set();edges.forEach(e=>{connected.add(e.source);connected.add(e.target)});nodes=nodes.filter(n=>connected.has(n.id))}
  visibleNodes=nodes;visibleEdges=edges;nodeById=new Map(nodes.map(n=>[n.id,n]));positions=new Map();
  computeLayout();renderNodes();renderEdges();updateStats();applyTransform();applySearch();requestAnimationFrame(fit);
}
function updateStats(){stats.textContent=`${visibleNodes.length}/${allNodes.length} nodes · ${visibleEdges.length}/${allEdges.length} edges · ${graph.event_count??0} events`}
function computeLayout(){
  const ids=[...nodeById.keys()],indegree=new Map(ids.map(id=>[id,0])),outgoing=new Map(ids.map(id=>[id,[]]));
  visibleEdges.forEach(e=>{if(!nodeById.has(e.source)||!nodeById.has(e.target))return;indegree.set(e.target,(indegree.get(e.target)||0)+1);outgoing.get(e.source).push(e.target)});
  const roots=ids.filter(id=>(indegree.get(id)||0)===0);if(!roots.length&&ids.length)roots.push(ids[0]);const depth=new Map(),q=roots.map(id=>[id,0]);q.forEach(([id,d])=>depth.set(id,d));
  for(let i=0;i<q.length;i++){const [id,d]=q[i];for(const next of outgoing.get(id)||[]){if(!depth.has(next)){depth.set(next,d+1);q.push([next,d+1])}}}
  const max=Math.max(0,...depth.values());ids.forEach(id=>{if(!depth.has(id))depth.set(id,max+1)});const layers=new Map();ids.forEach(id=>{const d=depth.get(id);if(!layers.has(d))layers.set(d,[]);layers.get(d).push(id)});
  [...layers.entries()].sort((a,b)=>a[0]-b[0]).forEach(([d,layer])=>{layer.sort((a,b)=>String(nodeById.get(a).type).localeCompare(String(nodeById.get(b).type))||a.localeCompare(b));layer.forEach((id,i)=>positions.set(id,{x:d*250,y:i*88}))});
}
function applyTransform(){viewport.setAttribute('transform',`translate(${transform.x} ${transform.y}) scale(${transform.scale})`)}
function anchor(id,right){const p=positions.get(id)||{x:0,y:0};return{x:p.x+(right?170:0),y:p.y+29}}
function edgePath(e){const a=anchor(e.source,true),b=anchor(e.target,false),bend=Math.max(45,Math.abs(b.x-a.x)*.45);return `M ${a.x} ${a.y} C ${a.x+bend} ${a.y}, ${b.x-bend} ${b.y}, ${b.x} ${b.y}`}
function showDetails(kind,value){details.classList.remove('empty');details.replaceChildren();const t=document.createElement('strong');t.textContent=kind;const p=document.createElement('pre');p.textContent=JSON.stringify(value,null,2);details.append(t,document.createElement('br'),document.createElement('br'),p)}
function renderEdges(){edgeLayer.replaceChildren();labelLayer.replaceChildren();edgeElements=[];visibleEdges.forEach(edge=>{if(!positions.has(edge.source)||!positions.has(edge.target))return;const d=edgePath(edge);const line=document.createElementNS('http://www.w3.org/2000/svg','path');line.setAttribute('d',d);line.setAttribute('marker-end','url(#arrow)');line.classList.add('edge');if(edge.causal===true)line.classList.add('causal');else if(edge.causal===false)line.classList.add('noncausal');edgeLayer.appendChild(line);const hit=document.createElementNS('http://www.w3.org/2000/svg','path');hit.setAttribute('d',d);hit.classList.add('edge-hit');hit.addEventListener('click',ev=>{ev.stopPropagation();showDetails('Edge',edge)});edgeLayer.appendChild(hit);const a=anchor(edge.source,true),b=anchor(edge.target,false),text=document.createElementNS('http://www.w3.org/2000/svg','text');text.setAttribute('x',String((a.x+b.x)/2));text.setAttribute('y',String((a.y+b.y)/2-7));text.setAttribute('text-anchor','middle');text.classList.add('edge-label');text.textContent=edge.count>1?`${edge.relation} ×${edge.count}`:edge.relation;labelLayer.appendChild(text);edgeElements.push({edge,visible:line,hit,text})})}
function renderNodes(){nodeLayer.replaceChildren();nodeElements=new Map();visibleNodes.forEach(node=>{const p=positions.get(node.id);if(!p)return;const g=document.createElementNS('http://www.w3.org/2000/svg','g');g.classList.add('node');g.setAttribute('transform',`translate(${p.x} ${p.y})`);const r=document.createElementNS('http://www.w3.org/2000/svg','rect');r.setAttribute('width','170');r.setAttribute('height','58');r.setAttribute('fill',colorForType(node.type));g.appendChild(r);const type=document.createElementNS('http://www.w3.org/2000/svg','text');type.setAttribute('x','12');type.setAttribute('y','18');type.classList.add('node-type');type.textContent=node.type||'unknown';g.appendChild(type);const label=document.createElementNS('http://www.w3.org/2000/svg','text');label.setAttribute('x','12');label.setAttribute('y','39');label.textContent=labelFor(node);g.appendChild(label);g.addEventListener('pointerdown',ev=>{ev.stopPropagation();const pt=svgPoint(ev);dragNode={id:node.id,dx:pt.x-p.x,dy:pt.y-p.y};g.setPointerCapture(ev.pointerId)});g.addEventListener('pointermove',ev=>{if(!dragNode||dragNode.id!==node.id)return;const pt=svgPoint(ev),np={x:pt.x-dragNode.dx,y:pt.y-dragNode.dy};positions.set(node.id,np);g.setAttribute('transform',`translate(${np.x} ${np.y})`);renderEdges()});g.addEventListener('pointerup',ev=>{dragNode=null;try{g.releasePointerCapture(ev.pointerId)}catch(_){}});g.addEventListener('click',ev=>{ev.stopPropagation();document.querySelectorAll('.node.selected').forEach(el=>el.classList.remove('selected'));g.classList.add('selected');showDetails('Node',node)});nodeLayer.appendChild(g);nodeElements.set(node.id,g)})}
function svgPoint(ev){const rect=svg.getBoundingClientRect();return{x:(ev.clientX-rect.left-transform.x)/transform.scale,y:(ev.clientY-rect.top-transform.y)/transform.scale}}
function fit(){if(!positions.size)return;const xs=[...positions.values()].map(p=>p.x),ys=[...positions.values()].map(p=>p.y),minX=Math.min(...xs),maxX=Math.max(...xs)+170,minY=Math.min(...ys),maxY=Math.max(...ys)+58,box=svg.getBoundingClientRect(),width=Math.max(1,maxX-minX),height=Math.max(1,maxY-minY),scale=Math.min(1.25,Math.max(.08,Math.min((box.width-70)/width,(box.height-70)/height)));transform={x:35-minX*scale,y:35-minY*scale,scale};applyTransform()}
function applySearch(){const q=search.value.trim().toLowerCase();if(!q){nodeElements.forEach(el=>el.classList.remove('dim'));edgeElements.forEach(i=>{i.visible.classList.remove('dim');i.text.classList.remove('dim')});return}const matched=new Set();visibleNodes.forEach(n=>{if(`${n.id} ${n.name||''} ${n.type||''}`.toLowerCase().includes(q))matched.add(n.id)});nodeElements.forEach((el,id)=>el.classList.toggle('dim',!matched.has(id)));edgeElements.forEach(i=>{const keep=matched.has(i.edge.source)||matched.has(i.edge.target)||String(i.edge.relation).toLowerCase().includes(q);i.visible.classList.toggle('dim',!keep);i.text.classList.toggle('dim',!keep)})}
svg.addEventListener('pointerdown',ev=>{if(ev.target.closest?.('.node'))return;panStart={x:ev.clientX,y:ev.clientY,tx:transform.x,ty:transform.y};svg.classList.add('panning');svg.setPointerCapture(ev.pointerId)});svg.addEventListener('pointermove',ev=>{if(!panStart)return;transform.x=panStart.tx+ev.clientX-panStart.x;transform.y=panStart.ty+ev.clientY-panStart.y;applyTransform()});svg.addEventListener('pointerup',ev=>{panStart=null;svg.classList.remove('panning');try{svg.releasePointerCapture(ev.pointerId)}catch(_){}});svg.addEventListener('wheel',ev=>{ev.preventDefault();const rect=svg.getBoundingClientRect(),mx=ev.clientX-rect.left,my=ev.clientY-rect.top,old=transform.scale,next=Math.min(4,Math.max(.08,old*Math.exp(-ev.deltaY*.0012))),gx=(mx-transform.x)/old,gy=(my-transform.y)/old;transform.scale=next;transform.x=mx-gx*next;transform.y=my-gy*next;applyTransform()},{passive:false});
search.addEventListener('input',applySearch);[typeFilter,relationFilter,causalFilter].forEach(el=>el.addEventListener('change',applyGraphFilters));document.getElementById('fit').addEventListener('click',fit);document.getElementById('reset').addEventListener('click',()=>{computeLayout();renderNodes();renderEdges();applySearch();fit()});window.addEventListener('resize',fit);svg.addEventListener('click',()=>document.querySelectorAll('.node.selected').forEach(el=>el.classList.remove('selected')));
applyGraphFilters();
})();
</script>
</body>
</html>
"""


def render_graph_html(graph: dict[str, Any]) -> str:
    return _VIEWER_TEMPLATE.replace("__GRAPH_DATA__", _safe_embedded_json(graph))


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
