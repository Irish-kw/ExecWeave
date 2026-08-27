from __future__ import annotations

import hmac
import json
import os
import secrets
import threading
import time
import webbrowser
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4

from .backends import create_collector
from .graph import GRAPH_SCHEMA_VERSION, GraphAccumulator, build_execution_graph, write_execution_graph
from .live_view import LIVE_HTML as _LIVE_HTML
from .semantic import LiveSemanticNormalizer, merge_semantic_sidecar
from .sink import JsonlSink
from .validate import validate_event_stream
from .viewer_projection import (
    VIEWER_MAX_DOM_ELEMENTS,
    VIEWER_MAX_EDGES,
    VIEWER_MAX_NODES,
    project_viewer_graph,
    render_graph_html,
    write_graph_html,
)

LIVE_DELTA_HISTORY = 256
LIVE_DELTA_HISTORY_BYTES = 8 * 1024 * 1024
_SEMANTIC_ENV = "EXECWEAVE_SEMANTIC_SIDECAR"
_LIVE_TOKEN_HEADER = "X-ExecWeave-Token"

_FINAL_THEME_CSS = """
:root[data-theme="light"]{color-scheme:light;--bg:#f7f9fc;--panel:#ffffff;--panel2:#eef3f8;--text:#172033;--muted:#617083;--border:#cbd5e1;--edge:#64748b;--causal:#15803d;--noncausal:#b45309;--inferred:#7e22ce;--identity:#0369a1;--selected:#2563eb;--accent:#2563eb}
#execweave-theme-toggle{position:fixed;right:14px;bottom:14px;z-index:9999;border:1px solid var(--border);background:var(--panel);color:var(--text);border-radius:8px;padding:7px 10px;cursor:pointer;box-shadow:0 4px 18px rgba(15,23,42,.12)}
#execweave-theme-toggle:hover{border-color:var(--selected,var(--accent))}
:root[data-theme="light"] .node text{fill:#f8fafc}:root[data-theme="light"] .node .node-type{fill:#cbd5e1}
""".strip()

_FINAL_THEME_CONTROLS = r"""
<button id="execweave-theme-toggle" type="button" aria-label="Switch to light theme" title="Switch to light theme">Light</button>
<script>
(()=>{const key='execweave-theme',button=document.getElementById('execweave-theme-toggle');function apply(theme,persist=false){const next=theme==='light'?'light':'dark';document.documentElement.dataset.theme=next;const light=next==='light';button.textContent=light?'Dark':'Light';button.setAttribute('aria-label',light?'Switch to dark theme':'Switch to light theme');button.title=light?'Switch to dark theme':'Switch to light theme';if(persist){try{localStorage.setItem(key,next)}catch(_){}}}let initial='dark';try{if(localStorage.getItem(key)==='light')initial='light'}catch(_){}apply(initial);button.onclick=()=>apply(document.documentElement.dataset.theme==='light'?'dark':'light',true)})();
</script>
""".strip()


def _inject_final_theme(html: str) -> str:
    if 'id="execweave-theme-toggle"' in html:
        return html
    themed = html.replace("</style>", _FINAL_THEME_CSS + "\n</style>", 1)
    return themed.replace("</body>", _FINAL_THEME_CONTROLS + "\n</body>", 1)


def _inject_live_auth(html: str) -> str:
    marker = "(()=>{\nconst MAX_NODES="
    replacement = (
        "(()=>{\n"
        "const liveAuthToken=new URLSearchParams(location.search).get('t')||'';"
        "if(liveAuthToken){try{history.replaceState(null,'',location.pathname)}catch(_){}}\n"
        "const MAX_NODES="
    )
    authenticated = html.replace(marker, replacement, 1)
    authenticated = authenticated.replace(
        "fetch(`/live.json?after=${liveSequence}`,{cache:'no-store'})",
        "fetch(`/live.json?after=${liveSequence}`,{cache:'no-store',headers:{'X-ExecWeave-Token':liveAuthToken}})",
        1,
    )
    authenticated = authenticated.replace(
        "if(finished){setTimeout(()=>{location.href='/final'},250);return}",
        "if(finished){setTimeout(async()=>{try{const finalResponse=await fetch('/final',{cache:'no-store',headers:{'X-ExecWeave-Token':liveAuthToken}});if(!finalResponse.ok)throw new Error(String(finalResponse.status));const finalHtml=await finalResponse.text();document.open();document.write(finalHtml);document.close()}catch(_){status.textContent='RECONNECTING'}},250);return}",
        1,
    )
    return authenticated


