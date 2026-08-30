from __future__ import annotations

import json
import webbrowser
from pathlib import Path
from typing import Any

from .graph_ops import load_graph

VIEWER_MAX_NODES = 1500
VIEWER_MAX_EDGES = 4000
VIEWER_MAX_DOM_ELEMENTS = 5000


def _safe_embedded_json(payload: dict[str, Any]) -> str:
    return (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _graph_render_counts(graph: dict[str, Any]) -> tuple[int, int]:
    """Count every node/edge that the standalone viewer could materialize.

    Expansion members are included even while collapsed because the current
    standalone viewer embeds them in the page. This keeps the safety guard tied
    to browser memory pressure rather than only to the initially visible graph.
    """

    nodes = graph.get("nodes")
    edges = graph.get("edges")
    node_count = len(nodes) if isinstance(nodes, list) else 0
    edge_count = len(edges) if isinstance(edges, list) else 0

    expansion = graph.get("expansion")
    clusters = expansion.get("clusters") if isinstance(expansion, dict) else None
    if isinstance(clusters, dict):
        for entry in clusters.values():
            if not isinstance(entry, dict):
                continue
            members = entry.get("nodes")
            member_edges = entry.get("edges")
            if isinstance(members, list):
                node_count += len(members)
            if isinstance(member_edges, list):
                edge_count += len(member_edges)
    return node_count, edge_count


def _estimated_svg_elements(node_count: int, edge_count: int) -> int:
    # Current retained SVG uses roughly 4 elements/node and 3 elements/edge.
    return node_count * 4 + edge_count * 3


def _render_protective_html(graph: dict[str, Any], node_count: int, edge_count: int) -> str:
    event_count = graph.get("event_count")
    event_text = str(event_count) if isinstance(event_count, int) else "unknown"
    estimated_dom = _estimated_svg_elements(node_count, edge_count)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ExecWeave — Large Graph Protective Mode</title>
<style>
:root{{color-scheme:dark;--bg:#0b0f14;--panel:#111821;--text:#e8edf3;--muted:#9eb0c4;--border:#2a3949;--accent:#73b7ff}}
*{{box-sizing:border-box}}html,body{{margin:0;min-height:100%;background:var(--bg);color:var(--text);font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:820px;margin:8vh auto;padding:28px;border:1px solid var(--border);border-radius:12px;background:var(--panel)}}
h1{{margin:0 0 12px;font-size:23px}}.badge{{display:inline-block;margin-bottom:18px;padding:4px 9px;border:1px solid var(--accent);border-radius:999px;color:var(--accent);font-size:12px;font-weight:700;letter-spacing:.04em}}
.stats{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:22px 0}}.stat{{padding:12px;border:1px solid var(--border);border-radius:8px}}.stat strong{{display:block;font-size:22px}}.stat span,p{{color:var(--muted)}}code{{color:var(--text)}}
@media(max-width:720px){{main{{margin:18px;padding:20px}}.stats{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
</style>
</head>
<body>
<main>
  <div class="badge">LARGE GRAPH PROTECTIVE MODE</div>
  <h1>Rendering disabled to protect browser memory.</h1>
  <p>The underlying ExecWeave graph exceeds the standalone SVG safety budget. No evidence was deleted or reclassified; only browser rendering was withheld.</p>
  <div class="stats">
    <div class="stat"><strong>{node_count}</strong><span>possible nodes</span></div>
    <div class="stat"><strong>{edge_count}</strong><span>possible edges</span></div>
    <div class="stat"><strong>{estimated_dom}</strong><span>estimated SVG elements</span></div>
    <div class="stat"><strong>{event_text}</strong><span>events</span></div>
  </div>
  <p>Hard safety limits: <strong>{VIEWER_MAX_NODES}</strong> possible nodes, <strong>{VIEWER_MAX_EDGES}</strong> possible edges, and approximately <strong>{VIEWER_MAX_DOM_ELEMENTS}</strong> SVG DOM elements. Use <code>graph-focus</code>, <code>graph-filter</code>, or <code>graph-condense</code> to create a smaller view. The full graph and raw evidence remain in the run artifacts.</p>
</main>
</body>
</html>
"""


_VIEWER_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ExecWeave — Execution Graph</title>
<style>
:root{color-scheme:dark;--bg:#0b0f14;--panel:#111821;--panel2:#18222e;--text:#e8edf3;--muted:#8ea0b5;--border:#2a3949;--edge:#72869c;--causal:#70d6a6;--noncausal:#f2b76d;--inferred:#c08cff;--identity:#38bdf8;--selected:#73b7ff}
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:var(--bg);color:var(--text);font:14px/1.4 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
#app{display:grid;grid-template-columns:minmax(0,1fr) 340px;grid-template-rows:auto minmax(0,1fr);width:100%;height:100%}
header{grid-column:1/3;display:flex;align-items:center;gap:9px;padding:9px 14px;border-bottom:1px solid var(--border);background:var(--panel);flex-wrap:wrap}
header strong{font-size:16px;margin-right:6px}.stats{color:var(--muted);white-space:nowrap;margin-right:auto}
input,select{border:1px solid var(--border);border-radius:7px;padding:7px 9px;background:var(--panel2);color:var(--text);outline:none}input:focus,select:focus{border-color:var(--selected)}
#search{width:min(240px,28vw)}#preset-select{max-width:160px}.toggle{display:inline-flex;align-items:center;gap:5px;color:var(--muted);font-size:12px;white-space:nowrap}.toggle input{accent-color:var(--selected)}
.timeline{display:flex;align-items:center;gap:7px;width:100%;padding-top:2px;color:var(--muted);font-size:12px}.timeline input[type=range]{flex:1;min-width:120px;padding:0;accent-color:var(--selected)}#sequence-label{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;white-space:nowrap}
#canvas-wrap{position:relative;min-width:0;min-height:0;overflow:hidden}#graph{width:100%;height:100%;display:block;cursor:grab;user-select:none}#graph.panning{cursor:grabbing}
aside{overflow:auto;border-left:1px solid var(--border);background:var(--panel);padding:16px}aside h2{margin:0 0 12px;font-size:15px}aside h3{margin:18px 0 8px;font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
#details pre{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}.empty{color:var(--muted)}.execweave-said{margin:10px 0;padding:11px;border:1px solid var(--border);border-radius:9px;background:var(--panel2)}.execweave-said-head{padding-bottom:8px;margin-bottom:9px;border-bottom:1px solid var(--border)}.execweave-said-title{font-size:13px;font-weight:700;color:var(--text);overflow-wrap:anywhere}.execweave-said-count{font-size:11px;color:var(--muted);margin-top:2px}.execweave-said-turn{display:grid;grid-template-columns:88px 1fr;gap:10px;padding:7px 0;border-top:1px solid var(--border)}.execweave-said-turn:first-of-type{border-top:0}.execweave-said-who{font-size:10px;color:var(--muted);overflow-wrap:anywhere}.execweave-said-who.self{color:var(--selected)}.execweave-said-body{font-size:12px;color:var(--text);white-space:pre-wrap;overflow-wrap:anywhere}.execweave-said-body.quiet{color:var(--muted);font-style:italic}.execweave-said-ctx summary{cursor:pointer;color:var(--muted);font-size:11px;font-style:italic}.execweave-said-ctx .execweave-said-body{margin-top:6px;padding:8px;background:rgba(0,0,0,.14);border-radius:6px;max-height:200px;overflow:auto}.execweave-raw-node{margin-top:10px}.execweave-raw-node summary{cursor:pointer;color:var(--muted);font-size:11px}@media(max-width:620px){.execweave-said-turn{grid-template-columns:1fr;gap:2px}}.detail-actions{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0 8px}.identity-note{margin:10px 0;padding:8px 10px;border:1px solid var(--identity);border-radius:7px;color:var(--text);background:var(--panel2);font-size:12px}
.correlation-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}.correlation-stat{border:1px solid var(--border);border-radius:7px;background:var(--panel2);padding:7px 9px;color:var(--muted);font-size:11px}.correlation-stat strong{display:block;color:var(--text);font-size:16px;line-height:1.2;margin-top:2px}
button{border:1px solid var(--border);background:var(--panel);color:var(--text);border-radius:7px;padding:6px 9px;cursor:pointer}button:hover{border-color:var(--selected)}button:disabled{opacity:.45;cursor:default}
.controls{position:absolute;top:12px;left:12px;z-index:5;display:flex;gap:6px;flex-wrap:wrap}
.node rect{stroke:var(--border);stroke-width:1.2;rx:9;ry:9}.node text{pointer-events:none;fill:var(--text)}.node .node-type{fill:var(--muted);font-size:10px}.node.selected rect{stroke:var(--selected);stroke-width:2.5}.node.dim{opacity:.13}.node.cluster rect{stroke:var(--selected);stroke-dasharray:6 4}
.edge{fill:none;stroke:var(--edge);stroke-width:1.4;opacity:.75;cursor:pointer}.edge.causal{stroke:var(--causal)}.edge.noncausal{stroke:var(--noncausal);stroke-dasharray:6 5}.edge.inferred{stroke:var(--inferred);stroke-width:1.8;stroke-dasharray:2 5}.edge.identity{stroke:var(--identity);stroke-width:2.2;stroke-dasharray:none}.edge.dim{opacity:.06}.edge-hit{fill:none;stroke:transparent;stroke-width:12;cursor:pointer}.edge-label{fill:var(--muted);font-size:9px;pointer-events:none}.edge-label.dim{opacity:.08}
.legend{display:flex;flex-wrap:wrap;gap:8px 12px}.legend span{display:inline-flex;align-items:center;gap:5px;color:var(--muted);font-size:12px}.dot{width:9px;height:9px;border-radius:50%;display:inline-block}
@media(max-width:900px){#app{grid-template-columns:1fr;grid-template-rows:auto minmax(0,1fr) 220px}header{grid-column:1}aside{border-left:0;border-top:1px solid var(--border)}#search{width:160px}}
</style>
</head>
<body>
<div id="app">
<header>
  <strong>ExecWeave</strong><span class="stats" id="stats"></span>
  <select id="type-filter" title="Node type"><option value="">All node types</option></select>
  <select id="relation-filter" title="Relation"><option value="">All relations</option></select>
  <label class="toggle"><input id="causal-filter" type="checkbox"> causal only</label>
  <label class="toggle"><input id="observed-only-filter" type="checkbox"> observed only</label>
  <input id="search" placeholder="Search visible graph…" autocomplete="off">
  <select id="preset-select" title="Saved view presets"><option value="">Saved views</option></select>
  <button id="save-preset" type="button">Save view</button>
  <button id="delete-preset" type="button" disabled>Delete view</button>
  <div class="timeline" id="timeline">
    <button id="timeline-play" type="button">Play</button>
    <span>Evidence sequence</span>
    <input id="sequence-filter" type="range" min="0" max="0" value="0" step="1">
    <span id="sequence-label">0 / 0</span>
  </div>
</header>
<div id="canvas-wrap">
  <div class="controls">
    <button id="fit">Fit</button>
    <button id="reset">Reset</button>
    <button id="clear-focus" disabled>Clear focus</button>
    <button id="collapse-clusters" disabled>Collapse clusters</button>
  </div>
  <svg id="graph" aria-label="ExecWeave execution graph">
    <defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10z" fill="context-stroke"></path></marker></defs>
    <g id="viewport"><g id="edges"></g><g id="labels"></g><g id="nodes"></g></g>
  </svg>
</div>
<aside>
  <h2>Selection</h2><div id="details" class="empty">Click a node or edge.</div>
  <section id="correlation-section" hidden><h3>Correlation</h3><div id="correlation-summary" class="correlation-summary"></div><div id="correlation-note" class="empty"></div></section>
  <h3>Saved views</h3><div class="empty">Save the current node/relation/causal/observed-only filters, search text, timeline position, focused neighborhood, and expanded clusters as a browser-local preset. Graph evidence is never copied into preset storage. If browser storage is unavailable, presets safely fall back to this page session only.</div>
  <h3>Focus</h3><div class="empty">Click a node, then choose <strong>Focus 1 hop</strong> or <strong>Focus 2 hops</strong>. Focus follows only edges allowed by the current timeline, relation, causal, and observed-only filters; it never creates inferred edges.</div>
  <h3>Clusters</h3><div class="empty">Expandable cluster nodes have a dashed outline. Click one, then choose <strong>Expand cluster</strong>. Only graphs created with <code>graph-condense --keep-expansion</code> carry the original member evidence.</div>
  <h3>Timeline</h3><div class="empty">Move the evidence-sequence slider or press Play to replay how the graph grew. Aggregated edges spanning future evidence are marked <code>partial</code>; future counts are never shown early.</div>
  <h3>Filters</h3><div class="empty">Node type and relation filters change the visible subgraph. <strong>Observed only</strong> removes derived inferred relationships before focus traversal and layout. Exact identity remains visible because it is explicit identity evidence, while still non-causal. Search highlights within the remaining subgraph.</div>
  <h3>Edge semantics</h3><div class="legend"><span><i class="dot" style="background:var(--causal)"></i>Causal evidence</span><span><i class="dot" style="background:var(--identity)"></i>Exact identity</span><span><i class="dot" style="background:var(--noncausal)"></i>Non-causal observation</span><span><i class="dot" style="background:var(--inferred)"></i>Inferred correlation</span><span><i class="dot" style="background:var(--edge)"></i>Mixed / unspecified</span></div><div class="empty">Exact identity means two observations carry an explicit shared identity; it does not prove one layer caused another. Inferred edges are heuristic correlations backed by explicit supporting evidence. They are not observed or causal evidence.</div>
</aside>
</div>
<script type="application/json" id="graph-data">__GRAPH_DATA__</script>
<script>
(()=>{
const graph=JSON.parse(document.getElementById('graph-data').textContent);
const baseNodes=graph.nodes||[],baseEdges=graph.edges||[];
const expansionClusters=(graph.expansion&&graph.expansion.clusters)||{};
const possibleNodes=[...baseNodes],possibleEdges=[...baseEdges];
Object.values(expansionClusters).forEach(entry=>{(entry.nodes||[]).forEach(n=>possibleNodes.push(n));(entry.edges||[]).forEach(e=>possibleEdges.push(e))});
const svg=document.getElementById('graph'),viewport=document.getElementById('viewport'),edgeLayer=document.getElementById('edges'),labelLayer=document.getElementById('labels'),nodeLayer=document.getElementById('nodes');
const details=document.getElementById('details'),search=document.getElementById('search'),stats=document.getElementById('stats'),typeFilter=document.getElementById('type-filter'),relationFilter=document.getElementById('relation-filter'),causalFilter=document.getElementById('causal-filter'),observedOnlyFilter=document.getElementById('observed-only-filter');
const correlationSection=document.getElementById('correlation-section'),correlationSummary=document.getElementById('correlation-summary'),correlationNote=document.getElementById('correlation-note');
const timeline=document.getElementById('timeline'),sequenceFilter=document.getElementById('sequence-filter'),sequenceLabel=document.getElementById('sequence-label'),playButton=document.getElementById('timeline-play'),collapseButton=document.getElementById('collapse-clusters'),clearFocusButton=document.getElementById('clear-focus');
const presetSelect=document.getElementById('preset-select'),savePresetButton=document.getElementById('save-preset'),deletePresetButton=document.getElementById('delete-preset');
const presetStorageKey=`execweave.viewer.presets.v1:${graph.session_id||'graph'}`;
const sequenceOf=(edge,key)=>Number.isInteger(edge[key])?edge[key]:null;
let maxSequence=0;possibleEdges.forEach(edge=>{const value=sequenceOf(edge,'last_sequence')??sequenceOf(edge,'first_sequence')??0;if(value>maxSequence)maxSequence=value});
let selectedSequence=maxSequence,playTimer=null,expandedClusters=new Set(),focusState=null,currentNodes=[],currentEdges=[],visibleNodes=[],visibleEdges=[],nodeById=new Map(),positions=new Map(),nodeElements=new Map(),edgeElements=[];
let transform={x:40,y:40,scale:1},panStart=null,dragNode=null,presets={},presetStorageAvailable=true,edgeRenderFrame=null;

function uniqueById(values){const seen=new Set();return values.filter(value=>{if(!value||!value.id||seen.has(value.id))return false;seen.add(value.id);return true})}
function materializedGraph(){
  const hiddenClusterEdges=new Set();
  expandedClusters.forEach(id=>{const entry=expansionClusters[id];if(entry&&entry.cluster_edge_id)hiddenClusterEdges.add(entry.cluster_edge_id)});
  let nodes=baseNodes.filter(node=>!expandedClusters.has(node.id));
  let edges=baseEdges.filter(edge=>!hiddenClusterEdges.has(edge.id));
  expandedClusters.forEach(id=>{const entry=expansionClusters[id];if(!entry)return;nodes=nodes.concat(entry.nodes||[]);edges=edges.concat(entry.edges||[])});
  return{nodes:uniqueById(nodes),edges:uniqueById(edges)};
}
function option(select,value){const o=document.createElement('option');o.value=value;o.textContent=value;select.appendChild(o)}
[...new Set(possibleNodes.map(n=>n.type).filter(Boolean))].sort().forEach(v=>option(typeFilter,v));
[...new Set(possibleEdges.map(e=>e.relation).filter(Boolean))].sort().forEach(v=>option(relationFilter,v));
if(maxSequence>0){sequenceFilter.max=String(maxSequence);sequenceFilter.value=String(maxSequence);sequenceLabel.textContent=`${maxSequence} / ${maxSequence}`}else{timeline.style.display='none'}
function colorForType(type){let h=0;for(const ch of String(type||'unknown'))h=((h<<5)-h+ch.charCodeAt(0))|0;return `hsl(${Math.abs(h)%360} 38% 27%)`}
function labelFor(node){const raw=node.name||node.id||node.type||'node';return raw.length>30?raw.slice(0,27)+'…':raw}
function edgeExistsAt(edge,sequence){const first=sequenceOf(edge,'first_sequence');return first===null||first<=sequence}
function edgeLabel(edge){const relation=edge.identity_exact===true?`${edge.relation} · exact identity`:edge.inferred===true?`${edge.relation} · inferred`:edge.relation;if(!(edge.count>1))return relation;const last=sequenceOf(edge,'last_sequence');if(selectedSequence>=maxSequence||last===null||last<=selectedSequence)return `${relation} ×${edge.count}`;return `${relation} · partial`}
function evidenceEdges(nodes,edges){
  const ids=new Set(nodes.map(n=>n.id)),relation=relationFilter.value,causal=causalFilter.checked,observedOnly=observedOnlyFilter.checked;
  return edges.filter(e=>ids.has(e.source)&&ids.has(e.target)&&(!relation||e.relation===relation)&&(!causal||e.causal===true)&&(!observedOnly||e.inferred!==true)&&edgeExistsAt(e,selectedSequence));
}
function focusNeighborhood(nodes,edges,state){
  if(!state)return new Set(nodes.map(n=>n.id));
  const ids=new Set(nodes.map(n=>n.id));if(!ids.has(state.anchor))return new Set();
  const adjacency=new Map();nodes.forEach(n=>adjacency.set(n.id,[]));
  edges.forEach(e=>{if(!adjacency.has(e.source)||!adjacency.has(e.target))return;adjacency.get(e.source).push(e.target);adjacency.get(e.target).push(e.source)});
  const selected=new Set([state.anchor]),queue=[[state.anchor,0]];
  for(let i=0;i<queue.length;i++){const [id,depth]=queue[i];if(depth>=state.hops)continue;for(const next of adjacency.get(id)||[]){if(selected.has(next))continue;selected.add(next);queue.push([next,depth+1])}}
  return selected;
}
function applyGraphFilters(){
  const materialized=materializedGraph();currentNodes=materialized.nodes;currentEdges=materialized.edges;
  const type=typeFilter.value,relation=relationFilter.value,causal=causalFilter.checked,observedOnly=observedOnlyFilter.checked,timelineActive=maxSequence>0&&selectedSequence<maxSequence;
  const eligible=evidenceEdges(currentNodes,currentEdges),focusIds=focusNeighborhood(currentNodes,eligible,focusState);
  let nodes=currentNodes.filter(n=>focusIds.has(n.id)&&(!type||n.type===type));let ids=new Set(nodes.map(n=>n.id));
  let edges=eligible.filter(e=>ids.has(e.source)&&ids.has(e.target));
  if(relation||causal||observedOnly||timelineActive){const connected=new Set();edges.forEach(e=>{connected.add(e.source);connected.add(e.target)});if(focusState&&ids.has(focusState.anchor))connected.add(focusState.anchor);nodes=nodes.filter(n=>connected.has(n.id));ids=new Set(nodes.map(n=>n.id));edges=edges.filter(e=>ids.has(e.source)&&ids.has(e.target))}
  visibleNodes=nodes;visibleEdges=edges;nodeById=new Map(nodes.map(n=>[n.id,n]));positions=new Map();collapseButton.disabled=expandedClusters.size===0;clearFocusButton.disabled=focusState===null;
  computeLayout();renderNodes();renderEdges();updateStats();applyTransform();applySearch();requestAnimationFrame(fit);
}
function updateStats(){
  const seq=maxSequence>0?` · seq ${selectedSequence}/${maxSequence}`:'';
  const expanded=expandedClusters.size?` · ${expandedClusters.size} cluster${expandedClusters.size===1?'':'s'} expanded`:'';
  const focused=focusState?` · focus ${focusState.hops}-hop`:'';
  const observed=observedOnlyFilter.checked?' · observed only':'';
  stats.textContent=`${visibleNodes.length}/${currentNodes.length} nodes · ${visibleEdges.length}/${currentEdges.length} edges · ${graph.event_count??0} events${seq}${expanded}${focused}${observed}`;
}
function renderCorrelationSummary(){
  const correlation=graph.metadata&&graph.metadata.correlation;
  if(!correlation||typeof correlation!=='object')return;
  const items=[
    ['Matched',correlation.correlated_tool_calls],
    ['Ambiguous',correlation.skipped_ambiguous],
    ['No match',correlation.skipped_no_match],
    ['Unsupported',correlation.skipped_unsupported],
    ['Considered',correlation.tool_calls_considered],
    ['Window (ms)',correlation.max_window_ms],
  ];
  correlationSummary.replaceChildren();
  items.forEach(([label,value])=>{const box=document.createElement('div');box.className='correlation-stat';const name=document.createElement('span');name.textContent=label;const count=document.createElement('strong');count.textContent=Number.isFinite(Number(value))?String(value):'—';box.append(name,count);correlationSummary.appendChild(box)});
  correlationNote.textContent='Missing inferred edges can mean conservative rejection: ambiguous, unmatched, or unsupported tool calls intentionally produce no bridge.';
  correlationSection.hidden=false;
}
function computeLayout(){
  const ids=[...nodeById.keys()],indegree=new Map(ids.map(id=>[id,0])),outgoing=new Map(ids.map(id=>[id,[]]));
  visibleEdges.forEach(e=>{if(!nodeById.has(e.source)||!nodeById.has(e.target))return;indegree.set(e.target,(indegree.get(e.target)||0)+1);outgoing.get(e.source).push(e.target)});
  const roots=ids.filter(id=>(indegree.get(id)||0)===0);if(!roots.length&&ids.length)roots.push(ids[0]);const depth=new Map(),q=roots.map(id=>[id,0]);q.forEach(([id,d])=>depth.set(id,d));
  for(let i=0;i<q.length;i++){const [id,d]=q[i];for(const next of outgoing.get(id)||[]){if(!depth.has(next)){depth.set(next,d+1);q.push([next,d+1])}}}
  let maxDepth=0;depth.forEach(value=>{if(value>maxDepth)maxDepth=value});ids.forEach(id=>{if(!depth.has(id))depth.set(id,maxDepth+1)});const layers=new Map();ids.forEach(id=>{const d=depth.get(id);if(!layers.has(d))layers.set(d,[]);layers.get(d).push(id)});
  [...layers.entries()].sort((a,b)=>a[0]-b[0]).forEach(([d,layer])=>{layer.sort((a,b)=>String(nodeById.get(a).type).localeCompare(String(nodeById.get(b).type))||a.localeCompare(b));layer.forEach((id,i)=>positions.set(id,{x:d*250,y:i*88}))});
}
function applyTransform(){viewport.setAttribute('transform',`translate(${transform.x} ${transform.y}) scale(${transform.scale})`)}
function anchor(id,right){const p=positions.get(id)||{x:0,y:0};return{x:p.x+(right?170:0),y:p.y+29}}
function edgePath(e){const a=anchor(e.source,true),b=anchor(e.target,false),bend=Math.max(45,Math.abs(b.x-a.x)*.45);return `M ${a.x} ${a.y} C ${a.x+bend} ${a.y}, ${b.x-bend} ${b.y}, ${b.x} ${b.y}`}
function setFocus(nodeId,hops){focusState={anchor:nodeId,hops};details.textContent=`Focused ${hops}-hop runtime neighborhood around ${nodeId}.`;applyGraphFilters()}
function execweaveInjectedContext(text){
  // Providers prepend the same multi-kilobyte plugin and environment preamble to every
  // subagent, so three different agents open with an identical wall of text. It is real
  // evidence and is kept, folded, rather than leading the panel.
  const value=String(text||'');
  return value.startsWith('<recommended_plugins>')||value.startsWith('<environment_context>');
}
function execweaveGroupSaidTurns(messages){
  // Consecutive turns the provider did not expose collapse into one line. They are
  // grouped by sender only: a run of assignments root wrote to three different
  // children is one line that still names all three, so nothing about who was
  // dispatched is lost to the fold.
  const groups=[];
  for(const message of messages){
    const encrypted=message?.content_state==='provider_encrypted',
          sender=String(message?.sender||''),recipient=String(message?.recipient||''),
          last=groups[groups.length-1];
    if(encrypted&&last&&last.encrypted&&last.sender===sender){
      last.count+=1;
      if(recipient&&!last.recipients.includes(recipient))last.recipients.push(recipient);
      continue;
    }
    groups.push({encrypted,count:1,sender,recipients:recipient?[recipient]:[],message});
  }
  return groups;
}
function execweaveAppendSaidGroup(box,group,path){
  if(group.count===1){execweaveAppendSaidTurn(box,group.message,path);return}
  const row=document.createElement('div');row.className='execweave-said-turn';
  const who=document.createElement('div');who.className='execweave-said-who';
  if(group.sender===path){who.classList.add('self');who.textContent='this agent'}
  else who.textContent=group.sender||'\u2014';
  const others=group.recipients.filter(value=>value!==path);
  if(others.length)who.textContent+=' \u2192';
  row.appendChild(who);
  const body=document.createElement('div');body.className='execweave-said-body quiet';
  body.textContent=`${group.count} turns the provider did not expose`
    +(others.length?` \u2192 ${others.join(', ')}`:'');
  row.appendChild(body);box.appendChild(row);
}
function execweaveAppendSaidTurn(box,message,path){
  const row=document.createElement('div');row.className='execweave-said-turn';
  const sender=String(message?.sender||''),recipient=String(message?.recipient||'');
  const who=document.createElement('div');who.className='execweave-said-who';
  if(sender===path){who.classList.add('self');who.textContent='this agent'}
  else who.textContent=sender||'\u2014';
  if(recipient&&recipient!==path)who.textContent+=' \u2192';
  const body=document.createElement('div');const text=String(message?.text||'');
  if(message?.content_state==='provider_encrypted'){
    body.className='execweave-said-body quiet';
    body.textContent='provider-encrypted \u2014 the provider did not expose this text';
  }else if(execweaveInjectedContext(text)){
    body.className='execweave-said-body';
    const fold=document.createElement('details');fold.className='execweave-said-ctx';
    const label=document.createElement('summary');
    label.textContent=`injected task context \u00b7 ${text.length} characters`;
    const full=document.createElement('div');full.className='execweave-said-body';full.textContent=text;
    fold.append(label,full);body.appendChild(fold);
  }else if(text){body.className='execweave-said-body';body.textContent=text}
  else{body.className='execweave-said-body quiet';body.textContent='(no plaintext body exposed)'}
  row.append(who,body);box.appendChild(row);
}
function execweaveAgentSaid(node){
  // Clicking an agent asks one question: what did this agent say? Answer that first,
  // before identity, capability and trace machinery.
  if(!node||node.type!=='agent'||typeof execweaveConversationAgentRecords!=='function')return null;
  let record=null;
  try{
    const records=execweaveConversationAgentRecords(execweaveEmbeddedConversationEntries());
    record=records.find(item=>item.nodeId&&String(item.nodeId)===String(node.id))||null;
  }catch(_){return null}
  if(!record)return null;
  const own=execweaveOwnConversationEntry(record),messages=own?.conversation_preview?.messages||[];
  const box=document.createElement('div');box.className='execweave-said';
  const head=document.createElement('div');head.className='execweave-said-head';
  const title=document.createElement('div');title.className='execweave-said-title';
  title.textContent=record.path||record.label;
  const count=document.createElement('div');count.className='execweave-said-count';
  const authored=messages.filter(message=>String(message?.sender||'')===record.path).length;
  count.textContent=`${messages.length} turn${messages.length===1?'':'s'} \u00b7 ${authored} written by this agent`;
  head.append(title,count);box.appendChild(head);
  if(!messages.length){
    const none=document.createElement('div');none.className='execweave-said-body quiet';
    none.textContent='No conversation evidence is available for this agent.';box.appendChild(none);
    return box;
  }
  for(const group of execweaveGroupSaidTurns(messages))execweaveAppendSaidGroup(box,group,record.path||record.label);
  return box;
}
function showDetails(kind,value){
  details.classList.remove('empty');details.replaceChildren();const t=document.createElement('strong');t.textContent=kind;let p=document.createElement('pre');p.textContent=JSON.stringify(value,null,2);details.append(t,document.createElement('br'));
  const said=kind==='Node'?execweaveAgentSaid(value):null;
  if(said){
    details.append(said);
    const fold=document.createElement('details');fold.className='execweave-raw-node';
    const label=document.createElement('summary');label.textContent='Raw node evidence';
    fold.append(label,p);p=fold;
  }
  if(kind==='Node'){
    const actions=document.createElement('div');actions.className='detail-actions';
    [1,2].forEach(hops=>{const button=document.createElement('button');button.textContent=`Focus ${hops} ${hops===1?'hop':'hops'}`;button.addEventListener('click',()=>setFocus(value.id,hops));actions.appendChild(button)});
    if(expansionClusters[value.id]&&!expandedClusters.has(value.id)){const button=document.createElement('button');button.textContent='Expand cluster';button.addEventListener('click',()=>{focusState=null;expandedClusters.add(value.id);details.textContent='Cluster expanded into original evidence nodes.';applyGraphFilters()});actions.appendChild(button)}
    details.append(actions);
  }else if(value.identity_exact===true){const note=document.createElement('div');note.className='identity-note';note.textContent='Exact identity: explicit shared identity evidence. This edge is non-causal and not inferred.';details.append(note)}else{details.append(document.createElement('br'))}
  details.append(p);
}
function renderEdges(){
  edgeLayer.replaceChildren();labelLayer.replaceChildren();edgeElements=[];
  visibleEdges.forEach(edge=>{if(!positions.has(edge.source)||!positions.has(edge.target))return;const d=edgePath(edge),line=document.createElementNS('http://www.w3.org/2000/svg','path');line.setAttribute('d',d);line.setAttribute('marker-end','url(#arrow)');line.classList.add('edge');if(edge.identity_exact===true)line.classList.add('identity');else if(edge.inferred===true)line.classList.add('inferred');else if(edge.causal===true)line.classList.add('causal');else if(edge.causal===false)line.classList.add('noncausal');edgeLayer.appendChild(line);const hit=document.createElementNS('http://www.w3.org/2000/svg','path');hit.setAttribute('d',d);hit.classList.add('edge-hit');hit.addEventListener('click',ev=>{ev.stopPropagation();showDetails('Edge',edge)});edgeLayer.appendChild(hit);const a=anchor(edge.source,true),b=anchor(edge.target,false),text=document.createElementNS('http://www.w3.org/2000/svg','text');text.setAttribute('x',String((a.x+b.x)/2));text.setAttribute('y',String((a.y+b.y)/2-7));text.setAttribute('text-anchor','middle');text.classList.add('edge-label');text.textContent=edgeLabel(edge);labelLayer.appendChild(text);edgeElements.push({edge,visible:line,hit,text})});
}
function scheduleEdgeRender(){if(edgeRenderFrame!==null)return;edgeRenderFrame=requestAnimationFrame(()=>{edgeRenderFrame=null;renderEdges()})}
function renderNodes(){
  nodeLayer.replaceChildren();nodeElements=new Map();
  visibleNodes.forEach(node=>{const p=positions.get(node.id);if(!p)return;const g=document.createElementNS('http://www.w3.org/2000/svg','g');g.classList.add('node');if(expansionClusters[node.id])g.classList.add('cluster');g.setAttribute('transform',`translate(${p.x} ${p.y})`);const r=document.createElementNS('http://www.w3.org/2000/svg','rect');r.setAttribute('width','170');r.setAttribute('height','58');r.setAttribute('fill',colorForType(node.type));g.appendChild(r);const type=document.createElementNS('http://www.w3.org/2000/svg','text');type.setAttribute('x','12');type.setAttribute('y','18');type.classList.add('node-type');type.textContent=node.type||'unknown';g.appendChild(type);const label=document.createElementNS('http://www.w3.org/2000/svg','text');label.setAttribute('x','12');label.setAttribute('y','39');label.textContent=labelFor(node);g.appendChild(label);g.addEventListener('pointerdown',ev=>{ev.stopPropagation();const pt=svgPoint(ev);dragNode={id:node.id,dx:pt.x-p.x,dy:pt.y-p.y};g.setPointerCapture(ev.pointerId)});g.addEventListener('pointermove',ev=>{if(!dragNode||dragNode.id!==node.id)return;const pt=svgPoint(ev),np={x:pt.x-dragNode.dx,y:pt.y-dragNode.dy};positions.set(node.id,np);g.setAttribute('transform',`translate(${np.x} ${np.y})`);scheduleEdgeRender()});g.addEventListener('pointerup',ev=>{dragNode=null;scheduleEdgeRender();try{g.releasePointerCapture(ev.pointerId)}catch(_){}});g.addEventListener('click',ev=>{ev.stopPropagation();document.querySelectorAll('.node.selected').forEach(el=>el.classList.remove('selected'));g.classList.add('selected');showDetails('Node',node);if(typeof execweaveFocusConversationAgent==='function')execweaveFocusConversationAgent(node)});nodeLayer.appendChild(g);nodeElements.set(node.id,g)});
}
function svgPoint(ev){const rect=svg.getBoundingClientRect();return{x:(ev.clientX-rect.left-transform.x)/transform.scale,y:(ev.clientY-rect.top-transform.y)/transform.scale}}
function fit(){if(!positions.size)return;let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;positions.forEach(p=>{if(p.x<minX)minX=p.x;if(p.x>maxX)maxX=p.x;if(p.y<minY)minY=p.y;if(p.y>maxY)maxY=p.y});maxX+=170;maxY+=58;const box=svg.getBoundingClientRect(),width=Math.max(1,maxX-minX),height=Math.max(1,maxY-minY),scale=Math.min(1.25,Math.max(.08,Math.min((box.width-70)/width,(box.height-70)/height)));transform={x:35-minX*scale,y:35-minY*scale,scale};applyTransform()}
function applySearch(){const q=search.value.trim().toLowerCase();if(!q){nodeElements.forEach(el=>el.classList.remove('dim'));edgeElements.forEach(i=>{i.visible.classList.remove('dim');i.text.classList.remove('dim')});return}const matched=new Set();visibleNodes.forEach(n=>{if(`${n.id} ${n.name||''} ${n.type||''}`.toLowerCase().includes(q))matched.add(n.id)});nodeElements.forEach((el,id)=>el.classList.toggle('dim',!matched.has(id)));edgeElements.forEach(i=>{const keep=matched.has(i.edge.source)||matched.has(i.edge.target)||String(i.edge.relation).toLowerCase().includes(q);i.visible.classList.toggle('dim',!keep);i.text.classList.toggle('dim',!keep)})}
function stopPlayback(){if(playTimer!==null){clearInterval(playTimer);playTimer=null}playButton.textContent='Play'}
function setSequence(value){selectedSequence=Math.max(0,Math.min(maxSequence,Number(value)||0));sequenceFilter.value=String(selectedSequence);sequenceLabel.textContent=`${selectedSequence} / ${maxSequence}`;applyGraphFilters()}
function togglePlayback(){if(playTimer!==null){stopPlayback();return}if(maxSequence<=0)return;if(selectedSequence>=maxSequence)setSequence(0);playButton.textContent='Pause';const step=Math.max(1,Math.ceil(maxSequence/180));playTimer=setInterval(()=>{if(selectedSequence>=maxSequence){stopPlayback();return}setSequence(Math.min(maxSequence,selectedSequence+step))},160)}
function snapshotView(){return{version:1,node_type:typeFilter.value,relation:relationFilter.value,causal_only:causalFilter.checked,observed_only:observedOnlyFilter.checked,search:search.value,sequence:selectedSequence,focus:focusState?{anchor:focusState.anchor,hops:focusState.hops}:null,expanded_clusters:[...expandedClusters]}}
function renderPresetOptions(selected=''){
  presetSelect.replaceChildren();const empty=document.createElement('option');empty.value='';empty.textContent='Saved views';presetSelect.appendChild(empty);
  Object.keys(presets).sort((a,b)=>a.localeCompare(b)).forEach(name=>{const o=document.createElement('option');o.value=name;o.textContent=name;presetSelect.appendChild(o)});
  presetSelect.value=selected&&presets[selected]?selected:'';deletePresetButton.disabled=!presetSelect.value;
}
function loadPresets(){
  try{const raw=localStorage.getItem(presetStorageKey);const parsed=raw?JSON.parse(raw):{};presets=parsed&&typeof parsed==='object'&&!Array.isArray(parsed)?parsed:{}}
  catch(_){presetStorageAvailable=false;presets={}}
  renderPresetOptions();
}
function persistPresets(){try{localStorage.setItem(presetStorageKey,JSON.stringify(presets))}catch(_){presetStorageAvailable=false}}
function applyPreset(name){
  const state=presets[name];if(!state||typeof state!=='object')return;stopPlayback();
  typeFilter.value=typeof state.node_type==='string'?state.node_type:'';relationFilter.value=typeof state.relation==='string'?state.relation:'';causalFilter.checked=state.causal_only===true;observedOnlyFilter.checked=state.observed_only===true;search.value=typeof state.search==='string'?state.search:'';
  selectedSequence=maxSequence>0?Math.max(0,Math.min(maxSequence,Number(state.sequence)||0)):0;if(maxSequence>0){sequenceFilter.value=String(selectedSequence);sequenceLabel.textContent=`${selectedSequence} / ${maxSequence}`}
  const expanded=Array.isArray(state.expanded_clusters)?state.expanded_clusters:[];expandedClusters=new Set(expanded.filter(id=>expansionClusters[id]));
  focusState=state.focus&&typeof state.focus.anchor==='string'&&Number.isInteger(state.focus.hops)?{anchor:state.focus.anchor,hops:Math.max(0,state.focus.hops)}:null;
  details.textContent=`Loaded saved view: ${name}`;applyGraphFilters();
}
function savePreset(){
  const name=(window.prompt('Saved view name')||'').trim();if(!name)return;presets[name]=snapshotView();persistPresets();renderPresetOptions(name);
  details.textContent=presetStorageAvailable?`Saved view locally: ${name}`:`Saved view for this page session: ${name}`;
}
function deletePreset(){const name=presetSelect.value;if(!name||!presets[name])return;delete presets[name];persistPresets();renderPresetOptions();details.textContent=`Deleted saved view: ${name}`}
svg.addEventListener('pointerdown',ev=>{if(ev.target.closest?.('.node'))return;panStart={x:ev.clientX,y:ev.clientY,tx:transform.x,ty:transform.y};svg.classList.add('panning');svg.setPointerCapture(ev.pointerId)});
svg.addEventListener('pointermove',ev=>{if(!panStart)return;transform.x=panStart.tx+ev.clientX-panStart.x;transform.y=panStart.ty+ev.clientY-panStart.y;applyTransform()});
svg.addEventListener('pointerup',ev=>{panStart=null;svg.classList.remove('panning');try{svg.releasePointerCapture(ev.pointerId)}catch(_){} });
svg.addEventListener('wheel',ev=>{ev.preventDefault();const rect=svg.getBoundingClientRect(),mx=ev.clientX-rect.left,my=ev.clientY-rect.top,old=transform.scale,next=Math.min(4,Math.max(.08,old*Math.exp(-ev.deltaY*.0012))),gx=(mx-transform.x)/old,gy=(my-transform.y)/old;transform.scale=next;transform.x=mx-gx*next;transform.y=my-gy*next;applyTransform()},{passive:false});
search.addEventListener('input',applySearch);
[typeFilter,relationFilter,causalFilter,observedOnlyFilter].forEach(el=>el.addEventListener('change',applyGraphFilters));
sequenceFilter.addEventListener('input',()=>{stopPlayback();setSequence(sequenceFilter.value)});
playButton.addEventListener('click',togglePlayback);
clearFocusButton.addEventListener('click',()=>{focusState=null;details.textContent='Focused subgraph cleared.';applyGraphFilters()});
collapseButton.addEventListener('click',()=>{focusState=null;expandedClusters=new Set();details.textContent='All expandable clusters collapsed.';applyGraphFilters()});
presetSelect.addEventListener('change',()=>{deletePresetButton.disabled=!presetSelect.value;if(presetSelect.value)applyPreset(presetSelect.value)});
savePresetButton.addEventListener('click',savePreset);deletePresetButton.addEventListener('click',deletePreset);
document.getElementById('fit').addEventListener('click',fit);
document.getElementById('reset').addEventListener('click',()=>{computeLayout();renderNodes();renderEdges();applySearch();fit()});
window.addEventListener('resize',fit);
svg.addEventListener('click',()=>{document.querySelectorAll('.node.selected').forEach(el=>el.classList.remove('selected'));if(typeof execweaveClearConversationFocus==='function')execweaveClearConversationFocus()});
renderCorrelationSummary();loadPresets();applyGraphFilters();
})();
</script>
</body>
</html>
"""


def render_graph_html(graph: dict[str, Any]) -> str:
    node_count, edge_count = _graph_render_counts(graph)
    estimated_dom = _estimated_svg_elements(node_count, edge_count)
    if (
        node_count > VIEWER_MAX_NODES
        or edge_count > VIEWER_MAX_EDGES
        or estimated_dom > VIEWER_MAX_DOM_ELEMENTS
    ):
        return _render_protective_html(graph, node_count, edge_count)
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
