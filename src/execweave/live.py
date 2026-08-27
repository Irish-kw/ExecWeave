from __future__ import annotations

from collections import deque

from . import live_core as _core
from .viewer_projection import (
    project_viewer_graph,
    render_graph_html as _projected_render_graph_html,
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
_LIVE_HTML = _core._LIVE_HTML
render_graph_html = _projected_render_graph_html
write_graph_html = _projected_write_graph_html

LIVE_RAW_EVENT_HISTORY = 320
_BaseLiveState = _core._LiveState
_base_inject_live_auth = _core._inject_live_auth


def _inject_live_auth(html: str) -> str:
    authenticated = _base_inject_live_auth(html)
    authenticated = authenticated.replace(
        "const liveAuthToken=new URLSearchParams(location.search).get('t')||'';"
        "if(liveAuthToken)",
        "const liveAuthToken=new URLSearchParams(location.search).get('t')||'';"
        "window.__execweaveToken=liveAuthToken;"
        "if(liveAuthToken)",
        1,
    )
    authenticated = authenticated.replace(
        "fetch('/final',{cache:'no-store'})",
        "fetch('/final',{cache:'no-store',headers:{"
        "'X-ExecWeave-Token':window.__execweaveToken||''}})",
        1,
    )
    return authenticated


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
        self._viewer_projection_ever_active = False

    def _reset_incremental_state_locked(self) -> None:
        super()._reset_incremental_state_locked()
        self._raw_events.clear()
        self._pending_raw_events.clear()

    def _read_tail_records_locked(
        self,
        tail: _JsonlTail,
    ) -> list[tuple[int, dict[str, object]]]:
        records = super()._read_tail_records_locked(tail)
        if tail is self._runtime_tail:
            for line_number, event in records:
                entry: dict[str, object] = {"line": line_number, "event": event}
                self._raw_events.append(entry)
                self._pending_raw_events.append(entry)
        return records

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
            if _core._within_live_payload_budget(node_count, edge_count)
            else _core._compact_live_graph(graph)
        )

    def _snapshot_from_accumulator_locked(self) -> dict[str, object]:
        return self._projected_snapshot_locked()

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
        # Preserve monkeypatch behavior for the established live delta limits.
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
_core._LiveState = _LiveState
_AUTHENTICATED_LIVE_HTML = _inject_live_auth(_LIVE_HTML)
_core._AUTHENTICATED_LIVE_HTML = _AUTHENTICATED_LIVE_HTML
