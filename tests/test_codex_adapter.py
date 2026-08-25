from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest

from execweave.codex_adapter import (
    append_semantic_records,
    codex_hook_to_semantic_events,
    read_hook_payload,
)
from execweave.codex_hook_cli import codex_hook_config


def _base(event: str) -> dict:
    return {
        "cwd": "/repo",
        "hook_event_name": event,
        "model": "gpt-5.6-codex",
        "permission_mode": "default",
        "session_id": "session-1",
        "transcript_path": None,
    }


def test_session_start_records_model_without_prompt_or_transcript_content() -> None:
    payload = {**_base("SessionStart"), "source": "startup"}
    events = codex_hook_to_semantic_events(payload, timestamp="2026-08-25T05:00:00Z")

    assert len(events) == 1
    event = events[0]
    assert event["relation"] == "USED_MODEL"
    assert event["source"]["id"] == "agent:OpenAI Codex"
    assert event["target"]["id"] == "model:codex:gpt-5.6-codex"
    assert event["attributes"]["provider"] == "codex"
    assert event["attributes"]["codex_session_source"] == "startup"
    assert "transcript_path" not in event["attributes"]


def test_pre_tool_use_records_logical_tool_call_and_bash_command() -> None:
    payload = {
        **_base("PreToolUse"),
        "turn_id": "turn-1",
        "tool_name": "Bash",
        "tool_use_id": "call-123",
        "tool_input": {"command": "python task.py"},
    }
    events = codex_hook_to_semantic_events(payload, timestamp="2026-08-25T05:00:01Z")

    relations = {event["relation"] for event in events}
    assert relations == {"REQUESTED_TOOL_CALL", "USES_TOOL", "DECLARED_COMMAND"}
    call = next(event["source"] for event in events if event["relation"] == "USES_TOOL")
    assert call["id"] == "tool-call:codex:session-1:call-123"
    assert call["attributes"]["codex_turn_id"] == "turn-1"
    command = next(event["target"] for event in events if event["relation"] == "DECLARED_COMMAND")
    assert command["attributes"]["command"] == "python task.py"


def test_non_bash_tool_does_not_fabricate_declared_command() -> None:
    payload = {
        **_base("PreToolUse"),
        "turn_id": "turn-1",
        "tool_name": "apply_patch",
        "tool_use_id": "call-patch",
        "tool_input": {"command": "*** Begin Patch"},
    }
    events = codex_hook_to_semantic_events(payload, timestamp="2026-08-25T05:00:01Z")

    assert "DECLARED_COMMAND" not in {event["relation"] for event in events}


def test_post_tool_use_is_neutral_about_success_or_failure() -> None:
    payload = {
        **_base("PostToolUse"),
        "turn_id": "turn-1",
        "tool_name": "Bash",
        "tool_use_id": "call-123",
        "tool_input": {"command": "false"},
        "tool_response": "Process exited with code 1",
    }
    events = codex_hook_to_semantic_events(payload, timestamp="2026-08-25T05:00:02Z")

    assert len(events) == 1
    event = events[0]
    assert event["relation"] == "TOOL_CALL_RETURNED"
    assert event["event_type"] == "semantic.codex.tool.returned"
    assert event["attributes"]["outcome_semantics"].startswith(
        "provider_reported_completion_without_reliable_success_signal"
    )
    assert event["attributes"]["tool_response_chars"] == len(payload["tool_response"])
    assert "tool_response" not in event["attributes"]


def test_unknown_codex_hook_is_ignored() -> None:
    payload = {**_base("PermissionRequest"), "tool_name": "Bash", "tool_input": {}}
    assert codex_hook_to_semantic_events(payload) == []


def test_required_tool_identity_is_enforced() -> None:
    payload = {
        **_base("PreToolUse"),
        "turn_id": "turn-1",
        "tool_name": "Bash",
        "tool_input": {"command": "echo hi"},
    }
    with pytest.raises(ValueError, match="tool_use_id"):
        codex_hook_to_semantic_events(payload)


def test_codex_hook_config_uses_supported_lifecycle_events() -> None:
    config = codex_hook_config("execweave-codex-hook --strict")
    hooks = config["hooks"]
    assert set(hooks) == {"SessionStart", "PreToolUse", "PostToolUse"}
    assert hooks["PreToolUse"][0]["matcher"] == ".*"
    assert hooks["PostToolUse"][0]["matcher"] == ".*"
    assert hooks["PreToolUse"][0]["hooks"][0]["command"] == "execweave-codex-hook --strict"


def test_sidecar_append_and_stdin_reader(tmp_path: Path) -> None:
    payload = {
        **_base("PreToolUse"),
        "turn_id": "turn-1",
        "tool_name": "Bash",
        "tool_use_id": "call-1",
        "tool_input": {"command": "echo hi"},
    }
    parsed = read_hook_payload(StringIO(json.dumps(payload)))
    records = codex_hook_to_semantic_events(parsed, timestamp="2026-08-25T05:00:01Z")
    output = append_semantic_records(tmp_path / "codex.jsonl", records)

    lines = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 3
    assert all(line["attributes"]["provider"] == "codex" for line in lines)
