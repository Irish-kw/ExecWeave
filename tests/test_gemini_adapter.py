from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

from execweave.gemini_adapter import append_semantic_records, gemini_hook_to_semantic_events, read_hook_payload
from execweave.gemini_hook_cli import gemini_hook_config


def _base(event: str, timestamp: str = "2026-08-25T08:20:00Z") -> dict:
    return {
        "cwd": "/repo",
        "hook_event_name": event,
        "session_id": "gemini-session-1",
        "timestamp": timestamp,
        "transcript_path": "/private/transcript.json",
    }


def test_session_start_records_provider_session_without_transcript() -> None:
    events = gemini_hook_to_semantic_events({**_base("SessionStart"), "source": "startup"})
    assert len(events) == 1
    event = events[0]
    assert event["relation"] == "STARTED_PROVIDER_SESSION"
    assert event["source"]["id"] == "agent:Gemini CLI"
    assert event["target"]["id"] == "provider-session:gemini:gemini-session-1"
    assert "transcript_path" not in event["attributes"]


def test_before_tool_records_shell_command_and_unique_request_identity() -> None:
    payload = {**_base("BeforeTool"), "tool_name": "run_shell_command", "tool_input": {"command": "python task.py"}}
    first = gemini_hook_to_semantic_events(payload)
    second = gemini_hook_to_semantic_events({**payload, "timestamp": "2026-08-25T08:20:01Z"})
    assert {event["relation"] for event in first} == {"REQUESTED_TOOL_CALL", "USES_TOOL", "DECLARED_COMMAND"}
    first_call = next(event["target"] for event in first if event["relation"] == "REQUESTED_TOOL_CALL")
    second_call = next(event["target"] for event in second if event["relation"] == "REQUESTED_TOOL_CALL")
    assert first_call["id"] != second_call["id"]
    assert first_call["attributes"]["identity_semantics"] == "provider_hook_without_unique_tool_call_id"


def test_after_tool_does_not_assert_direct_before_tool_linkage_or_store_content() -> None:
    payload = {
        **_base("AfterTool", "2026-08-25T08:20:02Z"),
        "tool_name": "run_shell_command",
        "tool_input": {"command": "false"},
        "tool_response": {"llmContent": "secret output", "returnDisplay": "secret output", "error": None},
    }
    events = gemini_hook_to_semantic_events(payload)
    assert len(events) == 1
    event = events[0]
    assert event["relation"] == "TOOL_RESULT_RETURNED"
    assert "secret output" not in json.dumps(event)
    assert "no direct BeforeTool linkage asserted" in event["attributes"]["result_identity_semantics"]


def test_after_tool_marks_provider_reported_error_without_storing_error_body() -> None:
    payload = {
        **_base("AfterTool"),
        "tool_name": "run_shell_command",
        "tool_input": {"command": "false"},
        "tool_response": {"error": "sensitive failure text"},
    }
    event = gemini_hook_to_semantic_events(payload)[0]
    assert event["relation"] == "TOOL_RESULT_REPORTED_ERROR"
    assert event["attributes"]["provider_reported_error"] is True
    assert "sensitive failure text" not in json.dumps(event)


def test_mcp_context_uses_explicit_server_identity_without_connection_details() -> None:
    payload = {
        **_base("BeforeTool"),
        "tool_name": "mcp_acme_search",
        "tool_input": {"query": "x"},
        "mcp_context": {"server_name": "acme", "tool_name": "search", "command": "npx", "args": ["--token", "secret"], "url": "https://secret.example"},
    }
    events = gemini_hook_to_semantic_events(payload)
    relations = {event["relation"] for event in events}
    assert {"VIA_MCP", "EXPOSES_TOOL"}.issubset(relations)
    rendered = json.dumps(events)
    assert "mcp-server:gemini:acme" in rendered
    assert "secret.example" not in rendered
    assert "--token" not in rendered


def test_gemini_hook_config_and_sidecar_io(tmp_path: Path) -> None:
    config = gemini_hook_config("execweave-gemini-hook --strict")
    assert set(config["hooks"]) == {"SessionStart", "BeforeTool", "AfterTool"}
    assert config["hooks"]["BeforeTool"][0]["matcher"] == ".*"
    payload = {**_base("BeforeTool"), "tool_name": "read_file", "tool_input": {"file_path": "README.md"}}
    parsed = read_hook_payload(StringIO(json.dumps(payload)))
    records = gemini_hook_to_semantic_events(parsed)
    output = append_semantic_records(tmp_path / "gemini.jsonl", records)
    lines = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert any(line["relation"] == "DECLARED_TARGET" for line in lines)
    assert all(line["attributes"]["provider"] == "gemini" for line in lines)
