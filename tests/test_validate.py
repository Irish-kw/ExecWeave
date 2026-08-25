import json
from pathlib import Path

import pytest

from execweave.schema import Entity, RuntimeEvent
from execweave.sink import JsonlSink
from execweave.validate import validate_event_stream


def _event(session_id: str, event_type: str, relation: str) -> RuntimeEvent:
    session = Entity(type="session", id=f"session:{session_id}")
    return RuntimeEvent.create(
        session_id=session_id,
        event_type=event_type,
        relation=relation,
        source=session,
    )


def test_valid_complete_stream(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    sink = JsonlSink(path)
    sink.emit(_event("s1", "session.started", "STARTED_SESSION"))
    sink.emit(_event("s1", "session.finished", "FINISHED_SESSION"))

    result = validate_event_stream(path)
    assert result.valid is True
    assert result.event_count == 2
    assert result.errors == []
    assert result.session_ids == ["s1"]


def test_sink_refuses_nonempty_existing_stream(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    first = JsonlSink(path)
    first.emit(_event("s1", "session.started", "STARTED_SESSION"))

    with pytest.raises(FileExistsError):
        JsonlSink(path)


def test_validator_rejects_sequence_gap_and_multiple_sessions(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    payloads = [
        {
            "schema_version": "0.2",
            "event_id": "e1",
            "session_id": "s1",
            "timestamp": "2026-08-25T00:00:00Z",
            "event_type": "session.started",
            "relation": "STARTED_SESSION",
            "source": {"type": "session", "id": "session:s1"},
            "target": None,
            "sequence": 1,
            "attributes": {},
        },
        {
            "schema_version": "0.2",
            "event_id": "e2",
            "session_id": "s2",
            "timestamp": "2026-08-25T00:00:01Z",
            "event_type": "session.finished",
            "relation": "FINISHED_SESSION",
            "source": {"type": "session", "id": "session:s2"},
            "target": None,
            "sequence": 3,
            "attributes": {},
        },
    ]
    path.write_text("\n".join(json.dumps(payload) for payload in payloads) + "\n", encoding="utf-8")

    result = validate_event_stream(path)
    assert result.valid is False
    assert any("multiple session IDs" in error for error in result.errors)
    assert any("sequence is not contiguous" in error for error in result.errors)


def test_validator_rejects_duplicate_event_id_and_incomplete_session(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    base = {
        "schema_version": "0.2",
        "event_id": "duplicate",
        "session_id": "s1",
        "timestamp": "2026-08-25T00:00:00Z",
        "event_type": "session.started",
        "relation": "STARTED_SESSION",
        "source": {"type": "session", "id": "session:s1"},
        "target": None,
        "sequence": 1,
        "attributes": {},
    }
    second = dict(base)
    second["sequence"] = 2
    second["event_type"] = "process.started"
    second["relation"] = "LAUNCHED"
    path.write_text(json.dumps(base) + "\n" + json.dumps(second) + "\n", encoding="utf-8")

    result = validate_event_stream(path)
    assert result.valid is False
    assert any("duplicate event_id" in error for error in result.errors)
    assert any("session.finished" in error for error in result.errors)


def test_allow_incomplete_accepts_interrupted_but_structurally_valid_stream(tmp_path: Path) -> None:
    path = tmp_path / "interrupted.jsonl"
    sink = JsonlSink(path)
    sink.emit(_event("s1", "session.started", "STARTED_SESSION"))

    strict = validate_event_stream(path)
    relaxed = validate_event_stream(path, require_complete_session=False)
    assert strict.valid is False
    assert relaxed.valid is True
