import json
from pathlib import Path

from execweave.live import (
    LIVE_RAW_EVENT_HISTORY,
    _AUTHENTICATED_LIVE_HTML,
    _LiveState,
)
from execweave.live_view import LIVE_HTML


def _event(*, event_id: str, sequence: int, timestamp: str) -> dict[str, object]:
    return {
        "schema_version": "0.2",
        "event_id": event_id,
        "session_id": "s1",
        "timestamp": timestamp,
        "sequence": sequence,
        "event_type": "process.started",
        "relation": "LAUNCHED",
        "source": {"id": "session:s1", "type": "session", "name": "s1"},
        "target": {"id": "process:s1:1", "type": "process", "name": "python"},
        "attributes": {"backend": "portable", "causal": True, "raw_marker": event_id},
    }


def _append(path: Path, event: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def test_live_state_streams_original_runtime_events_for_raw_log(tmp_path: Path) -> None:
    event_path = tmp_path / "events.jsonl"
    event_path.write_text("", encoding="utf-8")
    state = _LiveState("s1", event_path)

    initial = state.live_update(None)
    assert initial["kind"] == "snapshot"
    assert initial["raw_events"] == []

    event = _event(
        event_id="event-1",
        sequence=1,
        timestamp="2026-08-27T08:00:00Z",
    )
    _append(event_path, event)

    delta = state.live_update(0)
    assert delta["kind"] == "delta"
    raw = delta["updates"][0]["raw_events_added"]
    assert len(raw) == 1
    assert raw[0]["line"] == 1
    assert raw[0]["event"]["event_id"] == "event-1"
    assert raw[0]["event"]["attributes"]["raw_marker"] == "event-1"

    snapshot = state.live_update(-1)
    assert snapshot["raw_events"][0]["event"]["event_id"] == "event-1"
    assert state.snapshot()["raw_events"][0]["line"] == 1
    assert LIVE_RAW_EVENT_HISTORY == 320


def test_live_dashboard_has_structured_and_raw_log_modes() -> None:
    assert 'data-log-mode="structured"' in LIVE_HTML
    assert 'data-log-mode="raw"' in LIVE_HTML
    assert 'id="raw-log"' in LIVE_HTML
    assert 'id="raw-rows"' in LIVE_HTML
    assert "raw_events_added" in LIVE_HTML
    assert "events.jsonl line" in LIVE_HTML


def test_finished_dashboard_supports_replay_and_gif_export() -> None:
    assert 'id="replay-run"' in LIVE_HTML
    assert 'id="download-gif"' in LIVE_HTML
    assert 'id="open-final"' in LIVE_HTML
    assert "function replayRun()" in LIVE_HTML
    assert "function gifBlob(" in LIVE_HTML
    assert "GIF89a" in LIVE_HTML
    assert "maxFrames=48" in LIVE_HTML
    assert ".gif`" in LIVE_HTML
    assert "window.__execweaveDashboard?.onFinished?.()" in LIVE_HTML


def test_replay_final_fetch_keeps_live_authentication() -> None:
    # Historical test name retained. v0.7.9 no longer fetches /final or replaces
    # the document at completion; authentication remains on the live data channel.
    assert "window.__execweaveToken=liveAuthToken" in _AUTHENTICATED_LIVE_HTML
    assert "X-ExecWeave-Token':liveAuthToken" in _AUTHENTICATED_LIVE_HTML
    assert "fetch('/final'" not in _AUTHENTICATED_LIVE_HTML
    assert "location.href='/final'" not in _AUTHENTICATED_LIVE_HTML
    assert "document.write(finalHtml)" not in _AUTHENTICATED_LIVE_HTML
