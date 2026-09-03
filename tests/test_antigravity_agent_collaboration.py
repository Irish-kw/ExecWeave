from __future__ import annotations

import io
import json
import sys
from pathlib import Path

from execweave.antigravity_adapter import antigravity_hook_to_semantic_events
from execweave.antigravity_full_fidelity import antigravity_hook_to_content_events
from execweave.antigravity_hook_cli import main as antigravity_hook_main
from execweave.content_store import FullFidelityContentStore


def _post_tool(tmp_path: Path, *, tool_call: object = None, error: str = "") -> dict:
    payload = {
        "conversationId": "parent-conversation",
        "workspacePaths": [str(tmp_path)],
        "transcriptPath": str(tmp_path / "transcript.jsonl"),
        "artifactDirectoryPath": str(tmp_path / "artifacts"),
        "modelName": "agy-test",
        "stepIdx": 7,
        "error": error,
    }
    if tool_call is not None:
        payload["toolCall"] = tool_call
    return payload


def _read_content(root: Path, event: dict) -> str:
    return (root / event["target"]["attributes"]["path"]).read_text(encoding="utf-8")


def test_antigravity_post_tool_without_identity_preserves_step_evidence(tmp_path: Path) -> None:
    events = antigravity_hook_to_semantic_events(
        _post_tool(tmp_path),
        hook_event="PostToolUse",
        timestamp="2026-08-28T00:00:00Z",
    )
    assert len(events) == 1
    observed = events[0]
    assert observed["relation"] == "OBSERVED_TOOL_CALL"
    assert observed["target"]["type"] == "tool_call_observation"
    assert observed["target"]["id"] == (
        "tool-call-observation:antigravity:parent-conversation:7"
    )
    assert observed["attributes"]["provider_tool_identity_exposed"] is False
    assert observed["attributes"]["provider_step_index_exact"] is True
    assert all(event["relation"] != "USES_TOOL" for event in events)


def test_antigravity_cli_accepts_null_tool_call_without_dropping_event(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    sidecar = tmp_path / "semantic.jsonl"
    monkeypatch.setenv("EXECWEAVE_SEMANTIC_SIDECAR", str(sidecar))
    payload = _post_tool(tmp_path)
    payload["toolCall"] = None
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    assert antigravity_hook_main(["--auto", "--event", "PostToolUse"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    records = [json.loads(line) for line in sidecar.read_text().splitlines()]
    assert any(record["relation"] == "OBSERVED_TOOL_CALL" for record in records)
    assert any(record["relation"] == "OBSERVED_PROVIDER_METADATA" for record in records)
    assert all(record["relation"] != "USES_TOOL" for record in records)


def test_antigravity_invoke_subagent_materializes_request_without_fake_child(
    tmp_path: Path,
) -> None:
    store = FullFidelityContentStore(tmp_path)
    payload = _post_tool(
        tmp_path,
        tool_call={
            "name": "invoke_subagent",
            "args": {
                "Subagents": [
                    {
                        "Prompt": "inspect authentication paths",
                        "Role": "security reviewer",
                        "TypeName": "research",
                        "Workspace": "inherit",
                    }
                ]
            },
        },
    )
    events = antigravity_hook_to_content_events(
        payload,
        hook_event="PostToolUse",
        store=store,
        timestamp="2026-08-28T00:00:00Z",
    )
    requested = next(event for event in events if event["relation"] == "REQUESTED_SUBTASK")
    prompt = next(event for event in events if event["relation"] == "HAS_SUBTASK_PROMPT")
    targeted = next(event for event in events if event["relation"] == "TARGETS_AGENT_PROFILE")
    assert requested["source"]["id"] == (
        "agent:antigravity:conversation:parent-conversation"
    )
    assert requested["target"]["type"] == "subtask"
    assert requested["target"]["attributes"]["child_identity_exposed"] is False
    assert targeted["target"]["id"] == "agent-profile:antigravity:research"
    assert _read_content(tmp_path, prompt) == "inspect authentication paths"
    assert all(event["relation"] != "ASSIGNED_AGENT_TASK" for event in events)
    assert all(event["relation"] != "SPAWNED_AGENT" for event in events)


def test_antigravity_send_message_records_send_and_payload_only(tmp_path: Path) -> None:
    store = FullFidelityContentStore(tmp_path)
    payload = _post_tool(
        tmp_path,
        tool_call={
            "name": "send_message",
            "args": {
                "Recipient": "child-conversation",
                "Message": "check the token refresh path",
            },
        },
    )
    events = antigravity_hook_to_content_events(
        payload,
        hook_event="PostToolUse",
        store=store,
        timestamp="2026-08-28T00:00:00Z",
    )
    sent = next(event for event in events if event["relation"] == "SENT_AGENT_MESSAGE")
    message = sent["target"]
    payload_event = next(
        event for event in events if event["relation"] == "HAS_AGENT_MESSAGE_PAYLOAD"
    )
    addressed = next(
        event for event in events if event["relation"] == "TARGETS_AGENT_ADDRESS"
    )
    assert message["type"] == "agent_message"
    assert message["attributes"]["author"] == "parent-conversation"
    assert message["attributes"]["recipient"] == "child-conversation"
    assert addressed["target"]["attributes"]["routing_identity_only"] is True
    assert _read_content(tmp_path, payload_event) == "check the token refresh path"
    relations = {event["relation"] for event in events}
    assert "DELIVERED_AGENT_MESSAGE" not in relations
    assert "CONSUMED_AGENT_MESSAGE" not in relations


def test_antigravity_failed_send_does_not_claim_message_was_sent(tmp_path: Path) -> None:
    events = antigravity_hook_to_content_events(
        _post_tool(
            tmp_path,
            tool_call={
                "name": "send_message",
                "args": {"Recipient": "child", "Message": "hello"},
            },
            error="recipient unavailable",
        ),
        hook_event="PostToolUse",
        store=FullFidelityContentStore(tmp_path),
        timestamp="2026-08-28T00:00:00Z",
    )
    assert all(event["relation"] != "SENT_AGENT_MESSAGE" for event in events)
