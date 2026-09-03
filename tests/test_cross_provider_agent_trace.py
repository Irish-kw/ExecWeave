from __future__ import annotations

import json
from pathlib import Path

import execweave.cursor_hook_cli as cursor_hook_cli
import execweave.opencode_hook_cli as opencode_hook_cli
from execweave.agent_trace import (
    agent_trace_visibility,
    cursor_agent_trace_events,
    opencode_agent_trace_events,
)
from execweave.content_store import FullFidelityContentStore
from execweave.viewer_content_inspector import viewer_content_reference


def _read_content(root: Path, event: dict) -> object:
    path = root / event["attributes"]["content_path"]
    return json.loads(path.read_text()) if path.suffix == ".json" else path.read_text()


def _cursor(event: str, **extra: object) -> dict:
    return {
        "hook_event_name": event,
        "conversation_id": "conversation-1",
        "session_id": "session-1",
        "generation_id": "generation-1",
        "cwd": "/repo",
        **extra,
    }


def _opencode_bus(event_type: str, properties: dict, *, session_id: str = "child") -> dict:
    return {
        "hook_event_name": "event",
        "event_type": event_type,
        "sessionID": session_id,
        "cwd": "/repo",
        "event": {"type": event_type, "properties": properties},
    }


def test_visibility_contract_is_explicit_for_all_integrated_agent_providers() -> None:
    expected = {
        "claude": "not_exposed_by_source",
        "codex": "provider_exposed_plaintext_summary_or_encoded",
        "cursor": "provider_exposed_thinking_text",
        "opencode": "provider_exposed_reasoning_part",
        "antigravity": "not_exposed_by_source",
    }
    for provider, reasoning in expected.items():
        visibility = agent_trace_visibility(provider)
        assert visibility["reasoning_visibility"] == reasoning
        assert visibility["agent_identity_visibility"] != "unknown"
        assert visibility["subagent_visibility"] != "unknown"


def test_cursor_exact_subagent_lifecycle_and_tool_ownership(tmp_path: Path) -> None:
    store = FullFidelityContentStore(tmp_path)
    started = cursor_agent_trace_events(
        _cursor(
            "subagentStart",
            subagent_id="sub-1",
            subagent_type="research",
            task="inspect repository",
        ),
        store=store,
        timestamp="2026-08-28T00:00:00Z",
    )
    edge = next(event for event in started if event["relation"] == "SPAWNED_SUBAGENT")
    assert edge["source"]["id"] == "agent:Cursor"
    assert edge["target"]["id"] == "agent:cursor:conversation-1:subagent:sub-1"
    assert edge["attributes"]["provider_subagent_id_exact"] is True

    tool = cursor_agent_trace_events(
        _cursor(
            "preToolUse",
            subagent_id="sub-1",
            subagent_type="research",
            tool_name="Read",
            tool_use_id="tool-1",
            tool_input={"path": "/repo/a"},
        ),
        store=store,
        timestamp="2026-08-28T00:00:01Z",
    )
    ownership = next(event for event in tool if event["relation"] == "OWNED_TOOL_CALL")
    assert ownership["source"]["id"] == edge["target"]["id"]
    assert ownership["target"]["id"] == "tool-call:cursor:conversation-1:tool-1"


def test_cursor_reasoning_is_readable_only_when_hook_explicitly_labels_thought(
    tmp_path: Path,
) -> None:
    events = cursor_agent_trace_events(
        _cursor(
            "afterAgentThought",
            subagent_id="sub-1",
            subagent_type="research",
            text="provider-visible reasoning",
        ),
        store=FullFidelityContentStore(tmp_path),
        timestamp="2026-08-28T00:00:00Z",
    )
    reasoning = next(event for event in events if event["relation"] == "PRODUCED_REASONING_TEXT")
    assert reasoning["source"]["id"] == "agent:cursor:conversation-1:subagent:sub-1"
    assert reasoning["attributes"]["reasoning_readable"] is True
    assert reasoning["attributes"]["provider_labels_as_thinking_text"] is True
    assert _read_content(tmp_path, reasoning) == "provider-visible reasoning"


