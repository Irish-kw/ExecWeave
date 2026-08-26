from __future__ import annotations

import json
from pathlib import Path

import execweave.opencode_hook_cli as hook_cli
from execweave.content_store import FullFidelityContentStore
from execweave.opencode_full_fidelity import opencode_plugin_to_content_events


def _base(hook: str) -> dict:
    return {"hook_event_name": hook, "sessionID": "s1", "cwd": "/repo"}


def _read(root: Path, event: dict) -> object:
    path = root / event["attributes"]["content_path"]
    return json.loads(path.read_text()) if path.suffix == ".json" else path.read_text()


def _field(events: list[dict], name: str) -> dict:
    return next(event for event in events if event["attributes"]["observed_field"] == name)


def test_chat_message_preserves_complete_message_parts(tmp_path: Path) -> None:
    prompt = "P" * 12000 + "\x00tail"
    message = {"role": "user", "content": prompt, "api_key": "content-kept"}
    parts = [{"type": "text", "text": prompt}]
    events = opencode_plugin_to_content_events(
        {**_base("chat.message"), "message": message, "parts": parts},
        store=FullFidelityContentStore(tmp_path),
    )
    assert _read(tmp_path, _field(events, "message")) == message
    assert _read(tmp_path, _field(events, "parts")) == parts
    assert prompt not in json.dumps(events)


def test_tool_before_after_preserve_args_and_result_with_call_identity(tmp_path: Path) -> None:
    store = FullFidelityContentStore(tmp_path)
    args = {"filePath": "/repo/x", "content": "full write", "api_key": "keep"}
    before = opencode_plugin_to_content_events(
        {**_base("tool.execute.before"), "tool": "write", "callID": "c1", "args": args}, store=store,
    )
    result = {"title": "write", "output": "complete result", "metadata": {"bytes": 10}}
    after = opencode_plugin_to_content_events(
        {**_base("tool.execute.after"), "tool": "write", "callID": "c1", "args": args, "result": result}, store=store,
    )
    assert _read(tmp_path, _field(before, "args")) == args
    output = _field(after, "result")
    assert _read(tmp_path, output) == result
    assert output["source"]["id"] == "tool-call:opencode:s1:c1"


def test_model_context_system_and_completed_text_are_distinct(tmp_path: Path) -> None:
    store = FullFidelityContentStore(tmp_path)
    messages = [{"info": {"role": "user"}, "parts": [{"text": "full context"}]}]
    observed = opencode_plugin_to_content_events(
        {**_base("experimental.chat.messages.transform"), "messages": messages}, store=store,
    )
    assert _read(tmp_path, _field(observed, "messages")) == messages
    system = opencode_plugin_to_content_events(
        {**_base("experimental.chat.system.transform"), "system": ["system prompt"]}, store=store,
    )
    assert _read(tmp_path, _field(system, "system")) == ["system prompt"]
    text = opencode_plugin_to_content_events(
        {**_base("experimental.text.complete"), "text": "assistant text"}, store=store,
    )
    assert _read(tmp_path, _field(text, "text")) == "assistant text"


def test_provider_bus_event_is_preserved_as_provider_observation(tmp_path: Path) -> None:
    event = {"type": "message.part.updated", "properties": {"part": {"text": "provider event text"}}}
    records = opencode_plugin_to_content_events(
        {**_base("event"), "event_type": event["type"], "event": event},
        store=FullFidelityContentStore(tmp_path),
    )
    observed = _field(records, "event")
    assert _read(tmp_path, observed) == event
    assert observed["attributes"]["provider_event_type"] == "message.part.updated"
    assert observed["attributes"]["causal"] is False


def test_request_headers_drop_transport_credentials(tmp_path: Path) -> None:
    headers = {"Authorization": "Bearer secret", "Cookie": "s=secret", "anthropic-version": "2023-06-01"}
    events = opencode_plugin_to_content_events(
        {**_base("chat.headers"), "headers": headers}, store=FullFidelityContentStore(tmp_path),
    )
    observed = _field(events, "headers")
    assert _read(tmp_path, observed) == {"anthropic-version": "2023-06-01"}


def test_tool_definition_command_permission_and_compaction_content(tmp_path: Path) -> None:
    store = FullFidelityContentStore(tmp_path)
    definition = opencode_plugin_to_content_events(
        {**_base("tool.definition"), "toolID": "read", "description": "read full file", "parameters": {"type": "object"}}, store=store,
    )
    assert _read(tmp_path, _field(definition, "description")) == "read full file"
    command = opencode_plugin_to_content_events(
        {**_base("command.execute.before"), "command": "build", "arguments": "--all", "command_parts": [{"text": "context"}]}, store=store,
    )
    assert _read(tmp_path, _field(command, "arguments")) == "--all"
    permission = opencode_plugin_to_content_events(
        {**_base("permission.ask"), "permission": {"type": "bash", "pattern": "rm *"}, "decision": "ask"}, store=store,
    )
    assert _read(tmp_path, _field(permission, "permission"))["pattern"] == "rm *"
    compact = opencode_plugin_to_content_events(
        {**_base("experimental.session.compacting"), "context": ["ctx"], "prompt": "full compact prompt"}, store=store,
    )
    assert _read(tmp_path, _field(compact, "prompt")) == "full compact prompt"


def test_provider_metadata_excludes_transport_credentials_not_content(tmp_path: Path) -> None:
    payload = {**_base("tool.execute.before"), "tool": "bash", "callID": "c2",
               "args": {"command": "echo x", "api_key": "keep"},
               "provider": {"options": {"apiKey": "remove", "region": "us"}}}
    events = opencode_plugin_to_content_events(payload, store=FullFidelityContentStore(tmp_path))
    assert _read(tmp_path, _field(events, "args"))["api_key"] == "keep"
    metadata_event = next(event for event in events if event["relation"] == "OBSERVED_PROVIDER_METADATA")
    metadata = _read(tmp_path, metadata_event)
    assert metadata["provider"]["options"] == {"region": "us"}


def test_hook_cli_fail_open_keeps_summary_when_content_store_fails(tmp_path: Path, monkeypatch) -> None:
    sidecar = tmp_path / "semantic.jsonl"
    payload = {**_base("tool.execute.before"), "tool": "bash", "callID": "c3", "args": {"command": "echo hi"}}
    monkeypatch.setattr(hook_cli, "read_plugin_payload", lambda: payload)
    monkeypatch.setattr(
        hook_cli,
        "opencode_plugin_to_content_events",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("content failed")),
    )
    assert hook_cli.main(["--sidecar", str(sidecar)]) == 0
    assert "REQUESTED_TOOL_CALL" in sidecar.read_text()


def test_unscoped_provider_event_uses_unscoped_sidecar(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert hook_cli._default_sidecar({"cwd": str(tmp_path), "hook_event_name": "event"}).name == "unscoped.jsonl"
