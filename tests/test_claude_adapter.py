from __future__ import annotations

import io
import json
from pathlib import Path

from execweave.claude_adapter import append_semantic_records, claude_hook_to_semantic_events
from execweave.claude_hook_cli import main as claude_hook_main


def _base(event: str) -> dict:
    return {
        "session_id": "claude-session-1",
        "prompt_id": "prompt-1",
        "cwd": "/repo",
        "permission_mode": "default",
        "hook_event_name": event,
    }


def test_pretooluse_bash_creates_tool_call_and_bounded_command() -> None:
    payload = {
        **_base("PreToolUse"),
        "tool_name": "Bash",
        "tool_use_id": "toolu_1",
        "tool_input": {"command": "x" * 5000, "description": "demo"},
    }
    events = claude_hook_to_semantic_events(payload, timestamp="2026-08-25T03:00:00Z")

    assert [event["relation"] for event in events] == [
        "REQUESTED_TOOL_CALL",
        "USES_TOOL",
        "DECLARED_COMMAND",
    ]
    assert events[0]["source"]["id"] == "agent:Claude Code"
    assert events[0]["target"]["id"] == "tool-call:claude:claude-session-1:toolu_1"
    command = events[-1]["target"]
    assert command["type"] == "command"
    assert len(command["attributes"]["command"]) == 4096
    assert command["attributes"]["truncated"] is True
    assert all(event["attributes"]["causal"] is False for event in events)


def test_write_declares_file_target_without_storing_content() -> None:
    secret = "TOP-SECRET-CONTENT"
    payload = {
        **_base("PreToolUse"),
        "tool_name": "Write",
        "tool_use_id": "toolu_write",
        "tool_input": {"file_path": "/repo/output.txt", "content": secret},
    }
    events = claude_hook_to_semantic_events(payload, timestamp="2026-08-25T03:00:00Z")
    serialized = json.dumps(events)
    declared = next(event for event in events if event["relation"] == "DECLARED_TARGET")

    assert declared["target"]["type"] == "file"
    assert declared["target"]["id"].startswith("file:")
    assert declared["target"]["name"] == "output.txt"
    assert secret not in serialized
    assert "content" in events[0]["target"]["attributes"]["input_keys"]


def test_mcp_tool_creates_server_and_tool_relationships() -> None:
    payload = {
        **_base("PreToolUse"),
        "tool_name": "mcp__github__search_repositories",
        "tool_use_id": "toolu_mcp",
        "tool_input": {"query": "execweave"},
    }
    events = claude_hook_to_semantic_events(payload, timestamp="2026-08-25T03:00:00Z")

    assert [event["relation"] for event in events] == [
        "REQUESTED_TOOL_CALL",
        "USES_TOOL",
        "VIA_MCP",
        "EXPOSES_TOOL",
    ]
    assert events[2]["target"]["id"] == "mcp-server:claude:github"
    assert events[3]["target"]["id"] == "tool:mcp:github:search_repositories"


def test_posttooluse_records_status_not_tool_response() -> None:
    payload = {
        **_base("PostToolUse"),
        "tool_name": "Bash",
        "tool_use_id": "toolu_1",
        "tool_input": {"command": "pytest -q"},
        "tool_response": {"stdout": "DO-NOT-STORE", "stderr": ""},
        "duration_ms": 12,
    }
    events = claude_hook_to_semantic_events(payload, timestamp="2026-08-25T03:00:01Z")

    assert len(events) == 1
    assert events[0]["relation"] == "TOOL_CALL_SUCCEEDED"
    assert events[0]["attributes"]["duration_ms"] == 12
    assert "DO-NOT-STORE" not in json.dumps(events)


def test_posttooluse_failure_keeps_bounded_error_summary() -> None:
    payload = {
        **_base("PostToolUseFailure"),
        "tool_name": "Bash",
        "tool_use_id": "toolu_1",
        "tool_input": {"command": "pytest -q"},
        "error": "E" * 2000,
        "is_interrupt": False,
        "duration_ms": 99,
    }
    events = claude_hook_to_semantic_events(payload, timestamp="2026-08-25T03:00:01Z")

    assert events[0]["relation"] == "TOOL_CALL_FAILED"
    assert len(events[0]["attributes"]["error_summary"]) == 1024
    assert events[0]["attributes"]["error_summary_truncated"] is True


def test_subagent_hooks_create_agent_relationships() -> None:
    start = {
        **_base("SubagentStart"),
        "agent_id": "agent-123",
        "agent_type": "Explore",
    }
    stop = {**start, "hook_event_name": "SubagentStop"}

    start_events = claude_hook_to_semantic_events(start, timestamp="2026-08-25T03:00:00Z")
    stop_events = claude_hook_to_semantic_events(stop, timestamp="2026-08-25T03:00:01Z")

    child_id = "agent:claude:claude-session-1:subagent:agent-123"
    assert start_events[0]["relation"] == "SPAWNED_SUBAGENT"
    assert start_events[0]["target"]["id"] == child_id
    assert stop_events[0]["relation"] == "RETURNED_TO"
    assert stop_events[0]["source"]["id"] == child_id


def test_session_start_model_is_optional() -> None:
    without_model = claude_hook_to_semantic_events(
        _base("SessionStart"), timestamp="2026-08-25T03:00:00Z"
    )
    with_model = claude_hook_to_semantic_events(
        {**_base("SessionStart"), "model": "claude-sonnet"},
        timestamp="2026-08-25T03:00:00Z",
    )

    assert without_model == []
    assert with_model[0]["relation"] == "USED_MODEL"
    assert with_model[0]["target"]["type"] == "model"


def test_append_semantic_records_writes_jsonl(tmp_path: Path) -> None:
    output = tmp_path / "semantic.jsonl"
    records = claude_hook_to_semantic_events(
        {
            **_base("PreToolUse"),
            "tool_name": "Read",
            "tool_use_id": "toolu_read",
            "tool_input": {"file_path": "/repo/README.md"},
        },
        timestamp="2026-08-25T03:00:00Z",
    )
    append_semantic_records(output, records)

    lines = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 3
    assert lines[-1]["relation"] == "DECLARED_TARGET"
    assert not output.with_name(output.name + ".lock").exists()


def test_hook_cli_is_fail_open_by_default(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("not-json"))
    result = claude_hook_main(["--sidecar", str(tmp_path / "semantic.jsonl")])
    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == ""
    assert "warning" in captured.err.lower()


def test_hook_cli_strict_returns_nonzero(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("not-json"))
    assert claude_hook_main(["--strict", "--sidecar", str(tmp_path / "semantic.jsonl")]) == 1
