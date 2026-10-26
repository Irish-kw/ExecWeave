from __future__ import annotations

import json
import os
import shutil
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

import pytest

from dashboard_readability_fixture import (
    CHILD_IDS,
    COLLAB_TOOL_IDS,
    ROOT_ID,
    SHARED_TOOL_IDS,
    build_dashboard_readability_graph,
)
from execweave.dashboard_shell import DASHBOARD_HTML, render_static_dashboard_html

pytestmark = pytest.mark.viewer_e2e


def _chromium_path() -> str | None:
    explicit = os.environ.get("EXECWEAVE_E2E_CHROMIUM")
    if explicit and Path(explicit).exists():
        return explicit
    base = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""))
    if base.is_dir():
        for candidate in sorted(base.glob("chromium*/chrome-linux/chrome")):
            return str(candidate)
    return shutil.which("chromium") or shutil.which("chromium-browser")


def _launch() -> tuple[Any, Any]:
    try:
        from playwright import sync_api
    except ImportError:
        if os.environ.get("EXECWEAVE_E2E_REQUIRED"):
            pytest.fail("playwright is required for the dashboard readability regression")
        pytest.skip("playwright is not installed")
    playwright = sync_api.sync_playwright().start()
    executable = _chromium_path()
    try:
        browser = playwright.chromium.launch(
            **({"executable_path": executable} if executable else {})
        )
    except Exception as error:  # noqa: BLE001 - preserve launch diagnostics in CI
        playwright.stop()
        if os.environ.get("EXECWEAVE_E2E_REQUIRED"):
            pytest.fail(f"chromium would not launch: {error}")
        pytest.skip(f"chromium would not launch: {error}")
    return playwright, browser


def _artifact_dir() -> Path | None:
    value = os.environ.get("EXECWEAVE_VISUAL_ARTIFACT_DIR")
    if not value:
        return None
    path = Path(value).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _wait_graph(page: Any, agents: int) -> None:
    page.wait_for_function(
        """count=>document.querySelectorAll(
          '.node[data-layout-lane="agent"],.node[data-layout-lane="root"]'
        ).length===count""",
        arg=agents,
        timeout=15000,
    )


def _layout_contract(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """()=>({
          nodes:[...document.querySelectorAll('.node')].map(node=>({
            id:node.dataset.id,lane:node.dataset.layoutLane,rank:node.dataset.layoutRank,
            order:node.dataset.layoutOrder
          })).sort((a,b)=>a.id.localeCompare(b.id)),
          edges:[...document.querySelectorAll('.edge')].map(edge=>({
            id:edge.dataset.edgeId,route:edge.dataset.routeKind,
            bundle:edge.dataset.bundleSize,constraint:edge.dataset.layoutConstraint
          })).sort((a,b)=>a.id.localeCompare(b.id))
        })"""
    )


def _legacy_layout(page: Any) -> None:
    """Recreate v0.8.1's fixed BFS/center-anchor drawing for the before screenshot."""
    page.evaluate(
        """()=>{
          const graph=window.__execweaveCore.getDisplayGraph();
          const byId=new Map(graph.nodes.map(n=>[n.id,n])),ids=[...byId.keys()];
          const incoming=new Map(ids.map(id=>[id,0])),outgoing=new Map(ids.map(id=>[id,[]]));
          for(const edge of graph.edges){
            if(!byId.has(edge.source)||!byId.has(edge.target))continue;
            incoming.set(edge.target,(incoming.get(edge.target)||0)+1);
            outgoing.get(edge.source).push(edge.target);
          }
          let roots=ids.filter(id=>(incoming.get(id)||0)===0);
          if(!roots.length&&ids.length)roots=[ids[0]];
          const depth=new Map(),queue=roots.map(id=>[id,0]);
          for(let i=0;i<queue.length;i++){
            const[id,d]=queue[i];if(depth.has(id))continue;depth.set(id,d);
            for(const next of outgoing.get(id)||[])queue.push([next,d+1]);
          }
          let max=0;for(const value of depth.values())max=Math.max(max,value);
          for(const id of ids)if(!depth.has(id))depth.set(id,max+1);
          const layers=new Map();
          for(const id of ids){const d=depth.get(id);if(!layers.has(d))layers.set(d,[]);layers.get(d).push(id)}
          const positions=new Map();
          for(const[d,list]of layers){
            list.sort((a,b)=>String(byId.get(a)?.type).localeCompare(String(byId.get(b)?.type))||a.localeCompare(b));
            list.forEach((id,index)=>positions.set(id,{x:d*235,y:index*76}));
          }
          for(const node of document.querySelectorAll('.node')){
            const p=positions.get(node.dataset.id);if(p)node.setAttribute('transform',`translate(${p.x} ${p.y})`);
          }
          const anchor=(id,right)=>{const p=positions.get(id)||{x:0,y:0};return{x:p.x+(right?160:0),y:p.y+25}};
          for(const edge of graph.edges){
            const id=edge.id||`${edge.source}:${edge.relation}:${edge.target}`;
            const a=anchor(edge.source,true),b=anchor(edge.target,false),bend=Math.max(38,Math.abs(b.x-a.x)*.42);
            const d=`M ${a.x} ${a.y} C ${a.x+bend} ${a.y}, ${b.x-bend} ${b.y}, ${b.x} ${b.y}`;
            for(const path of document.querySelectorAll(`[data-edge-id="${CSS.escape(id)}"]`))
              if(path.tagName.toLowerCase()==='path')path.setAttribute('d',d);
            const label=document.querySelector(`.label[data-edge-id="${CSS.escape(id)}"]`);
            if(label){
              label.setAttribute('x',(a.x+b.x)/2);label.setAttribute('y',(a.y+b.y)/2-6);
              label.textContent=edge.count>1?`${edge.relation} ×${edge.count}`:edge.relation;
              label.style.opacity='1';
            }
          }
          let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;
          for(const p of positions.values()){
            minX=Math.min(minX,p.x);maxX=Math.max(maxX,p.x+160);
            minY=Math.min(minY,p.y);maxY=Math.max(maxY,p.y+50);
          }
          const svg=document.getElementById('svg'),box=svg.getBoundingClientRect();
          const w=Math.max(1,maxX-minX),h=Math.max(1,maxY-minY);
          const scale=Math.min(1.2,Math.max(.07,Math.min((box.width-72)/w,(box.height-72)/h)));
          document.getElementById('viewport').setAttribute(
            'transform',`translate(${36-minX*scale} ${36-minY*scale}) scale(${scale})`
          );
        }"""
    )


