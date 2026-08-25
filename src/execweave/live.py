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
:root{color-scheme:dark;--bg:#0b0f14;--panel:#111821;--text:#e8edf3;--muted:#8ea0b5;--border:#2a3949;--causal:#70d6a6;--edge:#72869c}
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:var(--bg);color:var(--text);font:14px/1.4 system-ui,sans-serif}
#app{display:grid;grid-template-rows:54px 1fr;width:100%;height:100%}header{display:flex;align-items:center;gap:14px;padding:0 16px;background:var(--panel);border-bottom:1px solid var(--border)}
#status{color:var(--causal)}#stats{color:var(--muted)}#wrap{overflow:auto;padding:18px}pre{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.45 ui-monospace,monospace;color:var(--text)}
</style>
</head>
<body>
<div id="app"><header><strong>ExecWeave Live</strong><span id="status">LIVE</span><span id="stats">Waiting for events…</span></header><div id="wrap"><pre id="graph">Waiting for graph snapshot…</pre></div></div>
<script>
(()=>{const status=document.getElementById('status'),stats=document.getElementById('stats'),view=document.getElementById('graph');
async function poll(){try{const response=await fetch('/graph.json',{cache:'no-store'});if(!response.ok)throw new Error(String(response.status));const data=await response.json();const finished=!!data.live_finished;stats.textContent=`${data.node_count||0} nodes · ${data.edge_count||0} edges · ${data.event_count||0} events`;view.textContent=JSON.stringify({nodes:data.nodes||[],edges:data.edges||[]},null,2);if(finished){status.textContent='FINISHED';setTimeout(()=>{location.href='/final'},250);return}}catch(_){status.textContent='RECONNECTING'}setTimeout(poll,500)}poll();})();
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
    """HTTP server that avoids HTTPServer's reverse-DNS lookup during bind.

    HTTPServer.server_bind() calls socket.getfqdn(host). That lookup can block for
    several seconds on otherwise healthy macOS hosts and CI runners even when the
    server is bound to 127.0.0.1. ExecWeave never needs a DNS-derived server name,
    so bind directly with TCPServer and preserve the HTTPServer attributes expected
    by BaseHTTPRequestHandler.
    """

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
