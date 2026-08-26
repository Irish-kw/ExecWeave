from __future__ import annotations

import json
from pathlib import Path

import execweave.cursor_hook_cli as hook_cli
from execweave.content_store import FullFidelityContentStore
from execweave.cursor_full_fidelity import cursor_hook_to_content_events


def _base(event: str) -> dict:
    return {
        "conversation_id": "conversation-1", "generation_id": "generation-1",
        "session_id": "session-1", "hook_event_name": event, "cwd": "/repo",
        "workspace_roots": ["/repo"], "transcript_path": "/private/transcript.json",
    }


def _read(root: Path, event: dict) -> object:
    path = root / event["attributes"]["content_path"]
    return json.loads(path.read_text()) if path.suffix == ".json" else path.read_text()


def _event(events: list[dict], field: str) -> dict:
    return next(event for event in events if event["attributes"]["observed_field"] == field)


def test_prompt_is_complete_and_not_inlined(tmp_path: Path) -> None:
    prompt = "A" * 12000 + "\x00tail"
    events = cursor_hook_to_content_events(
        {**_base("beforeSubmitPrompt"), "prompt": prompt},
        store=FullFidelityContentStore(tmp_path),
    )
    observed = _event(events, "prompt")
    assert _read(tmp_path, observed) == prompt
    assert prompt not in json.dumps(observed)


def test_tool_input_output_and_failure_are_full_fidelity(tmp_path: Path) -> None:
    store = FullFidelityContentStore(tmp_path)
    base = {**_base("postToolUse"), "tool_name": "Write", "tool_use_id": "t1",
            "tool_input": {"path": "/repo/x", "api_key": "keep"},
            "tool_output": '{"ok":true}', "agent_message": "agent context"}
    success = cursor_hook_to_content_events(base, store=store)
    assert _read(tmp_path, _event(success, "tool_input"))["api_key"] == "keep"
    assert _read(tmp_path, _event(success, "tool_output")) == '{"ok":true}'
    failed = cursor_hook_to_content_events(
        {**base, "hook_event_name": "postToolUseFailure", "error_message": "full error"},
        store=store,
    )
    assert _read(tmp_path, _event(failed, "error_message")) == "full error"


def test_shell_and_mcp_content_are_preserved(tmp_path: Path) -> None:
    store = FullFidelityContentStore(tmp_path)
    shell = cursor_hook_to_content_events(
        {**_base("afterShellExecution"), "command": "cat secret", "output": "whole output"},
        store=store,
    )
    assert _read(tmp_path, _event(shell, "command")) == "cat secret"
    assert _read(tmp_path, _event(shell, "output")) == "whole output"
    mcp = cursor_hook_to_content_events(
        {**_base("afterMCPExecution"), "command": "node server.js", "tool_input": {"q": "x"},
         "result_json": {"answer": "full"}, "url": "https://example.invalid"},
        store=store,
    )
    assert _read(tmp_path, _event(mcp, "command")) == "node server.js"
    assert _read(tmp_path, _event(mcp, "result_json")) == {"answer": "full"}


def test_file_content_and_edits_keep_evidence_boundaries(tmp_path: Path) -> None:
    store = FullFidelityContentStore(tmp_path)
    read = cursor_hook_to_content_events(
        {**_base("beforeReadFile"), "file_path": "/repo/a", "content": "entire file"}, store=store,
    )
    read_event = _event(read, "content")
    assert _read(tmp_path, read_event) == "entire file"
    assert read_event["attributes"]["read_completion_asserted"] is False
    edit = cursor_hook_to_content_events(
        {**_base("afterFileEdit"), "file_path": "/repo/a", "edits": [{"old_string": "a", "new_string": "b"}]},
        store=store,
    )
    edit_event = _event(edit, "edits")
    assert edit_event["attributes"]["complete_post_edit_file_snapshot_asserted"] is False


def test_assistant_thought_and_subagent_content_are_distinct(tmp_path: Path) -> None:
    store = FullFidelityContentStore(tmp_path)
    response = cursor_hook_to_content_events(
        {**_base("afterAgentResponse"), "text": "final answer"}, store=store,
    )
    thought = cursor_hook_to_content_events(
        {**_base("afterAgentThought"), "text": "provider thought"}, store=store,
    )
    assert _read(tmp_path, _event(response, "text")) == "final answer"
    assert _event(thought, "text")["attributes"]["provider_labels_as_thinking_text"] is True
    sub = cursor_hook_to_content_events(
        {**_base("subagentStop"), "task": "inspect", "summary": "full summary"}, store=store,
    )
    assert _read(tmp_path, _event(sub, "summary")) == "full summary"
    assert _event(sub, "summary")["source"]["attributes"]["direct_start_stop_linkage_asserted"] is False


def test_transport_credentials_filtered_only_from_metadata(tmp_path: Path) -> None:
    payload = {**_base("preToolUse"), "tool_name": "Write", "tool_use_id": "w1",
               "tool_input": {"api_key": "keep-in-tool"}, "authorization": "Bearer remove",
               "provider_extra": {"cookie": "remove", "opaque": "keep"}}
    events = cursor_hook_to_content_events(payload, store=FullFidelityContentStore(tmp_path))
    assert _read(tmp_path, _event(events, "tool_input"))["api_key"] == "keep-in-tool"
    metadata = _read(tmp_path, next(e for e in events if e["relation"] == "OBSERVED_PROVIDER_METADATA"))
    assert "authorization" not in metadata
    assert metadata["provider_extra"] == {"opaque": "keep"}


def test_cli_fail_open_keeps_summary_when_content_store_fails(tmp_path: Path, monkeypatch) -> None:
    sidecar = tmp_path / "semantic.jsonl"
    payload = {**_base("preToolUse"), "tool_name": "Shell", "tool_use_id": "c1",
               "tool_input": {"command": "echo hi"}}
    monkeypatch.setattr(hook_cli, "read_hook_payload", lambda: payload)
    monkeypatch.setattr(
        hook_cli, "cursor_hook_to_content_events",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("content failed")),
    )
    assert hook_cli.main(["--sidecar", str(sidecar)]) == 0
    relations = [json.loads(line)["relation"] for line in sidecar.read_text().splitlines()]
    assert "REQUESTED_TOOL_CALL" in relations


def test_config_registers_full_observation_surface() -> None:
    assert set(hook_cli.cursor_hook_config()["hooks"]) == {
        "sessionStart", "sessionEnd", "preToolUse", "postToolUse", "postToolUseFailure",
        "subagentStart", "subagentStop", "beforeShellExecution", "afterShellExecution",
        "beforeMCPExecution", "afterMCPExecution", "beforeReadFile", "afterFileEdit",
        "beforeSubmitPrompt", "preCompact", "stop", "afterAgentResponse", "afterAgentThought",
        "beforeTabFileRead", "afterTabFileEdit",
    }