def test_opencode_session_parent_id_creates_exact_child_session_edge(tmp_path: Path) -> None:
    payload = _opencode_bus(
        "session.created",
        {"info": {"id": "child", "parentID": "parent", "title": "research"}},
    )
    events = opencode_agent_trace_events(
        payload,
        store=FullFidelityContentStore(tmp_path),
        timestamp="2026-08-28T00:00:00Z",
    )
    edge = next(event for event in events if event["relation"] == "HAS_CHILD_AGENT_SESSION")
    assert edge["source"]["id"] == "agent:opencode:session:parent"
    assert edge["target"]["id"] == "agent:opencode:session:child"
    assert edge["attributes"]["provider_parent_id_exact"] is True
    assert edge["attributes"]["causal"] is False


def test_opencode_reasoning_part_is_preserved_and_projected_to_session_agent(
    tmp_path: Path,
) -> None:
    payload = _opencode_bus(
        "message.part.updated",
        {
            "part": {
                "id": "part-r1",
                "sessionID": "child",
                "messageID": "message-1",
                "type": "reasoning",
                "text": "full provider reasoning",
            }
        },
    )
    events = opencode_agent_trace_events(
        payload,
        store=FullFidelityContentStore(tmp_path),
        timestamp="2026-08-28T00:00:00Z",
    )
    reasoning = next(event for event in events if event["relation"] == "PRODUCED_REASONING_TEXT")
    assert reasoning["source"]["id"] == "agent:opencode:session:child"
    assert reasoning["attributes"]["reasoning_readable"] is True
    assert reasoning["attributes"]["provider_schema_type"] == "reasoning"
    assert _read_content(tmp_path, reasoning) == "full provider reasoning"

    reference = viewer_content_reference(reasoning["target"])
    assert reference is not None
    assert reference["category"] == "Reasoning Text"


def test_opencode_tool_event_projects_explicit_file_target_and_keeps_call_identity(
    tmp_path: Path,
) -> None:
    store = FullFidelityContentStore(tmp_path)
    plugin_events = opencode_agent_trace_events(
        {
            "hook_event_name": "tool.execute.before",
            "sessionID": "child",
            "tool": "write",
            "callID": "call-file-1",
            "args": {"filePath": str(tmp_path / "notes.md"), "content": "private"},
            "cwd": "/repo",
        },
        store=store,
        timestamp="2026-08-28T00:00:00Z",
    )
    bus_events = opencode_agent_trace_events(
        _opencode_bus(
            "message.part.updated",
            {
                "part": {
                    "id": "part-tool-1",
                    "sessionID": "child",
                    "messageID": "message-1",
                    "type": "tool",
                    "callID": "call-file-1",
                    "tool": "write",
                    "state": {"input": {"filePath": str(tmp_path / "notes.md"), "content": "private"}},
                }
            },
        ),
        store=store,
        timestamp="2026-08-28T00:00:01Z",
    )
    plugin_call = next(event["target"] for event in plugin_events if event["relation"] == "OWNED_TOOL_CALL")
    bus_call = next(event["target"] for event in bus_events if event["relation"] == "OBSERVED_TOOL_CALL")
    declared = next(event for event in bus_events if event["relation"] == "DECLARED_TARGET")
    assert plugin_call["id"] == bus_call["id"] == "tool-call:opencode:child:call-file-1"
    assert declared["target"]["id"] == f"file:{tmp_path / 'notes.md'}"
    assert declared["attributes"]["provider_event_projection"] is True
    assert '"content": "private"' not in json.dumps(bus_events)


