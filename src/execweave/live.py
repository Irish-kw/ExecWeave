from __future__ import annotations

import json
import threading
import time
import webbrowser
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from .backends import create_collector
from .graph import GRAPH_SCHEMA_VERSION, GraphAccumulator, build_execution_graph, write_execution_graph
from .live_view import LIVE_HTML as _LIVE_HTML
from .sink import JsonlSink
from .validate import validate_event_stream
from .viewer import (
    VIEWER_MAX_DOM_ELEMENTS,
    VIEWER_MAX_EDGES,
    VIEWER_MAX_NODES,
    render_graph_html,
    write_graph_html,
)

LIVE_DELTA_HISTORY = 256


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


class _LiveState:
    def __init__(self, session_id: str, event_path: Path) -> None:
        self.session_id = session_id
        self.event_path = event_path
        self._lock = threading.Lock()
        self._accumulator = GraphAccumulator(
            session_id=session_id,
            source_path=event_path,
            retain_event_ids=False,
        )
        self._read_offset = 0
        self._pending_bytes = b""
        self._finished = False
        self._final_graph: dict[str, object] | None = None
        self._final_html: str | None = None
        self._update_sequence = 0
        self._resync_floor = 0
        self._updates: deque[dict[str, object]] = deque(maxlen=LIVE_DELTA_HISTORY)

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

    def _reset_incremental_state_locked(self) -> None:
        self._accumulator = GraphAccumulator(
            session_id=self.session_id,
            source_path=self.event_path,
            retain_event_ids=False,
        )
        self._read_offset = 0
        self._pending_bytes = b""
        self._updates.clear()
        self._update_sequence += 1
        self._resync_floor = self._update_sequence

    def _snapshot_from_accumulator_locked(self) -> dict[str, object]:
        if self._finished and self._final_graph is not None:
            graph = self._final_graph
            node_count = int(graph.get("node_count", 0) or 0)
            edge_count = int(graph.get("edge_count", 0) or 0)
            return (
                dict(graph)
                if _within_live_payload_budget(node_count, edge_count)
                else _compact_live_graph(graph)
            )
        if _within_live_payload_budget(
            self._accumulator.node_count,
            self._accumulator.edge_count,
        ):
            return self._accumulator.to_dict()
        return _compact_live_graph(
            {
                "graph_schema_version": GRAPH_SCHEMA_VERSION,
                "session_id": self.session_id,
                "source_path": self._accumulator.source_path,
                "source_schema_versions": sorted(self._accumulator.source_schema_versions),
                "event_count": self._accumulator.event_count,
                "node_count": self._accumulator.node_count,
                "edge_count": self._accumulator.edge_count,
            }
        )

    def _append_update_locked(self, update: dict[str, object]) -> None:
        self._update_sequence += 1
        update["sequence"] = self._update_sequence
        self._updates.append(update)

    def _refresh_incremental_locked(self) -> None:
        try:
            file_size = self.event_path.stat().st_size
        except OSError:
            return
        if file_size < self._read_offset:
            self._reset_incremental_state_locked()
        if file_size <= self._read_offset:
            return

        try:
            with self.event_path.open("rb") as handle:
                handle.seek(self._read_offset)
                chunk = handle.read()
        except OSError:
            return
        if not chunk:
            return
        self._read_offset += len(chunk)

        buffered = self._pending_bytes + chunk
        lines = buffered.split(b"\n")
        self._pending_bytes = lines.pop()
        added_nodes: set[str] = set()
        updated_nodes: set[str] = set()
        added_edges: set[tuple[str, str, str]] = set()
        updated_edges: set[tuple[str, str, str]] = set()
        applied_count = 0

        for raw_line in lines:
            if not raw_line.strip():
                continue
            try:
                event = json.loads(raw_line.decode("utf-8"))
                if not isinstance(event, dict):
                    continue
                source_id = _entity_id(event.get("source"))
                target_id = _entity_id(event.get("target"))
                node_ids = {value for value in (source_id, target_id) if value}
                existing_nodes = {node_id for node_id in node_ids if node_id in self._accumulator.nodes}
                edge_key = _event_edge_key(event)
                edge_existed = edge_key in self._accumulator.edges if edge_key is not None else False
                self._accumulator.apply(event)
            except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
                continue

            applied_count += 1
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

        if not applied_count:
            return

        counts = self._counts_locked()
        node_count = int(counts["node_count"])
        edge_count = int(counts["edge_count"])
        compact = not _within_live_payload_budget(node_count, edge_count)
        update: dict[str, object] = {
            **counts,
            "event_count_delta": applied_count,
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

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            if not self._finished:
                self._refresh_incremental_locked()
            payload = self._snapshot_from_accumulator_locked()
            payload["live_finished"] = self._finished
            return payload

    def live_update(self, after: int | None) -> dict[str, object]:
        with self._lock:
            if not self._finished:
                self._refresh_incremental_locked()
            if after is None or after < 0:
                return {
                    "kind": "snapshot",
                    "sequence": self._update_sequence,
                    "graph": self._snapshot_from_accumulator_locked(),
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
                    "graph": self._snapshot_from_accumulator_locked(),
                    "live_finished": self._finished,
                    "resync": True,
                    "resync_reason": "future_sequence" if after > self._update_sequence else "history_gap",
                }
            counts = self._counts_locked()
            if after == self._update_sequence:
                return {
                    "kind": "noop",
                    "sequence": self._update_sequence,
                    **counts,
                    "live_finished": self._finished,
                }
            updates = [dict(update) for update in self._updates if int(update["sequence"]) > after]
            return {
                "kind": "delta",
                "base_sequence": after,
                "sequence": self._update_sequence,
                "updates": updates,
                **counts,
                "live_finished": self._finished,
            }

    def finish(self, graph: dict[str, object]) -> None:
        with self._lock:
            self._final_graph = dict(graph)
            self._final_html = render_graph_html(graph)
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
            parsed = urlsplit(self.path)
            path = parsed.path
            if path == "/":
                self._send(_LIVE_HTML.encode("utf-8"), "text/html; charset=utf-8")
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
