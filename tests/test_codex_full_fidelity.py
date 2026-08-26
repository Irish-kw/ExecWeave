from __future__ import annotations

import io
import json
from pathlib import Path

from execweave.codex_full_fidelity import codex_hook_to_content_events
from execweave.codex_hook_cli import main as codex_hook_main
from execweave.content_store import FullFidelityContentStore


def _base(event: str) -> dict:
    return {
        "session_id": "session-1",
        "turn_id": "turn-1",
        "transcript_path": "/tmp/transcript.jsonl",
        "cwd": "/repo",
        "hook_event_name": event,
        "model": "gpt-5.3-codex",
        "permission_mode": "default",
    }


def _load(root: Path, event: dict) -> bytes:
    return (root / event["attributes"]["content_path"]).read_bytes()


def test_prompt_complete_and_not_inline(tmp_path: Path) -> None:
    prompt = "start\x00" + "P" * 12000 + "end"
    events = codex_hook_to_content_events(
        {**_base("UserPromptSubmit"), "prompt": prompt},
        store=FullFidelityContentStore(tmp_path),
        timestamp="2026-08-26T00:00:00Z",
    )

    event = next(item for item in events if item["relation"] == "RECEIVED_USER_PROMPT")
    assert _load(tmp_path, event).decode() == prompt
    assert prompt not in json.dumps(events)
    assert event["attributes"]["causal"] is False
    assert event["attributes"]["inferred"] is False


def test_tool_input_credentials_preserved_metadata_filtered(tmp_path: Path) -> None:
    payload = {
        **_base("PreToolUse"),
        "authorization": "Bearer secret",
        "tool_name": "Bash",
        "tool_use_id": "call-1",
        "tool_input": {"command": "curl x", "api_key": "keep-me"},
    }
    events = codex_hook_to_content_events(
        payload,
        store=FullFidelityContentStore(tmp_path),
    )

    metadata = next(item for item in events if item["relation"] == "OBSERVED_PROVIDER_METADATA")
    assert "authorization" not in json.loads(_load(tmp_path, metadata))
    assert metadata["attributes"]["transport_credentials_excluded"] == ["authorization"]

    tool_input = next(item for item in events if item["relation"] == "HAS_TOOL_INPUT")
    assert json.loads(_load(tmp_path, tool_input))["api_key"] == "keep-me"


def test_post_tool_response_preserved_as_provider_value(tmp_path: Path) -> None:
    payload = {
        **_base("PostToolUse"),
        "tool_name": "Bash",
        "tool_use_id": "call-1",
        "tool_input": {"command": "false"},
        "tool_response": {"exit_code": 1, "output": "full output"},
    }
    events = codex_hook_to_content_events(
        payload,
        store=FullFidelityContentStore(tmp_path),
    )

    output = next(item for item in events if item["relation"] == "HAS_TOOL_OUTPUT")
    assert json.loads(_load(tmp_path, output)) == payload["tool_response"]
    assert output["attributes"]["model_visible_serialization"] is False


def test_permission_request_does_not_fabricate_tool_call_id(tmp_path: Path) -> None:
    payload = {
        **_base("PermissionRequest"),
        "tool_name": "Bash",
        "tool_input": {"command": "rm -rf build"},
    }
    events = codex_hook_to_content_events(
        payload,
        store=FullFidelityContentStore(tmp_path),
    )

    event = next(
        item for item in events if item["relation"] == "REQUESTED_PERMISSION_FOR_TOOL_INPUT"
    )
    assert event["source"]["id"] == "agent:OpenAI Codex"
    assert event["attributes"]["tool_name"] == "Bash"
    assert json.loads(_load(tmp_path, event)) == payload["tool_input"]


def test_stop_and_subagent_final_messages(tmp_path: Path) -> None:
    main_events = codex_hook_to_content_events(
        {
            **_base("Stop"),
            "stop_hook_active": False,
            "last_assistant_message": "main final",
        },
        store=FullFidelityContentStore(tmp_path),
    )
    main_event = next(
        item for item in main_events if item["relation"] == "PRODUCED_ASSISTANT_RESPONSE"
    )
    assert _load(tmp_path, main_event).decode() == "main final"

    subagent_events = codex_hook_to_content_events(
        {
            **_base("SubagentStop"),
            "agent_id": "a7",
            "agent_type": "Explore",
            "agent_transcript_path": "/tmp/a7.jsonl",
            "stop_hook_active": False,
            "last_assistant_message": "sub final",
        },
        store=FullFidelityContentStore(tmp_path),
    )
    subagent_event = next(
        item
        for item in subagent_events
        if item["relation"] == "PRODUCED_ASSISTANT_RESPONSE"
    )
    assert subagent_event["source"]["id"] == "agent:codex:session-1:subagent:a7"
    assert _load(tmp_path, subagent_event).decode() == "sub final"


def test_hook_cli_appends_content_references_and_creates_store(
    monkeypatch,
    tmp_path: Path,
) -> None:
    payload = {
        **_base("PreToolUse"),
        "cwd": str(tmp_path),
        "tool_name": "Bash",
        "tool_use_id": "call-cli",
        "tool_input": {"command": "echo cli", "opaque": "full-value"},
    }
    output = tmp_path / "semantic.jsonl"
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    assert codex_hook_main(["--sidecar", str(output)]) == 0
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [record["relation"] for record in records] == [
        "REQUESTED_TOOL_CALL",
        "USES_TOOL",
        "DECLARED_COMMAND",
        "OBSERVED_PROVIDER_METADATA",
        "HAS_TOOL_INPUT",
    ]
    input_event = records[-1]
    stored = json.loads((tmp_path / input_event["attributes"]["content_path"]).read_bytes())
    assert stored["opaque"] == "full-value"


def test_hook_cli_preserves_summary_when_content_store_fails(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    import execweave.codex_hook_cli as hook_cli

    payload = {
        **_base("PreToolUse"),
        "cwd": str(tmp_path),
        "tool_name": "Bash",
        "tool_use_id": "call-fail-open",
        "tool_input": {"command": "echo fail-open"},
    }
    output = tmp_path / "semantic.jsonl"
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))

    class FailingStore:
        def __init__(self, _root: Path) -> None:
            raise OSError("content store unavailable")

    monkeypatch.setattr(hook_cli, "FullFidelityContentStore", FailingStore)

    assert hook_cli.main(["--sidecar", str(output)]) == 0
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [record["relation"] for record in records] == [
        "REQUESTED_TOOL_CALL",
        "USES_TOOL",
        "DECLARED_COMMAND",
    ]
    assert "content store unavailable" in capsys.readouterr().err
