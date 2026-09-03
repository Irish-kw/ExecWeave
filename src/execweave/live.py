from __future__ import annotations

import json
import re
import shutil
from collections import deque

from . import live_core as _core
from .conversation_records import conversation_index_payload
from .dashboard_shell import DASHBOARD_HTML
from .viewer_limits import resolve_viewer_limits
from .viewer_projection import (
    internal_hook_process_ids_in_event,
    project_viewer_graph,
    render_graph_html as _projected_render_graph_html,
    strip_internal_hook_execution_graph,
    write_graph_html as _projected_write_graph_html,
)

# Re-export the established live API while keeping its implementation in live_core.
for _export_name in dir(_core):
    if not _export_name.startswith("__"):
        globals()[_export_name] = getattr(_core, _export_name)
del _export_name

# Make names referenced below explicit for static analysis as well as runtime use.
Path = _core.Path
_JsonlTail = _core._JsonlTail
LIVE_DELTA_HISTORY = _core.LIVE_DELTA_HISTORY
LIVE_DELTA_HISTORY_BYTES = _core.LIVE_DELTA_HISTORY_BYTES
VIEWER_MAX_NODES = _core.VIEWER_MAX_NODES
VIEWER_MAX_EDGES = _core.VIEWER_MAX_EDGES
VIEWER_MAX_DOM_ELEMENTS = _core.VIEWER_MAX_DOM_ELEMENTS
_BASE_LIVE_HTML = _core._LIVE_HTML
_LIVE_HTML = DASHBOARD_HTML
render_graph_html = _projected_render_graph_html
write_graph_html = _projected_write_graph_html

LIVE_RAW_EVENT_HISTORY = 320
_BaseLiveState = _core._LiveState
_base_inject_live_auth = _core._inject_live_auth
_base_inject_final_theme = _core._inject_final_theme
_base_build_execution_graph = _core.build_execution_graph
_base_handler_factory = _core._handler_factory
_RUN_CONTENT_ROUTE_RE = re.compile(r"^/content/sha256/[0-9a-f]{64}\.(?:json|txt|bin)$")


def _within_live_payload_budget(node_count: int, edge_count: int) -> bool:
    estimated_dom = node_count * 4 + edge_count * 3
    max_nodes, max_edges, max_dom_elements = resolve_viewer_limits(
        defaults=(VIEWER_MAX_NODES, VIEWER_MAX_EDGES, VIEWER_MAX_DOM_ELEMENTS)
    )
    return (
        node_count <= max_nodes
        and edge_count <= max_edges
        and estimated_dom <= max_dom_elements
    )


def _inject_live_auth(html: str) -> str:
    authenticated = _base_inject_live_auth(html)
    return authenticated.replace(
        "const liveAuthToken=new URLSearchParams(location.search).get('t')||'';"
        "if(liveAuthToken)",
        "const liveAuthToken=new URLSearchParams(location.search).get('t')||'';"
        "window.__execweaveToken=liveAuthToken;"
        "if(liveAuthToken)",
        1,
    )


def _inject_final_theme(html: str) -> str:
    """Honor the dashboard's built-in theme owner without injecting legacy controls."""
    return _base_inject_final_theme(html)


def _build_execution_graph_without_internal_hooks(*args, **kwargs):
    return strip_internal_hook_execution_graph(_base_build_execution_graph(*args, **kwargs))


def _handler_factory(state, token: str):
    base_handler = _base_handler_factory(state, token)
    run_root = state.event_path.parent.resolve()

    class Handler(base_handler):
        def _live_conversation_index(self) -> dict[str, object] | None:
            project = getattr(state, "conversation_index", None)
            if project is None:
                return None
            try:
                return project(run_root)
            except (OSError, RuntimeError, ValueError):
                return None

        def _send_run_file(self, target: Path, content_type: str) -> None:
            try:
                size = target.stat().st_size
                handle = target.open("rb")
            except OSError:
                self._send(b"Not found", "text/plain; charset=utf-8", 404)
                return
            with handle:
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(size))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                shutil.copyfileobj(handle, self.wfile, length=1024 * 1024)

        def do_GET(self) -> None:
            parsed = _core.urlsplit(self.path)
            request_path = parsed.path
            run_artifact = (
                request_path in {"/conversations.md", "/conversations.json"}
                or request_path.startswith("/content/")
            )
            if not run_artifact:
                super().do_GET()
                return
            if not self._authorized(parsed):
                self._send(b"Unauthorized", "text/plain; charset=utf-8", 401)
                return
            if request_path.startswith("/content/") and not _RUN_CONTENT_ROUTE_RE.fullmatch(
                request_path
            ):
                self._send(b"Not found", "text/plain; charset=utf-8", 404)
                return
            relative = request_path.lstrip("/")
            target = (run_root / relative).resolve(strict=False)
            try:
                target.relative_to(run_root)
            except ValueError:
                self._send(b"Not found", "text/plain; charset=utf-8", 404)
                return
            if not target.is_file():
                payload = (
                    self._live_conversation_index()
                    if request_path == "/conversations.json"
                    else None
                )
                if payload is None:
                    self._send(b"Not found", "text/plain; charset=utf-8", 404)
                    return
                self._send(
                    json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"),
                    "application/json; charset=utf-8",
                )
                return
            if request_path.endswith(".json"):
                content_type = "application/json; charset=utf-8"
            elif request_path.endswith(".md"):
                content_type = "text/markdown; charset=utf-8"
            elif request_path.endswith(".txt"):
                content_type = "text/plain; charset=utf-8"
            else:
                content_type = "application/octet-stream"
            self._send_run_file(target, content_type)

    return Handler


