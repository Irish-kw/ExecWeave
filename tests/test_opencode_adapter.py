from __future__ import annotations

import json
from pathlib import Path

from execweave.opencode_adapter import opencode_plugin_to_semantic_events


def test_opencode_before_after_share_exact_call_identity(tmp_path: Path) -> None:
    before = {
        "hook_event_name": "tool.execute.before",
        "sessionID": "session-1",
        "callID": "call-1",
        "tool": "bash",
        "args": {"command": "python task.py"},
        "cwd": str(tmp_path),
    }
    after = {
        "hook_event_name": "tool.execute.after",
        "sessionID": "session-1",
        "callID": "call-1",
        "tool": "bash",
        "args": {"command": "python task.py"},
        "cwd": str(tmp_path),
    }
    before_events = opencode_plugin_to_semantic_events(before, timestamp="2026-08-25T10:00:00Z")
    after_events = opencode_plugin_to_semantic_events(after, timestamp="2026-08-25T10:00:01Z")
    before_call = next(
        event["target"] for event in before_events if event["relation"] == "REQUESTED_TOOL_CALL"
    )
    after_call = next(
        event["source"] for event in after_events if event["relation"] == "TOOL_CALL_RETURNED"
    )
    assert before_call["id"] == "tool-call:opencode:session-1:call-1"
    assert after_call["id"] == before_call["id"]
    assert any(event["relation"] == "DECLARED_COMMAND" for event in before_events)


def test_opencode_file_tool_records_path_not_content(tmp_path: Path) -> None:
    payload = {
        "hook_event_name": "tool.execute.before",
        "sessionID": "session-1",
        "callID": "call-2",
        "tool": "write",
        "args": {
            "filePath": str(tmp_path / "output.txt"),
            "content": "PRIVATE_WRITE_CONTENT",
        },
        "cwd": str(tmp_path),
    }
    events = opencode_plugin_to_semantic_events(payload)
    rendered = json.dumps(events)
    assert "output.txt" in rendered
    assert "PRIVATE_WRITE_CONTENT" not in rendered
    assert any(event["relation"] == "DECLARED_TARGET" for event in events)


def test_opencode_chat_message_records_model_without_message_content() -> None:
    payload = {
        "hook_event_name": "chat.message",
        "sessionID": "session-1",
        "messageID": "message-1",
        "agent": "build",
        "model": {"providerID": "openrouter", "modelID": "openai/gpt-5.6-sol"},
        "message": "PRIVATE_MESSAGE",
        "parts": ["PRIVATE_PART"],
    }
    events = opencode_plugin_to_semantic_events(payload)
    rendered = json.dumps(events)
    assert "openrouter/openai/gpt-5.6-sol" in rendered
    assert "PRIVATE_MESSAGE" not in rendered
    assert "PRIVATE_PART" not in rendered