def test_opencode_subtask_keeps_prompt_and_profile_without_inventing_child_session(
    tmp_path: Path,
) -> None:
    payload = _opencode_bus(
        "message.part.updated",
        {
            "part": {
                "id": "part-task",
                "sessionID": "parent",
                "messageID": "message-2",
                "type": "subtask",
                "agent": "explore",
                "description": "inspect auth flow",
                "prompt": "trace every authentication call",
            }
        },
        session_id="parent",
    )
    events = opencode_agent_trace_events(
        payload,
        store=FullFidelityContentStore(tmp_path),
        timestamp="2026-08-28T00:00:00Z",
    )
    requested = next(event for event in events if event["relation"] == "REQUESTED_SUBTASK")
    targeted = next(event for event in events if event["relation"] == "TARGETS_AGENT_PROFILE")
    assert requested["source"]["id"] == "agent:opencode:session:parent"
    assert requested["attributes"]["exact_child_session_linkage_asserted"] is False
    assert targeted["target"]["id"] == "agent-profile:opencode:explore"
    assert targeted["attributes"]["exact_child_session_linkage_asserted"] is False
    prompt = next(event for event in events if event["relation"] == "HAS_SUBTASK_PROMPT")
    assert _read_content(tmp_path, prompt) == "trace every authentication call"


def test_opencode_assistant_message_and_tool_ownership_are_session_scoped(
    tmp_path: Path,
) -> None:
    store = FullFidelityContentStore(tmp_path)
    message = opencode_agent_trace_events(
        _opencode_bus(
            "message.updated",
            {
                "info": {
                    "id": "message-a",
                    "sessionID": "child",
                    "role": "assistant",
                    "agent": "explore",
                    "modelID": "gpt-5.6",
                    "providerID": "openai",
                    "tokens": {"reasoning": 321},
                }
            },
        ),
        store=store,
        timestamp="2026-08-28T00:00:00Z",
    )
    produced = next(event for event in message if event["relation"] == "PRODUCED_ASSISTANT_MESSAGE")
    assert produced["source"]["id"] == "agent:opencode:session:child"
    assert produced["target"]["attributes"]["reasoning_tokens"] == 321
    assert any(event["relation"] == "USED_AGENT_PROFILE" for event in message)

    ownership = opencode_agent_trace_events(
        {
            "hook_event_name": "tool.execute.before",
            "sessionID": "child",
            "agent": "explore",
            "tool": "read",
            "callID": "call-7",
            "args": {"filePath": "/repo/a"},
        },
        store=store,
        timestamp="2026-08-28T00:00:01Z",
    )
    edge = next(event for event in ownership if event["relation"] == "OWNED_TOOL_CALL")
    assert edge["source"]["id"] == "agent:opencode:session:child"
    assert edge["target"]["id"] == "tool-call:opencode:child:call-7"


def test_hook_clis_append_cross_provider_trace_events(tmp_path: Path, monkeypatch) -> None:
    cursor_sidecar = tmp_path / "cursor.jsonl"
    cursor_payload = _cursor(
        "afterAgentThought",
        subagent_id="sub-9",
        subagent_type="review",
        text="visible thought",
    )
    monkeypatch.setattr(cursor_hook_cli, "read_hook_payload", lambda: cursor_payload)
    assert cursor_hook_cli.main(["--sidecar", str(cursor_sidecar)]) == 0
    cursor_relations = {
        json.loads(line)["relation"] for line in cursor_sidecar.read_text().splitlines()
    }
    assert "PRODUCED_REASONING_TEXT" in cursor_relations

    opencode_sidecar = tmp_path / "opencode.jsonl"
    opencode_payload = _opencode_bus(
        "session.created",
        {"info": {"id": "child-9", "parentID": "parent-9"}},
        session_id="child-9",
    )
    monkeypatch.setattr(opencode_hook_cli, "read_plugin_payload", lambda: opencode_payload)
    assert opencode_hook_cli.main(["--sidecar", str(opencode_sidecar)]) == 0
    opencode_relations = {
        json.loads(line)["relation"] for line in opencode_sidecar.read_text().splitlines()
    }
    assert "HAS_CHILD_AGENT_SESSION" in opencode_relations