class _LiveState(_BaseLiveState):
    def __init__(
        self,
        session_id: str,
        event_path: Path,
        semantic_path: Path | None = None,
    ) -> None:
        super().__init__(session_id, event_path, semantic_path)
        self._raw_events: deque[dict[str, object]] = deque(maxlen=LIVE_RAW_EVENT_HISTORY)
        self._pending_raw_events: list[dict[str, object]] = []
        self._internal_hook_process_ids: set[str] = set()
        self._viewer_projection_ever_active = False

    def _reset_incremental_state_locked(self) -> None:
        super()._reset_incremental_state_locked()
        self._raw_events.clear()
        self._pending_raw_events.clear()
        self._internal_hook_process_ids.clear()

    @staticmethod
    def _event_entity_id(event: dict[str, object], key: str) -> str | None:
        entity = event.get(key)
        if not isinstance(entity, dict):
            return None
        value = entity.get("id")
        return value if isinstance(value, str) and value else None

    def _event_uses_internal_hook_process_locked(self, event: dict[str, object]) -> bool:
        direct_ids = internal_hook_process_ids_in_event(event)
        if direct_ids:
            self._internal_hook_process_ids.update(direct_ids)
        source_id = self._event_entity_id(event, "source")
        target_id = self._event_entity_id(event, "target")
        target = event.get("target")
        if (
            event.get("relation") == "SPAWNED"
            and isinstance(source_id, str)
            and source_id in self._internal_hook_process_ids
            and isinstance(target, dict)
            and target.get("type") == "process"
            and isinstance(target_id, str)
        ):
            self._internal_hook_process_ids.add(target_id)
        return bool(
            direct_ids
            or (isinstance(source_id, str) and source_id in self._internal_hook_process_ids)
            or (isinstance(target_id, str) and target_id in self._internal_hook_process_ids)
        )

    def _read_tail_records_locked(
        self,
        tail: _JsonlTail,
    ) -> list[tuple[int, dict[str, object]]]:
        records = super()._read_tail_records_locked(tail)
        if tail is self._runtime_tail:
            for line_number, event in records:
                if self._event_uses_internal_hook_process_locked(event):
                    continue
                entry: dict[str, object] = {"line": line_number, "event": event}
                self._raw_events.append(entry)
                self._pending_raw_events.append(entry)
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
        if self._event_uses_internal_hook_process_locked(event):
            return False
        return super()._apply_live_event_locked(
            event,
            added_nodes=added_nodes,
            updated_nodes=updated_nodes,
            added_edges=added_edges,
            updated_edges=updated_edges,
        )

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

    def _projected_snapshot_locked(
        self,
        projected: dict[str, object] | None = None,
    ) -> dict[str, object]:
        graph = projected if projected is not None else self._projected_graph_locked()
        node_count = int(graph.get("node_count", 0) or 0)
        edge_count = int(graph.get("edge_count", 0) or 0)
        return (
            graph
            if _within_live_payload_budget(node_count, edge_count)
            else _core._compact_live_graph(graph)
        )

    def _snapshot_from_accumulator_locked(self) -> dict[str, object]:
        return self._projected_snapshot_locked()

    def conversation_index(self, run_root: Path) -> dict[str, object]:
        """Project the conversation index from the graph observed so far."""
        with self._lock:
            graph = self._projected_graph_locked()
        return conversation_index_payload(graph, run_root)

    def _refresh_incremental_locked(self) -> None:
        before_sequence = self._update_sequence
        super()._refresh_incremental_locked()
        if self._pending_raw_events and self._update_sequence == before_sequence:
            counts = self._counts_locked()
            self._append_update_locked(
                {
                    **counts,
                    "event_count_delta": 0,
                    "evidence_event_count_delta": {"os_runtime": 0, "specialized": 0},
                    "nodes_added": [],
                    "nodes_updated": [],
                    "edges_added": [],
                    "edges_updated": [],
                }
            )

    def _append_update_locked(self, update: dict[str, object]) -> None:
        _core.LIVE_DELTA_HISTORY = LIVE_DELTA_HISTORY
        _core.LIVE_DELTA_HISTORY_BYTES = LIVE_DELTA_HISTORY_BYTES
        update.setdefault("raw_events_added", list(self._pending_raw_events))
        super()._append_update_locked(update)
        self._pending_raw_events.clear()

    def snapshot(self) -> dict[str, object]:
        payload = super().snapshot()
        with self._lock:
            payload["raw_events"] = list(self._raw_events)
        return payload

    def live_update(self, after: int | None) -> dict[str, object]:
        payload = super().live_update(after)
        with self._lock:
            projected = self._projected_graph_locked()
            if self._viewer_projection_ever_active:
                counts = self._projected_counts(projected)
                if payload.get("kind") == "delta":
                    payload = {
                        "kind": "snapshot",
                        "sequence": self._update_sequence,
                        "graph": self._projected_snapshot_locked(projected),
                        **self._evidence_metadata_locked(),
                        "live_finished": self._finished,
                    }
                elif payload.get("kind") == "noop":
                    payload.update(counts)
            if payload.get("kind") == "snapshot":
                payload["raw_events"] = list(self._raw_events)
        return payload


# Keep the extracted core on the latest presentation projection without rewriting
# its large implementation. run_live() resolves these globals at call time.
_core.render_graph_html = _projected_render_graph_html
_core.write_graph_html = _projected_write_graph_html
_core._inject_live_auth = _inject_live_auth
_core._inject_final_theme = _inject_final_theme
_core.build_execution_graph = _build_execution_graph_without_internal_hooks
_core._LiveState = _LiveState
_core._handler_factory = _handler_factory
_core._LIVE_HTML = _LIVE_HTML
_AUTHENTICATED_LIVE_HTML = _inject_live_auth(_LIVE_HTML)
_core._AUTHENTICATED_LIVE_HTML = _AUTHENTICATED_LIVE_HTML
