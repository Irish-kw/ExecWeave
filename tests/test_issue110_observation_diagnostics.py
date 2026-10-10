"""Regression tests for #110/#111 evidence gaps (original v0.8.35 baseline)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from execweave.graph import build_execution_graph
from execweave.schema import Entity, RuntimeEvent
from execweave.session_summary import SessionSummary
from execweave.validate import validate_event_stream
from execweave.viewer_agent_panel import _AGENT_PANEL_JS


def _stream(path: Path, versions: list[str]) -> None:
    session = Entity(type="session", id="session:fixed")
    events = [
        RuntimeEvent.create(
            session_id="fixed",
            event_type=event_type,
            relation=relation,
            source=session,
        ).to_dict()
        for event_type, relation in [
            ("session.started", "STARTED_SESSION"),
            ("session.finished", "FINISHED_SESSION"),
        ]
    ]
    for i, event in enumerate(events):
        event["schema_version"] = versions[i]
        event["sequence"] = i + 1
    path.write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )


@pytest.mark.parametrize("versions", [
    ["9.9", "9.9"],
    ["0.2", "9.9"],
    ["0.1", "0.1"],
])
def test_unknown_or_mixed_stream_versions_are_rejected(
    tmp_path: Path, versions: list[str],
) -> None:
    path = tmp_path / "stream.jsonl"
    _stream(path, versions)
    for allow_incomplete in (False, True):
        result = validate_event_stream(
            path, require_complete_session=not allow_incomplete
        )
        assert result.valid is False
        assert any("unsupported stream schema version" in error for error in result.errors)
        with pytest.raises(ValueError, match="unsupported stream schema version"):
            build_execution_graph(path, allow_incomplete=allow_incomplete)


def test_0834_current_stream_schema_remains_accepted(tmp_path: Path) -> None:
    path = tmp_path / "stream.jsonl"
    _stream(path, ["0.2", "0.2"])
    assert validate_event_stream(path).valid
    graph = build_execution_graph(path)
    assert graph.source_schema_versions == ["0.2"]


def _handoff(message_id: str, kind: str, recipient: str = "agent:reviewer") -> dict:
    return {
        "session_id": "fixed",
        "event_id": kind + message_id,
        "event_type": kind,
        "relation": kind,
        "source": {"type": "agent", "id": "agent:engineer"},
        "target": {"type": "agent", "id": recipient},
        "attributes": {
            "framework": "rolesdemo",
            "message_id": message_id,
            "sender_agent_id": "agent:engineer",
            "recipient_agent_id": recipient,
            "session_id": "fixed",
        },
    }


def _finish() -> dict:
    return {
        "event_type": "session.finished",
        "event_id": "terminal",
        "timestamp": "2026-10-11T00:00:00Z",
        "attributes": {"return_code": 0},
    }


def test_handoff_missing_receive_is_persisted_as_uncertainty() -> None:
    session = SessionSummary()
    session.observe(_handoff("msg-1", "MESSAGE_SENT"))
    session.observe(_handoff("msg-1", "MESSAGE_RECEIVED"))
    session.observe(_handoff("msg-2", "MESSAGE_SENT"))
    # Do not flag a message still in flight as a terminal observation gap.
    assert "message_receive_not_observed" not in session.observation["reasons"]
    session.observe(_finish())
    assessment = session.observation
    assert assessment["state"] == "observation_incomplete"
    assert "message_receive_not_observed" in assessment["reasons"]
    assert assessment["message_delivery"]["unconfirmed_count"] == 1
    assert assessment["message_delivery"]["unconfirmed"] == [
        {
            "message_id": "msg-2",
            "sender_id": "agent:engineer",
            "recipient_id": "agent:reviewer",
            "state": "receive_not_observed",
        }
    ]
    assert assessment["message_delivery"]["delivery_failure_proven"] is False


def test_handoff_receipt_must_match_message_and_recipient() -> None:
    session = SessionSummary()
    session.observe(_handoff("msg-1", "MESSAGE_SENT"))
    session.observe(_handoff("msg-1", "MESSAGE_RECEIVED", "agent:other"))
    session.observe(_finish())
    assert session.observation["message_delivery"]["unconfirmed_count"] == 1
    assert session.observation["message_delivery"]["unconfirmed"][0]["recipient_id"] == "agent:reviewer"


def test_handoff_matching_receive_clears_unconfirmed_gap() -> None:
    session = SessionSummary()
    session.observe(_handoff("msg-1", "MESSAGE_RECEIVED"))
    session.observe(_handoff("msg-1", "MESSAGE_SENT"))
    session.observe(_finish())
    assert session.observation["message_delivery"]["unconfirmed_count"] == 0
    assert "message_receive_not_observed" not in session.observation["reasons"]


def test_unknown_writer_inspector_never_silently_hides_attribution() -> None:
    assert "a.writer_identity==='unknown'" in _AGENT_PANEL_JS
    assert "add('Writer','unknown" in _AGENT_PANEL_JS
    assert "a.snapshot_state==='not_captured'" in _AGENT_PANEL_JS