_AUTHENTICATED_LIVE_HTML = _inject_live_auth(_LIVE_HTML)


@dataclass(frozen=True)
class LiveResult:
    session_id: str
    return_code: int
    live_url: str
    output_dir: Path
    event_stream: Path
    semantic_sidecar: Path
    materialized_event_stream: Path
    graph: Path
    viewer: Path

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "return_code": self.return_code,
            "live_url": self.live_url,
            "output_dir": str(self.output_dir),
            "event_stream": str(self.event_stream),
            "semantic_sidecar": str(self.semantic_sidecar),
            "materialized_event_stream": str(self.materialized_event_stream),
            "graph": str(self.graph),
            "viewer": str(self.viewer),
        }


def _within_live_payload_budget(node_count: int, edge_count: int) -> bool:
    estimated_dom = node_count * 4 + edge_count * 3
    return (
        node_count <= VIEWER_MAX_NODES
        and edge_count <= VIEWER_MAX_EDGES
        and estimated_dom <= VIEWER_MAX_DOM_ELEMENTS
    )


def _compact_live_graph(graph: dict[str, object]) -> dict[str, object]:
    return {
        "graph_schema_version": graph.get("graph_schema_version", GRAPH_SCHEMA_VERSION),
        "session_id": graph.get("session_id", "unknown"),
        "source_path": graph.get("source_path"),
        "source_schema_versions": graph.get("source_schema_versions", []),
        "event_count": graph.get("event_count", 0),
        "node_count": graph.get("node_count", 0),
        "edge_count": graph.get("edge_count", 0),
        "nodes": [],
        "edges": [],
        "live_payload_compact": True,
    }


def _entity_id(entity: object) -> str | None:
    if not isinstance(entity, dict):
        return None
    value = entity.get("id")
    return value if isinstance(value, str) and value else None


def _event_edge_key(event: dict[str, object]) -> tuple[str, str, str] | None:
    source_id = _entity_id(event.get("source"))
    target_id = _entity_id(event.get("target"))
    relation = event.get("relation")
    if source_id and target_id and isinstance(relation, str) and relation:
        return (source_id, relation, target_id)
    return None


@dataclass
class _JsonlTail:
    path: Path
    offset: int = 0
    pending_bytes: bytes = b""
    records_seen: int = 0


