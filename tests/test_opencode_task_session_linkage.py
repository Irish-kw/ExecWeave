from __future__ import annotations

import json
from pathlib import Path

import execweave.opencode_hook_cli as opencode_hook_cli
from execweave.opencode_task_linkage import opencode_task_session_events


def _task_part_payload(
    *,
    parent_session: str = "parent",
    metadata_parent: str = "parent",
    child_session: str = "child",
    tool: str = "task",
    task_id: str | None = None,
) -> dict:
    task_input = {
        "prompt": "inspect authentication",
        "description": "inspect auth",
        "subagent_type": "explore",
        "background": False,
    }
    if task_id is not None:
        task_input["task_id"] = task_id
    return {
        "hook_event_name": "event",
        "event_type": "message.part.updated",
        "sessionID": parent_session,
        "cwd": "/repo",
        "event": {
            "type": "message.part.updated",
            "properties": {
                "part": {
                    "id": "part-task",
                    "sessionID": parent_session,
                    "messageID": "message-task",
                    "type": "tool",
                    "callID": "call-task",
                    "tool": tool,
                    "state": {
                        "status": "running",
                        "input": task_input,
                        "metadata": {
                            "parentSessionId": metadata_parent,
                            "sessionId": child_session,
                        },
                    },
                }
            },
        },
    }


def test_opencode_task_metadata_exactly_assigns_child_session() -> None:
    events = opencode_task_session_events(
        _task_part_payload(),
        timestamp="2026-08-28T00:00:00Z",
    )

    assert len(events) == 1
    edge = events[0]
    assert edge["relation"] == "ASSIGNED_AGENT_TASK"
    assert edge["source"]["id"] == "tool-call:opencode:parent:call-task"
    assert edge["target"]["id"] == "agent:opencode:session:child"
    assert edge["target"]["attributes"]["native_agent_name"] == "explore"
    assert edge["attributes"]["provider_task_session_id_exact"] is True
    assert edge["attributes"]["provider_parent_session_id_exact"] is True
    assert edge["attributes"]["task_session_mode"] == "new_requested"
    assert edge["attributes"]["causal"] is False
    assert edge["attributes"]["inferred"] is False


def test_opencode_task_metadata_rejects_parent_session_mismatch() -> None:
    events = opencode_task_session_events(
        _task_part_payload(metadata_parent="different-parent"),
        timestamp="2026-08-28T00:00:00Z",
    )
    assert events == []


def test_opencode_non_task_tool_never_assigns_child_session() -> None:
    events = opencode_task_session_events(
        _task_part_payload(tool="read"),
        timestamp="2026-08-28T00:00:00Z",
    )
    assert events == []


def test_opencode_resumed_task_is_assignment_not_spawn() -> None:
    events = opencode_task_session_events(
        _task_part_payload(task_id="child"),
        timestamp="2026-08-28T00:00:00Z",
    )

    assert [event["relation"] for event in events] == ["ASSIGNED_AGENT_TASK"]
    assert events[0]["attributes"]["task_session_mode"] == "resume_requested"
    assert events[0]["attributes"]["requested_task_id"] == "child"


def test_opencode_hook_cli_appends_exact_task_session_assignment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sidecar = tmp_path / "opencode.jsonl"
    monkeypatch.setattr(
        opencode_hook_cli,
        "read_plugin_payload",
        lambda: _task_part_payload(),
    )

    assert opencode_hook_cli.main(["--sidecar", str(sidecar)]) == 0

    records = [json.loads(line) for line in sidecar.read_text().splitlines()]
    assignments = [
        record
        for record in records
        if record.get("relation") == "ASSIGNED_AGENT_TASK"
        and record.get("source", {}).get("id") == "tool-call:opencode:parent:call-task"
    ]
    assert len(assignments) == 1
    assert assignments[0]["target"]["id"] == "agent:opencode:session:child"
    assert assignments[0]["attributes"]["assignment_basis"] == (
        "task_tool_state.metadata.sessionId"
    )
