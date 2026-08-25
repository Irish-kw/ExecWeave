from __future__ import annotations

import json
import threading
import time
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer
from uuid import uuid4

from .backends import create_collector
from .graph import build_execution_graph, write_execution_graph
from .sink import JsonlSink
from .validate import validate_event_stream
from .viewer import render_graph_html, write_graph_html


_LIVE_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ExecWeave Live</title>
<style>
:root{color-scheme:dark;--bg:#0b0f14;--panel:#111821;--panel2:#18222e;--text:#e8edf3;--muted:#8ea0b5;--border:#2a3949;--edge:#72869c;--causal:#70d6a6;--noncausal:#f2b76d;--selected:#73b7ff}
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:var(--bg);color:var(--text);font:14px/1.4 system-ui,sans-serif}
#app{display:grid;grid-template-columns:minmax(0,1fr) 320px;grid-template-rows:54px minmax(0,1fr);width:100%;height:100%}
header{grid-column:1/3;display:flex;align-items:center;gap:12px;padding:0 14px;background:var(--panel);border-bottom:1px solid var(--border)}
#status{border:1px solid var(--border);border-radius:999px;padding:3px 8px;color:var(--causal)}#stats{color:var(--muted);white-space:nowrap}
header input{margin-left:auto;width:min(420px,36vw);padding:7px 9px;border:1px solid var(--border);border-radius:7px;background:var(--panel2);color:var(--text)}
#wrap{position:relative;overflow:hidden}svg{width:100%;height:100%;display:block;cursor:grab;user-select:none}svg.panning{cursor:grabbing}
#protective{position:absolute;inset:18px;z-index:4;display:grid;place-items:center;padding:24px;text-align:center;border:1px solid var(--border);border-radius:12px;background:rgba(17,24,33,.96)}#protective[hidden]{display:none}#protective strong{display:block;margin-bottom:8px;font-size:20px}#protective p{max-width:680px;margin:6px auto;color:var(--muted)}
aside{overflow:auto;border-left:1px solid var(--border);background:var(--panel);padding:13px}aside pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.45 ui-monospace,monospace}
.controls{position:absolute;left:10px;top:10px;z-index:3}.controls button{padding:6px 9px;border:1px solid var(--border);border-radius:7px;background:var(--panel);color:var(--text);cursor:pointer}
.node rect{stroke:var(--border);stroke-width:1.1;rx:8;ry:8}.node text{fill:var(--text);pointer-events:none}.node .type{fill:var(--muted);font-size:9px}.node.dim{opacity:.12}
.edge{fill:none;stroke:var(--edge);stroke-width:1.3;opacity:.72;marker-end:url(#arrow)}.edge.causal{stroke:var(--causal)}.edge.noncausal{stroke:var(--noncausal);stroke-dasharray:6 5}.edge.dim{opacity:.06}.edge-hit{fill:none;stroke:transparent;stroke-width:10;cursor:pointer}.label{fill:var(--muted);font-size:8.5px;pointer-events:none}
@media(max-width:820px){#app{grid-template-columns:1fr;grid-template-rows:54px minmax(0,1fr) 190px}header{grid-column:1}aside{border-left:0;border-top:1px solid var(--border)}}
</style>
</head>
<body>
<div id="app">
<header><strong>ExecWeave Live</strong><span id="status">LIVE</span><span id="stats">Waiting for events…</span><input id="search" placeholder="Search node id, name, type…"></header>
<div id="wrap"><div class="controls"><button id="fit">Fit</button></div><div id="protective" hidden><div><strong>LARGE GRAPH PROTECTIVE MODE</strong><p id="protective-summary"></p><p>Live SVG rendering has stopped to protect browser memory. Collection continues and no evidence is deleted or reclassified.</p></div></div><svg id="svg"><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="context-stroke"></path></marker></defs><g id="viewport"><g id="edges"></g><g id="labels"></g><g id="nodes"></g></g></svg></div>
<aside><strong>Selection</strong><div id="details" style="color:var(--muted);margin-top:10px">Click a node or edge.</div></aside>
</div>
<script>
(()=>{
const MAX_NODES=1500,MAX_EDGES=4000,MAX_DOM_ELEMENTS=5000;
const svg=document.getElementById('svg'),viewport=document.getElementById('viewport'),edgeLayer=document.getElementById('edges'),labelLayer=document.getElementById('labels'),nodeLayer=document.getElementById('nodes'),details=document.getElementById('details'),search=document.getElementById('search'),stats=document.getElementById('stats'),status=document.getElementById('status'),protective=document.getElementById('protective'),protectiveSummary=document.getElementById('protective-summary');
let graph={nodes:[],edges:[]},positions=new Map(),transform={x:35,y:35,scale:1},pan=null,lastSignature='';
function color(type){let h=0;for(const c of String(type||'unknown'))h=((h<<5)-h+c.charCodeAt(0))|0;return `hsl(${Math.abs(h)%360} 38% 27%)`}
function short(node){const value=node.name||node.id||node.type||'node';return value.length>28?value.slice(0,25)+'…':value}
function graphCounts(data){const nodes=Number(data.node_count)||((data.nodes||[]).length),edges=Number(data.edge_count)||((data.edges||[]).length);return{nodes,edges,estimated:nodes*4+edges*3}}
function withinRenderBudget(data){const counts=graphCounts(data);return counts.nodes<=MAX_NODES&&counts.edges<=MAX_EDGES&&counts.estimated<=MAX_DOM_ELEMENTS}
function enterProtectiveMode(data){const counts=graphCounts(data);edgeLayer.replaceChildren();labelLayer.replaceChildren();nodeLayer.replaceChildren();positions=new Map();svg.style.display='none';protective.hidden=false;protectiveSummary.textContent=`${counts.nodes} nodes · ${counts.edges} edges · about ${counts.estimated} SVG elements exceeds the live safety budget.`;status.textContent='PROTECTED'}
function leaveProtectiveMode(){protective.hidden=true;svg.style.display='block'}
function layout(){const ids=graph.nodes.map(n=>n.id),nodeMap=new Map(graph.nodes.map(n=>[n.id,n])),incoming=new Map(ids.map(id=>[id,0])),outgoing=new Map(ids.map(id=>[id,[]]));for(const e of graph.edges){if(!nodeMap.has(e.source)||!nodeMap.has(e.target))continue;incoming.set(e.target,(incoming.get(e.target)||0)+1);outgoing.get(e.source).push(e.target)}let roots=ids.filter(id=>(incoming.get(id)||0)===0);if(!roots.length&&ids.length)roots=[ids[0]];const depth=new Map(),queue=roots.map(id=>[id,0]);for(let i=0;i<queue.length;i++){const [id,d]=queue[i];if(depth.has(id))continue;depth.set(id,d);for(const next of outgoing.get(id)||[])queue.push([next,d+1])}let maxDepth=0;depth.forEach(value=>{if(value>maxDepth)maxDepth=value});for(const id of ids)if(!depth.has(id))depth.set(id,maxDepth+1);const layers=new Map();for(const id of ids){const d=depth.get(id);if(!layers.has(d))layers.set(d,[]);layers.get(d).push(id)}for(const [d,list] of layers){list.sort((a,b)=>String(nodeMap.get(a)?.type).localeCompare(String(nodeMap.get(b)?.type))||a.localeCompare(b));list.forEach((id,i)=>{if(!positions.has(id))positions.set(id,{x:d*235,y:i*76})})}}
function anchor(id,right){const p=positions.get(id)||{x:0,y:0};return{x:p.x+(right?160:0),y:p.y+25}}
function curve(e){const a=anchor(e.source,true),b=anchor(e.target,false),bend=Math.max(38,Math.abs(b.x-a.x)*.42);return `M ${a.x} ${a.y} C ${a.x+bend} ${a.y}, ${b.x-bend} ${b.y}, ${b.x} ${b.y}`}
function currentEdge(id,fallback){return(graph.edges||[]).find(edge=>edge.id===id)||fallback}
function currentNode(id,fallback){return(graph.nodes||[]).find(node=>node.id===id)||fallback}
function show(value){details.innerHTML='';const pre=document.createElement('pre');pre.textContent=JSON.stringify(value,null,2);details.appendChild(pre)}
function render(){leaveProtectiveMode();layout();edgeLayer.replaceChildren();labelLayer.replaceChildren();nodeLayer.replaceChildren();for(const e of graph.edges){if(!positions.has(e.source)||!positions.has(e.target))continue;const edgeId=e.id||`${e.source}:${e.relation}:${e.target}`,visible=document.createElementNS('http://www.w3.org/2000/svg','path');visible.setAttribute('d',curve(e));visible.classList.add('edge');if(e.causal===true)visible.classList.add('causal');else if(e.causal===false)visible.classList.add('noncausal');visible.dataset.source=e.source;visible.dataset.target=e.target;visible.dataset.relation=String(e.relation||'').toLowerCase();edgeLayer.appendChild(visible);const hit=document.createElementNS('http://www.w3.org/2000/svg','path');hit.setAttribute('d',curve(e));hit.classList.add('edge-hit');hit.dataset.edgeId=edgeId;hit.onclick=ev=>{ev.stopPropagation();show(currentEdge(edgeId,e))};edgeLayer.appendChild(hit);const a=anchor(e.source,true),b=anchor(e.target,false),label=document.createElementNS('http://www.w3.org/2000/svg','text');label.setAttribute('x',(a.x+b.x)/2);label.setAttribute('y',(a.y+b.y)/2-6);label.setAttribute('text-anchor','middle');label.classList.add('label');label.dataset.edgeId=edgeId;label.textContent=e.count>1?`${e.relation} ×${e.count}`:e.relation;labelLayer.appendChild(label)}for(const n of graph.nodes){const p=positions.get(n.id);if(!p)continue;const group=document.createElementNS('http://www.w3.org/2000/svg','g');group.classList.add('node');group.dataset.id=n.id;group.dataset.search=`${n.id} ${n.name||''} ${n.type||''}`.toLowerCase();group.setAttribute('transform',`translate(${p.x} ${p.y})`);const rect=document.createElementNS('http://www.w3.org/2000/svg','rect');rect.setAttribute('width',160);rect.setAttribute('height',50);rect.setAttribute('fill',color(n.type));group.appendChild(rect);const type=document.createElementNS('http://www.w3.org/2000/svg','text');type.setAttribute('x',10);type.setAttribute('y',15);type.classList.add('type');type.textContent=n.type||'unknown';group.appendChild(type);const label=document.createElementNS('http://www.w3.org/2000/svg','text');label.setAttribute('x',10);label.setAttribute('y',34);label.textContent=short(n);group.appendChild(label);group.onclick=ev=>{ev.stopPropagation();show(currentNode(n.id,n))};nodeLayer.appendChild(group)}applySearch()}
function refreshEdgeLabels(){const byId=new Map((graph.edges||[]).map(edge=>[edge.id||`${edge.source}:${edge.relation}:${edge.target}`,edge]));labelLayer.querySelectorAll('.label[data-edge-id]').forEach(label=>{const edge=byId.get(label.dataset.edgeId);if(edge)label.textContent=edge.count>1?`${edge.relation} ×${edge.count}`:edge.relation})}
function applyTransform(){viewport.setAttribute('transform',`translate(${transform.x} ${transform.y}) scale(${transform.scale})`)}
function fit(){if(!positions.size)return;let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;positions.forEach(p=>{if(p.x<minX)minX=p.x;if(p.x>maxX)maxX=p.x;if(p.y<minY)minY=p.y;if(p.y>maxY)maxY=p.y});maxX+=160;maxY+=50;const box=svg.getBoundingClientRect(),w=Math.max(1,maxX-minX),h=Math.max(1,maxY-minY),scale=Math.min(1.2,Math.max(.07,Math.min((box.width-60)/w,(box.height-60)/h)));transform={x:30-minX*scale,y:30-minY*scale,scale};applyTransform()}
function applySearch(){const q=search.value.trim().toLowerCase();const matched=new Set();document.querySelectorAll('.node').forEach(el=>{const ok=!q||el.dataset.search.includes(q);el.classList.toggle('dim',!ok);if(ok)matched.add(el.dataset.id)});document.querySelectorAll('.edge').forEach(el=>{const keep=!q||matched.has(el.dataset.source)||matched.has(el.dataset.target)||el.dataset.relation.includes(q);el.classList.toggle('dim',!keep)})}
async function poll(){try{const response=await fetch('/graph.json',{cache:'no-store'});if(!response.ok)throw new Error(String(response.status));const data=await response.json(),finished=!!data.live_finished;delete data.live_finished;const signature=`${data.node_count||0}:${data.edge_count||0}`;graph=data;stats.textContent=`${data.node_count||0} nodes · ${data.edge_count||0} edges · ${data.event_count||0} events`;if(!withinRenderBudget(data)){if(lastSignature!=='PROTECTED')enterProtectiveMode(data);else{const counts=graphCounts(data);protectiveSummary.textContent=`${counts.nodes} nodes · ${counts.edges} edges · about ${counts.estimated} SVG elements exceeds the live safety budget.`}lastSignature='PROTECTED';status.textContent=finished?'FINISHED':'PROTECTED'}else{status.textContent=finished?'FINISHED':'LIVE';if(signature!==lastSignature){lastSignature=signature;render();if(positions.size<4)fit()}else refreshEdgeLabels()}if(finished){setTimeout(()=>{location.href='/final'},250);return}}catch(_){status.textContent='RECONNECTING'}setTimeout(poll,500)}
svg.onpointerdown=e=>{if(e.target.closest?.('.node'))return;pan={x:e.clientX,y:e.clientY,tx:transform.x,ty:transform.y};svg.classList.add('panning');svg.setPointerCapture(e.pointerId)};svg.onpointermove=e=>{if(!pan)return;transform.x=pan.tx+e.clientX-pan.x;transform.y=pan.ty+e.clientY-pan.y;applyTransform()};svg.onpointerup=e=>{pan=null;svg.classList.remove('panning');try{svg.releasePointerCapture(e.pointerId)}catch(_){}};svg.addEventListener('wheel',e=>{e.preventDefault();const rect=svg.getBoundingClientRect(),mx=e.clientX-rect.left,my=e.clientY-rect.top,old=transform.scale,next=Math.min(4,Math.max(.07,old*Math.exp(-e.deltaY*.0012))),gx=(mx-transform.x)/old,gy=(my-transform.y)/old;transform.scale=next;transform.x=mx-gx*next;transform.y=my-gy*next;applyTransform()},{passive:false});search.oninput=applySearch;document.getElementById('fit').onclick=fit;window.onresize=fit;applyTransform();poll();
})();
</script>
</body>
</html>"""


@dataclass(frozen=True)
class LiveResult:
    session_id: str
    return_code: int
    live_url: str
    output_dir: Path
    event_stream: Path
    graph: Path
    viewer: Path

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "return_code": self.return_code,
            "live_url": self.live_url,
            "output_dir": str(self.output_dir),
            "event_stream": str(self.event_stream),
            "graph": str(self.graph),
            "viewer": str(self.viewer),
        }


class _LiveState:
    def __init__(self, session_id: str, event_path: Path) -> None:
        self.session_id = session_id
        self.event_path = event_path
        self._lock = threading.Lock()
        self._last_graph: dict[str, object] = self._empty_graph()
        self._finished = False
        self._final_html: str | None = None

    def _empty_graph(self) -> dict[str, object]:
        return {
            "graph_schema_version": "0.1",
            "session_id": self.session_id,
            "event_count": 0,
            "node_count": 0,
            "edge_count": 0,
            "nodes": [],
            "edges": [],
        }

    def snapshot(self) -> dict[str, object]:
        if self.event_path.exists() and self.event_path.stat().st_size > 0:
            try:
                graph = build_execution_graph(self.event_path, allow_incomplete=True).to_dict()
            except (OSError, ValueError, json.JSONDecodeError):
                graph = None
            if graph is not None:
                with self._lock:
                    self._last_graph = graph
        with self._lock:
            payload = dict(self._last_graph)
            payload["live_finished"] = self._finished
            return payload

    def finish(self, graph: dict[str, object]) -> None:
        with self._lock:
            self._last_graph = graph
            self._final_html = render_graph_html(graph)
            self._finished = True

    def final_html(self) -> str | None:
        with self._lock:
            return self._final_html


def _handler_factory(state: _LiveState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path == "/":
                self._send(_LIVE_HTML.encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/graph.json":
                payload = json.dumps(
                    state.snapshot(), ensure_ascii=False, separators=(",", ":")
                ).encode("utf-8")
                self._send(payload, "application/json; charset=utf-8")
                return
            if path == "/final":
                final = state.final_html()
                if final is None:
                    self._send(b"Final graph is not ready", "text/plain; charset=utf-8", 404)
                else:
                    self._send(final.encode("utf-8"), "text/html; charset=utf-8")
                return
            self._send(b"Not found", "text/plain; charset=utf-8", 404)

    return Handler


class _LocalThreadingHTTPServer(ThreadingHTTPServer):
    """Local HTTP server that skips HTTPServer's reverse-DNS lookup during bind."""

    def server_bind(self) -> None:
        TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = int(port)


def run_live(
    command: list[str],
    *,
    watch_root: str | Path,
    output_dir: str | Path | None = None,
    poll_interval: float = 0.10,
    collect_filesystem: bool = True,
    collect_network: bool = True,
    port: int = 0,
    open_browser: bool = True,
    linger_seconds: float = 2.0,
    announce: Callable[[str], None] | None = None,
) -> LiveResult:
    """Run a command with the portable collector and expose a localhost live graph."""
    if not command:
        raise ValueError("command must not be empty")
    if port < 0 or port > 65535:
        raise ValueError("port must be between 0 and 65535")
    if linger_seconds < 0:
        raise ValueError("linger_seconds must be >= 0")

    session_id = uuid4().hex
    root = Path(watch_root).expanduser().resolve()
    run_dir = (
        Path(output_dir).expanduser().resolve()
        if output_dir is not None
        else root / ".execweave" / "runs" / session_id
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    event_path = run_dir / "events.jsonl"
    graph_path = run_dir / "graph.json"
    viewer_path = run_dir / "viewer.html"
    for artifact in (event_path, graph_path, viewer_path):
        if artifact.exists() and artifact.stat().st_size > 0:
            raise FileExistsError(f"ExecWeave live artifact already exists: {artifact}")

    sink = JsonlSink(event_path)
    collector = create_collector(
        backend="portable",
        session_id=session_id,
        sink=sink,
        watch_root=root,
        poll_interval=poll_interval,
        collect_filesystem=collect_filesystem,
        collect_network=collect_network,
    )

    state = _LiveState(session_id, event_path)
    server = _LocalThreadingHTTPServer(("127.0.0.1", port), _handler_factory(state))
    server.daemon_threads = True
    server_thread = threading.Thread(
        target=server.serve_forever,
        name="execweave-live",
        daemon=True,
    )
    server_thread.start()
    host, selected_port = server.server_address[:2]
    live_url = f"http://{host}:{selected_port}/"
    if announce is not None:
        announce(live_url)
    if open_browser:
        webbrowser.open(live_url)

    return_code = 1
    try:
        return_code = collector.run(command)
        validation = validate_event_stream(event_path)
        if not validation.valid:
            details = "; ".join(validation.errors)
            raise RuntimeError(f"live event stream failed validation: {details}")

        execution_graph = build_execution_graph(event_path)
        graph_payload = execution_graph.to_dict()
        write_execution_graph(execution_graph, graph_path)
        write_graph_html(graph_payload, viewer_path, open_browser=False)
        state.finish(graph_payload)
        if linger_seconds:
            time.sleep(linger_seconds)

        return LiveResult(
            session_id=session_id,
            return_code=return_code,
            live_url=live_url,
            output_dir=run_dir,
            event_stream=event_path,
            graph=graph_path,
            viewer=viewer_path,
        )
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)