def _assert_geometry(page: Any) -> None:
    display = page.evaluate("()=>window.__execweaveCore.getDisplayGraph()")
    raw = page.evaluate("()=>window.__execweaveCore.getGraph()")
    assert len([node for node in display["nodes"] if node.get("type") == "agent"]) == 7
    assert len([node for node in raw["nodes"] if node.get("type") == "tool_call"]) == 27

    assert page.locator(f'.node[data-id="{ROOT_ID}"]').get_attribute("data-layout-rank") == "1"
    child_orders: list[int] = []
    for child_id in CHILD_IDS:
        child = page.locator(f'.node[data-id="{child_id}"]')
        assert child.get_attribute("data-layout-rank") == "2"
        child_orders.append(int(child.get_attribute("data-layout-order") or "-1"))
    assert child_orders == list(range(6))

    for index in range(1, 7):
        stopped = page.locator(f'.edge[data-edge-id="stop-{index}"]')
        assert stopped.get_attribute("data-layout-constraint") == "ignored-for-rank"
        assert stopped.get_attribute("data-route-kind") == "lifecycle-return"

    bundle_edges = page.locator('.edge[data-bundle-size="6"]')
    assert bundle_edges.count() == len(CHILD_IDS) * len(SHARED_TOOL_IDS)
    paths = bundle_edges.evaluate_all("edges=>edges.map(edge=>edge.getAttribute('d'))")
    assert len(set(paths)) > len(SHARED_TOOL_IDS)
    shared_labels = [
        text
        for text in page.locator(".label.aggregate-label").all_text_contents()
        if "CALLED_TOOL" in text
    ]
    assert len(shared_labels) >= len(SHARED_TOOL_IDS)
    assert all("×6" in text for text in shared_labels)

    overlaps = page.evaluate(
        """()=>{
          const agents=[...document.querySelectorAll('.node')].filter(
            node=>['root','agent'].includes(node.dataset.layoutLane));
          const labels=[...document.querySelectorAll('.label')].filter(
            label=>Number(getComputedStyle(label).opacity)>.2&&label.textContent.trim());
          let count=0;
          for(const label of labels){
            const a=label.getBoundingClientRect();
            for(const node of agents){
              const b=node.getBoundingClientRect();
              if(a.right>b.left&&a.left<b.right&&a.bottom>b.top&&a.top<b.bottom)count++;
            }
          }
          return count;
        }"""
    )
    assert overlaps == 0

    page.locator(f'.node[data-id="{CHILD_IDS[0]}"]').dispatch_event("click")
    page.wait_for_timeout(100)
    focus = page.evaluate(
        """()=>({
          related:[...document.querySelectorAll('.edge.context-related')].map(edge=>edge.dataset.edgeId),
          dimmed:[...document.querySelectorAll('.edge.context-dim')].map(edge=>edge.dataset.edgeId),
          display:window.__execweaveCore.getDisplayGraph().edges
        })"""
    )
    assert focus["related"] and focus["dimmed"]
    edge_by_id = {
        edge.get("id") or f"{edge['source']}:{edge['relation']}:{edge['target']}": edge
        for edge in focus["display"]
    }
    assert all(
        edge_by_id[edge_id]["source"] == CHILD_IDS[0]
        or edge_by_id[edge_id]["target"] == CHILD_IDS[0]
        for edge_id in focus["related"]
    )
    assert not set(focus["related"]) & set(focus["dimmed"])

    raw_relations = {(edge["source"], edge["relation"], edge["target"]) for edge in raw["edges"]}
    for child_id in CHILD_IDS:
        assert (ROOT_ID, "SPAWNED_AGENT", child_id) in raw_relations
        assert (child_id, "SUBAGENT_STOPPED", ROOT_ID) in raw_relations
    for tool_id in COLLAB_TOOL_IDS:
        assert any(edge["target"] == tool_id for edge in raw["edges"])