class _LiveState:
    def __init__(
        self,
        session_id: str,
        event_path: Path,
        semantic_path: Path | None = None,
    ) -> None:
        self.session_id = session_id
        self.event_path = event_path
        self.semantic_path = semantic_path
        self._lock = threading.Lock()
        self._accumulator = GraphAccumulator(
            session_id=session_id,
            source_path=event_path,
            retain_event_ids=False,
        )
        self._runtime_tail = _JsonlTail(event_path)
        self._semantic_tail = _JsonlTail(semantic_path) if semantic_path is not None else None
        self._semantic_normalizer = LiveSemanticNormalizer(session_id)
        self._runtime_event_count = 0
        self._specialized_event_count = 0
        self._finished = False
        self._final_graph: dict[str, object] | None = None
        self._final_html: str | None = None
        self._update_sequence = 0
        self._resync_floor = 0
        self._updates: deque[dict[str, object]] = deque()
        self._update_sizes: deque[int] = deque()
        self._updates_bytes = 0
        self._viewer_projection_ever_active = False

    def _empty_graph(self) -> dict[str, object]:
        return {
            "graph_schema_version": GRAPH_SCHEMA_VERSION,
            "session_id": self.session_id,
            "source_path": str(self.event_path.resolve()),
            "source_schema_versions": [],
            "event_count": 0,
            "node_count": 0,
            "edge_count": 0,
            "nodes": [],
            "edges": [],
        }

    def _counts_locked(self) -> dict[str, object]:
        if self._finished and self._final_graph is not None:
            return {
                "event_count": int(self._final_graph.get("event_count", 0) or 0),
                "node_count": int(self._final_graph.get("node_count", 0) or 0),
                "edge_count": int(self._final_graph.get("edge_count", 0) or 0),
            }
        return {
            "event_count": self._accumulator.event_count,
            "node_count": self._accumulator.node_count,
            "edge_count": self._accumulator.edge_count,
        }

    def _projected_graph_locked(self) -> dict[str, object]:
        raw_graph = (
            dict(self._final_graph)
            if self._finished and self._final_graph is not None
            else self._accumulator.to_dict()
        )
        projected = project_viewer_graph(raw_graph)
        if isinstance(projected.get("viewer_projection"), dict):
            self._viewer_projection_ever_active = True
        return projected

    @staticmethod
    def _projected_counts(graph: dict[str, object]) -> dict[str, object]:
        return {
            "event_count": int(graph.get("event_count", 0) or 0),
            "node_count": int(graph.get("node_count", 0) or 0),
            "edge_count": int(graph.get("edge_count", 0) or 0),
        }

    def _clear_update_history_locked(self) -> None:
        self._updates.clear()
        self._update_sizes.clear()
        self._updates_bytes = 0

    def _reset_incremental_state_locked(self) -> None:
        self._accumulator = GraphAccumulator(
            session_id=self.session_id,
            source_path=self.event_path,
            retain_event_ids=False,
        )
        tails = [self._runtime_tail]
        if self._semantic_tail is not None:
            tails.append(self._semantic_tail)
        for tail in tails:
            tail.offset = 0
            tail.pending_bytes = b""
            tail.records_seen = 0
        self._semantic_normalizer.reset()
        self._runtime_event_count = 0
        self._specialized_event_count = 0
        self._clear_update_history_locked()
        self._update_sequence += 1
        self._resync_floor = self._update_sequence

    def _snapshot_from_accumulator_locked(
        self,
        projected: dict[str, object] | None = None,
    ) -> dict[str, object]:
        graph = projected if projected is not None else self._projected_graph_locked()
        node_count = int(graph.get("node_count", 0) or 0)
        edge_count = int(graph.get("edge_count", 0) or 0)
        return (
            graph
            if _within_live_payload_budget(node_count, edge_count)
            else _compact_live_graph(graph)
        )

    def _append_update_locked(self, update: dict[str, object]) -> None:
        self._update_sequence += 1
        update["sequence"] = self._update_sequence
        encoded_size = len(
            json.dumps(update, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        self._updates.append(update)
        self._update_sizes.append(encoded_size)
        self._updates_bytes += encoded_size
        while (
            len(self._updates) > LIVE_DELTA_HISTORY
            or self._updates_bytes > LIVE_DELTA_HISTORY_BYTES
        ):
            evicted = self._updates.popleft()
            self._updates_bytes -= self._update_sizes.popleft()
            self._resync_floor = max(self._resync_floor, int(evicted["sequence"]))

    def _tail_truncated_locked(self, tail: _JsonlTail) -> bool:
        try:
            return tail.path.stat().st_size < tail.offset
        except OSError:
            return False

    def _read_tail_records_locked(
        self,
        tail: _JsonlTail,
    ) -> list[tuple[int, dict[str, object]]]:
        try:
            file_size = tail.path.stat().st_size
        except OSError:
            return []
        if file_size <= tail.offset:
            return []
        try:
            with tail.path.open("rb") as handle:
                handle.seek(tail.offset)
                chunk = handle.read()
        except OSError:
            return []
        if not chunk:
            return []
        tail.offset += len(chunk)
        buffered = tail.pending_bytes + chunk
        lines = buffered.split(b"\n")
        tail.pending_bytes = lines.pop()
        records: list[tuple[int, dict[str, object]]] = []
        for raw_line in lines:
            if not raw_line.strip():
                continue
            tail.records_seen += 1
            try:
                payload = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                records.append((tail.records_seen, payload))
        return records

    def _apply_live_event_locked(
        self,
        event: dict[str, object],
        *,
        added_nodes: set[str],
        updated_nodes: set[str],
        added_edges: set[tuple[str, str, str]],
        updated_edges: set[tuple[str, str, str]],
    ) -> bool:
        source_id = _entity_id(event.get("source"))
        target_id = _entity_id(event.get("target"))
        node_ids = {value for value in (source_id, target_id) if value}
        existing_nodes = {
            node_id for node_id in node_ids if node_id in self._accumulator.nodes
        }
        edge_key = _event_edge_key(event)
        edge_existed = edge_key in self._accumulator.edges if edge_key is not None else False
        try:
            self._accumulator.apply(event)
        except (TypeError, ValueError):
            return False

        for node_id in node_ids:
            if node_id in existing_nodes and node_id not in added_nodes:
                updated_nodes.add(node_id)
            else:
                added_nodes.add(node_id)
                updated_nodes.discard(node_id)
        if edge_key is not None and edge_key in self._accumulator.edges:
            if edge_existed and edge_key not in added_edges:
                updated_edges.add(edge_key)
            else:
                added_edges.add(edge_key)
                updated_edges.discard(edge_key)
        return True

    def _refresh_incremental_locked(self) -> None:
        tails = [self._runtime_tail]
        if self._semantic_tail is not None:
            tails.append(self._semantic_tail)
        if any(self._tail_truncated_locked(tail) for tail in tails):
            self._reset_incremental_state_locked()

        added_nodes: set[str] = set()
        updated_nodes: set[str] = set()
        added_edges: set[tuple[str, str, str]] = set()
        updated_edges: set[tuple[str, str, str]] = set()
        runtime_applied = 0
        specialized_applied = 0

        for _, event in self._read_tail_records_locked(self._runtime_tail):
            if not self._apply_live_event_locked(
                event,
                added_nodes=added_nodes,
                updated_nodes=updated_nodes,
                added_edges=added_edges,
                updated_edges=updated_edges,
            ):
                continue
            self._semantic_normalizer.observe_runtime_event(event)
            self._runtime_event_count += 1
            runtime_applied += 1

        if self._semantic_tail is not None and self._semantic_normalizer.ready:
            for line_number, record in self._read_tail_records_locked(self._semantic_tail):
                try:
                    normalized = self._semantic_normalizer.normalize(
                        record,
                        line_number=line_number,
                    )
                except ValueError:
                    continue
                if normalized is None:
                    continue
                if not self._apply_live_event_locked(
                    normalized,
                    added_nodes=added_nodes,
                    updated_nodes=updated_nodes,
                    added_edges=added_edges,
                    updated_edges=updated_edges,
                ):
                    continue
                self._specialized_event_count += 1
                specialized_applied += 1

        applied_count = runtime_applied + specialized_applied
        if not applied_count:
            return

        counts = self._counts_locked()
        node_count = int(counts["node_count"])
        edge_count = int(counts["edge_count"])
        compact = not _within_live_payload_budget(node_count, edge_count)
        update: dict[str, object] = {
            **counts,
            "event_count_delta": applied_count,
            "evidence_event_count_delta": {
                "os_runtime": runtime_applied,
                "specialized": specialized_applied,
            },
            "nodes_added": [],
            "nodes_updated": [],
            "edges_added": [],
            "edges_updated": [],
        }
        if compact:
            update["live_payload_compact"] = True
        else:
            update["nodes_added"] = [
                self._accumulator.nodes[node_id].to_dict()
                for node_id in sorted(added_nodes)
                if node_id in self._accumulator.nodes
            ]
            update["nodes_updated"] = [
                self._accumulator.nodes[node_id].to_dict()
                for node_id in sorted(updated_nodes - added_nodes)
                if node_id in self._accumulator.nodes
            ]
            update["edges_added"] = [
                self._accumulator.edges[key].to_dict()
                for key in sorted(added_edges)
                if key in self._accumulator.edges
            ]
            update["edges_updated"] = [
                self._accumulator.edges[key].to_dict()
                for key in sorted(updated_edges - added_edges)
                if key in self._accumulator.edges
            ]
        self._append_update_locked(update)

    def _evidence_metadata_locked(self) -> dict[str, object]:
        return {
            "live_evidence_counts": {
                "os_runtime": self._runtime_event_count,
                "specialized": self._specialized_event_count,
            },
            "live_specialized_provisional": (
                self._specialized_event_count > 0 and not self._finished
            ),
        }

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            if not self._finished:
                self._refresh_incremental_locked()
            payload = self._snapshot_from_accumulator_locked()
            payload["live_finished"] = self._finished
            payload.update(self._evidence_metadata_locked())
            return payload

    def live_update(self, after: int | None) -> dict[str, object]:
        with self._lock:
            if not self._finished:
                self._refresh_incremental_locked()
            projected = self._projected_graph_locked()
            projected_counts = self._projected_counts(projected)
            if after is None or after < 0:
                return {
                    "kind": "snapshot",
                    "sequence": self._update_sequence,
                    "graph": self._snapshot_from_accumulator_locked(projected),
                    **self._evidence_metadata_locked(),
                    "live_finished": self._finished,
                }
            oldest_sequence = (
                int(self._updates[0]["sequence"]) if self._updates else self._update_sequence + 1
            )
            history_gap = after < self._resync_floor or (
                self._updates and after < oldest_sequence - 1
            )
            if after > self._update_sequence or history_gap:
                return {
                    "kind": "snapshot",
                    "sequence": self._update_sequence,
                    "graph": self._snapshot_from_accumulator_locked(projected),
                    **self._evidence_metadata_locked(),
                    "live_finished": self._finished,
                    "resync": True,
                    "resync_reason": "future_sequence" if after > self._update_sequence else "history_gap",
                }
            counts = projected_counts if self._viewer_projection_ever_active else self._counts_locked()
            if after == self._update_sequence:
                return {
                    "kind": "noop",
                    "sequence": self._update_sequence,
                    **counts,
                    **self._evidence_metadata_locked(),
                    "live_finished": self._finished,
                }
            if self._viewer_projection_ever_active:
                return {
                    "kind": "snapshot",
                    "sequence": self._update_sequence,
                    "graph": self._snapshot_from_accumulator_locked(projected),
                    **self._evidence_metadata_locked(),
                    "live_finished": self._finished,
                }
            updates = [dict(update) for update in self._updates if int(update["sequence"]) > after]
            return {
                "kind": "delta",
                "base_sequence": after,
                "sequence": self._update_sequence,
                "updates": updates,
                **counts,
                **self._evidence_metadata_locked(),
                "live_finished": self._finished,
            }

    def finish(self, graph: dict[str, object]) -> None:
        with self._lock:
            self._final_graph = dict(graph)
            self._final_html = _inject_final_theme(render_graph_html(graph))
            self._finished = True
            counts = self._counts_locked()
            node_count = int(counts["node_count"])
            edge_count = int(counts["edge_count"])
            terminal: dict[str, object] = {
                **counts,
                "event_count_delta": 0,
                "nodes_added": [],
                "nodes_updated": [],
                "edges_added": [],
                "edges_updated": [],
                "terminal": True,
            }
            if not _within_live_payload_budget(node_count, edge_count):
                terminal["live_payload_compact"] = True
            self._append_update_locked(terminal)

    def final_html(self) -> str | None:
        with self._lock:
            return self._final_html


def _handler_factory(state: _LiveState, token: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self, parsed) -> bool:
            candidate = self.headers.get(_LIVE_TOKEN_HEADER)
            if candidate is None:
                values = parse_qs(parsed.query).get("t", [])
                if len(values) == 1:
                    candidate = values[0]
            return bool(candidate) and hmac.compare_digest(candidate, token)

        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            if not self._authorized(parsed):
                self._send(b"Unauthorized", "text/plain; charset=utf-8", 401)
                return
            path = parsed.path
            if path == "/":
                self._send(_AUTHENTICATED_LIVE_HTML.encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/graph.json":
                payload = json.dumps(
                    state.snapshot(), ensure_ascii=False, separators=(",", ":")
                ).encode("utf-8")
                self._send(payload, "application/json; charset=utf-8")
                return
            if path == "/live.json":
                values = parse_qs(parsed.query).get("after", [])
                try:
                    after = int(values[0]) if values else None
                except (TypeError, ValueError):
                    self._send(b"Invalid after sequence", "text/plain; charset=utf-8", 400)
                    return
                payload = json.dumps(
                    state.live_update(after), ensure_ascii=False, separators=(",", ":")
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
    """Run a command with the portable collector and expose an authenticated localhost graph."""
    if not command:
        raise ValueError("command must not be empty")
    if port < 0 or port > 65535:
        raise ValueError("port must be between 0 and 65535")
    if linger_seconds < 0:
        raise ValueError("linger_seconds must be >= 0")

    session_id = uuid4().hex
    live_token = secrets.token_urlsafe(32)
    root = Path(watch_root).expanduser().resolve()
    run_dir = (
        Path(output_dir).expanduser().resolve()
        if output_dir is not None
        else root / ".execweave" / "runs" / session_id
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    event_path = run_dir / "events.jsonl"
    semantic_path = run_dir / "semantic.jsonl"
    merged_event_path = run_dir / "events.semantic.jsonl"
    graph_path = run_dir / "graph.json"
    viewer_path = run_dir / "viewer.html"
    for artifact in (event_path, semantic_path, merged_event_path, graph_path, viewer_path):
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

    state = _LiveState(session_id, event_path, semantic_path)
    server = _LocalThreadingHTTPServer(("127.0.0.1", port), _handler_factory(state, live_token))
    server.daemon_threads = True
    server_thread = threading.Thread(
        target=server.serve_forever,
        name="execweave-live",
        daemon=True,
    )
    server_thread.start()
    host, selected_port = server.server_address[:2]
    live_url = f"http://{host}:{selected_port}/"
    authenticated_live_url = f"{live_url}?{urlencode({'t': live_token})}"
    if announce is not None:
        announce(authenticated_live_url)
    if open_browser:
        webbrowser.open(authenticated_live_url)

    return_code = 1
    previous_semantic_sidecar = os.environ.get(_SEMANTIC_ENV)
    os.environ[_SEMANTIC_ENV] = str(semantic_path)
    try:
        try:
            return_code = collector.run(command)
        finally:
            if previous_semantic_sidecar is None:
                os.environ.pop(_SEMANTIC_ENV, None)
            else:
                os.environ[_SEMANTIC_ENV] = previous_semantic_sidecar

        validation = validate_event_stream(event_path)
        if not validation.valid:
            details = "; ".join(validation.errors)
            raise RuntimeError(f"live event stream failed validation: {details}")

        materialized_event_path = event_path
        if semantic_path.exists() and semantic_path.stat().st_size > 0:
            merge_semantic_sidecar(event_path, semantic_path, merged_event_path)
            materialized_event_path = merged_event_path

        execution_graph = build_execution_graph(materialized_event_path)
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
            semantic_sidecar=semantic_path,
            materialized_event_stream=materialized_event_path,
            graph=graph_path,
            viewer=viewer_path,
        )
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)
