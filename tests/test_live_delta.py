import json
from pathlib import Path

import execweave.live as live_module
from execweave.live import _LIVE_HTML, _LiveState


def _event(
    *,
    event_id: str,
    sequence: int,
    timestamp: str,
    target_id: str = "process:s1:1",
) -> dict[str, object]:
    return {
        "schema_version": "0.2",
        "event_id": event_id,
        "session_id": "s1",
        "timestamp": timestamp,
        "sequence": sequence,
        "event_type": "process.started",
        "relation": "LAUNCHED",
        "source": {"id": "session:s1", "type": "session", "name": "s1"},
        "target": {"id": target_id, "type": "process", "name": "python"},
        "attributes": {"backend": "portable", "causal": True},
    }


def _append(path: Path, event: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def test_live_viewer_uses_sequence_delta_protocol() -> None:
    assert "/live.json?after=${liveSequence}" in _LIVE_HTML
    assert "kind==='snapshot'" in _LIVE_HTML
    assert "kind==='delta'" in _LIVE_HTML
    assert "applyDelta" in _LIVE_HTML
    assert "placeAddedNodes" in _LIVE_HTML
    assert "RESYNCING" in _LIVE_HTML


def test_live_state_returns_snapshot_then_only_changed_entities(tmp_path: Path) -> None:
    event_path = tmp_path / "events.jsonl"
    event_path.write_text("", encoding="utf-8")
    state = _LiveState("s1", event_path)

    initial = state.live_update(None)
    assert initial["kind"] == "snapshot"
    assert initial["sequence"] == 0
    assert initial["graph"]["event_count"] == 0

    _append(
        event_path,
        _event(
            event_id="event-1",
            sequence=1,
            timestamp="2026-08-26T00:00:00Z",
        ),
    )
    first = state.live_update(0)
    assert first["kind"] == "delta"
    assert first["base_sequence"] == 0
    assert first["sequence"] == 1
    assert len(first["updates"]) == 1
    update = first["updates"][0]
    assert update["sequence"] == 1
    assert update["event_count"] == 1
    assert update["node_count"] == 2
    assert update["edge_count"] == 1
    assert len(update["nodes_added"]) == 2
    assert update["nodes_updated"] == []
    assert len(update["edges_added"]) == 1
    assert update["edges_updated"] == []
    assert update["edges_added"][0]["event_ids"] == []

    noop = state.live_update(1)
    assert noop["kind"] == "noop"
    assert noop["sequence"] == 1
    assert noop["event_count"] == 1

    _append(
        event_path,
        _event(
            event_id="event-2",
            sequence=2,
            timestamp="2026-08-26T00:00:01Z",
        ),
    )
    second = state.live_update(1)
    assert second["kind"] == "delta"
    assert second["sequence"] == 2
    update = second["updates"][0]
    assert update["nodes_added"] == []
    assert len(update["nodes_updated"]) == 2
    assert update["edges_added"] == []
    assert len(update["edges_updated"]) == 1
    assert update["edges_updated"][0]["count"] == 2
    assert update["edges_updated"][0]["event_ids"] == []


def test_live_state_resyncs_when_delta_history_is_too_old(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(live_module, "LIVE_DELTA_HISTORY", 1)
    event_path = tmp_path / "events.jsonl"
    event_path.write_text("", encoding="utf-8")
    state = _LiveState("s1", event_path)

    for index in range(1, 4):
        _append(
            event_path,
            _event(
                event_id=f"event-{index}",
                sequence=index,
                timestamp=f"2026-08-26T00:00:0{index}Z",
            ),
        )
        response = state.live_update(index - 1)
        assert response["sequence"] == index

    resync = state.live_update(0)
    assert resync["kind"] == "snapshot"
    assert resync["resync"] is True
    assert resync["resync_reason"] == "history_gap"
    assert resync["sequence"] == 3
    assert resync["graph"]["event_count"] == 3


def test_live_state_resyncs_when_delta_history_exceeds_byte_budget(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(live_module, "LIVE_DELTA_HISTORY_BYTES", 1)
    event_path = tmp_path / "events.jsonl"
    event_path.write_text("", encoding="utf-8")
    state = _LiveState("s1", event_path)

    _append(
        event_path,
        _event(
            event_id="event-1",
            sequence=1,
            timestamp="2026-08-26T00:00:00Z",
        ),
    )
    response = state.live_update(0)
    assert response["kind"] == "snapshot"
    assert response["resync"] is True
    assert response["resync_reason"] == "history_gap"
    assert response["sequence"] == 1
    assert state._updates_bytes == 0


def test_live_finish_is_a_sequence_visible_terminal_update(tmp_path: Path) -> None:
    event_path = tmp_path / "events.jsonl"
    event_path.write_text("", encoding="utf-8")
    state = _LiveState("s1", event_path)
    graph = {
        "graph_schema_version": "0.1",
        "session_id": "s1",
        "source_path": str(event_path),
        "source_schema_versions": ["0.2"],
        "event_count": 1,
        "node_count": 2,
        "edge_count": 1,
        "nodes": [
            {"id": "session:s1", "type": "session"},
            {"id": "process:s1:1", "type": "process"},
        ],
        "edges": [
            {
                "id": "session:s1--LAUNCHED-->process:s1:1",
                "source": "session:s1",
                "target": "process:s1:1",
                "relation": "LAUNCHED",
            }
        ],
    }

    state.finish(graph)
    terminal = state.live_update(0)
    assert terminal["kind"] == "delta"
    assert terminal["live_finished"] is True
    assert terminal["sequence"] == 1
    assert terminal["updates"][0]["terminal"] is True
    assert terminal["updates"][0]["event_count"] == 1
    final_html = state.final_html()
    assert final_html is not None
    assert 'id="execweave-theme-toggle"' in final_html
    assert "execweave-theme" in final_html
    assert 'data-theme="light"' in final_html
