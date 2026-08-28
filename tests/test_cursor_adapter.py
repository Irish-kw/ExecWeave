from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

from execweave.cursor_adapter import (
    append_semantic_records,
    cursor_hook_to_semantic_events,
    read_hook_payload,
)
from execweave.cursor_hook_cli import cursor_hook_config


def _base(event: str) -> dict:
    return {
        "conversation_id": "conversation-1",
        "generation_id": "generation-1",
        "session_id": "session-1",
        "hook_event_name": event,
        "cursor_version": "1.7.2",
        "cwd": "/repo",
        "workspace_roots": ["/repo"],
        "model": "claude-sonnet",
        "model_id": "claude-sonnet-4",
        "user_email": "private@example.com",
        "transcript_path": "/private/transcript.json",
    }


def test_session_start_records_model_without_private_fields() -> None:
    events = cursor_hook_to_semantic_events(_base("sessionStart"))
    assert len(events) == 1
    event = events[0]
    assert event["relation"] == "USED_MODEL"
    assert event["source"]["id"] == "agent:Cursor"
    assert event["target"]["id"] == "model:cursor:claude-sonnet-4"
    rendered = json.dumps(event)
    assert "private@example.com" not in rendered
    assert "/private/transcript.json" not in rendered


def test_pre_tool_use_records_exact_tool_call_and_shell_command() -> None:
    payload = {
        **_base("preToolUse"),
        "tool_name": "Shell",
        "tool_use_id": "call-123",
        "tool_input": {"command": "python task.py", "working_directory": "/repo"},
        "agent_message": "secret narrative",
    }
    first = cursor_hook_to_semantic_events(payload)
    assert {event["relation"] for event in first} == {
        "REQUESTED_TOOL_CALL",
        "USES_TOOL",
        "DECLARED_COMMAND",
    }
    call = next(
        event["target"]
        for event in first
        if event["relation"] == "REQUESTED_TOOL_CALL"
    )
    assert call["id"] == "tool-call:cursor:conversation-1:call-123"
    rendered = json.dumps(first)
    assert "python task.py" in rendered
    assert "secret narrative" not in rendered


def test_post_tool_events_reuse_tool_use_id_without_storing_output() -> None:
    payload = {
        **_base("postToolUse"),
        "tool_name": "Shell",
        "tool_use_id": "call-123",
        "tool_input": {"command": "echo ok"},
        "tool_output": "sensitive output",
    }
    event = cursor_hook_to_semantic_events(payload)[0]
    assert event["relation"] == "TOOL_CALL_RETURNED"
    assert event["source"]["id"] == "tool-call:cursor:conversation-1:call-123"
    assert "sensitive output" not in json.dumps(event)

    failure = cursor_hook_to_semantic_events(
        {**payload, "hook_event_name": "postToolUseFailure"}
    )[0]
    assert failure["relation"] == "TOOL_CALL_FAILED"
    assert failure["attributes"]["provider_reported_failure"] is True


def test_mcp_tool_keeps_tool_identity_without_inventing_server() -> None:
    events = cursor_hook_to_semantic_events(
        {
            **_base("preToolUse"),
            "tool_name": "MCP:search_repositories",
            "tool_use_id": "mcp-1",
            "tool_input": {"query": "execweave"},
        }
    )
    tool = next(
        event["target"] for event in events if event["relation"] == "USES_TOOL"
    )
    assert tool["id"] == "tool:cursor:mcp:search_repositories"
    assert tool["attributes"]["mcp_server_identity_available"] is False
    assert all(event["target"]["type"] != "mcp_server" for event in events)


def test_cursor_config_and_sidecar_io(tmp_path: Path) -> None:
    config = cursor_hook_config("execweave-cursor-hook --strict")
    assert config["version"] == 1
    assert set(config["hooks"]) == {
        "sessionStart",
        "sessionEnd",
        "preToolUse",
        "postToolUse",
        "postToolUseFailure",
        "subagentStart",
        "subagentStop",
        "beforeShellExecution",
        "afterShellExecution",
        "beforeMCPExecution",
        "afterMCPExecution",
        "beforeReadFile",
        "afterFileEdit",
        "beforeSubmitPrompt",
        "preCompact",
        "stop",
        "afterAgentResponse",
        "afterAgentThought",
        "beforeTabFileRead",
        "afterTabFileEdit",
        "workspaceOpen",
    }
    payload = {
        **_base("preToolUse"),
        "tool_name": "Write",
        "tool_use_id": "write-1",
        "tool_input": {
            "path": str(tmp_path / "output.txt"),
            "content": "secret body",
        },
    }
    parsed = read_hook_payload(StringIO(json.dumps(payload)))
    output = append_semantic_records(
        tmp_path / "cursor.jsonl",
        cursor_hook_to_semantic_events(parsed),
    )
    rendered = output.read_text(encoding="utf-8")
    assert "DECLARED_TARGET" in rendered
    assert "secret body" not in rendered
