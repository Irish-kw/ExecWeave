from __future__ import annotations

import json
from pathlib import Path

import execweave.opencode_hook_cli as hook_cli
from execweave.opencode_event_contract import (
    OFFICIAL_OPENCODE_BUS_EVENTS,
    opencode_official_event_semantic_events,
)


def _payload(event_type: str, properties: dict) -> dict:
    return {
        "hook_event_name": "event",
        "event_type": event_type,
        "sessionID": properties.get("sessionID"),
        "cwd": "/repo",
        "event": {"type": event_type, "properties": properties},
    }


def _relations(events: list[dict]) -> set[str]:
    return {event["relation"] for event in events}


def test_official_event_set_matches_current_documented_surface() -> None:
    assert len(OFFICIAL_OPENCODE_BUS_EVENTS) == 28
    assert {
        "permission.asked",
        "permission.replied",
        "session.compacted",
        "session.deleted",
        "session.error",
        "session.idle",
        "session.status",
        "file.edited",
        "todo.updated",
    }.issubset(OFFICIAL_OPENCODE_BUS_EVENTS)


def test_permission_request_reuses_exact_provider_ids_and_tool_call() -> None:
    events = opencode_official_event_semantic_events(
        _payload(
            "permission.asked",
            {
                "id": "per_123",
                "sessionID": "ses_1",
                "permission": "bash",
                "patterns": ["git *", "python *"],
                "metadata": {"secret": "do-not-inline"},
                "always": ["git status"],
                "tool": {"messageID": "msg_1", "callID": "call_7"},
            },
        ),
        timestamp="2026-08-28T08:00:00Z",
    )

    assert _relations(events) == {
        "OBSERVED_PERMISSION_REQUEST",
        "PERMISSION_TARGETS_TOOL_CALL",
    }
    request = next(
        event["target"]
        for event in events
        if event["relation"] == "OBSERVED_PERMISSION_REQUEST"
    )
    link = next(
        event
        for event in events
        if event["relation"] == "PERMISSION_TARGETS_TOOL_CALL"
    )
    assert request["id"] == "permission-request:opencode:ses_1:per_123"
    assert link["source"]["id"] == request["id"]
    assert link["target"]["id"] == "tool-call:opencode:ses_1:call_7"
    assert link["attributes"]["provider_tool_call_id_exact"] is True
    rendered = json.dumps(events)
    assert "do-not-inline" not in rendered
    assert "git status" not in rendered
    assert "git *" not in rendered


def test_permission_reply_reuses_same_request_identity() -> None:
    event = opencode_official_event_semantic_events(
        _payload(
            "permission.replied",
            {
                "sessionID": "ses_1",
                "requestID": "per_123",
                "reply": "reject",
            },
        ),
        timestamp="2026-08-28T08:01:00Z",
    )[0]

    assert event["relation"] == "OBSERVED_PERMISSION_REPLY"
    assert event["target"]["id"] == "permission-request:opencode:ses_1:per_123"
    assert event["attributes"]["reply"] == "reject"


def test_session_status_keeps_retry_state_without_inline_message() -> None:
    event = opencode_official_event_semantic_events(
        _payload(
            "session.status",
            {
                "sessionID": "ses_1",
                "status": {
                    "type": "retry",
                    "attempt": 3,
                    "message": "secret retry explanation",
                    "next": 123456,
                },
            },
        ),
        timestamp="2026-08-28T08:02:00Z",
    )[0]

    assert event["relation"] == "OBSERVED_PROVIDER_SESSION_STATUS"
    assert event["attributes"]["status_type"] == "retry"
    assert event["attributes"]["retry_attempt"] == 3
    assert event["attributes"]["retry_next"] == 123456
    assert "secret retry explanation" not in json.dumps(event)


