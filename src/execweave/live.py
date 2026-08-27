from __future__ import annotations

from collections import deque

from . import live_core as _core

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
        if payload.get("kind") == "snapshot":
            with self._lock:
                payload["raw_events"] = list(self._raw_events)
        return payload


_core._inject_live_auth = _inject_live_auth
_core._LiveState = _LiveState
_AUTHENTICATED_LIVE_HTML = _inject_live_auth(_LIVE_HTML)
_core._AUTHENTICATED_LIVE_HTML = _AUTHENTICATED_LIVE_HTML
