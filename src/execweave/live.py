from __future__ import annotations

import json
import threading
import time
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
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
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:var(--bg);color:var(--text);font:14px/1.4 ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
#app{display:grid;grid-template-columns:minmax(0,1fr) 330px;grid-template-rows:54px minmax(0,1fr);width:100%;height:100%}
header{grid-column:1/3;display:flex;align-items:center;gap:14px;padding:0 16px;border-bottom:1px solid var(--border);background:var(--panel)}
header strong{font-size:16px}#status{border:1px solid var(--border);border-radius:999px;padding:4px 9px;color:var(--muted)}#status.live{color:var(--causal)}#status.done{color:var(--selected)}
#stats{color:var(--muted);white-space:nowrap}header input{margin-left:auto;width:min(420px,36vw);border:1px solid var(--border);border-radius:8px;padding:8px 10px;background:var(--panel2);color:var(--text);outline:none}
#wrap{position:relative;overflow:hidden;min-width:0;min-height:0}svg{width:100%;height:100%;display:block;cursor:grab;user-select:none}svg.panning{cursor:grabbing}
aside{overflow:auto;border-left:1px solid var(--border);background:var(--panel);padding:14px}aside h2{margin:0 0 10px;font-size:15px}aside pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.controls{position:absolute;z-index:3;left:10px;top:10px;display:flex;gap:6px}.controls button{border:1px solid var(--border);background:var(--panel);color:var(--text);border-radius:7px;padding:6px 9px;cursor:pointer}
.node rect{stroke:var(--border);stroke-width:1.1;rx:8;ry:8}.node text{fill:var(--text);pointer-events:none}.node .type{fill:var(--muted);font-size:9px}.node.dim{opacity:.14}
.edge{fill:none;stroke:var(--edge);stroke-width:1.3;opacity:.72;marker-end:url(#arrow)}.edge.causal{stroke:var(--causal)}.edge.noncausal{stroke:var(--noncausal);stroke-dasharray:6 5}.edge.dim{opacity:.07}.edge-hit{fill:none;stroke:transparent;stroke-width:10;cursor:pointer}.label{fill:var(--muted);font-size:8.5px;pointer-events:none}
@media(max-width:820px){#app{grid-template-columns:1fr;grid-template-rows:54px minmax(0,1fr) 210px}header{grid-column:1}aside{border-left:0;border-top:1px solid var(--border)}}
</style>
</head>
<body>
<div id="app">
<header><strong>ExecWeave Live</strong><span id="status" class="live">LIVE</span><span id="stats">Waiting for events…</span><input id="search" placeholder="Search node id, name, type…"></header>
<div id="wrap"><div class="controls"><button id="fit">Fit</button></div><svg id="svg"><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="context-stroke"></path></marker></defs><g id="viewport"><g id="edges"></g><g id="labels"></g><g id="nodes"></g></g></svg></div>
<aside><h2>Selection</h2><div id="details">Click a node or edge.</div></aside>
</div>
<script>
(()=>{
const svg=document.getElementById('svg'),viewport=document.getElementById('viewport'),nodeLayer=document.getElementById('nodes'),edgeLayer=document.getElementById('edges'),labelLayer=document.getElementById('labels'),details=document.getElementById('details'),search=document.getElementById('search'),stats=document.getElementById('stats'),status=document.getElementById('status');
let graph={nodes:[],edges:[]},positions=new Map(),transform={x:35,y:35,scale:1},pan=null,lastSignature='',finished=false;
function color(type){let h=0;for(const c of String(type||'unknown'))h=((h<<5)-h+c.charCodeAt(0))|0;return `hsl(${Math.abs(h)%360} 38% 27%)`}
function text(node){const x=node.name||node.id||node.type||'node';return x.length>27?x.slice(0,24)+'…':x}
function layout(){const ids=graph.nodes.map(n=>n.id),nodes=new Map(graph.nodes.map(n=>[n.id,n])),ind=new Map(ids.map(id=>[id,0])),out=new Map(ids.map(id=>[id,[]]));for(const e of graph.edges){if(!nodes.has(e.source)||!nodes.has(e.target))continue;ind.set(e.target,(ind.get(e.target)||0)+1);out.get(e.source).push(e.target)}let roots=ids.filter(id=>(ind.get(id)||0)===0);if(!roots.length&&ids.length)roots=[ids[0]];const depth=new Map(),q=roots.map(id=>[id,0]);for(const [id,d] of q)if(!depth.has(id))depth.set(id,d);for(let i=0;i<q.length;i++){const [id,d]=q[i];for(const n of out.get(id)||[]){if(!depth.has(n)){depth.set(n,d+1);q.push([n,d+1])}}}const max=Math.max(0,...depth.values());for(const id of ids)if(!depth.has(id))depth.set(id,max+1);const layers=new Map();for(const id of ids){const d=depth.get(id);if(!layers.has(d))layers.set(d,[]);layers.get(d).push(id)}for(const [d,arr] of layers){arr.sort((a,b)=>String(nodes.get(a)?.type).localeCompare(String(nodes.get(b)?.type))||a.localeCompare(b));arr.forEach((id,i)=>{if(!positions.has(id))positions.set(id,{x:d*240,y:i*80})})}}
function anchor(id,right){const p=positions.get(id)||{x:0,y:0};return{x:p.x+(right?165:0),y:p.y+27}}
function path(e){const a=anchor(e.source,true),b=anchor(e.target,false),bend=Math.max(42,Math.abs(b.x-a.x)*.44);return `M ${a.x} ${a.y} C ${a.x+bend} ${a.y}, ${b.x-bend} ${b.y}, ${b.x} ${b.y}`}
function render(){layout();nodeLayer.replaceChildren();edgeLayer.replaceChildren();labelLayer.replaceChildren();for(const e of graph.edges){if(!positions.has(e.source)||!positions.has(e.target))continue;const p=document.createElementNS('http://www.w3.org/2000/svg','path');p.setAttribute('d',path(e));p.classList.add('edge');if(e.causal===true)p.classList.add('causal');else if(e.causal===false)p.classList.add('noncausal');edgeLayer.appendChild(p);const hit=document.createElementNS('http://www.w3.org/2000/svg','path');hit.setAttribute('d',path(e));hit.classList.add('edge-hit');hit.onclick=ev=>{ev.stopPropagation();details.innerHTML='';const pre=document.createElement('pre');pre.textContent=JSON.stringify(e,null,2);details.appendChild(pre)};edgeLayer.appendChild(hit);const a=anchor(e.source,true),b=anchor(e.target,false),l=document.createElementNS('http://www.w3.org/2000/svg','text');l.setAttribute('x',(a.x+b.x)/2);l.setAttribute('y',(a.y+b.y)/2-6);l.setAttribute('text-anchor','middle');l.classList.add('label');l.textContent=e.count>1?`${e.relation} ×${e.count}`:e.relation;labelLayer.appendChild(l)}for(const n of graph.nodes){const p=positions.get(n.id);if(!p)continue;const g=document.createElementNS('http://www.w3.org/2000/svg','g');g.classList.add('node');g.dataset.search=`${n.id} ${n.name||''} ${n.type||''}`.toLowerCase();g.setAttribute('transform',`translate(${p.x} ${p.y})`);const r=document.createElementNS('http://www.w3.org/2000/svg','rect');r.setAttribute('width',165);r.setAttribute('height',54);r.setAttribute('fill',color(n.type));g.appendChild(r);const t=document.createElementNS('http://www.w3.org/2000/svg','text');t.setAttribute('x',10);t.setAttribute('y',16);t.classList.add('type');t.textContent=n.type||'unknown';g.appendChild(t);const l=document.createElementNS('http://www.w3.org/2000/svg','text');l.setAttribute('x',10);l.setAttribute('y',36);l.textContent=text(n);g.appendChild(l);g.onclick=ev=>{ev.stopPropagation();details.innerHTML='';const pre=document.createElement('pre');pre.textContent=JSON.stringify(n,null,2);details.appendChild(pre)};nodeLayer.appendChild(g)}applySearch()}
function apply(){viewport.setAttribute('transform',`translate(${transform.x} ${transform.y}) scale(${transform.scale})`)}
function fit(){if(!positions.size)return;const xs=[...positions.values()].map(p=>p.x),ys=[...positions.values()].map(p=>p.y),minX=Math.min(...xs),maxX=Math.max(...xs)+165,minY=Math.min(...ys),maxY=Math.max(...ys)+54,box=svg.getBoundingClientRect(),w=Math.max(1,maxX-minX),h=Math.max(1,maxY-minY),s=Math.min(1.2,Math.max(.07,Math.min((box.width-60)/w,(box.height-60)/h)));transform={x:30-minX*s,y:30-minY*s,scale:s};apply()}
function applySearch(){const q=search.value.trim().toLowerCase();document.querySelectorAll('.node').forEach(el=>el.classList.toggle('dim',!!q&&!el.dataset.search.includes(q)));}
async function poll(){try{const r=await fetch('/graph.json',{cache:'no-store'});if(!r.ok)throw new Error(String(r.status));const data=await r.json();finished=!!data.live_finished;delete data.live_finished;const sig=`${data.node_count||0}:${data.edge_count||0}:${data.event_count||0}`;graph=data;stats.textContent=`${data.node_count||0} nodes · ${data.edge_count||0} edges · ${data.event_count||0} events`;if(sig!==lastSignature){lastSignature=sig;render();if(positions.size<3)fit()}if(finished){status.textContent='FINISHED';status.className='done';setTimeout(()=>{location.href='/final'},350);return}}catch(e){status.textContent='RECONNECTING';status.className=''}setTimeout(poll,600)}
svg.onpointerdown=e=>{if(e.target.closest?.('.node'))return;pan={x:e.clientX,y:e.clientY,tx:transform.x,ty:transform.y};svg.classList.add('panning');svg.setPointerCapture(e.pointerId)};svg.onpointermove=e=>{if(!pan)return;transform.x=pan.tx+e.clientX-pan.x;transform.y=pan.ty+e.clientY-pan.y;apply()};svg.onpointerup=e=>{pan=null;svg.classList.remove('panning');try{svg.releasePointerCapture(e.pointerId)}catch(_){}};svg.addEventListener('wheel',e=>{e.preventDefault();const rect=svg.getBoundingClientRect(),mx=e.clientX-rect.left,my=e.clientY-rect.top,old=transform.scale,next=Math.min(4,Math.max(.07,old*Math.exp(-e.deltaY*.0012))),gx=(mx-transform.x)/old,gy=(my-transform.y)/old;transform.scale=next;transform.x=mx-gx*next;transform.y=my-gy*next;apply()},{passive:false});search.oninput=applySearch;document.getElementById('fit').onclick=fit;window.onresize=fit;apply();poll();
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
    """Run an agent with the portable collector and expose a localhost live graph.

    The current Linux strace backend is post-processed after the traced command exits,
    so the live MVP intentionally uses the portable backend. Final artifacts are still
    validated and written using the same Phase 1/2 graph contracts.
    """
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
    server = ThreadingHTTPServer(("127.0.0.1", port), _handler_factory(state))
    server.daemon_threads = True
    server_thread = threading.Thread(target=server.serve_forever, name="execweave-live", daemon=True)
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
        write_execution_graph(execution_graph, graph_path)
        write_graph_html(execution_graph.to_dict(), viewer_path, open_browser=False)
        state.finish(execution_graph.to_dict())
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