def test_compaction_and_error_keep_conservative_identity_boundaries() -> None:
    compacted = opencode_official_event_semantic_events(
        _payload("session.compacted", {"sessionID": "ses_1"}),
        timestamp="2026-08-28T08:03:00Z",
    )[0]
    error = opencode_official_event_semantic_events(
        _payload(
            "session.error",
            {
                "error": {
                    "name": "APIError",
                    "message": "private provider error",
                }
            },
        ),
        timestamp="2026-08-28T08:04:00Z",
    )[0]

    assert compacted["relation"] == "COMPACTED_CONTEXT"
    assert compacted["attributes"]["compaction_id_available"] is False
    assert compacted["target"]["attributes"]["compaction_id_available"] is False
    assert error["relation"] == "OBSERVED_PROVIDER_SESSION_ERROR"
    assert error["source"]["id"] == "agent:OpenCode"
    assert error["attributes"]["session_identity_available"] is False
    assert "private provider error" not in json.dumps(error)


def test_file_todo_and_removal_events_use_only_stable_metadata() -> None:
    file_event = opencode_official_event_semantic_events(
        _payload("file.edited", {"file": "src/main.py"}),
        timestamp="2026-08-28T08:05:00Z",
    )[0]
    todo_event = opencode_official_event_semantic_events(
        _payload(
            "todo.updated",
            {
                "sessionID": "ses_1",
                "todos": [
                    {"content": "secret A", "status": "pending"},
                    {"content": "secret B", "status": "completed"},
                    {"content": "secret C", "status": "pending"},
                ],
            },
        ),
        timestamp="2026-08-28T08:06:00Z",
    )[0]
    message_event = opencode_official_event_semantic_events(
        _payload(
            "message.removed",
            {"sessionID": "ses_1", "messageID": "msg_2"},
        ),
        timestamp="2026-08-28T08:07:00Z",
    )[0]
    part_event = opencode_official_event_semantic_events(
        _payload(
            "message.part.removed",
            {
                "sessionID": "ses_1",
                "messageID": "msg_2",
                "partID": "prt_9",
            },
        ),
        timestamp="2026-08-28T08:08:00Z",
    )[0]

    assert file_event["relation"] == "OBSERVED_FILE_CHANGE"
    assert file_event["target"]["attributes"]["provider_path"] == "src/main.py"
    assert todo_event["relation"] == "OBSERVED_TODO_STATE"
    assert todo_event["attributes"]["todo_count"] == 3
    assert todo_event["attributes"]["todo_status_counts"] == {
        "completed": 1,
        "pending": 2,
    }
    assert "secret A" not in json.dumps(todo_event)
    assert message_event["target"]["id"] == "agent-message:opencode:ses_1:msg_2"
    assert part_event["source"]["id"] == "agent-message:opencode:ses_1:msg_2"
    assert part_event["target"]["id"] == "message-part:opencode:ses_1:msg_2:prt_9"


def test_already_projected_and_low_value_events_remain_raw_only() -> None:
    assert (
        opencode_official_event_semantic_events(
            _payload("session.created", {"sessionID": "ses_1", "info": {}}),
            timestamp="2026-08-28T08:09:00Z",
        )
        == []
    )
    assert (
        opencode_official_event_semantic_events(
            _payload("tui.toast.show", {"message": "raw only"}),
            timestamp="2026-08-28T08:10:00Z",
        )
        == []
    )


def test_hook_cli_persists_official_bus_projection(tmp_path: Path, monkeypatch) -> None:
    sidecar = tmp_path / "semantic.jsonl"
    payload = {
        "hook_event_name": "event",
        "event_type": "permission.replied",
        "sessionID": "ses_1",
        "cwd": str(tmp_path),
        "event": {
            "type": "permission.replied",
            "properties": {
                "sessionID": "ses_1",
                "requestID": "per_1",
                "reply": "once",
            },
        },
    }
    monkeypatch.setattr(hook_cli, "read_plugin_payload", lambda: payload)

    assert hook_cli.main(["--sidecar", str(sidecar)]) == 0

    records = [
        json.loads(line)
        for line in sidecar.read_text(encoding="utf-8").splitlines()
    ]
    assert any(record["relation"] == "OBSERVED_PERMISSION_REPLY" for record in records)
    assert any(record["relation"] == "OBSERVED_PROVIDER_EVENT" for record in records)
