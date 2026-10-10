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


def test_exact_framework_model_request_preview_from_recorded_content(tmp_path: Path) -> None:
    """The exact Reviewer MODEL_REQUEST must enter the conversation index."""
    import hashlib

    from execweave.conversation_records import conversation_index_payload

    prompt = "You are a code reviewer. The handoff content is absent."
    payload = prompt.encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    relative = f"content/sha256/{digest}.txt"
    archive = tmp_path / relative
    archive.parent.mkdir(parents=True)
    archive.write_bytes(payload)
    agent = "agent:rolesdemo:session:Reviewer"
    content_id = "observed-content:model:sha256:" + digest
    graph = {
        "graph_schema_version": "0.2",
        "session_id": "session",
        "source_path": str(tmp_path / "semantic.jsonl"),
        "nodes": [
            {"id": agent, "type": "agent", "name": "Reviewer",
             "attributes": {"framework": "rolesdemo", "session_id": "session"}},
            {"id": content_id, "type": "observed_content",
             "name": "rolesdemo.model_request",
             "attributes": {
                 "path": relative, "sha256": digest, "size_bytes": len(payload),
                 "content_kind": "rolesdemo.model_request",
                 "media_type": "text/plain; charset=utf-8",
                 "representation": "text",
                 "complete_from_source": True,
             }},
        ],
        "edges": [
            {"id": "request", "source": agent, "target": content_id,
             "relation": "HAS_MODEL_CONTENT", "first_sequence": 1,
             "first_seen": "2026-10-10T17:57:54Z"},
        ],
    }
    result = conversation_index_payload(graph, tmp_path)
    exact = [
        entry for entry in result["entries"]
        if entry["source_id"] == agent
        and entry["relation"] == "HAS_MODEL_CONTENT"
        and entry["content_kind"] == "rolesdemo.model_request"
    ]
    assert len(exact) == 1
    messages = exact[0]["conversation_preview"]["messages"]
    assert any(
        msg["kind"] == "model_request" and msg["phase"] == "request"
        and msg["text"] == prompt
        for msg in messages
    )
    assert "String(entry?.source_id||'')===String(node.id||'')" in _AGENT_PANEL_JS
    assert "message?.kind==='model_request'" in _AGENT_PANEL_JS


def test_file_history_uses_canonical_node_counts_not_shared_edge_counts() -> None:
    """The original #111 Dashboard read ×11 from an edge against file node count 5."""
    assert "const node=rawNode(id)||nodeNamed(id)" in _AGENT_PANEL_JS
    assert "node.event_count" in _AGENT_PANEL_JS
    history = _AGENT_PANEL_JS.split("function fileHistory(id){", 1)[1].split(
        "function reachedBy(id){", 1
    )[0]
    assert "edge?.count" not in history
    assert "edge?.first_seen" not in history
