from __future__ import annotations

import json
from pathlib import Path

from execweave.antigravity_full_fidelity import antigravity_hook_to_content_events
from execweave.claude_full_fidelity import claude_hook_to_content_events
from execweave.content_store import FullFidelityContentStore
from execweave.conversation_records import conversation_record_entries
from execweave.cursor_full_fidelity import cursor_hook_to_content_events
from execweave.graph import GraphAccumulator
from execweave.opencode_full_fidelity import opencode_plugin_to_content_events
from execweave.opencode_task_linkage import opencode_task_session_events


def _graph(events: list[dict], root: Path) -> dict:
    accumulator = GraphAccumulator(
        session_id="provider-conversation-evidence",
        source_path=root / "events.jsonl",
    )
    for event in events:
        accumulator.apply(event)
    return accumulator.to_dict()


def _previews(events: list[dict], store: FullFidelityContentStore) -> list[dict]:
    graph = _graph(events, store.run_root)
    return [
        entry["conversation_preview"]
        for entry in conversation_record_entries(graph, store.run_root)
        if isinstance(entry.get("conversation_preview"), dict)
    ]


def test_claude_subagent_result_routes_back_to_root_without_inventing_task(tmp_path: Path) -> None:
    store = FullFidelityContentStore(tmp_path / "run")
    events = claude_hook_to_content_events(
        {
            "hook_event_name": "SubagentStop",
            "session_id": "session-1",
            "agent_id": "child-1",
            "agent_type": "Explore",
            "last_assistant_message": "Claude child result",
        },
        store=store,
        timestamp="2026-08-29T00:00:00Z",
    )

    child = next(preview for preview in _previews(events, store) if not preview["is_root"])
    assert child["agent_path"] == "/root/child-1"
    assert child["parent_thread_id"] == "claude:root"
    assert child["messages"] == [
        {
            "timestamp": "2026-08-29T00:00:00Z",
            "ordinal": None,
            "kind": "subagent_final_response",
            "sender": "/root/child-1",
            "recipient": "/root",
            "text": "Claude child result",
            "content_state": "plaintext",
            "phase": "final_answer",
            "task_name": None,
        }
    ]


def test_cursor_exact_subagent_task_and_summary_share_child_thread(tmp_path: Path) -> None:
    store = FullFidelityContentStore(tmp_path / "run")
    common = {
        "conversation_id": "conversation-1",
        "session_id": "session-1",
        "generation_id": "generation-1",
        "cwd": "/repo",
        "subagent_id": "child-1",
        "subagent_type": "Explore",
    }
    start = cursor_hook_to_content_events(
        {
            **common,
            "hook_event_name": "subagentStart",
            "task": "Inspect authentication flow",
            "description": "Auth review",
        },
        store=store,
        timestamp="2026-08-29T00:00:00Z",
    )
    stop = cursor_hook_to_content_events(
        {
            **common,
            "hook_event_name": "subagentStop",
            "summary": "Authentication flow reviewed",
        },
        store=store,
        timestamp="2026-08-29T00:00:01Z",
    )

    child = next(preview for preview in _previews(start + stop, store) if not preview["is_root"])
    assert child["agent_path"] == "/root/child-1"
    messages = child["messages"]
    assert any(
        message["kind"] == "task"
        and message["sender"] == "/root"
        and message["recipient"] == "/root/child-1"
        and message["text"] == "Inspect authentication flow"
        for message in messages
    )
    assert any(
        message["kind"] == "assistant_summary"
        and message["sender"] == "/root/child-1"
        and message["recipient"] == "/root"
        and message["text"] == "Authentication flow reviewed"
        for message in messages
    )


def _opencode_task_payload() -> dict:
    return {
        "hook_event_name": "event",
        "event_type": "message.part.updated",
        "sessionID": "parent",
        "cwd": "/repo",
        "event": {
            "type": "message.part.updated",
            "properties": {
                "part": {
                    "id": "part-task",
                    "sessionID": "parent",
                    "messageID": "message-task",
                    "type": "tool",
                    "callID": "call-task",
                    "tool": "task",
                    "state": {
                        "status": "running",
                        "input": {
                            "prompt": "Inspect authentication",
                            "description": "Auth review",
                            "subagent_type": "explore",
                            "background": False,
                        },
                        "metadata": {
                            "parentSessionId": "parent",
                            "sessionId": "child",
                        },
                    },
                }
            },
        },
    }