def _split_graph(full: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    removed_ids = {
        CHILD_IDS[-1],
        *[
            node["id"]
            for node in full["nodes"]
            if str(node.get("id", "")).startswith("tool_call:child:6:")
        ],
    }
    initial_nodes = [node for node in full["nodes"] if node["id"] not in removed_ids]
    added_nodes = [node for node in full["nodes"] if node["id"] in removed_ids]
    initial_edges = [
        edge
        for edge in full["edges"]
        if edge["source"] not in removed_ids and edge["target"] not in removed_ids
    ]
    initial_edge_ids = {edge["id"] for edge in initial_edges}
    added_edges = [edge for edge in full["edges"] if edge["id"] not in initial_edge_ids]
    initial = {
        **full,
        "nodes": initial_nodes,
        "edges": initial_edges,
        "node_count": len(initial_nodes),
        "edge_count": len(initial_edges),
    }
    update = {
        "sequence": 1,
        "event_count": full["event_count"],
        "node_count": full["node_count"],
        "edge_count": full["edge_count"],
        "nodes_added": added_nodes,
        "nodes_updated": [],
        "edges_added": added_edges,
        "edges_updated": [],
        "raw_events_added": [],
    }
    return initial, update


class _LiveState:
    def __init__(self, graph: dict[str, Any], update: dict[str, Any]) -> None:
        self.graph = graph
        self.update = update
        self.advance = False


@contextmanager
def _serve_live(state: _LiveState) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

        def _send_json(self, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlparse(self.path)
            if parsed.path == "/":
                body = DASHBOARD_HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path == "/conversations.json":
                self._send_json({"entries": []})
                return
            if parsed.path != "/live.json":
                self.send_error(404)
                return
            if "after=-1" in parsed.query:
                self._send_json(
                    {
                        "kind": "snapshot",
                        "sequence": 0,
                        "graph": state.graph,
                        "raw_events": [],
                        "live_finished": False,
                        "live_evidence_counts": {},
                    }
                )
            elif state.advance:
                self._send_json(
                    {
                        "kind": "delta",
                        "base_sequence": 0,
                        "sequence": 1,
                        "updates": [state.update],
                        "live_finished": False,
                        "live_evidence_counts": {},
                    }
                )
                state.advance = False
            else:
                self._send_json(
                    {
                        "kind": "noop",
                        "sequence": 0,
                        "node_count": state.graph["node_count"],
                        "edge_count": state.graph["edge_count"],
                        "event_count": state.graph["event_count"],
                        "live_finished": False,
                        "live_evidence_counts": {},
                    }
                )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_multi_agent_dashboard_layout_is_readable_and_shared_by_live_and_static(
    tmp_path: Path,
) -> None:
    graph = build_dashboard_readability_graph()
    static_path = tmp_path / "viewer.html"
    static_path.write_text(render_static_dashboard_html(graph), encoding="utf-8")
    initial, update = _split_graph(graph)
    state = _LiveState(initial, update)

    playwright, browser = _launch()
    try:
        static_page = browser.new_page(viewport={"width": 1600, "height": 1000})
        static_page.goto(static_path.as_uri())
        _wait_graph(static_page, 7)

        artifact_dir = _artifact_dir()
        if artifact_dir is not None:
            _legacy_layout(static_page)
            static_page.screenshot(
                path=str(artifact_dir / "dashboard-readability-before.png"), full_page=True
            )
            static_page.reload()
            _wait_graph(static_page, 7)
            static_page.screenshot(
                path=str(artifact_dir / "dashboard-readability-after.png"), full_page=True
            )

        _assert_geometry(static_page)
        static_contract = _layout_contract(static_page)

        with _serve_live(state) as live_url:
            live_page = browser.new_page(viewport={"width": 1600, "height": 1000})
            live_page.goto(live_url)
            _wait_graph(live_page, 6)
            stable_before = live_page.evaluate(
                """()=>Object.fromEntries([...document.querySelectorAll('.node')].map(
                  node=>[node.dataset.id,node.getAttribute('transform')]))"""
            )
            state.advance = True
            _wait_graph(live_page, 7)
            stable_after = live_page.evaluate(
                """()=>Object.fromEntries([...document.querySelectorAll('.node')].map(
                  node=>[node.dataset.id,node.getAttribute('transform')]))"""
            )
            for node_id in stable_before:
                assert node_id in stable_after, f"live layout dropped {node_id}"
            _assert_geometry(live_page)
            live_contract = _layout_contract(live_page)

        assert live_contract == static_contract
    finally:
        browser.close()
        playwright.stop()