def test_opencode_exact_task_metadata_and_completion_route_to_child_session(tmp_path: Path) -> None:
    store = FullFidelityContentStore(tmp_path / "run")
    task_events = opencode_task_session_events(
        _opencode_task_payload(),
        timestamp="2026-08-29T00:00:00Z",
        store=store,
    )
    completion_events = opencode_plugin_to_content_events(
        {
            "hook_event_name": "experimental.text.complete",
            "sessionID": "child",
            "cwd": "/repo",
            "agent": "explore",
            "text": "OpenCode child result",
        },
        store=store,
        timestamp="2026-08-29T00:00:01Z",
    )

    child = next(preview for preview in _previews(task_events + completion_events, store) if not preview["is_root"])
    assert child["agent_path"] == "/root/child"
    assert child["parent_thread_id"] == "opencode:root"
    messages = child["messages"]
    assert any(
        message["kind"] == "task"
        and message["recipient"] == "/root/child"
        and message["text"] == "Inspect authentication"
        for message in messages
    )
    assert any(
        message["kind"] == "subagent_final_response"
        and message["sender"] == "/root/child"
        and message["recipient"] == "/root"
        and message["text"] == "OpenCode child result"
        for message in messages
    )


def test_antigravity_send_message_preserves_exact_route_without_claiming_delivery(tmp_path: Path) -> None:
    store = FullFidelityContentStore(tmp_path / "run")
    events = antigravity_hook_to_content_events(
        {
            "conversationId": "parent-conversation",
            "workspacePaths": [str(tmp_path)],
            "transcriptPath": str(tmp_path / "transcript.jsonl"),
            "artifactDirectoryPath": str(tmp_path / "artifacts"),
            "modelName": "gemini-test",
            "stepIdx": 7,
            "error": "",
            "toolCall": {
                "name": "send_message",
                "args": {
                    "Recipient": "child-conversation",
                    "Message": "Check token refresh",
                },
            },
        },
        hook_event="PostToolUse",
        store=store,
        timestamp="2026-08-29T00:00:00Z",
    )

    previews = _previews(events, store)
    route = next(
        message
        for preview in previews
        for message in preview["messages"]
        if message["kind"] == "send_message"
    )
    assert route["sender"] == "antigravity:parent-conversation"
    assert route["recipient"] == "antigravity:child-conversation"
    assert route["text"] == "Check token refresh"
    relations = {event["relation"] for event in events}
    assert "DELIVERED_AGENT_MESSAGE" not in relations
    assert "CONSUMED_AGENT_MESSAGE" not in relations


def test_antigravity_validated_subagent_prompt_routes_to_exact_child_thread(tmp_path: Path) -> None:
    store = FullFidelityContentStore(tmp_path / "run")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    brain = tmp_path / "brain"
    parent_logs = brain / "parent-conversation" / ".system_generated" / "logs"
    child_logs = brain / "child-conversation" / ".system_generated" / "logs"
    parent_logs.mkdir(parents=True)
    child_logs.mkdir(parents=True)
    parent_transcript = parent_logs / "transcript.jsonl"
    child_transcript = child_logs / "transcript.jsonl"
    child_transcript.write_text("{}\n", encoding="utf-8")

    spec = {
        "Prompt": "Inspect authentication paths",
        "Role": "security reviewer",
        "TypeName": "research",
        "Workspace": "inherit",
    }
    parent_records = [
        {
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "status": "DONE",
            "tool_calls": [{"name": "invoke_subagent", "args": {"Subagents": [spec]}}],
        },
        {
            "source": "MODEL",
            "type": "INVOKE_SUBAGENT",
            "status": "DONE",
            "content": "Created the following subagents:"
            + json.dumps(
                {
                    "conversationId": "child-conversation",
                    "logAbsoluteUri": child_transcript.as_uri(),
                    "workspaceUris": [workspace.as_uri()],
                },
                separators=(",", ":"),
            ),
        },
    ]
    parent_transcript.write_text(
        "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in parent_records),
        encoding="utf-8",
    )

    events = antigravity_hook_to_content_events(
        {
            "conversationId": "parent-conversation",
            "workspacePaths": [str(workspace)],
            "transcriptPath": str(parent_transcript),
            "artifactDirectoryPath": str(tmp_path / "artifacts"),
            "modelName": "gemini-test",
            "stepIdx": 7,
            "error": "",
            "toolCall": {"name": "invoke_subagent", "args": {"Subagents": [spec]}},
        },
        hook_event="PostToolUse",
        store=store,
        timestamp="2026-08-29T00:00:00Z",
    )

    child = next(
        preview
        for preview in _previews(events, store)
        if preview["agent_path"] == "/root/child-conversation"
    )
    assert any(
        message["kind"] == "task"
        and message["sender"] == "/root"
        and message["recipient"] == "/root/child-conversation"
        and message["text"] == "Inspect authentication paths"
        for message in child["messages"]
    )
    assignment = next(event for event in events if event["relation"] == "ASSIGNED_AGENT_TASK")
    assert assignment["attributes"]["identity_exact"] is True
    assert assignment["attributes"]["timing_inference_used"] is False
